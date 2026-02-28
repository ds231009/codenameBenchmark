class GameSetup:
    def __init__(self, parent):
        self._parent = parent
        self.gameSize = None
        self.languageConfig = {}

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

    def done(self):
        if self.gameSize is None:
            raise ValueError("Game size must be defined")

        self._parent.game = self
        return self._parent