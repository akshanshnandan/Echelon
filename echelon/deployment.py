"""Optional mirrored starting positions; battle rules remain in engine.py."""
import random

from .model import BOARD_SIZE, BattleState


def randomize_deployment(state: BattleState, rng: random.Random) -> None:
    """Place Blue in rows 0-1 and mirror each formation into Red rows 7-6."""
    blue_cells = [(row, col) for row in (0, 1) for col in range(BOARD_SIZE)]
    for kind, (row, col) in zip(("infantry", "cavalry", "artillery"),
                                rng.sample(blue_cells, 3)):
        blue = next(u for u in state.units if u.army == "Blue" and u.kind == kind)
        red = next(u for u in state.units if u.army == "Red" and u.kind == kind)
        blue.row, blue.column = row, col
        red.row, red.column = BOARD_SIZE - 1 - row, col
