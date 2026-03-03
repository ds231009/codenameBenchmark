class GameConfig:
    def __init__(self, parent):
        self._parent = parent
        self.gameSize = None
        self.languageConfig = {}
        self.board = [
            {"word": "Peru", "group": "blue", "revealed": False},
            {"word": "Hello", "group": "blue", "revealed": False}, 
            {"word": "Chocolate", "group": "blue", "revealed": False}, 
            {"word": "pastery", "group": "blue", "revealed": False},
            {"word": "Badminton", "group": "blue", "revealed": False}, 
            {"word": "Football", "group": "blue", "revealed": False},
            {"word": "airplane", "group": "blue", "revealed": False}, 
            {"word": "Poet", "group": "blue", "revealed": False}, 
            {"word": "Tree", "group": "red", "revealed": False},
            {"word": "Hunt", "group": "red", "revealed": False},
            {"word": "Inn", "group": "red", "revealed": False}, 
            {"word": "Argentina", "group": "red", "revealed": False}, 
            {"word": "Hotel", "group": "red", "revealed": False}, 
            {"word": "World", "group": "assassin", "revealed": False}, 
            {"word": "Sprint", "group": "assassin", "revealed": False}, 
            {"word": "house", "group": "assassin", "revealed": False}, 
            {"word": "flight", "group": "assassin", "revealed": False}]
        self.initalBoard = self.board

    def setGameSize(self, size: int):
        if size <= 0:
            raise ValueError("Game size must be > 0")
        self.gameSize = size
        return self

    def setLanguageConfig(self, config: dict):
        if not isinstance(config, dict):
            raise TypeError("Language config must be a dictionary")
        self.languageConfig = config
        return self
    
    def getBluePlayedBoard(self):
        return [{w["word"].lower(): w["group"].lower()} for w in self.board if w["revealed"] is False and w["group"] == "blue"]
        
    
    def getFullBoard(self):
        return [{w["word"].lower(): w["group"].lower()} for w in self.board if w["revealed"] is False]
    
    def getRevealedBoard(self):
        return [w["word"].lower() for w in self.board if w["revealed"] is False]
    
    def getWordBoard(self):
        return [w["word"].lower() for w in self.board if w["revealed"] is False]
    
    def revealedWord(self, word):
        for referenceWord in self.board:
            if referenceWord["word"].lower() == word:
                referenceWord["revealed"] = True
                
                print("Found word in referenceList")
                
                return referenceWord.copy()
        
        return False
    
    def summary(self):
        return {
                "gameSize": self.gameSize, 
                "languageConfig": self.languageConfig,
                "board": self.initalBoard
            }

    def done(self):
        if self.gameSize is None:
            raise ValueError("Game size must be defined")

        self._parent.gameConfig = self
        return self._parent