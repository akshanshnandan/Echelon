"""Seeded Command matchups; writes compact, reproducible JSON to stdout."""
import json
from collections import Counter
from itertools import product

from echelon.command_engine import CommandBattle as LegacyBattle, Formation, STATS
from echelon.command_engine_v4 import CommandBattle
from echelon.command_general import CommandGeneral as LegacyGeneral
from echelon.command_general_v4 import CommandGeneral

COMPOSITIONS = {
    "balanced": ("infantry", "infantry", "cavalry", "artillery"),
    "artillery": ("artillery",) * 3,
    "infantry": ("infantry",) * 3,
    "cavalry": ("cavalry",) * 3,
}


def run(version, blue, red, seed):
    if version == 3:
        # Legacy constructor mirrors its roster; give Red independent kinds solely
        # for a controlled diagnostic. The saved v3 engine remains untouched.
        battle = LegacyBattle(seed, roster=blue)
        for index in range(len(red) + 1, len(blue) + 1):
            del battle.units[f"R{index}"]
        for index in range(len(blue) + 1, len(red) + 1):
            battle.units[f"R{index}"] = Formation(f"R{index}", "Red", red[index - 1], 1055, index * 800 / (len(red) + 1), 3.141592653589793, STATS[red[index - 1]][0])
        for index, kind in enumerate(red, 1):
            battle.units[f"R{index}"].kind = kind
            battle.units[f"R{index}"].health = STATS[kind][0]
        general_type = LegacyGeneral
    else:
        battle = CommandBattle(seed, roster=blue, enemy_roster=red)
        general_type = CommandGeneral
    generals = (general_type("Blue"), general_type("Red"))
    while not battle.finished:
        for general in generals:
            general.decide(battle)
        battle.step()
    return {"winner": battle.winner, "ticks": battle.tick,
            "routed": sum(e["type"] == "routed" for e in battle.events),
            "reason": battle.reason}


def tournament(version, seeds=range(6)):
    results = {}
    for blue, red in product(COMPOSITIONS, repeat=2):
        games = [run(version, COMPOSITIONS[blue], COMPOSITIONS[red], seed) for seed in seeds]
        results[f"{blue}_vs_{red}"] = {
            "blue": sum(g["winner"] == "Blue" for g in games),
            "red": sum(g["winner"] == "Red" for g in games),
            "draw": sum(g["winner"] is None for g in games),
            "mean_seconds": round(sum(g["ticks"] for g in games) / len(games) / 10, 1),
            "mean_routings": round(sum(g["routed"] for g in games) / len(games), 1),
            "terminations": dict(Counter(g["reason"] for g in games)),
        }
    return results


if __name__ == "__main__":
    print(json.dumps({"seeds": list(range(6)), "compositions": COMPOSITIONS,
                      "legacy_diagnostic": tournament(3), "version_4": tournament(4)}, indent=2))
