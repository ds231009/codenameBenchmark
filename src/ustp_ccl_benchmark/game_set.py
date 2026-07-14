"""Runs a set of Codenames games (a "benchmark run") for one model pairing
under one config, and saves the results to disk."""

import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import random
import json
from tqdm import tqdm

from ustp_ccl_benchmark.board import Board
from ustp_ccl_benchmark.game import Game
from ustp_ccl_benchmark.logging_utils import log

class GameSet:
    def __init__(self, llm, guesser, duration, language_config, group_config, word_count,
                 benchmarkID="default", enable_live_output=True):
        self.modelCodemaster = llm
        self.modelGuesser = guesser
        self.benchmarkID = benchmarkID

        self.duration = duration
        self.language_config = language_config
        self.group_config = group_config
        self.word_count = word_count  # NEW parameter

        # Master on/off switch for the detailed live-output log (all boards +
        # every individual codemaster/guesser/refinement LLM call). When
        # False, calls aren't even recorded on the LLM side (see log_calls
        # below), and results/live/{benchmarkID}.json is never written.
        self.enable_live_output = enable_live_output
        self.modelCodemaster.log_calls = enable_live_output
        self.modelGuesser.log_calls = enable_live_output

        # 1. Generate all board data upfront
        self.all_boards_data = self._generate_boards()

        self.all_games_results = []

        # Detailed live-output tracking: per game and per refinement step, every
        # individual LLM call (codemaster move, guesser move, refinement call)
        # made during that step, with its prompt and response. Populated in
        # play() and written out (together with all_boards_data) by
        # _appendLiveOutput(). Stays empty when enable_live_output is False.
        self.all_games_llm_calls = []
        self.refinements_llm_calls = []

        self.refinements_results = []
        self.refinement_batch = []

    def _generate_boards(self):
        """Generates the initial board data for all rounds based on word_count."""
        base_dir = Path(__file__).resolve().parent

        total_board_size = self.word_count

        def allocate_proportional(target_total: int, ratios: dict) -> dict:
            """Scales ratios to exactly hit target_total using the largest remainder method."""
            ratio_sum = sum(ratios.values())
            
            # 1. Calculate exact float shares
            exact_shares = {k: target_total * (v / ratio_sum) for k, v in ratios.items()}
            
            # 2. Assign base integers (floor)
            allocated = {k: int(share) for k, share in exact_shares.items()}
            
            # 3. Figure out how many items are missing due to rounding down
            remainders = {k: exact_shares[k] - allocated[k] for k in ratios.keys()}
            shortfall = target_total - sum(allocated.values())
            
            # 4. Give 1 extra item to the keys with the highest decimal remainders
            for k in sorted(remainders, key=remainders.get, reverse=True)[:shortfall]:
                allocated[k] += 1
                
            return allocated

        # Scale Languages and Groups dynamically (no clean divisibility required)
        words_per_lang = allocate_proportional(total_board_size, self.language_config)
        scaled_group_counts = allocate_proportional(total_board_size, self.group_config)

        # Load only the necessary wordlists into memory
        loaded_wordlists = {}
        for lang, needed in words_per_lang.items():
            if needed <= 0:
                continue # Skip loading if a language rounded down to 0
                
            wordlist_path = base_dir / "wordlists" / f"wordlist{lang.upper()}.txt"

            with open(wordlist_path, 'r', encoding="utf-8") as file:
                loaded_wordlists[lang] = [line.strip() for line in file if line.strip()]

            if len(loaded_wordlists[lang]) < needed:
                raise ValueError(
                    f"Wordlist '{lang}' has only {len(loaded_wordlists[lang])} words "
                    f"but the board needs {needed}. Add more words or reduce the count."
                )

        boards = []
        total_games = self.duration["rounds"]

        # Generate each board
        for _ in range(total_games):
            board_pool = []

            # Step A: Draw the required number of words from each language.
            # Dedup across the whole board, case-insensitive: the same string can
            # live in more than one wordlist (e.g. ROSE in both DE and EN), and a
            # wordlist file can contain a repeated line. Either one used to place
            # the same word on the board twice, which is ambiguous for the guesser
            # (two identical strings it can't tell apart) and can corrupt scoring,
            # since the copies may sit in different groups. Every word is checked
            # against what's already on the board before it's added.
            seen = set()
            remaining_by_lang = {}
            for lang, target_count in words_per_lang.items():
                if target_count <= 0:
                    continue
                lang_words_copy = loaded_wordlists[lang].copy()
                random.shuffle(lang_words_copy)
                drawn = 0
                while drawn < target_count and lang_words_copy:
                    candidate = lang_words_copy.pop()
                    if candidate.upper() in seen:
                        continue
                    seen.add(candidate.upper())
                    board_pool.append(candidate)
                    drawn += 1
                remaining_by_lang[lang] = lang_words_copy  # unused, still available

            # If cross-language overlaps left us short of word_count, backfill
            # from whatever unique words remain in any language rather than
            # crashing. Ratios may drift slightly when this kicks in.
            leftover_pool = [w for words in remaining_by_lang.values() for w in words]
            random.shuffle(leftover_pool)
            while len(board_pool) < total_board_size and leftover_pool:
                candidate = leftover_pool.pop()
                if candidate.upper() in seen:
                    continue
                seen.add(candidate.upper())
                board_pool.append(candidate)

            if len(board_pool) < total_board_size:
                raise ValueError(
                    f"Could not assemble {total_board_size} unique words from the "
                    f"configured wordlists (only {len(board_pool)} available after "
                    f"removing overlaps). Add more words or lower word_count."
                )

            # Step B: Shuffle so languages are spread across groups randomly
            random.shuffle(board_pool)

            # Step C: Assign words to groups using the scaled counts
            board_layout = []
            for group, count in scaled_group_counts.items():
                for _ in range(count):
                    word_str = board_pool.pop()  # Pop from the mixed, randomized pool
                    board_layout.append({
                        "word": word_str.upper(),
                        "group": group,
                        "revealed": False
                    })

            boards.append(board_layout)

        return boards

    def _run_signature(self) -> str:
        """A short, filesystem-safe fingerprint of this run's config (rounds +
        language ratios + group sizes + word count), so a parameter sweep that
        reuses the same benchmarkID/model pair across multiple configs doesn't
        overwrite results -- see createDirectory() below for the bug this fixes."""
        def short(d: dict) -> str:
            return "-".join(f"{k}{v}" for k, v in d.items())

        rounds = self.duration.get("rounds", "?")
        return f"r{rounds}_w{self.word_count}_{short(self.language_config)}_{short(self.group_config)}"

    def play(self):
        total_games = self.duration["rounds"]
        refinement_step = self.duration.get("refinement_after") or (total_games + 1)

        for game_index in tqdm(range(total_games), desc=f"Playing Benchmark ({self.benchmarkID})", unit="game"):

            # 2. Instantiate a fresh Board object for this specific round
            raw_board_data = self.all_boards_data[game_index]
            current_board = Board(raw_board_data)

            initial_board_state = current_board.get_formatted("detailed", filter_by_group=["blue", "red", "assassin"])

            # Actual per-group counts for THIS board (post-scaling), so the
            # prompt can show the true split rather than the group_config ratios.
            board_composition = {}
            for card in raw_board_data:
                board_composition[card["group"]] = board_composition.get(card["group"], 0) + 1

            # 3. Pass the Board and group_config into the Game
            single_game = Game(self.modelCodemaster, self.modelGuesser, current_board, self.group_config, self.duration,
                               board_composition=board_composition)
            game_result = single_game.play()

            self.all_games_results.append({
                "game_index": game_index + 1,
                "rounds": game_result["rounds"],
                "turn_history": game_result["turn_history"],
                "stats": game_result["stats"],
            })

            # Drain every codemaster/guesser LLM call (prompt + response) made
            # during this game so it can be written to the detailed live log.
            # pop_new_calls() is cheap to call even when disabled (it just
            # returns whatever log_calls left behind, i.e. nothing), but we
            # skip storing it entirely when live output is off.
            codemaster_move_calls = self.modelCodemaster.pop_new_calls()
            guesser_move_calls = self.modelGuesser.pop_new_calls()
            if self.enable_live_output:
                self.all_games_llm_calls.append({
                    "game_index": game_index + 1,
                    "codemaster_calls": codemaster_move_calls,
                    "guesser_calls": guesser_move_calls,
                })

            self.refinement_batch.append({
                "game_index": game_index + 1,
                "initial_board": initial_board_state,
                "turn_history": game_result["turn_history"],
                "outcome": game_result["stats"]["outcome"],
            })

            # Refinement Logic
            if (game_index + 1) % refinement_step == 0:
                # Both roles get to reflect on the same batch.
                codemaster_reflection = self.modelCodemaster.writeRefinement(self.refinement_batch)
                codemaster_refinement_calls = self.modelCodemaster.pop_new_calls()

                guesser_reflection = self.modelGuesser.writeRefinement(self.refinement_batch)
                guesser_refinement_calls = self.modelGuesser.pop_new_calls()

                self.refinements_results.append({
                    "after_game": game_index + 1,
                    "batch_data": self.refinement_batch,
                    "codemaster_reflection": codemaster_reflection,
                    "guesser_reflection": guesser_reflection,
                })

                # Drain the refinement LLM calls (prompt + response, including
                # any failed retry attempts) for the detailed live log.
                if self.enable_live_output:
                    self.refinements_llm_calls.append({
                        "after_game": game_index + 1,
                        "codemaster_calls": codemaster_refinement_calls,
                        "guesser_calls": guesser_refinement_calls,
                    })

                self.refinement_batch = []
                self.modelCodemaster.clearMemory()
                self.modelGuesser.clearMemory()

        if self.enable_live_output:
            self._appendLiveOutput()
        else:
            log("liveOutput", f"Live output disabled for benchmark '{self.benchmarkID}' -- skipping.")

        return self.saveStats()

    def _aggregate_stats(self):
        """Rolls up per-game stats into one GameSet-level summary: win rate,
        average score, and total error/play counts across every game in this
        run. This is the level stage 2 will probably want to start from."""
        outcomes = {"WIN": 0, "LOSS_ASSASSIN": 0, "TIMEOUT": 0}
        error_totals = defaultdict(int)
        play_totals = defaultdict(int)
        scores = []

        for game in self.all_games_results:
            stats = game["stats"]
            outcomes[stats["outcome"]] = outcomes.get(stats["outcome"], 0) + 1
            scores.append(stats["final_score"])
            for k, v in stats["errors"].items():
                error_totals[k] += v
            for k, v in stats["play_counts"].items():
                play_totals[k] += v

        games_played = len(self.all_games_results) or 1
        return {
            "games_played": len(self.all_games_results),
            "outcomes": outcomes,
            "win_rate": outcomes["WIN"] / games_played,
            "avg_final_score": sum(scores) / games_played if scores else 0,
            "error_totals": dict(error_totals),
            "play_count_totals": dict(play_totals),
        }

    def _appendLiveOutput(self):
        """Saves this GameSet run's detailed live output to a unique CSV file.
        
        Captures every individual LLM call made by the codemaster and guesser 
        during the game and refinement steps. Sorts chronologically by timestamp.
        """
        import csv
        from datetime import datetime
        
        live_dir = Path.cwd() / "results" / "live"
        live_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize model names for the filename
        short_cm = self.modelCodemaster.modelName.replace(".", "").replace(":", "").replace("/", "-").replace("\\", "-")
        short_guesser = self.modelGuesser.modelName.replace(".", "").replace(":", "").replace("/", "-").replace("\\", "-")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"{self.benchmarkID}_{short_cm}_{short_guesser}_{timestamp}.csv"
        csv_path = live_dir / csv_filename

        all_calls = []
        
        # Extract game calls and tag them with their game index
        for game_calls in self.all_games_llm_calls:
            idx = game_calls.get("game_index", "?")
            for call in game_calls.get("codemaster_calls", []):
                call["game_index"] = idx
                all_calls.append(call)
            for call in game_calls.get("guesser_calls", []):
                call["game_index"] = idx
                all_calls.append(call)
            
        # Extract refinement calls and tag them
        for ref_calls in self.refinements_llm_calls:
            idx = f"{ref_calls.get('after_game', '?')} (Refinement)"
            for call in ref_calls.get("codemaster_calls", []):
                call["game_index"] = idx
                all_calls.append(call)
            for call in ref_calls.get("guesser_calls", []):
                call["game_index"] = idx
                all_calls.append(call)

        # Sort everything chronologically by the timestamp recorded in llm.py
        all_calls.sort(key=lambda x: x.get("timestamp", ""))

        # Write to CSV with richer headers
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Game_Index", "Role", "Call_Type", "Prompt", "Answer"])
            
            for call in all_calls:
                ts = call.get("timestamp", "")
                g_idx = call.get("game_index", "")
                role = call.get("role", "")
                c_type = call.get("call_type", "")
                prompt = call.get("prompt", "")
                answer = call.get("response", "")
                
                # If there was a context error or timeout, append it
                if call.get("error"):
                    answer = f"{answer} [ERROR: {call.get('error')}]".strip()
                    
                writer.writerow([ts, g_idx, role, c_type, prompt, answer])

        log("liveOutput", f"Saved full sorted LLM interactions to {csv_path}")

    def saveStats(self):
        summary_data = {
            "gameSize": self.group_config,
            "languageConfig": self.language_config,
            "wordCount": self.word_count,  # Log the new parameter
            "duration": self.duration,
        }

        file_path = createDirectory(
            self.benchmarkID,
            self.modelCodemaster.modelName,
            self.modelGuesser.modelName,
            self._run_signature(),
        )

        result = {
            "modelDetailsCodemaster": self.modelCodemaster.summary(),
            "modelDetailsGuesser": self.modelGuesser.summary(),
            "gameSetup": summary_data,
            "games": self.all_games_results,
            "refinements": self.refinements_results,
            "aggregateStats": self._aggregate_stats(),
        }

        agg = result["aggregateStats"]
        log("saveStats", f"Win rate: {agg['win_rate']:.0%}, Avg score: {agg['avg_final_score']:.2f}")

        return result


# --- Helper File Operations ---

def liveOutputPath(benchmarkID):
    """Path to the live-updating raw-output JSON for a given benchmark_id.
    One file per benchmark_id, in results/live/, regardless of model or config.

    Uses the current working directory (i.e. wherever the benchmark was
    invoked from), NOT the package's install location -- this package is
    installed via pip+git, so `Path(__file__).resolve().parent` would resolve
    inside site-packages/the git checkout instead of the user's project
    folder.
    """
    live_dir = Path.cwd() / "results" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    return live_dir / f"{benchmarkID}.json"


def createDirectory(benchmarkID, modelCodemaster, modelGuesser, run_signature):
    # Same reasoning as liveOutputPath(): anchor to the caller's cwd, not the
    # installed package directory.
    results_dir = Path.cwd() / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    shortModelCodemaster = modelCodemaster.replace(".", "").replace(":", "")
    shortModelGuesser = modelGuesser.replace(".", "").replace(":", "")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"resultsTest_{benchmarkID}_{shortModelCodemaster}_{shortModelGuesser}_{run_signature}_{timestamp}.json"
    return results_dir / filename


def saveFile(file_path, result):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"Saved results to: {file_path}")