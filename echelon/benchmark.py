"""Paired, reproducible evaluations of commander policies."""
import argparse
import random
from collections import Counter
from dataclasses import dataclass, field

from .engine import apply_order, legal_orders, living, new_battle
from .generals import HeuristicGeneral, RandomGeneral
from .model import OrderType


@dataclass
class CommanderStats:
    wins: int = 0
    losses: int = 0
    draws: int = 0
    decisive_wins: int = 0
    time_wins: int = 0
    health: int = 0
    morale: int = 0
    destroyed: int = 0
    routed: int = 0
    damage: int = 0
    actions: Counter = field(default_factory=Counter)
    attack_available: int = 0


@dataclass
class BenchmarkResult:
    a_name: str
    b_name: str
    battles: int
    a: CommanderStats = field(default_factory=CommanderStats)
    b: CommanderStats = field(default_factory=CommanderStats)
    rounds: int = 0
    orders: int = 0
    time_limits: int = 0


def game_schedule(battles: int, seed: int):
    """Four side/first-order combinations per seed; A and B each act first twice."""
    if battles < 4 or battles % 4:
        raise ValueError("Battle count must be a positive multiple of four")
    combinations = (("Blue", "Blue"), ("Red", "Red"),
                    ("Blue", "Red"), ("Red", "Blue"))
    for group in range(battles // 4):
        for a_army, first_army in combinations:
            yield seed + group, a_army, first_army


def make_general(name: str, seed: int, role: str):
    if name == "random":
        return RandomGeneral(random.Random(f"{seed}:{role}"))
    if name == "heuristic":
        return HeuristicGeneral()
    raise ValueError(f"Unknown commander: {name}")


def evaluate(a_name: str, b_name: str, battles: int = 500,
             seed: int = 42) -> BenchmarkResult:
    """Evaluate A against B with paired seeds, sides, and first turns."""
    if a_name not in ("random", "heuristic") or b_name not in ("random", "heuristic"):
        raise ValueError("Commander must be random or heuristic")
    result = BenchmarkResult(a_name, b_name, battles)
    for game_seed, a_army, first_army in game_schedule(battles, seed):
        b_army = "Red" if a_army == "Blue" else "Blue"
        state = new_battle(first_army)
        generals = {a_army: make_general(a_name, game_seed, "A"),
                    b_army: make_general(b_name, game_seed, "B")}
        stats = {a_army: result.a, b_army: result.b}
        while not state.finished:
            army = state.active_army
            orders = legal_orders(state)
            choice = generals[army].choose(state)
            own = stats[army]
            own.attack_available += any(o.kind == OrderType.ATTACK for o in orders)
            own.actions[choice.kind.value] += 1
            target = next((u for u in state.units if u.id == choice.target), None) if choice.kind == OrderType.ATTACK else None
            before_health = target.health if target else 0
            apply_order(state, choice)
            if target:
                own.damage += before_health - target.health
        result.rounds += state.completed_rounds
        result.orders += len(state.history)
        result.time_limits += state.reason == "time limit"
        for army, own in ((a_army, result.a), (b_army, result.b)):
            if state.winner == army:
                own.wins += 1
                if state.reason == "elimination":
                    own.decisive_wins += 1
                else:
                    own.time_wins += 1
            elif state.winner is None:
                own.draws += 1
            else:
                own.losses += 1
            effective = living(state, army)
            own.health += sum(u.health for u in effective)
            own.morale += sum(u.morale for u in effective)
            own.destroyed += sum(u.health == 0 for u in state.units if u.army == army)
            own.routed += sum(u.health > 0 and u.morale < 30 for u in state.units if u.army == army)
    return result


def format_result(result: BenchmarkResult) -> str:
    n = result.battles
    lines = [f"{result.a_name.title()} (A) vs {result.b_name.title()} (B) | {n} battles",
             f"Time limits: {result.time_limits} | Avg rounds: {result.rounds / n:.2f} | Avg orders: {result.orders / n:.2f}",
             f"{'Metric':<29}{'A':<22}B",
             "-" * 64]
    metrics = (
        ("Wins / losses / draws", lambda s: f"{s.wins} / {s.losses} / {s.draws}"),
        ("Win rate (draw = half)", lambda s: f"{100 * (s.wins + s.draws / 2) / n:.1f}%"),
        ("Decisive / time wins", lambda s: f"{s.decisive_wins} / {s.time_wins}"),
        ("Avg remaining health", lambda s: f"{s.health / n:.2f}"),
        ("Avg remaining morale", lambda s: f"{s.morale / n:.2f}"),
        ("Avg destroyed / routed", lambda s: f"{s.destroyed / n:.2f} / {s.routed / n:.2f}"),
        ("Avg damage dealt", lambda s: f"{s.damage / n:.2f}"),
        ("Attack opportunities used", lambda s: f"{s.actions['ATTACK']} / {s.attack_available}"),
    )
    for label, display in metrics:
        lines.append(f"{label:<29}{display(result.a):<22}{display(result.b)}")
    lines.append("Orders (count and share):")
    for kind in OrderType:
        def frequency(stats: CommanderStats) -> str:
            count = stats.actions[kind.value]
            total = sum(stats.actions.values())
            return f"{count} ({100 * count / total:.1f}%)"
        lines.append(f"  {kind.value:<27}{frequency(result.a):<22}{frequency(result.b)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paired Echelon commander benchmark")
    parser.add_argument("--battles", type=int, default=500,
                        help="positive multiple of four; default 500")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--matchup", choices=("all", "random-random", "heuristic-random",
                                               "heuristic-heuristic"), default="all")
    args = parser.parse_args()
    matchups = (("random", "random"), ("heuristic", "random"),
                ("heuristic", "heuristic"))
    print("Paired seeds: four side/first-turn combinations per seed; A and B have separate seed streams.")
    for a, b in matchups:
        if args.matchup in ("all", f"{a}-{b}"):
            print("\n" + format_result(evaluate(a, b, args.battles, args.seed)))


if __name__ == "__main__":
    main()
