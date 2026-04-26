from .game_config import GameConfig
from .game_runner import Game

from datetime import datetime

class Benchmark:
    def __init__(self):
        self.gameConfig = None
        self.id = datetime.now().strftime("%m%d%H%M%S")

    def addLLM(self, model):
        self.llm = model
        return self

    def configureGame(self):
        return GameConfig(self)

    def build(self):
        if not self.llm:
            raise ValueError("Benchmark must contain LLM")

        if self.gameConfig is None:
            raise ValueError("Benchmark requires a configured game")

        return self

    def runBenchmarkSet(self):
        benchmarkGame = Game(self.llm, self.gameConfig, self.id)
        benchmarkGame.runAllGames()

    def summary(self):
        return {
            "models":  [m for m in self.modelList],
            "gameConfig": self.gameConfig.summary()
        }