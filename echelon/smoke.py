"""Run complete masked episodes without learning a policy."""
import argparse
import random

import numpy as np

from .env import EchelonEnv


def run_smoke(episodes: int = 100, seed: int = 42, opponent: str = "both",
              deployment: str = "random") -> dict[str, dict[str, int]]:
    if episodes < 1 or opponent not in ("both", "random", "heuristic"):
        raise ValueError("episodes must be positive; opponent must be both, random, or heuristic")
    results = {name: {"episodes": 0, "wins": 0, "losses": 0, "draws": 0,
                      "decisive": 0, "time_limits": 0, "decisions": 0}
               for name in (("random", "heuristic") if opponent == "both" else (opponent,))}
    action_rng = random.Random(seed)
    env = EchelonEnv(deployment=deployment)
    for index in range(episodes):
        name = ("random", "heuristic")[index % 2] if opponent == "both" else opponent
        agent_army = ("Blue", "Red")[(index // 2) % 2]
        first_army = ("Blue", "Red")[(index // 4) % 2]
        _, _ = env.reset(seed=seed + index, options={"agent_army": agent_army,
                                                       "first_army": first_army,
                                                       "opponent": name})
        row = results[name]
        row["episodes"] += 1
        done = False
        while not done:
            valid = np.flatnonzero(env.action_masks())
            if len(valid) == 0:
                raise RuntimeError("Nonterminal state has no legal actions")
            action = int(valid[action_rng.randrange(len(valid))])
            _, reward, terminated, truncated, info = env.step(action)
            row["decisions"] += 1
            done = terminated or truncated
        row["wins" if reward > 0 else "losses" if reward < 0 else "draws"] += 1
        row["decisive" if info["reason"] == "elimination" else "time_limits"] += 1
    env.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Masked random-action Echelon smoke test")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--opponent", choices=("both", "random", "heuristic"), default="both")
    parser.add_argument("--deployment", choices=("fixed", "random"), default="random")
    args = parser.parse_args()
    rows = run_smoke(args.episodes, args.seed, args.opponent, args.deployment)
    print(f"Masked legal-action smoke test: {args.episodes} episodes, seed {args.seed}, {args.deployment} deployment")
    print(f"{'Opponent':<12}{'Games':>7}{'W':>7}{'L':>7}{'D':>7}{'Decisive':>12}{'Time':>8}{'Avg decisions':>16}")
    for name, row in rows.items():
        print(f"{name:<12}{row['episodes']:>7}{row['wins']:>7}{row['losses']:>7}{row['draws']:>7}"
              f"{row['decisive']:>12}{row['time_limits']:>8}{row['decisions'] / row['episodes']:>16.2f}")


if __name__ == "__main__":
    main()
