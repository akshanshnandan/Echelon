"""The unchanged Phase 4 observation and 396-action encoding, for any army."""
import numpy as np

from .engine import STATS, legal_orders
from .model import ARMIES, BOARD_SIZE, MAX_ROUNDS, BattleState, Order, OrderType


KINDS = ("infantry", "cavalry", "artillery")
CELLS = BOARD_SIZE * BOARD_SIZE
SLOTS_PER_UNIT = 1 + CELLS + CELLS + len(KINDS)
ACTION_COUNT = len(KINDS) * SLOTS_PER_UNIT
UNIT_FEATURES = 10
OBSERVATION_SIZE = 6 * UNIT_FEATURES + 3


def army_units(state: BattleState, army: str):
    return [next(u for u in state.units if u.army == army and u.kind == kind)
            for kind in KINDS]


def encode_order(state: BattleState, army: str, order: Order) -> int:
    """Convert an order to the same stable index used in Phase 4."""
    own = army_units(state, army)
    enemy = ARMIES[1] if army == ARMIES[0] else ARMIES[0]
    enemies = army_units(state, enemy)
    unit_slot = next(i for i, u in enumerate(own) if u.id == order.unit_id)
    base = unit_slot * SLOTS_PER_UNIT
    if order.kind == OrderType.HOLD:
        return base
    if order.kind in (OrderType.ADVANCE, OrderType.RETREAT):
        row, col = order.target
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            raise ValueError(f"Destination is outside the board: {order.target}")
        if army == "Red":
            row = BOARD_SIZE - 1 - row
        cell = row * BOARD_SIZE + col
        offset = 1 if order.kind == OrderType.ADVANCE else 1 + CELLS
        return base + offset + cell
    if order.kind == OrderType.ATTACK:
        target_slot = next(i for i, u in enumerate(enemies) if u.id == order.target)
        return base + 1 + 2 * CELLS + target_slot
    raise ValueError(f"Unknown order type: {order.kind}")


def decode_action(state: BattleState, army: str, action: int) -> Order:
    """Decode an in-space index; the caller checks legality with action_masks."""
    if not isinstance(action, (int, np.integer)) or not 0 <= action < ACTION_COUNT:
        raise ValueError(f"Action is outside Discrete({ACTION_COUNT}): {action}")
    unit_slot, slot = divmod(int(action), SLOTS_PER_UNIT)
    unit_id = army_units(state, army)[unit_slot].id
    if slot == 0:
        return Order(unit_id, OrderType.HOLD)
    if slot <= CELLS:
        cell = slot - 1
        row, col = divmod(cell, BOARD_SIZE)
        if army == "Red":
            row = BOARD_SIZE - 1 - row
        return Order(unit_id, OrderType.ADVANCE, (row, col))
    if slot <= 2 * CELLS:
        cell = slot - 1 - CELLS
        row, col = divmod(cell, BOARD_SIZE)
        if army == "Red":
            row = BOARD_SIZE - 1 - row
        return Order(unit_id, OrderType.RETREAT, (row, col))
    enemy = ARMIES[1] if army == ARMIES[0] else ARMIES[0]
    target_slot = slot - 1 - 2 * CELLS
    target_id = army_units(state, enemy)[target_slot].id
    return Order(unit_id, OrderType.ATTACK, target_id)


def action_masks(state: BattleState, army: str) -> np.ndarray:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    if not state.finished:
        for order in legal_orders(state):
            mask[encode_order(state, army, order)] = True
    return mask


def observation(state: BattleState, army: str, first_army: str) -> np.ndarray:
    enemy = ARMIES[1] if army == ARMIES[0] else ARMIES[0]
    values = []
    for unit in army_units(state, army) + army_units(state, enemy):
        row = unit.row if army == "Blue" else BOARD_SIZE - 1 - unit.row
        kind = [float(unit.kind == name) for name in KINDS]
        destroyed = unit.health == 0
        routed = unit.health > 0 and unit.morale < 30
        values.extend((row / (BOARD_SIZE - 1), unit.column / (BOARD_SIZE - 1),
                       *kind, unit.health / STATS[unit.kind][0], unit.morale / 100,
                       float(unit.effective), float(routed), float(destroyed)))
    values.extend((state.completed_rounds / MAX_ROUNDS,
                   float(first_army == army), float(not state.finished)))
    return np.asarray(values, dtype=np.float32)
