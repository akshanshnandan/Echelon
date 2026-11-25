"""Deterministic battle rules, independent of commander strategy."""
from collections import deque
from .model import ARMIES, BOARD_SIZE, MAX_ROUNDS, BattleState, Order, OrderType, Unit

STATS = {"infantry": (12, 1, 4, 1), "cavalry": (10, 2, 5, 1), "artillery": (8, 1, 5, 3)}

def new_battle(first_army: str = "Blue") -> BattleState:
    if first_army not in ARMIES:
        raise ValueError("First army must be Blue or Red")
    units = []
    for army, row in (("Blue", 0), ("Red", BOARD_SIZE - 1)):
        for kind, col in (("infantry", 1), ("cavalry", 3), ("artillery", 5)):
            hp, movement, power, attack_range = STATS[kind]
            units.append(Unit(f"{army[0]}-{kind[0].upper()}", army, kind, row, col,
                              hp, 100, movement, power, attack_range))
    return BattleState(units, first_army, first_army)

def distance(a: Unit | tuple[int, int], b: Unit | tuple[int, int]) -> int:
    ar, ac = (a.row, a.column) if isinstance(a, Unit) else a
    br, bc = (b.row, b.column) if isinstance(b, Unit) else b
    return abs(ar - br) + abs(ac - bc)

def living(state: BattleState, army: str | None = None) -> list[Unit]:
    return [u for u in state.units if u.effective and (army is None or u.army == army)]

def reachable(state: BattleState, unit: Unit) -> list[tuple[int, int]]:
    """Empty cells reachable through orthogonal empty cells."""
    blocked = {(u.row, u.column) for u in living(state) if u.id != unit.id}
    start = (unit.row, unit.column)
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        (row, col), steps = queue.popleft()
        if steps == unit.movement:
            continue
        for cell in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            r, c = cell
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and cell not in blocked and cell not in seen:
                seen.add(cell)
                queue.append((cell, steps + 1))
    return sorted(seen - {start})

def legal_orders(state: BattleState) -> list[Order]:
    if state.finished:
        return []
    orders = []
    enemy_army = ARMIES[1] if state.active_army == ARMIES[0] else ARMIES[0]
    enemies = living(state, enemy_army)
    for unit in living(state, state.active_army):
        orders.append(Order(unit.id, OrderType.HOLD))
        if enemies:
            nearest = min(distance(unit, enemy) for enemy in enemies)
            for cell in reachable(state, unit):
                new_distance = min(distance(cell, enemy) for enemy in enemies)
                if new_distance < nearest:
                    orders.append(Order(unit.id, OrderType.ADVANCE, cell))
                elif new_distance > nearest:
                    orders.append(Order(unit.id, OrderType.RETREAT, cell))
            for enemy in enemies:
                if distance(unit, enemy) <= unit.attack_range:
                    orders.append(Order(unit.id, OrderType.ATTACK, enemy.id))
    return orders

def score(state: BattleState, army: str) -> tuple[int, int, int]:
    """Compare effective formations, then their total health, then morale."""
    units = living(state, army)
    return len(units), sum(u.health for u in units), sum(u.morale for u in units)

def damage_at_distance(attacker: Unit, distance_to_target: int) -> int:
    """Deterministic damage for an in-range attack at the given distance."""
    damage = max(1, attacker.attack_power - (100 - attacker.morale) // 20)
    if distance_to_target == 1:
        if attacker.kind == "cavalry":
            damage += 2
        elif attacker.kind == "artillery":
            damage = max(1, damage - 2)
    return damage

def apply_order(state: BattleState, order: Order) -> str:
    """Apply one legal order and advance the turn; reject illegal orders."""
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
            b, r = score(state, "Blue"), score(state, "Red")
            state.winner = "Blue" if b > r else "Red" if r > b else None
            state.reason = "time limit"
        else:
            state.active_army = ARMIES[1] if state.active_army == ARMIES[0] else ARMIES[0]
    return message
