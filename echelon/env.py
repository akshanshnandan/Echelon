"""Gymnasium wrapper around the unchanged Echelon battle engine."""
import random
from copy import deepcopy
from typing import Callable

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .deployment import randomize_deployment
from .engine import STATS, apply_order, legal_orders, new_battle
from .generals import HeuristicGeneral, RandomGeneral
from .model import ARMIES, BOARD_SIZE, MAX_ROUNDS, BattleState, Order, OrderType


KINDS = ("infantry", "cavalry", "artillery")
CELLS = BOARD_SIZE * BOARD_SIZE
SLOTS_PER_UNIT = 1 + CELLS + CELLS + len(KINDS)  # hold, advance, retreat, attack
ACTION_COUNT = len(KINDS) * SLOTS_PER_UNIT       # 396
UNIT_FEATURES = 10
OBSERVATION_SIZE = 6 * UNIT_FEATURES + 3


class EchelonEnv(gym.Env):
    """One agent order and any opponent response form one environment step."""

    metadata = {"render_modes": []}

    def __init__(self, agent_army: str = "Blue", opponent: str = "random",
                 first_army: str = "Blue", deployment: str = "fixed"):
        super().__init__()
        self._defaults = {"agent_army": agent_army, "opponent": opponent,
                          "first_army": first_army, "deployment": deployment}
        self.agent_army = agent_army
        self.opponent_name = opponent
        self.first_army = first_army
        self.deployment = deployment
        self._validate_settings()
        self.action_space = spaces.Discrete(ACTION_COUNT)
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(OBSERVATION_SIZE,), dtype=np.float32)
        self.state: BattleState | None = None
        self._opponent: RandomGeneral | HeuristicGeneral | None = None
        # Optional observer receives each engine transition, including an
        # opponent order made during reset. Normal play pays no copy cost.
        self.order_observer: Callable | None = None

    def _validate_settings(self) -> None:
        if self.agent_army not in ARMIES or self.first_army not in ARMIES:
            raise ValueError("agent_army and first_army must be Blue or Red")
        if self.opponent_name not in ("random", "heuristic"):
            raise ValueError("opponent must be random or heuristic")
        if self.deployment not in ("fixed", "random"):
            raise ValueError("deployment must be fixed or random")

    def _army_units(self, army: str):
        if self.state is None:
            raise RuntimeError("Call reset() before encoding orders or observations")
        return [next(u for u in self.state.units if u.army == army and u.kind == kind)
                for kind in KINDS]

    def encode_order(self, order: Order) -> int:
        """Stable index for an agent-side order, whether legal in this state or not."""
        own = self._army_units(self.agent_army)
        enemy_army = ARMIES[1] if self.agent_army == ARMIES[0] else ARMIES[0]
        enemies = self._army_units(enemy_army)
        unit_slot = next(i for i, u in enumerate(own) if u.id == order.unit_id)
        base = unit_slot * SLOTS_PER_UNIT
        if order.kind == OrderType.HOLD:
            return base
        if order.kind in (OrderType.ADVANCE, OrderType.RETREAT):
            row, col = order.target
            if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
                raise ValueError(f"Destination is outside the board: {order.target}")
            if self.agent_army == "Red":
                row = BOARD_SIZE - 1 - row
            cell = row * BOARD_SIZE + col
            offset = 1 if order.kind == OrderType.ADVANCE else 1 + CELLS
            return base + offset + cell
        if order.kind == OrderType.ATTACK:
            target_slot = next(i for i, u in enumerate(enemies) if u.id == order.target)
            return base + 1 + 2 * CELLS + target_slot
        raise ValueError(f"Unknown order type: {order.kind}")

    def decode_action(self, action: int) -> Order:
        """Decode an in-space index; legality is checked separately by the mask."""
        if not self.action_space.contains(action):
            raise ValueError(f"Action is outside Discrete({ACTION_COUNT}): {action}")
        unit_slot, slot = divmod(int(action), SLOTS_PER_UNIT)
        unit_id = self._army_units(self.agent_army)[unit_slot].id
        if slot == 0:
            return Order(unit_id, OrderType.HOLD)
        if slot <= CELLS:
            cell = slot - 1
            row, col = divmod(cell, BOARD_SIZE)
            if self.agent_army == "Red":
                row = BOARD_SIZE - 1 - row
            return Order(unit_id, OrderType.ADVANCE, (row, col))
        if slot <= 2 * CELLS:
            cell = slot - 1 - CELLS
            row, col = divmod(cell, BOARD_SIZE)
            if self.agent_army == "Red":
                row = BOARD_SIZE - 1 - row
            return Order(unit_id, OrderType.RETREAT, (row, col))
        enemy_army = ARMIES[1] if self.agent_army == ARMIES[0] else ARMIES[0]
        target_slot = slot - 1 - 2 * CELLS
        target_id = self._army_units(enemy_army)[target_slot].id
        return Order(unit_id, OrderType.ATTACK, target_id)

    def action_masks(self) -> np.ndarray:
        """True exactly for indexes produced by engine.legal_orders()."""
        mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
        if self.state is not None and not self.state.finished:
            for order in legal_orders(self.state):
                mask[self.encode_order(order)] = True
        return mask

    def _observation(self) -> np.ndarray:
        enemy_army = ARMIES[1] if self.agent_army == ARMIES[0] else ARMIES[0]
        values = []
        for unit in self._army_units(self.agent_army) + self._army_units(enemy_army):
            row = unit.row if self.agent_army == "Blue" else BOARD_SIZE - 1 - unit.row
            kind = [float(unit.kind == name) for name in KINDS]
            destroyed = unit.health == 0
            routed = unit.health > 0 and unit.morale < 30
            values.extend((row / (BOARD_SIZE - 1), unit.column / (BOARD_SIZE - 1),
                           *kind, unit.health / STATS[unit.kind][0], unit.morale / 100,
                           float(unit.effective), float(routed), float(destroyed)))
        values.extend((self.state.completed_rounds / MAX_ROUNDS,
                       float(self.first_army == self.agent_army),
                       float(not self.state.finished)))
        return np.asarray(values, dtype=np.float32)

    def _info(self, **extra) -> dict:
        return {"agent_army": self.agent_army, "first_army": self.first_army,
                "opponent": self.opponent_name, "deployment": self.deployment,
                "winner": self.state.winner, "reason": self.state.reason,
                "completed_rounds": self.state.completed_rounds, **extra}

    def _play_opponent(self) -> list[str]:
        events = []
        while not self.state.finished and self.state.active_army != self.agent_army:
            events.append(self._apply(self._opponent.choose(self.state)))
        return events

    def _apply(self, order: Order) -> str:
        before = deepcopy(self.state) if self.order_observer else None
        legal_count = len(legal_orders(self.state)) if self.order_observer else 0
        message = apply_order(self.state, order)
        if self.order_observer:
            self.order_observer(before, order, legal_count, self.state, message)
        return message

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        options = options or {}
        if options.keys() - self._defaults.keys():
            raise ValueError(f"Unknown reset options: {options.keys() - self._defaults.keys()}")
        settings = {**self._defaults, **options}
        self.agent_army = settings["agent_army"]
        self.first_army = settings["first_army"]
        self.opponent_name = settings["opponent"]
        self.deployment = settings["deployment"]
        self._validate_settings()
        # Always draw two sub-seeds so a deployment option does not shift the
        # opponent's random stream within the same episode seed.
        deployment_seed = int(self.np_random.integers(0, 2**63))
        opponent_seed = int(self.np_random.integers(0, 2**63))
        self.state = new_battle(self.first_army)
        if self.deployment == "random":
            randomize_deployment(self.state, random.Random(deployment_seed))
        self._opponent = (RandomGeneral(random.Random(opponent_seed))
                          if self.opponent_name == "random" else HeuristicGeneral())
        opponent_orders = self._play_opponent()
        return self._observation(), self._info(opponent_orders=opponent_orders)

    def step(self, action: int):
        if self.state is None:
            raise RuntimeError("Call reset() before step()")
        if self.state.finished:
            raise RuntimeError("Episode finished; call reset() before step()")
        mask = self.action_masks()
        if not self.action_space.contains(action) or not mask[int(action)]:
            return self._observation(), 0.0, False, False, self._info(invalid_action=True)
        order = self.decode_action(action)
        agent_event = self._apply(order)
        opponent_orders = self._play_opponent()
        reward = (1.0 if self.state.winner == self.agent_army else
                  -1.0 if self.state.winner is not None else 0.0) if self.state.finished else 0.0
        return (self._observation(), reward, self.state.finished, False,
                self._info(invalid_action=False, agent_order=agent_event,
                           opponent_orders=opponent_orders))
