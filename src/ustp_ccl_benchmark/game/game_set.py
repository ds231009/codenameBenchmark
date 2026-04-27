from ustp_ccl_benchmark.llms.llm_wrapper import LLM

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
        self.all_games_results = [] 
        self.refinements_results = [] # <--- NEW: Stores the refinement data for the JSON
        self.refinement_batch = []    # <--- NEW: The temporary list that holds data for 5 games
        
        self.modelCodemaster = LLM(model, "Codemaster")
        self.modelGuesser = LLM(model, "Guesser")
        self.gameConfig = copy.deepcopy(gameConfig)
        self.benchmarkID = benchmarkID
        

    def runAllGames(self):
        total_games = self.gameConfig.rounds 
        refinement_step = getattr(self.gameConfig, 'roundsUntilRefinement', 5)

        for game_index in range(total_games):
            log("runGame", f"=== STARTING GAME {game_index + 1} OF {total_games} ===")
            
            self.gameConfig.setActiveBoard(game_index)
            
            # 1. Capture the initial board BEFORE the game starts
            initial_board = self.gameConfig.getBoard("detailed", filterByGroup=["blue", "red", "assassin"])
            
            # 2. Play the game
            game_rounds_data, game_turn_history = self.playSingleGame()
            
            # 3. Save the single game to the master JSON list
            self.all_games_results.append({
                "game_index": game_index + 1,
                "rounds": game_rounds_data,
                "turn_history": game_turn_history # Optional: adds text history to JSON
            })

            # 4. Add this game's summary to the Refinement Batch
            self.refinement_batch.append({
                "game_index": game_index + 1,
                "initial_board": initial_board,
                "turn_history": game_turn_history
            })

            # 5. Break / Memory Wipe / Refinement Logic
            if (game_index + 1) % refinement_step == 0:
                log("runGame", f"--- BREAK TIME: Refinement and Clearing Memory ---")
                
                # Have the LLM analyze the batch of games
                # (You will need to implement writeRefinement in your LLM class to accept this list)
                reflection_output = self.modelCodemaster.writeRefinement(self.refinement_batch)
                
                # Save the reflection and the batch data to our final JSON results
                self.refinements_results.append({
                    "after_game": game_index + 1,
                    "batch_data": self.refinement_batch,
                    "llm_reflection": reflection_output
                })
                
                # RESET the batch for the next 5 games
                self.refinement_batch = [] 
                
                # Clear memories
                self.modelCodemaster.clearMemory()
                self.modelGuesser.clearMemory()
                
        self.saveStats()


    def playSingleGame(self):
        self.turn_history = [] 
        current_game_rounds = [] 

        max_turns = sum(self.gameConfig.groupConfig.values())
        
        for turn in range(max_turns):
            log("runGame", f"Playing turn {turn}")
            
            continueGame, round_data = self.runRound()
            current_game_rounds.append(round_data)
            
            # 1. Check for the WIN condition FIRST
            if len(self.gameConfig.getBoard("word", True, ["blue"])) == 0:
                log("runGame", "Board solved! All blue words found. (WIN)")
                break
                
            # 2. If not won, check if game was forced to end (Assassin hit)
            if not continueGame:
                log("runGame", "Game over. Assassin hit! (LOSS)")
                break
                
        # RETURN BOTH: the raw JSON data AND the text-based turn history
        return current_game_rounds, self.turn_history
        
        
    def runRound(self):
        log("runGame", "--- Starting New Round ---")
        
        # 1. Build the cumulative history for the Codemaster
        if not self.turn_history:
            history_prompt = "This is the first turn. No guesses have been made yet."
        else:
            history_prompt = "HISTORY OF PREVIOUS TURNS IN THIS GAME:\n" + "\n".join(self.turn_history)
        
        # 2. Get Clue 
        clue, count = self.getClue(feedback=history_prompt)
        
        # FIX: If the Codemaster failed entirely, skip the Guesser and waste the turn
        if clue is None:
            log("runGame", "--- Round Summary: Codemaster failed. Turn skipped. ---")
            self.turn_history.append(f"- Turn {len(self.turn_history) + 1}: Codemaster failed to format a clue. Turn skipped.")
            
            round_data = {
                "clue": "FAILED_FORMAT", 
                "count": 0, 
                "guesses": []
            }
            # Return True to keep playing, but this turn is wasted
            return True, round_data 
            
        # 3. If clue is valid, get Guesses
        guesses, continueGame = self.getGuesses(clue, count)
        
        log("runGame", f"--- Round Summary: Clue: ({clue}, {count}), Guesses made: {len(guesses)} ---")
        
        # 4. Compile the JSON data for this round
        round_data = {
            "clue": clue, 
            "count": count, 
            "guesses": []
        }
        guess_strings = [] 
        
        for g in guesses:
            if g.get("guess"): 
                word = g["guess"]["word"]
                group = g["guess"]["group"]
                score = g["score"]
                
                round_data["guesses"].append({"word": word, "group": group, "score": score})
                guess_strings.append(f"'{word}' (which was {group})")

        # 5. Update the Codemaster's history log for the NEXT turn
        if not guess_strings:
            self.turn_history.append(f"- Turn {len(self.turn_history) + 1}: You gave clue ({clue}, {count}). Guesser passed.")
        else:
            self.turn_history.append(f"- Turn {len(self.turn_history) + 1}: You gave clue ({clue}, {count}). Guesser picked: {', '.join(guess_strings)}.")

        return continueGame, round_data
        
    def getClue(self, feedback=None):
        max_attempts = 5
        
        for attempt in range(max_attempts):
            try: 
                # Pass the feedback into the LLM call
                rawClue = self.modelCodemaster.getLLMResponse(
                    self.gameConfig.getBoard("codemaster", True), 
                    feedback=feedback
                )
                
                match = re.search(r'\(\s*([a-zA-Z]+)\s*,\s*(\d+)\s*\)', rawClue)
                if not match:
                    raise ValueError(f"Could not find (word, count) format in response: {rawClue}")
                
                clue_word = match.group(1).lower()
                count = int(match.group(2))
                
                if clue_word in self.gameConfig.getBoard("word", True):
                    raise ValueError(f"Clue '{clue_word}' is in the word list.")
                
                log("getClue", f"Codemaster gave clue: ({clue_word}, {count})")
                return clue_word, count
                
            except Exception as e:
                log("getClue", f"Attempt {attempt + 1} failed: {e}")
    
        # FIX: Instead of raising an error, log it and return None
        log("getClue", "Codemaster failed to provide a valid clue. Wasting turn.")
        return None, 0

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
                    
                rawGuess = self.modelGuesser.getLLMResponse(self.gameConfig.getBoard("word",True), prompt_clue)

                match = re.search(r'\[([^\]]*)\]', rawGuess)
                if not match:
                    raise ValueError(f"Could not find [word] format in response: {rawGuess}")
                    
                guess_word = match.group(1).lower()

                if guess_word == "no guess" or rawGuess == "no guess":
                    # SUCCESS LOG (Pass)
                    log("getGuess", "Guesser chose to pass [no guess]")
                    return None
                
                if guess_word in self.gameConfig.getBoard("word",True):
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
            
        log("handleGuess", f"Checking if game is finshied. Here are the open cards: {self.gameConfig.getBoard('codemaster', True, ['blue'])}")
            
        if len(self.gameConfig.getBoard("codemaster",True,["blue"])) == 0:
            continueGame = False
        
        return continueGame, continueRound, score
    
    def saveStats(self):
        file_path = createDirectory(self.benchmarkID, self.modelCodemaster.modelName, self.modelGuesser.modelName)
        
        result = {
            "modelDetailsCodemaster": self.modelCodemaster.summary(),
            "modelDetailsGuesser": self.modelGuesser.summary(),
            "gameSetup": self.gameConfig.summary(),
            "games": self.all_games_results,
            "refinements": self.refinements_results # <--- Nested refinement data added here!
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