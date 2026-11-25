"""Human-versus-AI turn controller; all rules stay in engine.py."""
import json
import random
from copy import deepcopy
from pathlib import Path

from .deployment import randomize_deployment
from .engine import apply_order, legal_orders, new_battle, score
from .generals import HeuristicGeneral, RandomGeneral
from .model import ARMIES, Order, OrderType
from .recording import decision_record, replay_battle, state_snapshot


class LiveGame:
    """One human order followed by one AI order, unless the battle ends."""

    def __init__(self, human_army: str = "Blue", opponent: str = "heuristic",
                 first_army: str = "Blue", deployment: str = "fixed",
                 seed: int = 42, checkpoint: Path | None = None):
        if human_army not in ARMIES or first_army not in ARMIES:
            raise ValueError("Human and first army must be Blue or Red")
        if opponent not in ("random", "heuristic", "ppo"):
            raise ValueError("Opponent must be random, heuristic, or ppo")
        if deployment not in ("fixed", "random"):
            raise ValueError("Deployment must be fixed or random")
        if opponent == "ppo" and checkpoint is None:
            raise ValueError("A --checkpoint path is required for the PPO opponent")
        self.human_army = human_army
        self.ai_army = ARMIES[1] if human_army == ARMIES[0] else ARMIES[0]
        self.opponent_name = opponent
        self.first_army = first_army
        self.deployment = deployment
        self.checkpoint = Path(checkpoint) if opponent == "ppo" and checkpoint is not None else None
        self._ppo = None
        if opponent == "ppo":
            from .ppo_general import PPOGeneral
            self._ppo = PPOGeneral(self.checkpoint, self.ai_army)
        self.reset(seed)

    def reset(self, seed: int | None = None):
        """Restart the same seeded setup, or start a new seed when supplied."""
        if seed is not None:
            self.seed = int(seed)
        self.state = new_battle(self.first_army)
        if self.deployment == "random":
            randomize_deployment(self.state, random.Random(self.seed))
        self.initial = state_snapshot(self.state)
        self.decisions = []
        self.invalid_attempts = 0
        self.last_error = ""
        self.general = (RandomGeneral(random.Random(f"{self.seed}:ai"))
                        if self.opponent_name == "random" else
                        HeuristicGeneral() if self.opponent_name == "heuristic" else self._ppo)
        if self.state.active_army == self.ai_army:
            self._play_ai()

    def new_seed(self):
        self.reset(self.seed + 1)

    def human_orders(self, unit_id: str | None = None,
                     kind: OrderType | None = None) -> list[Order]:
        if self.state.finished or self.state.active_army != self.human_army:
            return []
        return [order for order in legal_orders(self.state)
                if (unit_id is None or order.unit_id == unit_id)
                and (kind is None or order.kind == kind)]

    def _apply(self, order: Order):
        before = deepcopy(self.state)
        message = apply_order(self.state, order)
        self.decisions.append(decision_record(before, order, self.state, message))

    def _play_ai(self):
        if not self.state.finished and self.state.active_army == self.ai_army:
            order = self.general.choose(self.state)
            self._apply(order)

    def submit(self, order: Order) -> bool:
        """Reject illegal human input without changing battle state or AI memory."""
        if order not in self.human_orders():
            self.invalid_attempts += 1
            self.last_error = "That order is not legal on your turn."
            return False
        self.last_error = ""
        self._apply(order)
        self._play_ai()
        return True

    def recording(self) -> dict:
        if not self.state.finished:
            raise RuntimeError("A battle can be saved after it finishes")
        result = ("draw" if self.state.winner is None else
                  "win" if self.state.winner == self.human_army else "loss")
        record = {"seed": self.seed, "agent_army": self.human_army,
                  "human_army": self.human_army, "first_army": self.first_army,
                  "opponent": self.opponent_name, "deployment": self.deployment,
                  "checkpoint_name": self.checkpoint.name if self.checkpoint else None,
                  "initial": self.initial, "decisions": self.decisions,
                  "final": state_snapshot(self.state), "outcome": result,
                  "classification": ("decisive" if self.state.reason == "elimination"
                                     else "tiebreak"),
                  "blue_score": score(self.state, "Blue"),
                  "red_score": score(self.state, "Red"),
                  "invalid_actions": self.invalid_attempts}
        replay_battle(record)
        return record

    def save(self, path: Path) -> Path:
        record = self.recording()
        path = Path(path)
        if path.exists():
            raise FileExistsError(f"Recording already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return path
