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

class Game:
    def __init__(self, llm_codemaster, llm_guesser, board, group_config: dict):
        self.modelCodemaster = llm_codemaster # Fixed missing assignment
        self.modelGuesser = llm_guesser
        self.board = board
        self.group_config = group_config
        self.turn_history = [] 
        self.current_game_rounds = []

    def play(self):
        max_turns = sum(self.group_config.values()) # Fixed typo
        
        for turn in range(max_turns):
            log("runGame", f"Playing turn {turn}")
            
            continueGame, round_data = self.runRound()
            self.current_game_rounds.append(round_data)
            
            # 1. Check for the WIN condition FIRST
            # Fixed to use Board class
            if len(self.board.get_formatted("word", show_only_unrevealed=True, filter_by_group=["blue"])) == 0:
                log("runGame", "Board solved! All blue words found. (WIN)")
                break
                
            # 2. If not won, check if game was forced to end (Assassin hit)
            if not continueGame:
                log("runGame", "Game over. Assassin hit! (LOSS)")
                break
                
        return self.current_game_rounds, self.turn_history

    def runRound(self):
        log("runGame", "--- Starting New Round ---")
        
        if not self.turn_history:
            history_prompt = "This is the first turn. No guesses have been made yet."
        else:
            history_prompt = "HISTORY OF PREVIOUS TURNS IN THIS GAME:\n" + "\n".join(self.turn_history)
        
        clue, count = self.getClue(feedback=history_prompt)
        
        if clue is None:
            log("runGame", "--- Round Summary: Codemaster failed. Turn skipped. ---")
            self.turn_history.append(f"- Turn {len(self.turn_history) + 1}: Codemaster failed to format a clue. Turn skipped.")
            return True, {"clue": "FAILED_FORMAT", "count": 0, "guesses": []}
            
        guesses, continueGame = self.getGuesses(clue, count)
        log("runGame", f"--- Round Summary: Clue: ({clue}, {count}), Guesses made: {len(guesses)} ---")
        
        round_data = {"clue": clue, "count": count, "guesses": []}
        guess_strings = [] 
        
        for g in guesses:
            if g.get("guess"): 
                word = g["guess"]["word"]
                group = g["guess"]["group"]
                score = g["score"]
                round_data["guesses"].append({"word": word, "group": group, "score": score})
                guess_strings.append(f"'{word}' (which was {group})")

        if not guess_strings:
            self.turn_history.append(f"- Turn {len(self.turn_history) + 1}: You gave clue ({clue}, {count}). Guesser passed.")
        else:
            self.turn_history.append(f"- Turn {len(self.turn_history) + 1}: You gave clue ({clue}, {count}). Guesser picked: {', '.join(guess_strings)}.")

        return continueGame, round_data

    def getClue(self, feedback=None):
        max_attempts = 5
        for attempt in range(max_attempts):
            try: 
                rawClue = self.modelCodemaster.getLLMResponse(
                    self.board.get_formatted("codemaster", show_only_unrevealed=True), 
                    feedback=feedback # Fixed variable scope issue
                )
                match = re.search(r'\(\s*([a-zA-Z]+)\s*,\s*(\d+)\s*\)', rawClue)
                if not match: raise ValueError(f"Could not find (word, count) format in response: {rawClue}")
                
                clue_word = match.group(1).upper()
                count = int(match.group(2))
                
                # Fixed to use Board class
                if clue_word in self.board.get_formatted("word", show_only_unrevealed=True):
                    raise ValueError(f"Clue '{clue_word}' is in the word list.")
                
                log("getClue", f"Codemaster gave clue: ({clue_word}, {count})")
                return clue_word, count
            except Exception as e:
                log("getClue", f"Attempt {attempt + 1} failed: {e}")
                
        log("getClue", "Codemaster failed to provide a valid clue. Wasting turn.")
        return None, 0

    def getGuesses(self, clue, count):
        guesses = []
        continueGame = True
        while count > 0:
            guess = self.getGuess(clue)
            if guess is None: 
                log("getGuesses", "Guesser ended their turn early.")
                break
            
            continueGame, continueRound, score = self.handleGuess(guess)
            guesses.append({"guess": guess, "score": score})
            if not continueRound or not continueGame: break
            count -= 1
        return guesses, continueGame

    def getGuess(self, clue):
        max_attempts = 5
        error_feedback = "" 
        for attempt in range(max_attempts):
            try:
                prompt_clue = f"{clue}. WARNING: {error_feedback}" if error_feedback else clue
                # Fixed to use Board class
                rawGuess = self.modelGuesser.getLLMResponse(
                    self.board.get_formatted("word", show_only_unrevealed=True), 
                    prompt_clue
                )

                match = re.search(r'\[([^\]]*)\]', rawGuess)
                if not match: raise ValueError(f"Could not find [word] format in response: {rawGuess}")
                    
                guess_word = match.group(1).upper()
                if guess_word == "no guess" or rawGuess == "no guess":
                    log("getGuess", "Guesser chose to pass [no guess]")
                    return None
                
                # Fixed to use Board class
                if guess_word in self.board.get_formatted("word", show_only_unrevealed=True):
                    log("getGuess", f"Guesser chose word: [{guess_word}]")
                    return self.board.reveal_word(guess_word) # Fixed
                else: raise ValueError(f"You guessed '{guess_word}', but it is not on the board!")
            except ValueError as e:
                log("getGuess", f"Attempt {attempt + 1} validation error: {e}")
                error_feedback = str(e) 
        return None 
        
    def handleGuess(self, guess):
        continueGame, continueRound, score = True, True, 0
        group = guess["group"]
        word = guess["word"]
        
        if group == "blue":
            score = 1
            log("handleGuess", f"Guessed '{word}' correctly.")
        elif group == "red":
            score = -1
            continueRound = False
            log("handleGuess", f"Guessed '{word}' wrong")
        elif group == "assassin":
            continueGame = False
            score = -25
            log("handleGuess", f"Guessed '{word}' as assassin")
            
        # Fixed to use Board class
        if len(self.board.get_formatted("codemaster", show_only_unrevealed=True, filter_by_group=["blue"])) == 0:
            continueGame = False
        
        return continueGame, continueRound, score