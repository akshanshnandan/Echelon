"""Export four named commanders on one matched, replayable scenario."""
import argparse
import json
from pathlib import Path

import torch
from sb3_contrib import MaskablePPO

from .recording import record_battle, replay_battle
from .scenarios import DEV_BASE_SEED, SIDE_FIRST, scenario_seed


MODELS = (
    ("Untrained", "runs/first_25000/untrained.zip"),
    ("Phase 5", "runs/first_25000/train_final.zip"),
    ("Phase 6 selected", "runs/phase6_mixed_50000/checkpoints/model_76624_steps.zip"),
    ("HeuristicGeneral", "heuristic"),
)


def export_comparison(output: Path, deployment_index: int = 0,
                      assignment_index: int = 0, opponent: str = "heuristic",
                      root: Path = Path(".")) -> dict:
    if deployment_index < 0 or not 0 <= assignment_index < len(SIDE_FIRST):
        raise ValueError("Invalid deployment or assignment index")
    if opponent not in ("random", "heuristic"):
        raise ValueError("Opponent must be random or heuristic")
    torch.set_num_threads(1)
    seed = scenario_seed("dev", DEV_BASE_SEED, deployment_index)
    side, first = SIDE_FIRST[assignment_index]
    entries = []
    for label, model_path in MODELS:
        policy = ("heuristic" if model_path == "heuristic" else
                  MaskablePPO.load(root / model_path, device="cpu"))
        record = record_battle(policy, opponent, seed, side, first)
        replay_battle(record)  # Verify the export with the existing engine tool.
        entries.append({"label": label, "record": record})
    initial = entries[0]["record"]["initial"]
    if any(entry["record"]["initial"] != initial for entry in entries[1:]):
        raise RuntimeError("Comparison deployments do not match")
    bundle = {"scenario": {"split": "dev", "base_seed": DEV_BASE_SEED,
                           "deployment_index": deployment_index, "seed": seed,
                           "assignment_index": assignment_index,
                           "agent_army": side, "first_army": first,
                           "opponent": opponent},
              "recordings": entries}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"Saved four matched replays: {output}")
    return bundle


def main():
    parser = argparse.ArgumentParser(description="Export matched AI evolution replays")
    parser.add_argument("--output", type=Path, default=Path("runs/phase7_comparison.json"))
    parser.add_argument("--deployment-index", type=int, default=0)
    parser.add_argument("--assignment-index", type=int, default=0)
    parser.add_argument("--opponent", choices=("random", "heuristic"), default="heuristic")
    args = parser.parse_args()
    export_comparison(args.output, args.deployment_index, args.assignment_index,
                      args.opponent)


if __name__ == "__main__":
    main()
