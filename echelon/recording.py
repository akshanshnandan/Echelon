"""Record exact engine orders and verify them by replaying the battle."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .engine import apply_order, legal_orders, new_battle, score
from .generals import HeuristicGeneral
from .model import Order, OrderType
from .scenarios import SIDE_FIRST, scenario_seed
from .simulation import battlefield, summary


def units_snapshot(state):
    return {u.id: {"army": u.army, "kind": u.kind, "position": [u.row, u.column],
                   "health": u.health, "morale": u.morale, "effective": u.effective}
            for u in state.units}


def state_snapshot(state):
    return {"units": units_snapshot(state), "active_army": state.active_army,
            "completed_rounds": state.completed_rounds, "finished": state.finished,
            "winner": state.winner, "reason": state.reason}


def decision_record(before, order, after, message, legal_count=None):
    """One engine transition in the Phase 6/7 replay JSON format."""
    old, new = state_snapshot(before), state_snapshot(after)
    available_orders = legal_orders(before)
    available = [{"unit": o.unit_id, "action": o.kind.value,
                  "target": list(o.target) if isinstance(o.target, tuple) else o.target}
                 for o in available_orders]
    damage = sum(max(0, old["units"][name]["health"] - new["units"][name]["health"])
                 for name in old["units"])
    casualties = [name for name in old["units"] if old["units"][name]["effective"]
                  and not new["units"][name]["effective"]]
    return {"round": before.completed_rounds + 1,
            "army": before.active_army, "unit": order.unit_id,
            "unit_type": old["units"][order.unit_id]["kind"],
            "action": order.kind.value,
            "target": list(order.target) if isinstance(order.target, tuple) else order.target,
            "legal_count": len(available_orders) if legal_count is None else legal_count,
            "legal_orders": available,
            "attack_opportunities": sum(o.kind == OrderType.ATTACK for o in available_orders),
            "before": old, "after": new, "damage": damage,
            "casualties": casualties, "message": message}


def record_battle(policy, opponent: str, seed: int, side: str, first: str,
                  deployment: str = "random") -> dict:
    """Policy is a loaded MaskablePPO model or a fresh HeuristicGeneral."""
    import numpy as np
    from .env import EchelonEnv
    env = EchelonEnv(opponent=opponent, deployment=deployment)
    decisions = []
    initial = None

    def observe(before, order, legal_count, after, message):
        nonlocal initial
        old = state_snapshot(before)
        if initial is None:
            initial = old
        decisions.append(decision_record(before, order, after, message, legal_count))

    env.order_observer = observe
    observation, _ = env.reset(seed=seed, options={"agent_army": side, "first_army": first})
    if initial is None:
        initial = state_snapshot(env.state)
    agent_heuristic = HeuristicGeneral() if policy == "heuristic" else None
    invalid = 0
    while not env.state.finished:
        mask = env.action_masks()
        if not mask.any():
            raise RuntimeError("No legal agent order")
        if agent_heuristic:
            action = env.encode_order(agent_heuristic.choose(env.state))
        else:
            action, _ = policy.predict(observation, action_masks=mask, deterministic=True)
            action = int(np.asarray(action).item())
        if not env.action_space.contains(action) or not mask[action]:
            invalid += 1
            raise RuntimeError("Policy chose an illegal masked action")
        observation, _, _, _, info = env.step(action)
        if info["invalid_action"]:
            invalid += 1
    outcome = "win" if env.state.winner == side else "draw" if env.state.winner is None else "loss"
    record = {"seed": seed, "agent_army": side, "first_army": first,
              "opponent": opponent, "deployment": deployment,
              "initial": initial, "decisions": decisions,
              "final": state_snapshot(env.state), "outcome": outcome,
              "classification": "decisive" if env.state.reason == "elimination" else "tiebreak",
              "blue_score": score(env.state, "Blue"), "red_score": score(env.state, "Red"),
              "invalid_actions": invalid}
    env.close()
    return record


def replay_battle(record: dict) -> str:
    """Apply recorded orders independently and compare every transition."""
    state = new_battle(record["first_army"])
    for unit in state.units:
        old = record["initial"]["units"][unit.id]
        unit.row, unit.column = old["position"]
    if state_snapshot(state) != record["initial"]:
        raise ValueError("Initial state does not match a fresh battle")
    lines = ["Initial battlefield:", battlefield(state)]
    for index, step in enumerate(record["decisions"]):
        if state_snapshot(state) != step["before"]:
            raise ValueError(f"Recorded pre-order state differs at {index}: "
                             f"{state_snapshot(state)} != {step['before']}")
        target = step["target"]
        if isinstance(target, list):
            target = tuple(target)
        order = Order(step["unit"], OrderType(step["action"]), target)
        if len(legal_orders(state)) != step["legal_count"]:
            raise ValueError("Recorded legal-action count differs")
        message = apply_order(state, order)
        if state_snapshot(state) != step["after"] or message != step["message"]:
            raise ValueError("Recorded order outcome differs")
        lines.append(f"Round {step['round']:>2} {step['army']:<4}: {message} "
                     f"[legal {step['legal_count']}, damage {step['damage']}]")
    if state_snapshot(state) != record["final"]:
        raise ValueError("Recorded final state differs")
    lines.extend(("Final battlefield:", battlefield(state), summary(state)))
    return "\n".join(lines)


def summarize(records: list[dict]) -> dict:
    """Aggregate observable tactics. An opportunity means any legal ATTACK."""
    actions = Counter()
    by_type = defaultdict(Counter)
    opportunities = taken = damage_dealt = damage_received = 0
    first_engagement = []
    repeated_hold_retreat = 0
    positions = defaultdict(list)
    survival = morale = 0
    destroyed = routed = 0
    results = Counter()
    tiebreak_dimensions = Counter()
    for record in records:
        results[(record["classification"], record["outcome"])] += 1
        if record["classification"] == "tiebreak":
            own = record["blue_score"] if record["agent_army"] == "Blue" else record["red_score"]
            other = record["red_score"] if record["agent_army"] == "Blue" else record["blue_score"]
            component = next((name for name, a, b in zip(
                ("effective_units", "health", "morale"), own, other) if a != b), "exact_draw")
            tiebreak_dimensions[(record["outcome"], component)] += 1
        previous = None
        first_damage = None
        for step in record["decisions"]:
            if step["damage"] and first_damage is None:
                first_damage = step["round"]
            if step["army"] != record["agent_army"]:
                damage_received += step["damage"]
                continue
            actions[step["action"]] += 1
            by_type[step["unit_type"]][step["action"]] += 1
            opportunities += bool(step["attack_opportunities"])
            taken += step["action"] == "ATTACK" and bool(step["attack_opportunities"])
            damage_dealt += step["damage"]
            if previous == step["action"] and previous in ("HOLD", "RETREAT"):
                repeated_hold_retreat += 1
            previous = step["action"]
            row = step["after"]["units"][step["unit"]]["position"][0]
            positions[step["unit_type"]].append(
                row if record["agent_army"] == "Blue" else 7 - row)
        first_engagement.append(first_damage if first_damage is not None else 31)
        for unit in record["final"]["units"].values():
            if unit["army"] == record["agent_army"]:
                survival += unit["effective"]
                morale += unit["morale"]
                destroyed += unit["health"] == 0
                routed += unit["health"] > 0 and unit["morale"] < 30
    n = len(records)
    return {"battles": n, "results": {f"{k[0]}_{k[1]}": v for k, v in results.items()},
            "tiebreak_deciding_components":
                {f"{k[0]}_{k[1]}": v for k, v in tiebreak_dimensions.items()},
            "actions": dict(actions), "actions_by_unit_type": {k: dict(v) for k, v in by_type.items()},
            "attack_opportunities": opportunities, "attacks_taken": taken,
            "attack_take_rate": taken / opportunities if opportunities else 0,
            "damage_dealt_per_battle": damage_dealt / n,
            "damage_received_per_battle": damage_received / n,
            "round_before_first_damage": sum(first_engagement) / n,
            "repeat_hold_retreat": repeated_hold_retreat,
            "effective_units_at_end": survival / n, "unit_morale_at_end": morale / (3 * n),
            "destroyed_units_at_end": destroyed / n,
            "routed_units_at_end": routed / n,
            "mean_distance_from_home_row_by_type":
                {k: sum(v) / len(v) for k, v in positions.items()}}


def main():
    from sb3_contrib import MaskablePPO
    parser = argparse.ArgumentParser(description="Record, analyze, and replay masked battles")
    parser.add_argument("--models", nargs="+",
                        help="Model .zip paths or 'heuristic'")
    parser.add_argument("--replay-json", type=Path,
                        help="Print one verified replay from a saved battles JSON file")
    parser.add_argument("--battle-index", type=int, default=0)
    parser.add_argument("--opponent", choices=("random", "heuristic"), default="heuristic")
    parser.add_argument("--deployment-seeds", type=int, default=25)
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.replay_json:
        records = json.loads(args.replay_json.read_text(encoding="utf-8"))
        print(replay_battle(records[args.battle_index]))
        return
    if not args.models or args.output is None:
        parser.error("--models and --output are required when recording battles")
    import torch
    torch.set_num_threads(1)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {}
    for item in args.models:
        policy = item if item == "heuristic" else MaskablePPO.load(item, device="cpu")
        label = "heuristic" if item == "heuristic" else Path(item).stem
        records = [record_battle(policy, args.opponent, scenario_seed("dev", args.seed, i),
                                 side, first)
                   for i in range(args.deployment_seeds) for side, first in SIDE_FIRST]
        for record in records:
            replay_battle(record)
        (args.output / f"{label}_battles.json").write_text(
            json.dumps(records, indent=2), encoding="utf-8")
        (args.output / f"{label}_replay.txt").write_text(
            replay_battle(records[0]), encoding="utf-8")
        report[label] = summarize(records)
        print(f"{label}: {json.dumps(report[label])}")
    (args.output / "analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
