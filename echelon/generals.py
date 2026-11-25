"""A simple commander that selects only legal orders."""
import random
from collections import deque
from .engine import damage_at_distance, distance, legal_orders, living, score as battle_score
from .model import ARMIES, BattleState, Order, OrderType, Unit

class RandomGeneral:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def choose(self, state: BattleState) -> Order:
        orders = legal_orders(state)
        if not orders:
            raise ValueError("No orders available")
        weights = {OrderType.ATTACK: 8, OrderType.ADVANCE: 3,
                   OrderType.RETREAT: 1, OrderType.HOLD: 1}
        return self.rng.choices(orders, weights=[weights[o.kind] for o in orders])[0]


class HeuristicGeneral:
    """One-step tactical scores. Equal scores use legal-order list order."""

    def __init__(self):
        self.recent_cells: dict[str, deque[tuple[int, int]]] = {}

    @staticmethod
    def threat(unit: Unit, position: tuple[int, int], enemies: list[Unit]) -> int:
        """Most damage an enemy could deal on its next order from its current cell."""
        return max((damage_at_distance(enemy, distance(position, enemy))
                    for enemy in enemies if distance(position, enemy) <= enemy.attack_range),
                   default=0)

    def choose(self, state: BattleState) -> Order:
        orders = legal_orders(state)
        if not orders:
            raise ValueError("No orders available")
        by_id = {unit.id: unit for unit in state.units}
        enemy_army = ARMIES[1] if state.active_army == ARMIES[0] else ARMIES[0]
        enemies = living(state, enemy_army)
        allies = living(state, state.active_army)
        behind = battle_score(state, state.active_army) < battle_score(state, enemy_army)

        def value(order: Order) -> float:
            unit = by_id[order.unit_id]
            here = (unit.row, unit.column)
            current_threat = self.threat(unit, here, enemies)
            if order.kind == OrderType.HOLD:
                return -18.0 if behind else -2.0 if current_threat else 0.0

            if order.kind == OrderType.ATTACK:
                target = by_id[order.target]
                damage = damage_at_distance(unit, distance(unit, target))
                removes_target = damage >= target.health or target.morale - 8 * damage < 30
                remaining = [enemy for enemy in enemies if enemy.id != target.id or not removes_target]
                retaliation = self.threat(unit, here, remaining)
                score = 8 + 2 * min(damage, target.health)
                if removes_target:
                    score += 18
                if target.kind == "artillery":
                    score += 2
                if retaliation >= unit.health or unit.morale - 8 * retaliation < 30:
                    score -= 18  # likely to lose this formation next turn
                return score

            destination = order.target
            future_threat = self.threat(unit, destination, enemies)
            if order.kind == OrderType.RETREAT:
                # Retreat only when it materially improves immediate safety.
                if current_threat == 0 or future_threat >= current_threat:
                    return -20.0
                danger = current_threat >= unit.health or unit.morale - 8 * current_threat < 30
                if not danger:
                    return -10.0
                score = 14 + 3 * (current_threat - future_threat)
                if destination in self.recent_cells.get(unit.id, ()):
                    score -= 40  # do not spend every turn dodging the same threat
                if behind:
                    score -= 12 + (10 if state.completed_rounds >= 20 else 0)
                return score

            before = min(distance(here, enemy) for enemy in enemies)
            after = min(distance(destination, enemy) for enemy in enemies)
            in_own_range = any(distance(destination, enemy) <= unit.attack_range
                               for enemy in enemies)
            support = sum(distance(destination, ally) <= 2 for ally in allies if ally.id != unit.id)
            nearby_enemies = sum(distance(destination, enemy) <= 2 for enemy in enemies)
            score = 3 * (before - after) + (5 if in_own_range else 0)
            if behind:
                score += 8  # a losing army must seek contact before the clock expires
            score += 2 * support - 3 * max(0, nearby_enemies - support - 1)
            score -= 2 * future_threat
            if future_threat >= unit.health or unit.morale - 8 * future_threat < 30:
                score -= 12
            if unit.kind == "artillery" and after == 1:
                score -= 5  # preserve the artillery's range advantage
            if destination in self.recent_cells.get(unit.id, ()):
                score -= 12  # discourage moving back and forth without progress
            return float(score)

        choice = max(orders, key=value)
        if choice.kind in (OrderType.ADVANCE, OrderType.RETREAT):
            unit = by_id[choice.unit_id]
            self.recent_cells.setdefault(unit.id, deque(maxlen=4)).append((unit.row, unit.column))
        return choice
