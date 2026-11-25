"""Evaluate saved MaskablePPO models on identical held-out scenarios."""
import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from .env import EchelonEnv
from .scenarios import SIDE_FIRST, scenario_seed


@dataclass
class Results:
    episodes: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    decisive_wins: int = 0
    decisive_losses: int = 0
    time_wins: int = 0
    time_losses: int = 0
    time_draws: int = 0
    decisions: int = 0
    invalid_actions: int = 0
    total_rounds: int = 0
    actions: dict[str, int] = field(default_factory=dict)
    by_side: dict[str, dict[str, int]] = field(default_factory=dict)
    by_seed: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return (self.wins + self.draws / 2) / self.episodes

    @property
    def average_length(self) -> float:
        return self.decisions / self.episodes

    @property
    def average_rounds(self) -> float:
        return self.total_rounds / self.episodes


def test_situations(episodes_per_opponent: int, seed: int, split: str = "eval"):
    """Same seeds and four side/first combinations for every model/opponent."""
    if episodes_per_opponent < 4 or episodes_per_opponent % 4:
        raise ValueError("episodes_per_opponent must be a positive multiple of four")
    for group in range(episodes_per_opponent // 4):
        game_seed = scenario_seed(split, seed, group)
        for side, first in SIDE_FIRST:
            yield game_seed, side, first


def evaluate_model(model: MaskablePPO, opponent: str, situations,
                   deployment: str = "random") -> Results:
    results = Results()
    env = EchelonEnv(opponent=opponent, deployment=deployment)
    for game_seed, side, first in situations:
        observation, _ = env.reset(seed=game_seed,
            options={"agent_army": side, "first_army": first})
        results.episodes += 1
        seed_row = results.by_seed.setdefault(str(game_seed),
            {"wins": 0, "losses": 0, "draws": 0, "rounds": 0, "episodes": 0,
             "decisive_wins": 0, "decisive_losses": 0, "time_wins": 0,
             "time_losses": 0, "time_draws": 0})
        side_row = results.by_side.setdefault(side,
            {"wins": 0, "losses": 0, "draws": 0, "episodes": 0})
        episode_decisions = 0
        while True:
            mask = env.action_masks()
            if not mask.any():
                raise RuntimeError("No legal action in an ongoing battle")
            action, _ = model.predict(observation, action_masks=mask, deterministic=True)
            action = int(np.asarray(action).item())
            valid_choice = env.action_space.contains(action) and bool(mask[action])
            if not valid_choice:
                results.invalid_actions += 1
            else:
                kind = env.decode_action(action).kind.value
                results.actions[kind] = results.actions.get(kind, 0) + 1
            observation, reward, terminated, truncated, info = env.step(action)
            if info.get("invalid_action", False) and valid_choice:
                results.invalid_actions += 1
            results.decisions += 1
            episode_decisions += 1
            if episode_decisions > 60:
                raise RuntimeError("Evaluation stalled, likely from invalid actions")
            if terminated or truncated:
                if truncated:
                    raise RuntimeError("Unexpected truncated battle")
                outcome = "wins" if reward > 0 else "losses" if reward < 0 else "draws"
                setattr(results, outcome, getattr(results, outcome) + 1)
                seed_row[outcome] += 1
                side_row[outcome] += 1
                seed_row["episodes"] += 1
                side_row["episodes"] += 1
                seed_row["rounds"] += info["completed_rounds"]
                results.total_rounds += info["completed_rounds"]
                if info["reason"] == "elimination":
                    if outcome != "draws":
                        name = "decisive_wins" if outcome == "wins" else "decisive_losses"
                        setattr(results, name, getattr(results, name) + 1)
                        seed_row[name] += 1
                else:
                    name = "time_wins" if outcome == "wins" else "time_losses" if outcome == "losses" else "time_draws"
                    setattr(results, name, getattr(results, name) + 1)
                    seed_row[name] += 1
                break
    env.close()
    return results


def evaluate_paths(paths: list[Path], episodes_per_opponent: int = 100,
                   seed: int = 2026, deployment: str = "random",
                   split: str = "eval") -> dict[str, dict[str, Results]]:
    torch.set_num_threads(1)
    situations = list(test_situations(episodes_per_opponent, seed, split))
    reports = {}
    for path in paths:
        path = Path(path)
        model = MaskablePPO.load(path, device="cpu")
        label = f"{path.parent.name}/{path.stem}"
        reports[label] = {}
        for opponent in ("random", "heuristic"):
            reports[label][opponent] = evaluate_model(model, opponent, situations, deployment)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Mask-aware held-out model evaluation")
    parser.add_argument("--models", nargs="+", type=Path, required=True)
    parser.add_argument("--episodes-per-opponent", type=int, default=100)
    parser.add_argument("--deployment-seeds", type=int,
                        help="Distinct maps per opponent, each with four mirrored games")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--split", choices=("eval", "dev"), default="eval")
    parser.add_argument("--deployment", choices=("fixed", "random"), default="random")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    episodes = (4 * args.deployment_seeds if args.deployment_seeds is not None
                else args.episodes_per_opponent)
    reports = evaluate_paths(args.models, episodes,
                             args.seed, args.deployment, args.split)
    label_width = max(28, max(len(label) for label in reports) + 2)
    print(f"{args.split} seed base {args.seed}; {episodes // 4} deployments, {episodes} paired episodes "
          f"per opponent; deployment {args.deployment}")
    print(f"{'Model':<{label_width}}{'Opponent':<12}{'W/L/D':<15}{'Win rate':>9}"
          f"{'Dec W/L':>11}{'Time W/L/D':>14}{'Avg len':>10}{'Rounds':>8}{'Invalid':>9}")
    for label, opponents in reports.items():
        for opponent, row in opponents.items():
            print(f"{label:<{label_width}}{opponent:<12}{f'{row.wins}/{row.losses}/{row.draws}':<15}"
                  f"{row.win_rate:>8.1%}{f'{row.decisive_wins}/{row.decisive_losses}':>11}"
                  f"{f'{row.time_wins}/{row.time_losses}/{row.time_draws}':>14}"
                  f"{row.average_length:>10.2f}{row.average_rounds:>8.2f}{row.invalid_actions:>9}")
            print(f"  Blue {row.by_side['Blue']['wins']}/{row.by_side['Blue']['losses']}/{row.by_side['Blue']['draws']}"
                  f" | Red {row.by_side['Red']['wins']}/{row.by_side['Red']['losses']}/{row.by_side['Red']['draws']}"
                  f" | actions {row.actions}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seed": args.seed, "split": args.split,
                   "deployment_seeds": episodes // 4, "episodes_per_opponent": episodes,
                   "deployment": args.deployment,
                   "models": {label: {name: {**asdict(row),
                                                  "score": row.win_rate,
                                                  "average_rounds": row.average_rounds,
                                                  "average_decisions": row.average_length}
                                      for name, row in opponents.items()}
                              for label, opponents in reports.items()}}
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
