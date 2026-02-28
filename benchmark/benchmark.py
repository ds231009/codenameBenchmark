from .game_setup import GameSetup
from .game_runner import Game


class Benchmark:
    def __init__(self):
        self.modelList = []
        self.game = None

    def addLLM(self, model: str):
        if not isinstance(model, str):
            raise TypeError("Model name must be a string")
        self.modelList.append(model)
        return self

    def configureGame(self):
        return GameSetup(self)

    def build(self):
        if not self.modelList:
            raise ValueError("Benchmark must contain at least one LLM")

        if self.game is None:
            raise ValueError("Benchmark requires a configured game")

        return self

    def runBenchmarkSet(self):
        benchmarkGame = Game()
        benchmarkGame.runBenchmarkSet(self.modelList, self.game)

    def summary(self):
        return {
            "models": self.modelList,
            "gameSize": self.game.gameSize,
            "languageConfig": self.game.languageConfig,
        }