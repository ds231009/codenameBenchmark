import itertools
from typing import Any

from ustp_ccl_benchmark.game_set import GameSet
from ustp_ccl_benchmark.config_dict import ConfigDict
from ustp_ccl_benchmark.llm import LLM

# Master on/off switch for the detailed live-output log (results/live/{benchmarkID}.json --
# all boards plus every individual codemaster/guesser/refinement LLM call with
# its prompt and response). Flip to False to skip recording/writing it, e.g.
# for large sweeps where you only care about the final aggregated results.
# Can also be overridden per-call via run_benchmark(..., enable_live_output=...).
ENABLE_LIVE_OUTPUT = True

default_config: ConfigDict = {
    "duration":         [{"total_games": 4, "refinement_after": 2}],
    "language_config":  [{"DE": 1}],
    "group_config":     [{"blue": 1, "red": 1, "assassin": 2}],
    "word_count":       [10],
    # Secondary, non-iterated combos to run alongside the sweep above. Each
    # entry is a complete run_kwargs dict, e.g.:
    #   {"duration": {"total_games": 4}, "language_config": {"EN": 1},
    #    "group_config": {"blue": 1, "red": 1, "assassin": 2}, "word_count": 10}
    "direct_config":    [],
}

# default_config: ConfigDict = {
#     "duration":         [{"total_games": 10, "refinement_after": 2}, {"rounds": 10, "refinement_after": 5}, {"rounds": 20, "refinement_after": 5}],
#     "language_config":  [{"DE": 5}, {"DE": 5, "EN": 5}],
#     "group_config":     [{"blue": 4, "red": 4, "assassin": 2}]
# }


def _validate_run_kwargs(run_kwargs: dict) -> bool:
    """Applies the same per-combo rule checks (duration/word_count/language/
    group) to a single fully-formed run_kwargs dict, regardless of whether it
    came from the itertools.product sweep or from a direct_config entry.
    Prints a "Skipped combo" message and returns False on the first failure."""
    d       = run_kwargs.get("duration")
    lang    = run_kwargs.get("language_config")
    grp     = run_kwargs.get("group_config")
    w_count = run_kwargs.get("word_count")

    # 1. Validate Duration
    if not isinstance(d, dict) or "total_games" not in d or not isinstance(d["total_games"], int) or d["total_games"] <= 0:
        print(f"Skipped combo: Invalid duration config {d}")
        return False
    if "refinement_after" in d and (
        not isinstance(d["refinement_after"], int) or d["refinement_after"] <= 0
    ):
        print(f"Skipped combo: Invalid refinement config in {d}")
        return False

    # 2. Validate Word Count
    if not isinstance(w_count, int) or w_count <= 0:
        print(f"Skipped combo: Invalid word_count {w_count}")
        return False

    # 3. Validate Languages
    if not isinstance(lang, dict) or not lang or not all(
        isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in lang.items()
    ):
        print(f"Skipped combo: Invalid language config {lang}")
        return False

    # 4. Validate Groups
    if not isinstance(grp, dict) or "blue" not in grp or "red" not in grp or not all(
        isinstance(k, str) and isinstance(v, int) and v >= 0 for k, v in grp.items()
    ):
        print(f"Skipped combo: Invalid group config {grp}. Must have 'blue' and 'red'.")
        return False

    # DIVISIBILITY CHECKS REMOVED HERE!

    return True


def get_valid_combinations(config: ConfigDict) -> list[dict]:
    required_keys = ["duration", "language_config", "group_config", "word_count"]

    for key in required_keys:
        if key not in config or not isinstance(config[key], list) or not config[key]:
            print(f"CRITICAL: Missing or empty required config key: '{key}'. Aborting benchmark.")
            return []

    # Only these four keys feed the itertools.product sweep. direct_config is
    # a separate, non-iterated list of already-complete run_kwargs dicts and
    # must NOT be treated as another axis of the product.
    sweep_keys = ["duration", "language_config", "group_config", "word_count"]
    config_values = [config[key] for key in sweep_keys]

    valid_combinations = []

    for combo in itertools.product(*config_values):
        run_kwargs = dict(zip(sweep_keys, combo))
        if _validate_run_kwargs(run_kwargs):
            valid_combinations.append(run_kwargs)

    # Secondary, non-iterated path: explicit run_kwargs dicts to run as-is,
    # mixed in alongside the sweep combinations above. Defaults to [] so this
    # is fully opt-in and doesn't change behavior for existing configs.
    for direct_run_kwargs in config.get("direct_config", []) or []:
        if not isinstance(direct_run_kwargs, dict):
            print(f"Skipped direct_config entry: not a dict: {direct_run_kwargs}")
            continue
        if not all(k in direct_run_kwargs for k in required_keys):
            print(f"Skipped direct_config entry: missing required key(s): {direct_run_kwargs}")
            continue
        if _validate_run_kwargs(direct_run_kwargs):
            valid_combinations.append(direct_run_kwargs)

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
    enable_live_output: bool = ENABLE_LIVE_OUTPUT,
) -> tuple[float, dict]:

    guesser_model = guesser_model or llm_model
    custom_config = custom_config or {}
    active_config = default_config | custom_config

    valid_combinations = get_valid_combinations(active_config)

    if not valid_combinations:
        print("No valid configurations found to run. Exiting early.")
        return 0.0, {"completed_runs": 0, "results": []}

    # 1. Calculate and log the total valid combinations
    total_runs = len(valid_combinations)
    print(f"\n=== BENCHMARK SETUP ===")
    print(f"Found {total_runs} valid combinations to run.")
    print(f"Live output logging: {'ON' if enable_live_output else 'OFF'}")
    print(f"=======================\n")

    results = []

    for combo_index, run_kwargs in enumerate(valid_combinations, start=1):
        run_id = f"{benchmark_id}_{combo_index:02d}"

        # 2. Update the print statement to show progress out of the total
        print(f"Running Game {combo_index}/{total_runs} (ID: {run_id}) with: {run_kwargs}")

        game_instance = GameSet(
            llm=LLM(llm_model, {}, "Codemaster"),
            guesser=LLM(guesser_model, {}, "Guesser"),
            benchmarkID=run_id,
            enable_live_output=enable_live_output,
            **run_kwargs
        )

        game_result = game_instance.play()
        game_result["run_id"]     = run_id
        game_result["run_kwargs"] = run_kwargs
        results.append(game_result)

    score = calculate_result(results)

    print(f"\n=== BENCHMARK COMPLETE ===")
    print(f"Successfully ran {total_runs} configurations. Final Score: {score}")

    return score, {"completed_runs": len(results), "results": results}