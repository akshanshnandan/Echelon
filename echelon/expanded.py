"""Expanded battles: variable rosters and a strength-based time-limit score.

Classic's pure movement, range, and damage helpers are reused unchanged.
"""
import random
from dataclasses import dataclass, field
from fractions import Fraction

from .drafting import RULES, DraftRules, validate
from .engine import STATS, damage_at_distance, distance, legal_orders, living
from .model import ARMIES, BOARD_SIZE, MAX_ROUNDS, BattleState, Order, OrderType, Unit


@dataclass
class ExpandedState(BattleState):
    rosters: dict[str, tuple[str, ...]] = field(default_factory=dict)
    rules: DraftRules = RULES


def new_battle(blue, red, seed=42, first_army="Blue", rules=RULES):
    if first_army not in ARMIES:
        raise ValueError("First army must be Blue or Red")
    rosters = {"Blue": validate(tuple(blue), rules),
               "Red": validate(tuple(red), rules)}
    rng = random.Random(seed)
    units = []
    for army in ARMIES:
        cells = [(row, col) for row in ((0, 1) if army == "Blue" else (7, 6))
                 for col in range(BOARD_SIZE)]
        for index, (kind, (row, col)) in enumerate(
                zip(rosters[army], rng.sample(cells, len(rosters[army]))), 1):
            health, movement, power, attack_range = STATS[kind]
            units.append(Unit(f"{army[0]}-{kind[0].upper()}{index}", army, kind,
                              row, col, health, 100, movement, power, attack_range))
    return ExpandedState(units, first_army, first_army, rosters=rosters, rules=rules)


def strength(state, army):
    """Gold-weighted surviving HP and morale. Routed formations contribute zero."""
    total = Fraction(0)
    for unit in living(state, army):
        gold = state.rules.costs[unit.kind][0]
        maximum = STATS[unit.kind][0]
        total += Fraction(gold * unit.health * unit.morale, maximum * 100)
    return total


def apply_order(state, order):
    """The Classic order effects with an Expanded-only terminal tiebreak."""
    if not isinstance(state, ExpandedState):
        raise TypeError("Expanded orders require an ExpandedState")
    if order not in legal_orders(state):
        raise ValueError(f"Illegal order: {order}")
    unit = next(u for u in state.units if u.id == order.unit_id)
    if order.kind == OrderType.HOLD:
        message = f"{unit.army} {unit.kind} holds"
    elif order.kind in (OrderType.ADVANCE, OrderType.RETREAT):
        unit.row, unit.column = order.target
        if order.kind == OrderType.RETREAT:
            unit.morale = min(100, unit.morale + 5)
        message = f"{unit.army} {unit.kind} {order.kind.value.lower()}s to {order.target}"
    else:
        target = next(u for u in state.units if u.id == order.target)
        damage = damage_at_distance(unit, distance(unit, target))
        target.health = max(0, target.health - damage)
        target.morale = max(0, target.morale - 8 * damage)
        outcome = " destroyed" if target.health == 0 else " routed" if target.morale < 30 else ""
        message = f"{unit.army} {unit.kind} attacks {target.army} {target.kind} for {damage} damage{outcome}"
    state.history.append(message)

    blue, red = living(state, "Blue"), living(state, "Red")
    if not blue or not red:
        state.finished = True
        state.winner = "Blue" if blue else "Red" if red else None
        state.reason = "elimination"
    else:
        second = ARMIES[1] if state.first_army == ARMIES[0] else ARMIES[0]
        if state.active_army == second:
            state.completed_rounds += 1
        if state.completed_rounds >= MAX_ROUNDS:
            state.finished = True
            b, r = strength(state, "Blue"), strength(state, "Red")
            state.winner = "Blue" if b > r else "Red" if r > b else None
            state.reason = "time limit"
        else:
            state.active_army = ARMIES[1] if state.active_army == ARMIES[0] else ARMIES[0]
    return message
