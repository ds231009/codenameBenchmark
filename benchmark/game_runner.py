from llms.llm import LLM

from pathlib import Path
from datetime import datetime
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
    def __init__(self, model, gameConfig, benchmarkID):
        self.gameResults = []
        self.modelCodemaster = LLM(model, "Codemaster")
        self.modelGuesser = LLM(model, "Guesser")
        self.gameConfig = copy.deepcopy(gameConfig)
        self.benchmarkID = benchmarkID
        

    def runGame(self):
        for round in range(self.gameConfig.gameSize):
            log("runGame", f"Playing round {round}")
            continueGame = self.runRound()
            if not continueGame:
                log("runGame", "Game over")
                break
            if len(self.gameConfig.getRevealedBoard()) == 0:
                log("runGame", "Board solved")
                break
        self.saveStats()
        
        
    def runRound(self):
        log("runGame", "--- Starting New Round ---")
        clue, count = self.getClue()
        guesses, continueGame = self.getGuesses(clue, count)
        
        log("runGame", f"--- Round Summary: Clue: ({clue}, {count}), Guesses made: {len(guesses)}{guesses} ---")
        
        self.gameResults.append({
            "clue": clue, 
            "count": count, 
            "guesses": [{"guess": g["guess"], "score": g["score"]} for g in guesses]
        })
        
        return continueGame
        
    def getClue(self):
        max_attempts = 5
        
        for attempt in range(max_attempts):
            try: 
                rawClue = self.modelCodemaster.getLLMResponse(self.gameConfig.getFullBoard())
                
                match = re.search(r'\(\s*([a-zA-Z]+)\s*,\s*(\d+)\s*\)', rawClue)
                if not match:
                    raise ValueError(f"Could not find (word, count) format in response: {rawClue}")
                
                clue_word = match.group(1).lower()
                count = int(match.group(2))
                
                if clue_word in self.gameConfig.getWordBoard():
                    raise ValueError(f"Clue '{clue_word}' is in the word list.")
                
                # SUCCESS LOG
                log("getClue", f"Codemaster gave clue: ({clue_word}, {count})")
                return clue_word, count
                
            except Exception as e:
                # ERROR LOG: Actually print the error so you can debug it!
                log("getClue", f"Attempt {attempt + 1} failed: {e}")
    
        raise ValueError(f"Codemaster failed to provide a valid clue after {max_attempts} tries.")

    def getGuesses(self, clue, count):
        guesses = []
        continueGame = True
        while count > 0:
            guess = self.getGuess(clue)
            
            if guess is None: # The Guesser passed
                log("getGuesses", "Guesser ended their turn early.")
                break
            
            continueGame, continueRound, score = self.handleGuess(guess)
            log("getGuesses", continueGame)
            guesses.append({"guess": guess, "score": score})
            
            if not continueRound or not continueGame:
                break
                
            count -= 1

        return guesses, continueGame

    def getGuess(self, clue):
        max_attempts = 5
        error_feedback = "" 
        
        for attempt in range(max_attempts):
            try:
                prompt_clue = clue
                if error_feedback:
                    prompt_clue = f"{clue}. WARNING: {error_feedback}"
                    
                rawGuess = self.modelGuesser.getLLMResponse(self.gameConfig.getRevealedBoard(), prompt_clue)

                match = re.search(r'\[([^\]]*)\]', rawGuess)
                if not match:
                    raise ValueError(f"Could not find [word] format in response: {rawGuess}")
                    
                guess_word = match.group(1).lower()

                if guess_word == "no guess" or rawGuess == "no guess":
                    # SUCCESS LOG (Pass)
                    log("getGuess", "Guesser chose to pass [no guess]")
                    return None
                
                if guess_word in self.gameConfig.getRevealedBoard():
                    # SUCCESS LOG (Guess)
                    log("getGuess", f"Guesser chose word: [{guess_word}]")
                    return self.gameConfig.revealedWord(guess_word)
                else:
                    raise ValueError(f"You guessed '{guess_word}', but it is not on the board!")

            except ValueError as e:
                # ERROR LOG
                log("getGuess", f"Attempt {attempt + 1} validation error: {e}")
                error_feedback = str(e) 
                
        log("getGuess", "Max attempts reached, forcing turn end.")
        return None 
        
    def handleGuess(self, guess):
        continueGame = True
        continueRound = True
        group = guess["group"]
        word = guess["word"]
        score = 0
        
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
            
        log("handleGuess", f"Checking if game is finshied. Here are the open cards: {self.gameConfig.getBluePlayedBoard()}")
            
        if len(self.gameConfig.getBluePlayedBoard()) == 0:
            continueGame = False
        
        return continueGame, continueRound, score
    
    def saveStats(self):
        file_path = createDirectory(self.benchmarkID, self.modelCodemaster.modelName, self.modelGuesser.modelName)
        
        result = {
            "modelDetailsCodemaster": self.modelCodemaster.summary(),
            "modelDetailsGuesser": self.modelGuesser.summary(),
            "gameSetup": self.gameConfig.summary(),
            "gameResults": self.gameResults
        }

        saveFile(file_path, result)
        
        

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