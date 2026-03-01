class GameConfig:
    def __init__(self, parent):
        self._parent = parent
        self.gameSize = None
        self.languageConfig = {}
        self.board = [
            {"word": "Tree", "group": "red", "revealed": False},
            {"word": "flight", "group": "assasin", "revealed": False}, 
            {"word": "Hello", "group": "blue", "revealed": False}, 
            {"word": "World", "group": "assasin", "revealed": False}, 
            {"word": "Chocolate", "group": "blue", "revealed": False}, 
            {"word": "pastery", "group": "blue", "revealed": False},
            {"word": "Inn", "group": "red", "revealed": False}, 
            {"word": "airplane", "group": "blue", "revealed": False}, 
            {"word": "house", "group": "assisin", "revealed": False}, 
            {"word": "Peru", "group": "blue", "revealed": False}]

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
    
    def getFullBoard(self):
        return [{w["word"].lower(): w["group"].lower()} for w in self.board]
    
    def getRevealedBoard(self):
        return [w["word"].lower() for w in self.board if w["revealed"] is False]
    
    def getWordBoard(self):
        return [w["word"].lower() for w in self.board]
    
    def revealedWord(self, word):
        for referenceWord in self.board:
            print("Checking reveal for the word", word, "-", referenceWord["word"].lower(), referenceWord["word"].lower() == word)
            if referenceWord["word"].lower() == word:
                referenceWord["revealed"] = True
                
                print("Found word in referenceList")
                
                return referenceWord.copy()
        
        return False
    
    def summary(self):
        return {
                "gameSize": self.gameSize, 
                "languageConfig": self.languageConfig
            }

    def done(self):
        if self.gameSize is None:
            raise ValueError("Game size must be defined")

        self._parent.gameConfig = self
        return self._parent