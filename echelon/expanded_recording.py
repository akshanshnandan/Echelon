"""Version 2 replay files for variable Expanded rosters."""
import json
from copy import deepcopy
from pathlib import Path

from .expanded import apply_order, new_battle, strength
from .model import Order, OrderType
from .recording import decision_record, state_snapshot


def make_record(state, initial, decisions, seed, agent_army, opponent):
    if not state.finished:
        raise ValueError("Complete the battle before saving")
    return {"version": 2, "ruleset": "Expanded", "seed": seed,
            "agent_army": agent_army, "first_army": state.first_army,
            "opponent": opponent, "rosters": state.rosters,
            "initial": initial, "decisions": decisions,
            "final": state_snapshot(state),
            "outcome": ("draw" if state.winner is None else
                        "win" if state.winner == agent_army else "loss"),
            "classification": "decisive" if state.reason == "elimination" else "tiebreak",
            "blue_strength": float(strength(state, "Blue")),
            "red_strength": float(strength(state, "Red"))}


def verify(record):
    """Re-simulate every recorded order; reject malformed or altered battles."""
    try:
        if record["version"] != 2 or record["ruleset"] != "Expanded":
            raise ValueError("Expected an Expanded version 2 replay")
        if record["agent_army"] not in ("Blue", "Red"):
            raise ValueError("Invalid agent army")
        state = new_battle(record["rosters"]["Blue"], record["rosters"]["Red"],
                           record["seed"], record["first_army"])
        if state_snapshot(state) != record["initial"]:
            raise ValueError("Initial deployment differs")
        for index, step in enumerate(record["decisions"]):
            if state_snapshot(state) != step["before"]:
                raise ValueError(f"Pre-order snapshot differs at {index}")
            before = deepcopy(state)
            target = tuple(step["target"]) if isinstance(step["target"], list) else step["target"]
            order = Order(step["unit"], OrderType(step["action"]), target)
            message = apply_order(state, order)
            if decision_record(before, order, state, message) != step:
                raise ValueError(f"Order outcome differs at {index}")
        if not record["decisions"] or not state.finished or state_snapshot(state) != record["final"]:
            raise ValueError("Final state differs or battle is incomplete")
        expected = make_record(state, record["initial"], record["decisions"],
                               record["seed"], record["agent_army"], record["opponent"])
        for key in ("outcome", "classification", "blue_strength", "red_strength"):
            if record[key] != expected[key]:
                raise ValueError(f"Incorrect {key}")
        return record
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f"Malformed Expanded replay: {exc}") from exc


def load(path):
    path = Path(path)
    try:
        return verify(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read Expanded replay {path}: {exc}") from exc


def save(record, path):
    verify(record)
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path
