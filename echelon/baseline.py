"""Paired diagnostic: uniform masked choices versus weighted RandomGeneral."""
import argparse
import random
from collections import Counter

import numpy as np

from .engine import legal_orders
from .env import EchelonEnv
from .generals import RandomGeneral


ASSIGNMENTS = (("Blue", "Blue"), ("Red", "Red"),
               ("Blue", "Red"), ("Red", "Blue"))


def compare(episodes: int = 500, seed: int = 10_000) -> dict:
    """Use the same 4 side/first assignments for each scenario seed."""
    if episodes < 4 or episodes % 4:
        raise ValueError("episodes must be a positive multiple of four")
    results = {}
    for deployment in ("fixed", "random"):
        for policy in ("uniform", "weighted"):
            totals = Counter()
            by_assignment = {assignment: Counter() for assignment in ASSIGNMENTS}
            layouts = set()
            env = EchelonEnv(opponent="random", deployment=deployment)
            for group in range(episodes // 4):
                game_seed = seed + group
                for agent_army, first_army in ASSIGNMENTS:
                    observation, info = env.reset(seed=game_seed,
                        options={"agent_army": agent_army, "first_army": first_army})
                    # Only count before the first order; otherwise the
                    # opponent's opening move looks like a new deployment.
                    if first_army == agent_army:
                        layouts.add(tuple((u.row, u.column) for u in env.state.units))
                    assert env.state.active_army == agent_army
                    assert len(env.state.history) == int(first_army != agent_army)
                    chooser = RandomGeneral(random.Random(f"{game_seed}:agent"))
                    uniform_rng = random.Random(f"{game_seed}:agent")
                    while not env.state.finished:
                        assert env.observation_space.contains(observation)
                        legal = legal_orders(env.state)
                        mask = env.action_masks()
                        assert set(np.flatnonzero(mask)) == {env.encode_order(o) for o in legal}
                        if policy == "uniform":
                            valid = np.flatnonzero(mask)
                            action = int(valid[uniform_rng.randrange(len(valid))])
                        else:
                            action = env.encode_order(chooser.choose(env.state))
                        order = env.decode_action(action)
                        totals[order.kind.value] += 1
                        totals["attack_available"] += any(o.kind.value == "ATTACK" for o in legal)
                        before = len(env.state.history)
                        observation, reward, terminated, truncated, info = env.step(action)
                        assert not info["invalid_action"] and not truncated
                        assert len(env.state.history) in (before + 1, before + 2)
                        assert terminated == env.state.finished
                        if not terminated:
                            assert env.state.active_army == agent_army and reward == 0
                        totals["decisions"] += 1
                    expected = 1 if info["winner"] == agent_army else -1 if info["winner"] else 0
                    assert reward == expected
                    outcome = "win" if expected == 1 else "loss" if expected == -1 else "draw"
                    totals[outcome] += 1
                    by_assignment[(agent_army, first_army)][outcome] += 1
                    totals["time_limit"] += info["reason"] == "time limit"
                    totals["rounds"] += info["completed_rounds"]
            env.close()
            totals["layouts"] = len(layouts)
            results[(deployment, policy)] = (totals, by_assignment)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose masked uniform and weighted random baselines")
    parser.add_argument("--episodes", type=int, default=500,
                        help="episodes per policy and deployment; multiple of four")
    parser.add_argument("--seed", type=int, default=10_000)
    args = parser.parse_args()
    print(f"Paired baseline: {args.episodes} episodes per row, seeds {args.seed}.."
          f"{args.seed + args.episodes // 4 - 1}")
    for (deployment, policy), (total, assignments) in compare(args.episodes, args.seed).items():
        played = total["win"] + total["loss"] + total["draw"]
        print(f"\n{deployment:<6} {policy:<8} W/L/D {total['win']}/{total['loss']}/{total['draw']} "
              f"win rate {(total['win'] + total['draw'] / 2) / played:.1%} "
              f"time limits {total['time_limit']} avg rounds {total['rounds'] / played:.1f} "
              f"layouts {total['layouts']}")
        print("  actions:", " ".join(f"{kind}={total[kind]}" for kind in
              ("HOLD", "ADVANCE", "ATTACK", "RETREAT")),
              f"attack opportunities={total['attack_available']}")
        for (side, first), row in assignments.items():
            print(f"  {side:<4} first={first:<4}: {row['win']}/{row['loss']}/{row['draw']}")


if __name__ == "__main__":
    main()
