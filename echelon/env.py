"""Gymnasium wrapper around the unchanged Echelon battle engine."""
import random
from copy import deepcopy
from typing import Callable

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from . import encoding
from .deployment import randomize_deployment
from .engine import apply_order, legal_orders, new_battle
from .generals import HeuristicGeneral, RandomGeneral
from .model import ARMIES, BattleState, Order


KINDS = encoding.KINDS
CELLS = encoding.CELLS
SLOTS_PER_UNIT = encoding.SLOTS_PER_UNIT
ACTION_COUNT = encoding.ACTION_COUNT
UNIT_FEATURES = encoding.UNIT_FEATURES
OBSERVATION_SIZE = encoding.OBSERVATION_SIZE


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
        return encoding.army_units(self.state, army)

    def encode_order(self, order: Order) -> int:
        """Stable index for an agent-side order, whether legal in this state or not."""
        if self.state is None:
            raise RuntimeError("Call reset() before encoding orders")
        return encoding.encode_order(self.state, self.agent_army, order)

    def decode_action(self, action: int) -> Order:
        """Decode an in-space index; legality is checked separately by the mask."""
        if not self.action_space.contains(action):
            raise ValueError(f"Action is outside Discrete({ACTION_COUNT}): {action}")
        if self.state is None:
            raise RuntimeError("Call reset() before decoding actions")
        return encoding.decode_action(self.state, self.agent_army, int(action))

    def action_masks(self) -> np.ndarray:
        """True exactly for indexes produced by engine.legal_orders()."""
        return (np.zeros(ACTION_COUNT, dtype=np.bool_) if self.state is None else
                encoding.action_masks(self.state, self.agent_army))

    def _observation(self) -> np.ndarray:
        if self.state is None:
            raise RuntimeError("Call reset() before encoding orders or observations")
        return encoding.observation(self.state, self.agent_army, self.first_army)

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
