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
    
    
    def generateBoard(self):
        with open('./benchmark/wordlist.txt', 'r') as file:
            inputBoard = [line.strip() for line in file]
       
        board = [] 
        for key, value in self.groupConfig.items():
            for i in range(int(value)):
                wordString = inputBoard.pop(random.randrange(len(inputBoard)))
                board.append({"word": wordString.lower(), "group": key, "revealed": False})
                print(wordString, key, value)

        self.initalBoard = board
        return board
    
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

    def done(self):
        if self.groupConfig is None:
            raise ValueError("Game size must be defined")

        self.board = self.generateBoard()
        self._parent.gameConfig = self
        return self._parent
    