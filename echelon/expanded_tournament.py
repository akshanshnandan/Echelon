"""Paired, seeded AI doctrine comparisons for the Expanded ruleset."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from .doctrines import WEIGHTS, draft
from .drafting import resources
from .expanded_game import ai_battle


def tournament(battles_per_pair=100, seed=9000):
    if battles_per_pair <= 0 or battles_per_pair % 4:
        raise ValueError("Battles per pair must be a positive multiple of four")
    names = tuple(WEIGHTS)
    rows = []
    for left_index, left in enumerate(names):
        for right in names[left_index + 1:]:
            for scenario in range(battles_per_pair // 4):
                battle_seed = seed + scenario
                drafts = {name: draft(name, f"{battle_seed}:draft:{name}")
                          for name in (left, right)}
                for blue in (left, right):
                    red = right if blue == left else left
                    for first in ("Blue", "Red"):
                        record = ai_battle(drafts[blue], drafts[red], battle_seed, first)
                        rows.append({"left": left, "right": right,
                                     "seed": battle_seed, "blue": blue, "red": red,
                                     "first": first, "winner": record["final"]["winner"],
                                     "reason": record["final"]["reason"],
                                     "blue_roster": drafts[blue], "red_roster": drafts[red],
                                     "blue_gold": resources(drafts[blue])[0],
                                     "red_gold": resources(drafts[red])[0],
                                     "blue_strength": record["blue_strength"],
                                     "red_strength": record["red_strength"]})
    return rows


def summary(rows):
    groups = defaultdict(list)
    for row in rows:
        for side in ("Blue", "Red"):
            doctrine = row[side.lower()]
            opponent = row["red" if side == "Blue" else "blue"]
            groups[(doctrine, "all")].append((row, side))
            groups[(doctrine, opponent)].append((row, side))
            groups[(doctrine, side)].append((row, side))
    result = {}
    for (doctrine, group), games in sorted(groups.items()):
        wins = sum(row["winner"] == side for row, side in games)
        losses = sum(row["winner"] not in (side, None) for row, side in games)
        draws = len(games) - wins - losses
        result[f"{doctrine} / {group}"] = {
            "battles": len(games), "wins": wins, "losses": losses, "draws": draws,
            "score": round((wins + draws / 2) / len(games), 3),
            "decisive_wins": sum(row["winner"] == side and row["reason"] == "elimination"
                                   for row, side in games),
            "time_limit_wins": sum(row["winner"] == side and row["reason"] == "time limit"
                                     for row, side in games),
            "avg_gold_spent": round(sum(row[f"{side.lower()}_gold"] for row, side in games)
                                    / len(games)),
            "avg_remaining_strength": round(sum(row[f"{side.lower()}_strength"]
                                               for row, side in games) / len(games)),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description="Expanded doctrine tournament")
    parser.add_argument("--battles-per-pair", type=int, default=100)
    parser.add_argument("--seed", type=int, default=9000)
    parser.add_argument("--output", type=Path, default=Path("runs/phase9_tournament.json"))
    args = parser.parse_args()
    rows = tournament(args.battles_per_pair, args.seed)
    report = {"seed": args.seed, "battles_per_pair": args.battles_per_pair,
              "results": summary(rows), "battles": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Doctrine / group          N    W    L    D  Score   Dec  Time  Gold  Strength")
    for name, values in report["results"].items():
        print(f"{name:<24} {values['battles']:>3} {values['wins']:>4} "
              f"{values['losses']:>4} {values['draws']:>4} "
              f"{values['score']:>6.1%} {values['decisive_wins']:>5} "
              f"{values['time_limit_wins']:>5} {values['avg_gold_spent']:>5} "
              f"{values['avg_remaining_strength']:>8}")
    print(f"Saved {len(rows)} battles to {args.output}")


if __name__ == "__main__":
    main()
