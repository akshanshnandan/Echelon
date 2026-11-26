"""Read recorded battle data for the viewer without running the battle engine."""
import json
from pathlib import Path


KINDS = {"infantry", "cavalry", "artillery"}
ACTIONS = {"HOLD", "ADVANCE", "ATTACK", "RETREAT"}


def validate_record(record: dict) -> dict:
    """Check structure and snapshot continuity, not combat rules."""
    if isinstance(record, dict) and record.get("version") == 2:
        from .expanded_recording import verify
        return verify(record)
    try:
        if not isinstance(record, dict) or not isinstance(record["decisions"], list):
            raise ValueError("A battle must be a JSON object with a decisions list")
        if not record["decisions"]:
            raise ValueError("Battle has no decisions")
        if record["agent_army"] not in ("Blue", "Red") or record["first_army"] not in ("Blue", "Red"):
            raise ValueError("Unknown army")
        if record["classification"] not in ("decisive", "tiebreak"):
            raise ValueError("Unknown result classification")

        def check_state(state):
            units = state["units"]
            if set(units) != {"B-I", "B-C", "B-A", "R-I", "R-C", "R-A"}:
                raise ValueError("Expected six named formations")
            for unit in units.values():
                row, col = unit["position"]
                if (unit["army"] not in ("Blue", "Red") or unit["kind"] not in KINDS
                        or not all(isinstance(x, int) and 0 <= x < 8 for x in (row, col))
                        or not isinstance(unit["health"], int) or unit["health"] < 0
                        or not isinstance(unit["morale"], int) or not 0 <= unit["morale"] <= 100
                        or not isinstance(unit["effective"], bool)
                        or unit["effective"] != (unit["health"] > 0 and unit["morale"] >= 30)):
                    raise ValueError("Invalid formation snapshot")
            if state["active_army"] not in ("Blue", "Red"):
                raise ValueError("Invalid active army")
            if (not isinstance(state["finished"], bool) or
                    state["winner"] not in (None, "Blue", "Red") or
                    state["reason"] not in (None, "elimination", "time limit")):
                raise ValueError("Invalid battle status")

        check_state(record["initial"])
        current = record["initial"]
        for index, step in enumerate(record["decisions"]):
            check_state(step["before"])
            check_state(step["after"])
            if step["before"] != current:
                raise ValueError(f"Snapshot continuity breaks at action {index}")
            if (step["army"] != current["active_army"] or step["unit"] not in current["units"]
                    or step["action"] not in ACTIONS or step["legal_count"] < 1
                    or step["damage"] < 0 or not isinstance(step["message"], str)):
                raise ValueError(f"Malformed action {index}")
            target = step["target"]
            if (step["action"] == "ATTACK" and target not in current["units"] or
                    step["action"] in ("ADVANCE", "RETREAT") and
                    (not isinstance(target, list) or len(target) != 2 or
                     not all(isinstance(x, int) and 0 <= x < 8 for x in target)) or
                    step["action"] == "HOLD" and target is not None):
                raise ValueError(f"Invalid target at action {index}")
            if "legal_orders" in step:
                orders = step["legal_orders"]
                if (not isinstance(orders, list) or len(orders) != step["legal_count"] or
                        any(not isinstance(order, dict) or
                            order.get("unit") not in current["units"] or
                            order.get("action") not in ACTIONS for order in orders)):
                    raise ValueError(f"Malformed legal-order list at action {index}")
            current = step["after"]
        if current != record["final"] or not current["finished"]:
            raise ValueError("Missing or inconsistent terminal snapshot")
        if ((record["classification"] == "decisive") !=
                (current["reason"] == "elimination")):
            raise ValueError("Terminal classification disagrees with final state")
        outcome = ("draw" if current["winner"] is None else
                   "win" if current["winner"] == record["agent_army"] else "loss")
        if record["outcome"] != outcome:
            raise ValueError("Outcome disagrees with final winner")
        return record
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"Malformed battle recording: {exc}") from exc


def load_recordings(paths: list[Path], battle_index: int = 0) -> list[tuple[str, dict]]:
    """Accept an old battle array, one battle, or a labeled comparison bundle."""
    loaded = []
    for path in paths:
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Recording file not found: {path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read recording {path}: {exc}") from exc
        if isinstance(data, list):
            if not 0 <= battle_index < len(data):
                raise ValueError(f"Battle index {battle_index} is outside {path}")
            loaded.append((f"{path.stem} #{battle_index}", validate_record(data[battle_index])))
        elif isinstance(data, dict) and "recordings" in data:
            try:
                for entry in data["recordings"]:
                    loaded.append((str(entry["label"]), validate_record(entry["record"])))
            except (KeyError, TypeError) as exc:
                raise ValueError(f"Malformed comparison bundle: {exc}") from exc
        else:
            loaded.append((path.stem, validate_record(data)))
    if not loaded:
        raise ValueError("No battle recordings selected")
    return loaded


def battle_stats(record: dict) -> dict:
    army = record["agent_army"]
    steps = [step for step in record["decisions"] if step["army"] == army]
    counts = {kind: sum(step["action"] == kind for step in steps)
              for kind in ACTIONS}
    return {"attacks": counts["ATTACK"], "holds": counts["HOLD"],
            "retreats": counts["RETREAT"], "advances": counts["ADVANCE"],
            "damage_dealt": sum(step["damage"] for step in steps),
            "survivors": sum(unit["effective"] for unit in record["final"]["units"].values()
                             if unit["army"] == army),
            "result": record["outcome"], "condition": record["classification"]}


def terminal_caption(record: dict, state: dict) -> str:
    """Show the recorded result from the viewed agent's perspective."""
    winner = state["winner"]
    outcome = "Draw" if winner is None else "Victory" if winner == record["agent_army"] else "Defeat"
    reason = "elimination" if state["reason"] == "elimination" else "30-round tiebreak"
    return f"{outcome}  |  {winner or 'Draw'} by {reason}"
