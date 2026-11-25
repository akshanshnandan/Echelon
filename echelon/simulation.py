"""Run battles and format text reports."""
import random
from .engine import apply_order, living, new_battle, score
from .generals import RandomGeneral
from .model import ARMIES, BOARD_SIZE, BattleState

def run_battle(seed: int = 0, first_army: str = "Blue") -> BattleState:
    state = new_battle(first_army)
    generals = {army: RandomGeneral(random.Random(f"{seed}:{army}")) for army in ARMIES}
    while not state.finished:
        apply_order(state, generals[state.active_army].choose(state))
    return state

def run_batch(count: int = 100, seed: int = 0,
              first_army: str = "alternate") -> tuple[dict[str, int], list[BattleState]]:
    if count < 1 or first_army not in (*ARMIES, "alternate"):
        raise ValueError("Count must be positive and first army must be Blue, Red, or alternate")
    states = []
    for index in range(count):
        first = ARMIES[index % 2] if first_army == "alternate" else first_army
        states.append(run_battle(seed + index, first))
    results = {"Blue": 0, "Red": 0, "Draw": 0}
    for state in states:
        results[state.winner or "Draw"] += 1
    return results, states

def battlefield(state: BattleState) -> str:
    board = [[" . " for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    for unit in living(state):
        board[unit.row][unit.column] = f"{unit.army[0]}{unit.kind[0].upper()} "
    return "   " + "  ".join(str(c) for c in range(BOARD_SIZE)) + "\n" + "\n".join(
        f"{row}  " + "".join(cells) for row, cells in enumerate(board))

def summary(state: BattleState) -> str:
    lines = [f"Result: {state.winner or 'Draw'} ({state.reason}) after "
             f"{state.completed_rounds} full rounds, {len(state.history)} orders.",
             "Final formations:"]
    for unit in state.units:
        status = "destroyed" if unit.health == 0 else "routed" if unit.morale < 30 else "effective"
        lines.append(f"  {unit.army} {unit.kind}: health {unit.health}, "
                     f"morale {unit.morale}, {status}")
    lines.append("Tiebreak scores (formations, health, morale): "
                 f"Blue {score(state, 'Blue')}, Red {score(state, 'Red')}")
    return "\n".join(lines)
