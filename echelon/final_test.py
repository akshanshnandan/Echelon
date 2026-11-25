"""One locked comparison on the reserved Phase 7 final-test deployments."""
import argparse
import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path

from .evaluate import evaluate_paths
from .scenarios import FINAL_TEST_BASE_SEED, scenario_seed


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_selection(manifest: dict, root: Path) -> dict:
    """Check the frozen choice, seed partition, and locally recorded seed use."""
    if (manifest["final_seed_split"] != "final" or
            manifest["final_seed_base"] != FINAL_TEST_BASE_SEED or
            manifest["deployment_indices"] != "0..99" or
            manifest["assignments_per_seed"] != 4 or
            manifest["opponents"] != ["random", "heuristic"]):
        raise ValueError("Final-test plan differs from the frozen selection")
    for name in ("selected", "reference"):
        path = root / manifest[f"{name}_model"]
        if file_sha256(path) != manifest[f"{name}_sha256"]:
            raise ValueError(f"{name} checkpoint differs from the frozen file")
    final_seeds = {scenario_seed("final", FINAL_TEST_BASE_SEED, i) for i in range(100)}
    if len(final_seeds) != 100:
        raise ValueError("Final-test deployment seeds are not distinct")
    if min(final_seeds) < 1 << 65:
        raise ValueError("Final-test seeds escaped their reserved range")
    previous = set()
    for run in ("runs/first_25000/run.json", "runs/phase6_mixed_50000/run.json"):
        previous.update(json.loads((root / run).read_text(encoding="utf-8"))["training_seeds"])
    previous.update(scenario_seed("eval", 2026, i) for i in range(25))
    previous.update(scenario_seed("dev", 2027, i) for i in range(100))
    if final_seeds & previous:
        raise ValueError("Final-test seeds overlap recorded earlier experiments")
    return {"final_deployments": len(final_seeds),
            "historical_seeds_checked": len(previous),
            "disjoint_from_recorded_training_and_evaluation": True}


def paired_difference(reference: dict, selected: dict) -> dict:
    """Resample deployment groups, keeping each group of four games together."""
    old, new = reference["by_seed"], selected["by_seed"]
    if set(old) != set(new):
        raise ValueError("Models were not evaluated on matching deployments")
    changes = [(new[seed]["wins"] + new[seed]["draws"] / 2
                - old[seed]["wins"] - old[seed]["draws"] / 2) / 4
               for seed in sorted(old)]
    rng = random.Random(7)
    samples = sorted(sum(rng.choices(changes, k=len(changes))) / len(changes)
                     for _ in range(10_000))
    return {"score_difference": sum(changes) / len(changes),
            "deployment_groups": len(changes),
            "groups_better": sum(x > 0 for x in changes),
            "groups_equal": sum(x == 0 for x in changes),
            "groups_worse": sum(x < 0 for x in changes),
            "paired_bootstrap_95": [samples[250], samples[9750]]}


def run_final_test(root: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output = root / manifest["planned_output"]
    if output.exists():
        raise FileExistsError(f"Final-test report already exists: {output}")
    verification = verify_selection(manifest, root)
    paths = [root / manifest["reference_model"], root / manifest["selected_model"]]
    reports = evaluate_paths(paths, episodes_per_opponent=400,
                             seed=FINAL_TEST_BASE_SEED, deployment="random", split="final")
    labels = list(reports)
    rows = {name: {opponent: {**asdict(row), "score": row.win_rate,
                               "average_rounds": row.average_rounds}
                   for opponent, row in opponents.items()}
            for name, opponents in reports.items()}
    comparison = {opponent: paired_difference(rows[labels[0]][opponent],
                                               rows[labels[1]][opponent])
                  for opponent in manifest["opponents"]}
    result = {"frozen_selection": manifest, "verification": verification,
              "models": rows, "paired_comparison": comparison,
              "interpretation_rule": "Report once; do not use these results to select another checkpoint."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for opponent in manifest["opponents"]:
        a, b = rows[labels[0]][opponent], rows[labels[1]][opponent]
        diff = comparison[opponent]
        print(f"{opponent}: original {a['wins']}/{a['losses']}/{a['draws']} "
              f"({a['score']:.1%}), selected {b['wins']}/{b['losses']}/{b['draws']} "
              f"({b['score']:.1%}), paired difference {diff['score_difference']:+.1%}, "
              f"95% interval {diff['paired_bootstrap_95']}")
    print(f"Frozen final-test report: {output}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run the one frozen Phase 7 final test")
    parser.add_argument("--manifest", type=Path, default=Path("docs/phase7_selection.json"))
    args = parser.parse_args()
    run_final_test(Path.cwd(), args.manifest)


if __name__ == "__main__":
    main()
