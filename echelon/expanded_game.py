"""Live Expanded controller and AI-vs-AI runner."""
from copy import deepcopy

from .doctrines import draft
from .engine import legal_orders
from .expanded import apply_order, new_battle
from .expanded_general import ExpandedGeneral
from .expanded_recording import make_record, save
from .model import ARMIES
from .recording import decision_record, state_snapshot


class ExpandedGame:
    def __init__(self, human_roster, doctrine="balanced", human_army="Blue",
                 first_army="Blue", seed=42):
        if human_army not in ARMIES or first_army not in ARMIES:
            raise ValueError("Army must be Blue or Red")
        self.human_army = human_army
        self.ai_army = "Red" if human_army == "Blue" else "Blue"
        self.human_roster = tuple(human_roster)
        self.doctrine = doctrine
        self.first_army = first_army
        self.opponent_name = doctrine
        self.deployment = "seeded"
        self.reset(seed)

    def reset(self, seed=None):
        if seed is not None:
            self.seed = int(seed)
        self.ai_roster = draft(self.doctrine, f"{self.seed}:draft:{self.ai_army}")
        rosters = {self.human_army: self.human_roster, self.ai_army: self.ai_roster}
        self.state = new_battle(rosters["Blue"], rosters["Red"], self.seed,
                                self.first_army)
        self.initial = state_snapshot(self.state)
        self.decisions = []
        self.invalid_attempts = 0
        self.last_error = ""
        self.general = ExpandedGeneral()
        if self.state.active_army == self.ai_army:
            self._play_ai()

    def new_seed(self):
        self.reset(self.seed + 1)

    def human_orders(self, unit_id=None, kind=None):
        if self.state.finished or self.state.active_army != self.human_army:
            return []
        return [o for o in legal_orders(self.state)
                if (unit_id is None or o.unit_id == unit_id)
                and (kind is None or o.kind == kind)]

    def _apply(self, order):
        before = deepcopy(self.state)
        message = apply_order(self.state, order)
        self.decisions.append(decision_record(before, order, self.state, message))

    def _play_ai(self):
        if not self.state.finished and self.state.active_army == self.ai_army:
            self._apply(self.general.choose(self.state))

    def submit(self, order):
        if order not in self.human_orders():
            self.invalid_attempts += 1
            self.last_error = "That order is not legal on your turn."
            return False
        self.last_error = ""
        self._apply(order)
        self._play_ai()
        return True

    def recording(self):
        return make_record(self.state, self.initial, self.decisions,
                           self.seed, self.human_army, self.doctrine)

    def save(self, path):
        return save(self.recording(), path)


def ai_battle(blue_roster, red_roster, seed=42, first_army="Blue"):
    state = new_battle(blue_roster, red_roster, seed, first_army)
    initial = state_snapshot(state)
    decisions = []
    generals = {army: ExpandedGeneral() for army in ARMIES}
    while not state.finished:
        before = deepcopy(state)
        order = generals[state.active_army].choose(state)
        message = apply_order(state, order)
        decisions.append(decision_record(before, order, state, message))
    return make_record(state, initial, decisions, seed, "Blue", "Expanded AI")
