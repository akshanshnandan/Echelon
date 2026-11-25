"""Read-only MaskablePPO commander for the unchanged battle engine."""
from pathlib import Path

import numpy as np

from .encoding import ACTION_COUNT, OBSERVATION_SIZE, action_masks, decode_action, observation
from .engine import legal_orders
from .model import ARMIES, BattleState, Order


class PPOGeneral:
    """Choose an engine order using the exact Phase 4 observation/action codec."""

    def __init__(self, checkpoint: Path, army: str, deterministic: bool = True):
        if army not in ARMIES:
            raise ValueError("PPO army must be Blue or Red")
        self.checkpoint = Path(checkpoint)
        if not self.checkpoint.is_file():
            raise FileNotFoundError(f"Trained model checkpoint not found: {self.checkpoint}")
        from gymnasium import spaces
        from sb3_contrib import MaskablePPO
        try:
            self.model = MaskablePPO.load(self.checkpoint, device="cpu")
        except Exception as exc:
            raise ValueError(f"Could not load MaskablePPO checkpoint {self.checkpoint}: {exc}") from exc
        obs = self.model.observation_space
        actions = self.model.action_space
        if (not isinstance(obs, spaces.Box) or obs.shape != (OBSERVATION_SIZE,)
                or obs.dtype != np.float32
                or not np.all(obs.low == 0.0) or not np.all(obs.high == 1.0)
                or not isinstance(actions, spaces.Discrete)
                or actions.n != ACTION_COUNT or actions.start != 0):
            raise ValueError(f"Checkpoint spaces are incompatible with Echelon Phase 4: "
                             f"observation={obs}, action={actions}")
        self.army = army
        self.deterministic = deterministic

    def choose(self, state: BattleState) -> Order:
        if state.finished or state.active_army != self.army:
            raise ValueError("PPOGeneral can act only on its army's active turn")
        mask = action_masks(state, self.army)
        if not mask.any():
            raise RuntimeError("No legal PPO action in an active battle")
        values = observation(state, self.army, state.first_army)
        action, _ = self.model.predict(values, action_masks=mask,
                                       deterministic=self.deterministic)
        action = int(np.asarray(action).item())
        if not 0 <= action < ACTION_COUNT or not mask[action]:
            raise RuntimeError(f"PPO checkpoint chose illegal action {action}")
        order = decode_action(state, self.army, action)
        if order not in legal_orders(state):
            raise RuntimeError(f"PPO action decoded to illegal order {order}")
        return order
