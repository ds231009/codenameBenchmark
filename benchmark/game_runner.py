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
        
        # clue, count = self.getClue()
        count = 1
        clue= "Wood"
        guess = self.getGuess(clue,count)
        print(clue, count, guess)
        
        # self.handleGuess(guess)
        
        # self.gameResults.append({"clue": clue, "guess": guess})
        
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
    
    def getGuess(self, clue, count):
        max_attempts = 5
        earlyStop = False
        guesses = []
        while count > 0 and earlyStop == False:
            print(count,earlyStop,clue)
            for attempt in range(max_attempts):
                print("Attempting Guess", attempt)
                try: 
                    rawGuess = self.modelGuesser.getLLMResponse(self.gameConfig.getWordBoard(), clue)
                    
                    match = re.search(r'\[([^\]]*)\]', rawGuess)
                    if not match:
                        raise ValueError(f"Could not find [word] format in response: {rawGuess}")
                    
                    guess_word = match.group(1).lower()
                    print(guess_word)
                    
                    if guess_word == "no guess":
                        earlyStop = True
                        break
                    else:
                        count -= 1
                        guesses.append(guess_word)
                        break
                    
                    
                except :
                    print("We had an error")
        
            raise ValueError(f"Max tries")

        return guesses
        
        
    def handleGuess(self, guess):
        element = self.board[guess]
        if not element:
            return #Error
        
        if element.values()[0] == "blue":
            #score +1
            pass
        elif element.values()[0] == "red":
            #score -1
            pass
        elif element.values()[0] == "assasin":
            #score -25 end
            pass
    
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