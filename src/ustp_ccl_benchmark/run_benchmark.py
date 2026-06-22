import itertools
from typing import Any

from ustp_ccl_benchmark.game_set import GameSet
from ustp_ccl_benchmark.config_dict import ConfigDict
from ustp_ccl_benchmark.llm import LLM

# The rest of the code remains exactly the same
default_config: ConfigDict = {
    "duration":         [{"rounds": 4, "refinement_after": 2}, {"rounds": 10, "refinement_after": 5}],
    "language_config":  [{"DE": 5}, {"DE": 5, "EN": 5}],
    "group_config":     [{"blue": 4, "red": 4, "assassin": 2}]
}

# default_config: ConfigDict = {
#     "duration":         [{"rounds": 10, "refinement_after": 2}, {"rounds": 10, "refinement_after": 5}, {"rounds": 20, "refinement_after": 5}],
#     "language_config":  [{"DE": 5}, {"DE": 5, "EN": 5}, {"EN": 5, "FR": 5}],
#     "group_config":     [{"blue": 4, "red": 4, "assassin": 2}, {"blue": 2, "red": 2, "assassin": 6}, {"blue": 5, "red": 5, "assassin": 0}]
# }

def calculate_result(results: list[dict]) -> float:
    """Turns the collected GameSet results into a single benchmark score.

    Placeholder: averages the win_rate across every run in the sweep, so
    run_benchmark() returns something that actually reflects how the games
    went instead of a hardcoded 1.0. Swap this out once stage 2 settles on
    a real scoring formula -- e.g. blending in avg_final_score, weighting
    error rates, or scoring per-config instead of pooling everything
    together.
    """
    # if not results:
    #     return 0.0

    # win_rates = [r["aggregateStats"]["win_rate"] for r in results]
    # return sum(win_rates) / len(win_rates)
    return 1.0


def run_benchmark(
    bench_config: dict,
    llm_model: Any,
    guesser_model: Any = None,
    custom_config: ConfigDict = None,  # <--- Now the IDE knows exactly what goes here!
    benchmark_id: str = "bench",
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
    for combo_index, combination in enumerate(itertools.product(*config_values), start=1):

        run_kwargs = dict(zip(config_keys, combination))

        # FIX: previously GameSet always got the default benchmarkID="default",
        # so every combination in this loop (different duration/language/group
        # configs) wrote its results to the same file and overwrote the last
        # one. Each combination now gets its own id. GameSet._run_signature()
        # also bakes the config into the filename as a second layer of
        # protection, so this isn't the only thing standing between you and
        # an overwrite.
        run_id = f"{benchmark_id}_{combo_index:02d}"

        print(f"Running Game {run_id} with: {run_kwargs}")

        # **run_kwargs unpacks the dictionary directly into the Game constructor
        game_instance = GameSet(
            llm=LLM(llm_model, {}, "Codemaster"),
            guesser=LLM(guesser_model, {}, "Guesser"),
            benchmarkID=run_id,
            **run_kwargs
        )

        game_result = game_instance.play()
        # Tag each run with what produced it, since `results` below pools
        # every combination in the sweep together -- without this you can't
        # tell which row came from which config.
        game_result["run_id"] = run_id
        game_result["run_kwargs"] = run_kwargs
        results.append(game_result)

    score = calculate_result(results)

    return score, {"completed_runs": len(results), "results": results}