from pathlib import Path
from datetime import datetime
import random
import json
import re
import copy

from ustp_ccl_benchmark.board import Board
from ustp_ccl_benchmark.game import Game

from colorama import Fore, Style, init
init(autoreset=True)

def log(function, *args, **kwargs):
    colorMap = {
        "runGame": Fore.CYAN,
        "getClue": Fore.BLUE,
        "getGuesses": Fore.RED,
        "getGuess": Fore.YELLOW,
        "handleGuess": Fore.GREEN,
        "saveStats": Fore.LIGHTCYAN_EX,
    }
    print(
        colorMap[function]
        + f"[Runner] [{function}] "
        + "     "
        + ", ".join(map(str, (*args, *kwargs.values())))
        + Style.RESET_ALL
    )


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
        
        if total_board_size % lang_ratio_sum != 0:
            raise ValueError(f"Board size ({total_board_size}) must be cleanly divisible by the language ratio sum ({lang_ratio_sum}).")
            
        multiplier = total_board_size // lang_ratio_sum
        words_per_lang = {lang: count * multiplier for lang, count in self.language_config.items()}
        
        # 2. Load only the necessary wordlists into memory
        loaded_wordlists = {}
        for lang in self.language_config.keys():
            # Assuming files are named like 'wordlist_english.txt', 'wordlist_german.txt'
            # (Adjust the formatting string below if your files are named differently, e.g., f"{lang.upper()}.txt")
            wordlist_path = base_dir / "wordlists" / f"wordlist{lang.upper()}.txt" 
            
            with open(wordlist_path, 'r', encoding="utf-8") as file:
                loaded_wordlists[lang] = [line.strip() for line in file if line.strip()]
                
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
                    word_str = board_pool.pop() # Pop from the mixed, randomized pool
                    board_layout.append({
                        "word": word_str.upper(), 
                        "group": group, 
                        "revealed": False
                    })
                    
            boards.append(board_layout)
            
        return boards

    def play(self):
        total_games = self.duration["rounds"]
        refinement_step = self.duration.get("refinement_after", total_games + 1)

        for game_index in range(total_games):
            log("runGame", f"=== STARTING GAME {game_index + 1} OF {total_games} ===")
            
            # 2. Instantiate a fresh Board object for this specific round
            raw_board_data = self.all_boards_data[game_index]
            current_board = Board(raw_board_data)
            
            initial_board_state = current_board.get_formatted("detailed", filter_by_group=["blue", "red", "assassin"])
            
            # 3. Pass the Board and group_config into the Game
            single_game = Game(self.modelCodemaster, self.modelGuesser, current_board, self.group_config)
            game_rounds_data, game_turn_history = single_game.play()
            
            self.all_games_results.append({
                "game_index": game_index + 1,
                "rounds": game_rounds_data,
                "turn_history": game_turn_history 
            })

            self.refinement_batch.append({
                "game_index": game_index + 1,
                "initial_board": initial_board_state,
                "turn_history": game_turn_history
            })

            # Refinement Logic
            if (game_index + 1) % refinement_step == 0:
                log("runGame", f"--- BREAK TIME: Refinement ---")
                reflection_output = self.modelCodemaster.writeRefinement(self.refinement_batch)
                self.refinements_results.append({
                    "after_game": game_index + 1,
                    "batch_data": self.refinement_batch,
                    "llm_reflection": reflection_output
                })
                self.refinement_batch = [] 
                self.modelCodemaster.clearMemory()
                self.modelGuesser.clearMemory()
                
        self.saveStats()
        return self.all_games_results
        
    def saveStats(self):
        summary_data = {
            "gameSize": self.group_config, 
            "languageConfig": self.language_config,
        }
        
        file_path = createDirectory(self.benchmarkID, self.modelCodemaster.modelName, self.modelGuesser.modelName)
        
        result = {
            "modelDetailsCodemaster": self.modelCodemaster.summary(),
            "modelDetailsGuesser": self.modelGuesser.summary(),
            "gameSetup": summary_data,
            "games": self.all_games_results,
            "refinements": self.refinements_results
        }

        saveFile(file_path, result)


# --- Helper File Operations ---

def createDirectory(benchmarkID, modelCodemaster, modelGuesser):
    BASE_DIR = Path(__file__).resolve().parent

    results_dir = BASE_DIR.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    shortModelCodemaster = modelCodemaster.replace(".","").replace(":","")
    shortModelGuesser = modelGuesser.replace(".","").replace(":","")
    return results_dir / f"resultsTest_{benchmarkID}_{shortModelCodemaster}_{shortModelGuesser}.json"
    
def saveFile(file_path, result):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"Saved results to: {file_path}")