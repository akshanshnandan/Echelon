"""Plain battle data. Positions are zero-based (row, column)."""
from dataclasses import dataclass, field
from enum import Enum

BOARD_SIZE = 8
MAX_ROUNDS = 30
ARMIES = ("Blue", "Red")

class OrderType(str, Enum):
    HOLD = "HOLD"
    ADVANCE = "ADVANCE"
    ATTACK = "ATTACK"
    RETREAT = "RETREAT"

@dataclass(frozen=True)
class Order:
    unit_id: str
    kind: OrderType
    target: tuple[int, int] | str | None = None

@dataclass
class Unit:
    id: str
    army: str
    kind: str
    row: int
    column: int
    health: int
    morale: int
    movement: int
    attack_power: int
    attack_range: int

    @property
    def effective(self) -> bool:
        return self.health > 0 and self.morale >= 30

@dataclass
class BattleState:
    units: list[Unit]
    active_army: str
    first_army: str
    completed_rounds: int = 0
    finished: bool = False
    winner: str | None = None
    reason: str | None = None
    history: list[str] = field(default_factory=list)
