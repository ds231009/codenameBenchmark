import copy
import itertools
from typing import Any, TypedDict

from ustp_ccl_benchmark.game_set import GameSet
from ustp_ccl_benchmark.config_dict import ConfigDict
from ustp_ccl_benchmark.llm import LLM

# The rest of the code remains exactly the same
default_config: ConfigDict = {
    "duration":         [{"rounds": 4, "refinement_after": 2}],
    "language_config":  [{"DE": 4}],
    "group_config":     [{"blue": 1, "red": 1, "assassin": 2}]
}

# default_config: ConfigDict = {
#     "duration":         [{"rounds": 10, "refinement_after": 2}, {"rounds": 10, "refinement_after": 5}, {"rounds": 20, "refinement_after": 5}],
#     "language_config":  [{"DE": 5}, {"DE": 5, "EN": 5}],
#     "group_config":     [{"blue": 4, "red": 4, "assassin": 2}]
# }

def run_benchmark(
    bench_config: dict, 
    llm_model: Any, 
    guesser_model: Any = None,
    custom_config: ConfigDict = None  # <--- Now the IDE knows exactly what goes here!
) -> tuple[float, dict]:
    
    guesser_model = guesser_model or llm_model    
    
    # Safely handle the mutable default and merge dictionaries
    custom_config = custom_config or {}
    
    # This takes default_config, and overwrites any matching keys with custom_config
    active_config = default_config | custom_config
    
    # Extract keys and values dynamically
    config_keys = active_config.keys()
    config_values = active_config.values()
    
    results = []
    
    # *config_values unpacks all the lists into itertools.product automatically
    for combination in itertools.product(*config_values):
        
        run_kwargs = dict(zip(config_keys, combination))
        
        print(f"Running Game with: {run_kwargs}")
        
        # **run_kwargs unpacks the dictionary directly into the Game constructor
        game_instance = GameSet(
            llm=LLM(llm_model,{},"Codemaster"),
            guesser=LLM(guesser_model,{},"Guesser"),
            **run_kwargs 
        )
        
        results.append(game_instance.play())
        
    return 1.0, {"completed_runs": len(results)}
