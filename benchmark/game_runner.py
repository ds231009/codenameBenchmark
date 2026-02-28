from pathlib import Path
from datetime import datetime
import json

class Game:
    def runBenchmarkSet(self, models, game):
        for model in models:
            self.runBenchmark(model, game)

    def runBenchmark(self, model, game):
        print(f"Running {model} on game size {game.gameSize}")
        self.saveStats()
        
    
    def saveStats(self, result=None):
        if result is None:
            result = {"Result": "test"}

        BASE_DIR = Path(__file__).resolve().parent

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        results_dir = BASE_DIR.parent / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        file_path = results_dir / f"results_{timestamp}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)

        print(f"Saved results to: {file_path}")