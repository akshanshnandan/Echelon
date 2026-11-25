"""A roster-agnostic tactical commander for Expanded battles."""
from .engine import damage_at_distance, distance, legal_orders, living
from .expanded import strength
from .model import ARMIES, OrderType


class ExpandedGeneral:
    def choose(self, state):
        orders = legal_orders(state)
        if not orders:
            raise ValueError("No legal orders")
        units = {u.id: u for u in state.units}
        enemy_army = "Red" if state.active_army == "Blue" else "Blue"
        enemies = living(state, enemy_army)
        behind = strength(state, state.active_army) < strength(state, enemy_army)

        def value(order):
            unit = units[order.unit_id]
            if order.kind == OrderType.ATTACK:
                target = units[order.target]
                damage = damage_at_distance(unit, distance(unit, target))
                removed = damage >= target.health or target.morale - 8 * damage < 30
                return 12 + 3 * min(damage, target.health) + (20 if removed else 0)
            if order.kind == OrderType.HOLD:
                return -8 if behind else 0
            here = min(distance(unit, foe) for foe in enemies)
            there = min(distance(order.target, foe) for foe in enemies)
            threat = max((damage_at_distance(foe, distance(order.target, foe))
                          for foe in enemies if distance(order.target, foe) <= foe.attack_range),
                         default=0)
            if order.kind == OrderType.ADVANCE:
                return (4 * (here - there) + (7 if there <= unit.attack_range else 0)
                        + (5 if behind else 0) - 2 * threat
                        - (20 if threat >= unit.health else 0))
            current_threat = max((damage_at_distance(foe, distance(unit, foe))
                                  for foe in enemies if distance(unit, foe) <= foe.attack_range),
                                 default=0)
            return (12 if current_threat >= unit.health and threat < current_threat
                    else -20)

        return max(orders, key=value)
