import random

class GameConfig:
    def __init__(self, parent):
        self._parent = parent
        self.groupConfig = None
        self.languageConfig = {}

    def setGroupConfig(self, groupConfig):
        if groupConfig["blue"] <= 0:
            raise ValueError("Game size must be > 0")
        self.groupConfig = groupConfig
        return self

    def setLanguageConfig(self, config: dict):
        if not isinstance(config, dict):
            raise TypeError("Language config must be a dictionary")
        self.languageConfig = config
        return self

    def setDuration(self, rounds):
        self.rounds = rounds
        return self

    def setRefinementStep(self, roundsUntilRefinement):
        self.roundsUntilRefinement = roundsUntilRefinement
        return self
    
    
    def generateBoard(self):
        with open('./benchmark/wordlist.txt', 'r') as file:
            rawBoard = [line.strip() for line in file]
        
        boards = []
        for round in range(self.rounds):
            inputBoard = rawBoard.copy() # FIXED: Copy so we don't drain the master list
            board = [] 
            for key, value in self.groupConfig.items():
                for i in range(int(value)):
                    wordString = inputBoard.pop(random.randrange(len(inputBoard)))
                    board.append({"word": wordString.lower(), "group": key, "revealed": False})
            boards.append(board)
            
        return boards
        
    def setActiveBoard(self, index):
        """Loads a specific board from the generated list for the current game."""
        import copy
        self.board = copy.deepcopy(self.boards[index])

    def done(self):
        if self.groupConfig is None:
            raise ValueError("Game size must be defined")

        self.boards = self.generateBoard()
        self.setActiveBoard(0) # Initialize the first board
        self._parent.gameConfig = self
        return self._parent
    
    def getBoard(self, structure="detailed", showOnlyNotRevieled = False,  filterByGroup = ["blue", "red", "assassin"]):
        board = []
        for word in self.board:
            if showOnlyNotRevieled and word["revealed"]: continue
            
            if word["group"] in filterByGroup:
                if structure == "detailed":
                    board.append(word)
                elif structure == "codemaster":
                    board.append({word["word"].lower(): word["group"].lower()})
                elif structure == "word":
                    board.append(word["word"])
                else:
                    raise ValueError("Not a valid structure")
        return board
    
    def revealedWord(self, word):
        for referenceWord in self.board:
            if referenceWord["word"].lower() == word:
                referenceWord["revealed"] = True
                
                print("Found word in referenceList")
                
                return referenceWord.copy()
        
        return False
    
    def summary(self):
        return {
                "gameSize": self.groupConfig, 
                "languageConfig": self.languageConfig,
                "board": self.initalBoard
            }