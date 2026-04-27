from ..game.game_config import GameConfig
from ..game.game_set import Game
from datetime import datetime
import copy

class Benchmark:
    def __init__(self):
        self.llm_model = None
        self.llm_guesser = None
        self.llm_codemaster = None
        self.prompts:  dict = {}
        self.bench_config = None
        self.game_config:  GameConfig | None = None
        self.id = datetime.now().strftime("%m%d%H%M%S")
        self._results = None

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def addLLM(self, llm_model, role: str = None):
        """Register the LangchainLLM/OllamaLLM instance to use for both roles."""
        self.llm_model = llm_model
        
        if not role:
            self.llm_codemaster = llm_model
            self.llm_guesser = copy.deepcopy(llm_model)
        elif role == "codemaster":
            self.llm_codemaster = llm_model
        elif role == "guesser":
            self.llm_guesser = llm_model
            
        return self

    def addPrompts(self, codemaster_prompt: str, guesser_prompt: str):
        """Register the system prompts for each role."""
        self.prompts = {
            "Codemaster": codemaster_prompt,
            "Guesser":    guesser_prompt,
        }
        return self

    def addBenchConfig(self, bench_config: dict):
        self.bench_config = bench_config
        return self

    def configureGame(self) -> GameConfig:
        """Return a GameConfig builder; call .done() on it to return here."""
        return GameConfig(self)
    
    def setGameConfig(self, game_config: GameConfig) -> "Benchmark":
        """Sets game_config from suite."""
        self.game_config = game_config
        return self

    def build(self) -> "Benchmark":
        if self.llm_codemaster is None or self.llm_guesser is None:
            raise ValueError("Benchmark must have an LLM registered via addLLM().")
        if not self.prompts:
            raise ValueError("Benchmark must have prompts registered via addPrompts().")
        if self.game_config is None:
            raise ValueError("Benchmark requires a configured game (call configureGame()).")
        return self

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def runBenchmarkSet(self):
        game = Game(
            model_codemaster=self.llm_codemaster,
            model_guesser=self.llm_guesser,
            prompts=self.prompts,
            game_config=self.game_config,
            benchmark_id=self.id,
        )
        # Store results for get_results
        self._results = game.runAllGames()

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        model_name = self.llm_model.get_model_name() if self.llm_model else None
        if not model_name and self.llm_codemaster:
            model_name = self.llm_codemaster.get_model_name()
            
        return {
            "model":      model_name,
            "gameConfig": self.game_config.summary() if self.game_config else None,
        }

    def get_results(self):
        if self._results is None:
            raise RuntimeError("Benchmark has not been run yet. Call runBenchmarkSet() first.")
        
        return self._results