from ..llms import OllamaLLM, LangchainLLM
from ..game.game_config import GameConfig
from .benchmark import Benchmark


class BenchmarkSuite:
    def __init__(self):
        self.modelList = []
        self.prompts = {
            "Codemaster": "You are the Codemaster.",
            "Guesser": "You are the Guesser."
        }
        
    def addModel(self, config: dict):
        try:
            if not config:
                print("Warning: Received empty config in addModel.")
                return self
                
            if config.get("type") == "Langchain":
                llm_model = LangchainLLM(
                    model_name = config["name"],
                    base_url = config["base_url"],
                    api_key = config["api_key"],
                ) 
            elif config.get("type") == "Ollama":
                llm_model = OllamaLLM(config["name"])
            else:
                raise ValueError(f"Unknown model type: {config.get('type')}")
                
            self.modelList.append(llm_model)
        except Exception as e:
            print(f"Model configuration error: {e}")
            
        return self

    def addPrompts(self, codemaster_prompt: str, guesser_prompt: str):
        self.prompts["Codemaster"] = codemaster_prompt
        self.prompts["Guesser"] = guesser_prompt
        return self

    def configureGame(self) -> GameConfig:
        """Return a GameConfig builder; call .done() on it to return here."""
        return GameConfig(self)

    
    def runBenchmarkSet(self):
        if len(self.modelList) == 0:
            print("Warning: No models configured. Please add at least one model.")
            return
        
        for llm_model in self.modelList:
            results = []
            benchmark = (
                Benchmark()
                .addLLM(llm_model)
                .addPrompts(self.prompts["Codemaster"], self.prompts["Guesser"])
                .addBenchConfig({})
                .setGameConfig(self.game_config)
                .build()
            )
            
            print(benchmark.summary())
            benchmark.runBenchmarkSet()
            
            final_score, raw_details = benchmark.get_results()
            results.append({"score": final_score, "details": raw_details})
            print(f"Suite completed for model: {llm_model.get_model_name()} | Final Score: {final_score}")