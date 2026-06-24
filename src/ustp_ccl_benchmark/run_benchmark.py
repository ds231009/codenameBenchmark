import itertools
from typing import Any

from ustp_ccl_benchmark.game_set import GameSet
from ustp_ccl_benchmark.config_dict import ConfigDict
from ustp_ccl_benchmark.llm import LLM

default_config: ConfigDict = {
    "duration":         [{"rounds": 4, "refinement_after": 2}],
    "language_config":  [{"DE": 1}],
    "group_config":     [{"blue": 1, "red": 1, "assassin": 2}],
    "word_count":       [4] 
}

# default_config: ConfigDict = {
#     "duration":         [{"rounds": 10, "refinement_after": 2}, {"rounds": 10, "refinement_after": 5}, {"rounds": 20, "refinement_after": 5}],
#     "language_config":  [{"DE": 5}, {"DE": 5, "EN": 5}],
#     "group_config":     [{"blue": 4, "red": 4, "assassin": 2}]
# }


def get_valid_combinations(config: ConfigDict) -> list[dict]:
    required_keys = ["duration", "language_config", "group_config", "word_count"]

    for key in required_keys:
        if key not in config or not isinstance(config[key], list) or not config[key]:
            print(f"CRITICAL: Missing or empty required config key: '{key}'. Aborting benchmark.")
            return []

    config_keys = list(config.keys())
    config_values = list(config.values())

    valid_combinations = []

    for combo in itertools.product(*config_values):
        run_kwargs = dict(zip(config_keys, combo))
        is_valid = True

        d       = run_kwargs["duration"]
        lang    = run_kwargs["language_config"]
        grp     = run_kwargs["group_config"]
        w_count = run_kwargs["word_count"]

        # 1. Validate Duration
        if "rounds" not in d or not isinstance(d["rounds"], int) or d["rounds"] <= 0:
            print(f"Skipped combo: Invalid duration config {d}")
            is_valid = False
        elif "refinement_after" in d and (
            not isinstance(d["refinement_after"], int) or d["refinement_after"] <= 0
        ):
            print(f"Skipped combo: Invalid refinement config in {d}")
            is_valid = False
            
        # 2. Validate Word Count
        elif not isinstance(w_count, int) or w_count <= 0:
            print(f"Skipped combo: Invalid word_count {w_count}")
            is_valid = False

        # 3. Validate Languages
        elif not lang or not all(
            isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in lang.items()
        ):
            print(f"Skipped combo: Invalid language config {lang}")
            is_valid = False

        # 4. Validate Groups
        elif "blue" not in grp or "red" not in grp or not all(
            isinstance(k, str) and isinstance(v, int) and v >= 0 for k, v in grp.items()
        ):
            print(f"Skipped combo: Invalid group config {grp}. Must have 'blue' and 'red'.")
            is_valid = False

        # DIVISIBILITY CHECKS REMOVED HERE!

        if is_valid:
            valid_combinations.append(run_kwargs)

    return valid_combinations


def calculate_result(results: list[dict]) -> float:
    """Composite benchmark score across all runs in a sweep, range [0, 1].

    Three components, each normalized to [0, 1]:

    Performance (weight 0.60)
        avg_final_score / blue_count_per_game
        Already encodes everything the model did right and wrong:
        +1 per blue guess, -1 per red, -25 per assassin. Dividing by the
        theoretical max (all blue words found, zero mistakes) gives a clean
        fraction. Clamped to 0 from below so a catastrophic assassin game
        doesn't drag the composite negative -- the win_rate already captures
        "did you lose".

    Speed (weight 0.20)
        1 - mean(rounds_played / rounds_allowed)
        1.0 = won on the first round, 0.0 = used every allowed turn (or
        timed out). Rewards efficient communication between codemaster and
        guesser; penalizes games that crawl to a win over many turns.

    Reliability (weight 0.20)
        1 - clamp(total_model_errors / total_turns_played, 0, 1)
        Counts every format error, rule error, clue failure, and guesser
        forfeit across all games and normalises by total rounds played.
        A model that formats its output correctly every time scores 1.0 here.
        This is intentionally a secondary signal -- a model that wins fast
        with a couple of format errors is still good.

    Why these weights:
        Performance is primary because it directly reflects game outcome.
        Speed and reliability matter for a production-quality model but
        shouldn't dominate -- a slow-but-accurate model beats a fast sloppy one.
    """
    if not results:
        return 0.0

    perf_scores, speed_scores, reliability_scores = [], [], []

    for run in results:
        agg        = run.get("aggregateStats", {})
        games      = run.get("games", [])
        blue_count = run.get("run_kwargs", {}).get("group_config", {}).get("blue", 1)

        # --- Performance ---
        raw_perf = agg.get("avg_final_score", 0) / blue_count
        perf_scores.append(max(0.0, min(1.0, raw_perf)))

        # --- Speed ---
        if games:
            speed_ratios = [
                g["stats"]["rounds_played"] / max(g["stats"]["rounds_total_allowed"], 1)
                for g in games if g.get("stats")
            ]
            speed_scores.append(1.0 - (sum(speed_ratios) / len(speed_ratios)) if speed_ratios else 0.0)
        else:
            speed_scores.append(0.0)

        # --- Reliability ---
        err          = agg.get("error_totals", {})
        total_errors = sum(err.values())
        total_rounds = sum(g["stats"].get("rounds_played", 0) for g in games if g.get("stats"))
        error_rate   = total_errors / max(total_rounds, 1)
        reliability_scores.append(max(0.0, 1.0 - error_rate))

    def mean(lst):
        return sum(lst) / len(lst) if lst else 0.0

    score = (
        0.60 * mean(perf_scores) +
        0.20 * mean(speed_scores) +
        0.20 * mean(reliability_scores)
    )

    return round(score, 4)


def run_benchmark(
    bench_config: dict,
    llm_model: Any,
    guesser_model: Any = None,
    custom_config: ConfigDict = None,
    benchmark_id: str = "bench",
) -> tuple[float, dict]:

    guesser_model = guesser_model or llm_model
    custom_config = custom_config or {}
    active_config = default_config | custom_config

    valid_combinations = get_valid_combinations(active_config)

    if not valid_combinations:
        print("No valid configurations found to run. Exiting early.")
        return 0.0, {"completed_runs": 0, "results": []}

    results = []

    # FIX: the previous version stored valid_combinations but then re-ran
    # itertools.product() in the loop, bypassing the validation entirely.
    # We now iterate directly over valid_combinations.
    for combo_index, run_kwargs in enumerate(valid_combinations, start=1):
        run_id = f"{benchmark_id}_{combo_index:02d}"

        print(f"Running Game {run_id} with: {run_kwargs}")

        game_instance = GameSet(
            llm=LLM(llm_model, {}, "Codemaster"),
            guesser=LLM(guesser_model, {}, "Guesser"),
            benchmarkID=run_id,
            **run_kwargs
        )

        game_result = game_instance.play()
        game_result["run_id"]     = run_id
        game_result["run_kwargs"] = run_kwargs
        results.append(game_result)

    score = calculate_result(results)

    return score, {"completed_runs": len(results), "results": results}