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
    def __init__(self, llm_codemaster, llm_guesser, board, group_config: dict, duration: dict):
        self.modelCodemaster = llm_codemaster
        self.modelGuesser = llm_guesser
        self.board = board
        self.group_config = group_config
        self.duration = duration
        self.turn_history = []
        self.current_game_rounds = []

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
        if not self.turn_history:
            history_prompt = "This is the first turn. No guesses have been made yet."
        else:
            history_prompt = "HISTORY OF PREVIOUS TURNS IN THIS GAME:\n" + "\n".join(self.turn_history)

        clue, count, clue_errors = self.getClue(feedback=history_prompt)

        round_data = {
            "round_number": round_number,
            "clue": clue,
            "clue_count_requested": count,
            "clue_errors": clue_errors,
            "guesses": [],
        }

        if clue is None:
            self.turn_history.append(f"- Turn {round_number}: Codemaster failed to format a clue. Turn skipped.")
            return True, round_data

        guesses, continueGame = self.getGuesses(clue, count)

        round_data["guesses"] = guesses
        guess_strings = [f"'{g['word']}' (which was {g['group']})" for g in guesses]

        if not guess_strings:
            self.turn_history.append(f"- Turn {round_number}: You gave clue ({clue}, {count}). Guesser passed.")
        else:
            self.turn_history.append(
                f"- Turn {round_number}: You gave clue ({clue}, {count}). Guesser picked: {', '.join(guess_strings)}."
            )

        return continueGame, round_data

    def getClue(self, feedback=None):
        max_attempts = 5
        clue_errors = []

        for attempt in range(1, max_attempts + 1):
            try:
                rawClue = self.modelCodemaster.getLLMResponse(
                    self.board.get_formatted("codemaster", show_only_unrevealed=True),
                    feedback=feedback
                )
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

        self.stats["errors"]["codemaster_clue_failures"] += 1
        return None, 0, clue_errors

    def getGuesses(self, clue, count):
        guesses = []
        continueGame = True

        while count > 0:
            guess_attempt = self.getGuess(clue)
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
            if not continueRound or not continueGame:
                break
            count -= 1

        return guesses, continueGame

    def getGuess(self, clue):
        """Returns a dict: {"result": board word or None, "outcome": "guess"|"pass"|"forfeit",
        "attempts": int, "errors": [...]}."""
        max_attempts = 5
        guess_errors = []
        error_feedback = ""

        for attempt in range(1, max_attempts + 1):
            try:
                prompt_clue = f"{clue}. WARNING: {error_feedback}" if error_feedback else clue
                rawGuess = self.modelGuesser.getLLMResponse(self.board.remaining_words(), prompt_clue)

                match = re.search(r'\[([^\]]*)\]', rawGuess)
                if not match:
                    raise GuessFormatError(f"Could not find [word] format in response: {rawGuess}")

                guess_word = match.group(1).strip().upper()

                # FIX: this used to compare an upper-cased guess_word against the
                # lowercase literal "no guess", which could never match -- a
                # deliberate [no guess] pass was silently mis-handled as an
                # "invalid word" guess. Compared upper-to-upper now.
                if guess_word == "NO GUESS":
                    return {"result": None, "outcome": "pass", "attempts": attempt, "errors": guess_errors}

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