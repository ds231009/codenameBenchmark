from .game_config import GameConfig
from .game_runner import Game


class Benchmark:
    def __init__(self):
        self.modelList = []
        self.gameConfig = None

    def addLLM(self, modelDetail):
        
        self.modelList.append(modelDetail)
        return self

    def configureGame(self):
        return GameConfig(self)

    def build(self):
        if not self.modelList:
            raise ValueError("Benchmark must contain at least one LLM")

        if self.gameConfig is None:
            raise ValueError("Benchmark requires a configured game")

        return self

    def runBenchmarkSet(self):
        for model in self.modelList:
            benchmarkGame = Game(model, self.gameConfig)
            benchmarkGame.runGame()

    def summary(self):
        return {
            "models":  [m for m in self.modelList],
            "gameConfig": self.gameConfig.summary()
        }