"""Runs a set of Codenames games (a "benchmark run") for one model pairing
under one config, and saves the results to disk."""

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
    def __init__(self, llm, guesser, duration, language_config, group_config, word_count, benchmarkID="default"):
        self.modelCodemaster = llm
        self.modelGuesser = guesser
        self.benchmarkID = benchmarkID

        self.duration = duration
        self.language_config = language_config
        self.group_config = group_config
        self.word_count = word_count  # NEW parameter

        # 1. Generate all board data upfront
        self.all_boards_data = self._generate_boards()

        self.all_games_results = []
        self.refinements_results = []
        self.refinement_batch = []

    def _generate_boards(self):
        """Generates the initial board data for all rounds based on word_count."""
        base_dir = Path(__file__).resolve().parent

        total_board_size = self.word_count
        lang_ratio_sum   = sum(self.language_config.values())
        group_ratio_sum  = sum(self.group_config.values())

        # (Safety check - validation should already catch this in run_benchmark.py)
        if total_board_size % lang_ratio_sum != 0 or total_board_size % group_ratio_sum != 0:
            raise ValueError("word_count is not cleanly divisible by your language or group ratios.")

        # 1. Scale Languages
        lang_multiplier = total_board_size // lang_ratio_sum
        words_per_lang  = {k: v * lang_multiplier for k, v in self.language_config.items()}

        # 2. Scale Groups
        group_multiplier    = total_board_size // group_ratio_sum
        scaled_group_counts = {k: v * group_multiplier for k, v in self.group_config.items()}

        log("runGame", (
            f"Board layout: {total_board_size} words | "
            f"groups {scaled_group_counts} | "
            f"languages {words_per_lang}"
        ))

        # 3. Load only the necessary wordlists into memory
        loaded_wordlists = {}
        for lang, needed in words_per_lang.items():
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

        # 4. Generate each board
        for _ in range(total_games):
            board_pool = []

            # Step A: Draw the required number of words from each language
            for lang, target_count in words_per_lang.items():
                lang_words_copy = loaded_wordlists[lang].copy()
                for _ in range(target_count):
                    board_pool.append(lang_words_copy.pop(random.randrange(len(lang_words_copy))))

            # Step B: Shuffle so languages are spread across groups randomly
            random.shuffle(board_pool)

            # Step C: Assign words to groups using the scaled counts
            board_layout = []
            for group, count in scaled_group_counts.items():
                for _ in range(int(count)):
                    word_str = board_pool.pop()  # Pop from the mixed, randomized pool
                    board_layout.append({
                        "word": word_str.upper(),
                        "group": group,
                        "revealed": False
                    })

            boards.append(board_layout)

        return boards

    def _run_signature(self) -> str:
        """Updated to include word_count in the filesystem signature."""
        def short(d: dict) -> str:
            return "-".join(f"{k}{v}" for k, v in d.items())

        rounds = self.duration.get("rounds", "?")
        return f"r{rounds}_w{self.word_count}_{short(self.language_config)}_{short(self.group_config)}"


    def play(self):
        total_games = self.duration["rounds"]
        refinement_step = self.duration.get("refinement_after") or (total_games + 1)

        for game_index in tqdm(range(total_games), desc=f"Playing Benchmark ({self.benchmarkID})", unit="game"):
            log("runGame", f"=== STARTING GAME {game_index + 1} OF {total_games} ===", level="debug")

            # 2. Instantiate a fresh Board object for this specific round
            raw_board_data = self.all_boards_data[game_index]
            current_board = Board(raw_board_data)

            initial_board_state = current_board.get_formatted("detailed", filter_by_group=["blue", "red", "assassin"])

            # 3. Pass the Board and group_config into the Game
            single_game = Game(self.modelCodemaster, self.modelGuesser, current_board, self.group_config)
            game_result = single_game.play()

            self.all_games_results.append({
                "game_index": game_index + 1,
                "rounds": game_result["rounds"],
                "turn_history": game_result["turn_history"],
                "stats": game_result["stats"],
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
                guesser_reflection = self.modelGuesser.writeRefinement(self.refinement_batch)

                self.refinements_results.append({
                    "after_game": game_index + 1,
                    "batch_data": self.refinement_batch,
                    "codemaster_reflection": codemaster_reflection,
                    "guesser_reflection": guesser_reflection,
                })
                self.refinement_batch = []
                self.modelCodemaster.clearMemory()
                self.modelGuesser.clearMemory()

        return self.saveStats()

    def _run_signature(self) -> str:
        """A short, filesystem-safe fingerprint of this run's config (rounds +
        language ratios + group sizes), so a parameter sweep that reuses the
        same benchmarkID/model pair across multiple configs doesn't overwrite
        results -- see createDirectory() below for the bug this fixes."""
        def short(d: dict) -> str:
            return "-".join(f"{k}{v}" for k, v in d.items())

        rounds = self.duration.get("rounds", "?")
        return f"r{rounds}_{short(self.language_config)}_{short(self.group_config)}"

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

def createDirectory(benchmarkID, modelCodemaster, modelGuesser, run_signature):
    BASE_DIR = Path(__file__).resolve().parent

    results_dir = BASE_DIR.parent / "results"
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