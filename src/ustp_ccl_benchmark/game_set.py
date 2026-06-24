"""Runs a set of Codenames games (a "benchmark run") for one model pairing
under one config, and saves the results to disk."""

from pathlib import Path
from datetime import datetime
from collections import defaultdict
import random
import json

from ustp_ccl_benchmark.board import Board
from ustp_ccl_benchmark.game import Game
from ustp_ccl_benchmark.logging_utils import log


class GameSet:
    def __init__(self, llm, guesser, duration, language_config, group_config, benchmarkID="default"):
        self.modelCodemaster = llm
        self.modelGuesser = guesser
        self.benchmarkID = benchmarkID

        self.duration = duration
        self.language_config = language_config
        self.group_config = group_config

        # 1. Generate all board data upfront
        self.all_boards_data = self._generate_boards()

        self.all_games_results = []
        self.refinements_results = []
        self.refinement_batch = []

    def _generate_boards(self):
        """Reads the wordlists and generates the initial board data for all rounds based on language ratios."""
        base_dir = Path(__file__).resolve().parent

        # 1. Calculate how many words we need per language for a single board
        total_board_size = sum(self.group_config.values())
        lang_ratio_sum = sum(self.language_config.values())

        # Upscale the multiplier using ceiling division so we always draw AT LEAST 
        # enough words to cover the board size. 
        # e.g., board size 5, ratio 10 -> multiplier 1 -> draws 10 words.
        multiplier = (total_board_size + lang_ratio_sum - 1) // lang_ratio_sum

        if total_board_size % lang_ratio_sum != 0:
            upscaled_pool_size = lang_ratio_sum * multiplier
            log("runGame", f"Warning: Board size ({total_board_size}) and language ratio sum ({lang_ratio_sum}) aren't cleanly divisible. Upscaling pool to {upscaled_pool_size} words.")

        words_per_lang = {lang: count * multiplier for lang, count in self.language_config.items()}

        # 2. Load only the necessary wordlists into memory
        loaded_wordlists = {}
        for lang in self.language_config.keys():
            wordlist_path = base_dir / "wordlists" / f"wordlist{lang.upper()}.txt"

            with open(wordlist_path, 'r', encoding="utf-8") as file:
                loaded_wordlists[lang] = [line.strip() for line in file if line.strip()]

            # Fail fast if we don't have enough words in the file to fulfill the upscaled request
            if len(loaded_wordlists[lang]) < words_per_lang[lang]:
                raise ValueError(
                    f"Wordlist '{lang}' has only {len(loaded_wordlists[lang])} words, but each board "
                    f"needs {words_per_lang[lang]} (due to upscaling). Add more words or lower the language ratio."
                )

        boards = []
        total_games = self.duration["rounds"]

        # 3. Generate each board
        for _ in range(total_games):
            board_pool = []

            # Step A: Gather the required number of words from each language for this board
            for lang, target_count in words_per_lang.items():
                lang_words_copy = loaded_wordlists[lang].copy()
                for _ in range(target_count):
                    # Pop randomly to avoid duplicates of the same language within the same board
                    board_pool.append(lang_words_copy.pop(random.randrange(len(lang_words_copy))))

            # Step B: Shuffle the combined word pool so languages are assigned to groups randomly
            random.shuffle(board_pool)

            # Step C: Assign words to their respective groups (blue, red, etc.)
            board_layout = []
            for group, count in self.group_config.items():
                for _ in range(int(count)):
                    word_str = board_pool.pop()  # Pop from the mixed, randomized pool
                    board_layout.append({
                        "word": word_str.upper(),
                        "group": group,
                        "revealed": False
                    })

            boards.append(board_layout)

        return boards

    def play(self):
        total_games = self.duration["rounds"]
        refinement_step = self.duration.get("refinement_after") or (total_games + 1)

        for game_index in range(total_games):
            log("runGame", f"=== STARTING GAME {game_index + 1} OF {total_games} ===")

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
                log("runGame", "--- BREAK TIME: Refinement ---")

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