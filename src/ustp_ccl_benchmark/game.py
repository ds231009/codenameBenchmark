"""Runs a single Codenames game between a codemaster LLM and a guesser LLM.

Tracks, per game: the outcome (win / assassin loss / timeout), the final
score, and a breakdown of errors by role and type, plus raw "risk" counts
(how many red/assassin words got guessed, how many passes happened, how
much clue count was requested overall). Deliberately NOT collapsed into a
single "risk score" -- that's an analysis-layer decision, so the raw
counts are exposed and stage 2 can define risk however it wants.
"""

import re

from ustp_ccl_benchmark.logging_utils import log
from ustp_ccl_benchmark.exceptions import (
    ClueFormatError,
    ClueRuleError,
    GuessFormatError,
    GuessRuleError,
)


class Game:
    def __init__(self, llm_codemaster, llm_guesser, board, group_config: dict, duration: dict,
                 board_composition: dict = None):
        self.modelCodemaster = llm_codemaster
        self.modelGuesser = llm_guesser
        self.board = board
        self.group_config = group_config
        self.duration = duration
        self.turn_history = []
        self.current_game_rounds = []

        # Actual per-group word counts for THIS board (not the group_config
        # ratios -- those get scaled by word_count in GameSet). Decremented as
        # words are revealed so the prompt can show what's still in play.
        self.remaining_composition = dict(board_composition) if board_composition else {}

        self.stats = {
            "errors": {
                "codemaster_format_errors": 0,   # response didn't match (word, count)
                "codemaster_rule_errors": 0,      # parsed fine, broke a game rule
                "codemaster_clue_failures": 0,    # rounds where no valid clue ever landed
                "guesser_format_errors": 0,       # response didn't match [word]
                "guesser_rule_errors": 0,         # parsed fine, not a valid board word
                "guesser_turn_forfeits": 0,       # guesser exhausted attempts mid-round
            },
            "play_counts": {
                "blue_guesses": 0,
                "red_guesses": 0,
                "assassin_guesses": 0,
                "passes": 0,
                "total_clue_count_requested": 0,
            },
        }

    def play(self):
        max_turns = self.duration.get("rounds") or sum(self.group_config.values())
        outcome = "TIMEOUT"

        for turn in range(1, max_turns + 1):
            continueGame, round_data = self.runRound(turn)
            self.current_game_rounds.append(round_data)

            # 1. Check for the WIN condition FIRST
            if self.board.is_group_cleared("blue"):
                outcome = "WIN"
                break

            # 2. If not won, check if game was forced to end (Assassin hit)
            if not continueGame:
                outcome = "LOSS_ASSASSIN"
                break
        else:
            # Loop ran out of turns without break-ing -- neither solved nor lost.
            pass

        self.stats["outcome"] = outcome
        self.stats["final_score"] = sum(g["score"] for r in self.current_game_rounds for g in r["guesses"])
        self.stats["rounds_played"] = len(self.current_game_rounds)
        self.stats["rounds_total_allowed"] = max_turns

        return {
            "rounds": self.current_game_rounds,
            "turn_history": self.turn_history,
            "stats": self.stats,
        }

    def runRound(self, round_number):
        # Turn history is kept in a compact one-line-per-turn format, e.g.
        #   T1 (OCEAN,2) -> WASSER[blue], FISCH[red]
        #   T2 (METALL,1) -> pass
        # It's the model's ONLY memory of past turns: LLM calls are stateless
        # (no chat history), so this block plus the current board is the
        # entire round state. Same format is reused by the reflection step.
        if not self.turn_history:
            history_prompt = "This is the first turn. No guesses have been made yet."
        else:
            history_prompt = (
                "Turn history so far (clue -> guessed words with their revealed group):\n"
                + "\n".join(self.turn_history)
            )

        clue, count, clue_errors = self.getClue(feedback=history_prompt)

        round_data = {
            "round_number": round_number,
            "clue": clue,
            "clue_count_requested": count,
            "clue_errors": clue_errors,
            "guesses": [],
        }

        if clue is None:
            self.turn_history.append(f"T{round_number} no valid clue -> turn skipped")
            return True, round_data

        guesses, continueGame = self.getGuesses(clue, count, history_prompt)

        round_data["guesses"] = guesses
        guess_strings = [f"{g['word']}[{g['group']}]" for g in guesses]

        if not guess_strings:
            self.turn_history.append(f"T{round_number} ({clue},{count}) -> pass")
        else:
            self.turn_history.append(
                f"T{round_number} ({clue},{count}) -> {', '.join(guess_strings)}"
            )

        return continueGame, round_data

    def getClue(self, feedback=None):
        max_attempts = 5
        clue_errors = []
        error_feedback = "" # Add this

        for attempt in range(1, max_attempts + 1):
            try:
                current_feedback = f"{feedback}\n\nWARNING ON PREVIOUS ATTEMPT: {error_feedback}" if error_feedback else feedback
                
                rawClue = self.modelCodemaster.getLLMResponse(
                    self.board.get_formatted("codemaster", show_only_unrevealed=True),
                    feedback=current_feedback,
                    composition=self._composition_line()
                )
                
                # --- ADD THIS CHECK ---
                # If the API timed out or failed, it likely returned None.
                if not isinstance(rawClue, str):
                    raise ClueFormatError(f"API returned a non-string response (likely an API failure): {rawClue}")
                # ----------------------

                match = re.search(r'\(\s*([^\s,()]+)\s*,\s*(\d+)\s*\)', rawClue)
                if not match:
                    raise ClueFormatError(f"Could not find (word, count) format in response: {rawClue}")

                clue_word = match.group(1).upper()
                count = int(match.group(2))

                if count <= 0:
                    raise ClueRuleError(f"Clue count must be greater than 0, got {count}.")

                if clue_word in self.board.remaining_words():
                    raise ClueRuleError(f"Clue '{clue_word}' is a word currently on the board.")

                self.stats["play_counts"]["total_clue_count_requested"] += count
                return clue_word, count, clue_errors

            except (ClueFormatError, ClueRuleError) as e:
                clue_errors.append({"attempt": attempt, "type": type(e).__name__, "error": str(e)})
                if isinstance(e, ClueFormatError):
                    self.stats["errors"]["codemaster_format_errors"] += 1
                else:
                    self.stats["errors"]["codemaster_rule_errors"] += 1
                
                # Capture the error for the next loop iteration. Calls are
                # stateless, so the failed attempt leaves no trace anywhere
                # except this warning line in the retry prompt.
                error_feedback = str(e)

        self.stats["errors"]["codemaster_clue_failures"] += 1
        return None, 0, clue_errors

    def getGuesses(self, clue, count, history_prompt):
        guesses = []
        continueGame = True

        total_for_clue = count      # how many words this clue points to (fixed)
        picked_this_turn = []       # running record of guesses already made this turn

        while count > 0:
            # Tell the guesser what it has already picked this turn and how many
            # guesses remain. Without this, a multi-guess clue just repeats the
            # same stale history + clue with only the board shrinking, which the
            # model can't distinguish from a fresh turn.
            turn_context = self._build_guesser_context(history_prompt, picked_this_turn, count)

            guess_attempt = self.getGuess(clue, total_for_clue, turn_context)
            outcome = guess_attempt["outcome"]

            if outcome == "pass":
                self.stats["play_counts"]["passes"] += 1
                break

            if outcome == "forfeit":
                # Guesser never produced a valid move within max_attempts.
                break

            guess = guess_attempt["result"]
            continueGame, continueRound, score = self.handleGuess(guess)
            guesses.append({
                "word": guess["word"],
                "group": guess["group"],
                "score": score,
                "attempts": guess_attempt["attempts"],
                "errors": guess_attempt["errors"],
            })
            picked_this_turn.append({"word": guess["word"], "group": guess["group"]})
            if not continueRound or not continueGame:
                break
            count -= 1

        return guesses, continueGame

    @staticmethod
    def _build_guesser_context(history_prompt, picked_this_turn, guesses_remaining):
        """Feedback shown to the guesser for a single guess within a round.

        Adds the two things the raw history block never conveyed on multi-guess
        turns: what was already picked THIS turn, and how many guesses are still
        available for the current clue.
        """
        parts = [history_prompt]
        if picked_this_turn:
            picked = ", ".join(
                f"{g['word']}[{g['group']}]" for g in picked_this_turn
            )
            parts.append(f"Already guessed this turn: {picked}.")
        noun = "guess" if guesses_remaining == 1 else "guesses"
        parts.append(
            f"You have {guesses_remaining} {noun} remaining for the current clue. "
            "To stop guessing and keep your points, reply [no guess]."
        )
        return "\n\n".join(parts)

    def _composition_line(self):
        """One-line summary of how many words of each group are still on the
        board. Public info in Codenames (the starting split is known and every
        reveal is in the turn history), so it's fair to show both sides."""
        if not self.remaining_composition:
            return ""
        order = ["blue", "red", "assassin"]
        comp = self.remaining_composition
        keys = [k for k in order if k in comp] + [k for k in comp if k not in order]
        body = ", ".join(f"{k}: {comp[k]}" for k in keys)
        return f"Words still on the board by group: {body}"

    def getGuess(self, clue, clue_count, history_prompt):
        """Returns a dict..."""
        max_attempts = 5
        guess_errors = []
        error_feedback = ""

        noun = "word" if clue_count == 1 else "words"
        clue_with_count = f"{clue} (points to {clue_count} {noun})"

        for attempt in range(1, max_attempts + 1):
            try:
                prompt_clue = f"{clue_with_count}. WARNING: {error_feedback}" if error_feedback else clue_with_count
                
                rawGuess = self.modelGuesser.getLLMResponse(
                    self.board.remaining_words(), 
                    prompt_clue,
                    feedback=history_prompt,
                    composition=self._composition_line()
                )
                
                if not isinstance(rawGuess, str):
                    raise GuessFormatError(f"API returned a non-string response (likely an API failure): {rawGuess}")
                
                # Check for a pass BEFORE the word regex. "[no guess]" contains
                # a space, so the [word] pattern below (which forbids whitespace)
                # could never match it -- a deliberate pass was always being
                # counted as a format error and retried.
                if re.search(r'\[\s*no guess\s*\]', rawGuess, re.IGNORECASE):
                    return {"result": None, "outcome": "pass", "attempts": attempt, "errors": guess_errors}

                match = re.search(r'\[\s*([^\s,\[\]]+)\s*\]', rawGuess)
                if not match:
                    raise GuessFormatError(f"Could not find [word] format in response: {rawGuess}")

                guess_word = match.group(1).strip().upper()

                if guess_word in self.board.remaining_words():
                    return {
                        "result": self.board.reveal_word(guess_word),
                        "outcome": "guess",
                        "attempts": attempt,
                        "errors": guess_errors,
                    }

                raise GuessRuleError(f"You guessed '{guess_word}', but it isn't a valid, unrevealed word on the board!")

            except (GuessFormatError, GuessRuleError) as e:
                guess_errors.append({"attempt": attempt, "type": type(e).__name__, "error": str(e)})
                if isinstance(e, GuessFormatError):
                    self.stats["errors"]["guesser_format_errors"] += 1
                else:
                    self.stats["errors"]["guesser_rule_errors"] += 1
                error_feedback = str(e)

        self.stats["errors"]["guesser_turn_forfeits"] += 1
        return {"result": None, "outcome": "forfeit", "attempts": max_attempts, "errors": guess_errors}

    def handleGuess(self, guess):
        continueGame, continueRound, score = True, True, 0
        group = guess["group"]
        word = guess["word"]

        # A word just left the board -- keep the live composition in sync.
        if group in self.remaining_composition:
            self.remaining_composition[group] = max(0, self.remaining_composition[group] - 1)

        if group == "blue":
            score = 1
            self.stats["play_counts"]["blue_guesses"] += 1
        elif group == "red":
            score = -1
            continueRound = False
            self.stats["play_counts"]["red_guesses"] += 1
        elif group == "assassin":
            continueGame = False
            score = -25
            self.stats["play_counts"]["assassin_guesses"] += 1
        else:
            pass

        if self.board.is_group_cleared("blue"):
            continueGame = False

        return continueGame, continueRound, score