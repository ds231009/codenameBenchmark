from pathlib import Path
from datetime import datetime
import random
import json
import re
import copy

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

class Board:
    def __init__(self, initial_words: list[dict]):
        self.words = copy.deepcopy(initial_words)

    def get_formatted(self, structure="detailed", show_only_unrevealed=False, filter_by_group=("blue", "red", "assassin")):
        """Formats the board for the LLM prompts."""
        formatted_board = []
        for word in self.words:
            if show_only_unrevealed and word["revealed"]: 
                continue
            
            if word["group"] in filter_by_group:
                if structure == "detailed":
                    formatted_board.append(word)
                elif structure == "codemaster":
                    formatted_board.append({word["word"].upper(): word["group"].upper()})
                elif structure == "word":
                    formatted_board.append(word["word"])
                else:
                    raise ValueError(f"Not a valid structure: {structure}")
        return formatted_board

    def reveal_word(self, guessed_word: str):
        """Marks a word as revealed and returns it. Returns False if not found."""
        guessed_word = guessed_word.upper()
        for ref_word in self.words:
            if ref_word["word"].upper() == guessed_word:
                ref_word["revealed"] = True
                return ref_word.copy()
        return False