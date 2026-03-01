from llms.llm import LLM

from pathlib import Path
from datetime import datetime
import json
import re


class Game:
    def __init__(self, model, gameConfig):
        self.gameResults = []
        self.modelCodemaster = LLM(model, "Codemaster")
        self.modelGuesser = LLM(model, "Guesser")
        self.gameConfig = gameConfig
        

    def runGame(self):
        
        clue, count = self.getClue()
        # count = 1
        # clue= "Wood"
        guesses = self.getGuesses(clue,count)
        
        self.handleGuess(guesses)
        print(clue, count, guesses)
        
        score = self.handleGuess(guesses)
        
        self.gameResults.append({"clue": clue, "guess": guesses, "score": score})
        
        self.saveStats()
    
    
    def getClue(self):
        max_attempts = 5
        for attempt in range(max_attempts):
            print("Attempting Clue", attempt)
            
            try: 
                rawClue =  self.modelCodemaster.getLLMResponse(self.gameConfig.getFullBoard())
                
                match = re.search(r'\(\s*([a-zA-Z]+)\s*,\s*(\d+)\s*\)', rawClue)
                if not match:
                    raise ValueError(f"Could not find (word, count) format in response: {rawClue}")
                
                clue_word = match.group(1).lower()
                count = int(match.group(2))
                
                if clue_word in self.gameConfig.getWordBoard():
                    raise ValueError(f"Clue {clue_word} is in word list")
                else:
                    return clue_word, count
                
            except:
                print("We had an error")
    
        raise ValueError(f"Max tries")


    def getGuesses(self, clue, count):
        guesses = []

        while count > 0:
            guess = self.getGuess(clue, count)
            if guess == None:
                break
            else:
                guesses.append(guess)
            count -= 1
        return guesses


    def getGuess(self, clue, count):
        max_attempts = 5
        print(count,clue)
        for attempt in range(max_attempts):
            print("Attempting Guess", attempt)
            try:
                rawGuess = self.modelGuesser.getLLMResponse(self.gameConfig.getRevealedBoard(), clue)

                match = re.search(r'\[([^\]]*)\]', rawGuess)
                if not match:
                    raise ValueError(f"Could not find [word] format in response: {rawGuess}")

                guess_word = match.group(1).lower()
                print(guess_word)

                if guess_word == "no guess":
                    return None
                else:
                    print("Checking word in list", guess_word in self.gameConfig.getRevealedBoard())
                    if guess_word in self.gameConfig.getRevealedBoard():
                        return self.gameConfig.revealedWord(guess_word)
                    else:
                        raise ValueError("Word has to be in word list")


            except :
                print("We had an error")
        
        
    def handleGuess(self, guesses):
        score = 0
        print(guesses)
        for guess in guesses:
            if guess["group"] == "blue":
                score += 1
                pass
            elif guess["group"] == "red":
                score -= 1
                pass
            elif guess["group"] == "assasin":
                score = -25
                break
        
        return score
    
    def saveStats(self):
        file_path = createDirectory()
        
        result = {
            "modelDetailsCodemaster": self.modelCodemaster.summary(),
            "modelDetailsGuesser": self.modelGuesser.summary(),
            "gameSetup": self.gameConfig.summary(),
            "gameResults": self.gameResults
        }

        saveFile(file_path, result)
        
        

def createDirectory():
    BASE_DIR = Path(__file__).resolve().parent

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results_dir = BASE_DIR.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    return results_dir / f"resultsTest_{timestamp}.json"
    
    
def saveFile(file_path, result):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"Saved results to: {file_path}")