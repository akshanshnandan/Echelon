"""Reconstruct version 3 Command outcomes without rendered frames."""
import json

from .command_engine import CommandBattle
from .command_general import CommandGeneral
from .command_engine_v4 import CommandBattle as CommandBattleV4
from .command_general_v4 import CommandGeneral as CommandGeneralV4


def verify(record):
    def same(a, b):
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    version = record.get("version")
    if version not in (3, 4) or record.get("ruleset") != "Command":
        raise ValueError("Not a supported Command replay")
    battle = (CommandBattle(record["seed"], record["map"], record["roster"]) if version == 3 else
              CommandBattleV4(record["seed"], record["map"], record["roster"], size=record["size"],
                              enemy_roster=record["enemy_roster"], budget=record["budget"],
                              manpower=record["manpower"], opponent=record["opponent"], human_army=record["human_army"],
                              morale_rules=record["morale_rules"]))
    if not same(battle.snapshot(), record["initial"]):
        raise ValueError("Initial state mismatch")
    general_type = CommandGeneral if version == 3 else CommandGeneralV4
    general = general_type("Red" if record["human_army"] == "Blue" else "Blue", record["opponent"])
    commands = record["commands"]
    index = 0
    checkpoints = record.get("checkpoints", [])
    checkpoint_index = 0
    final_tick = record["final"]["tick"]
    while battle.tick < final_tick:
        while index < len(commands) and commands[index]["tick"] == battle.tick:
            c = commands[index]
            battle.command(record["human_army"], c["ids"], c["kind"], c["target"], c["waypoints"])
            index += 1
        general.decide(battle)
        battle.step()
        while checkpoint_index < len(checkpoints) and checkpoints[checkpoint_index]["tick"] == battle.tick:
            expected = checkpoints[checkpoint_index]["state"]
            actual = battle.snapshot()
            if "events" not in expected:
                actual.pop("events")
            if not same(actual, expected):
                raise ValueError("Command replay checkpoint diverged")
            checkpoint_index += 1
    while index < len(commands) and commands[index]["tick"] == battle.tick:
        c = commands[index]
        battle.command(record["human_army"], c["ids"], c["kind"], c["target"], c["waypoints"])
        index += 1
    if checkpoint_index != len(checkpoints) or index != len(commands) or not same(battle.snapshot(), record["final"]) or not same(battle.events, record["events"]):
        raise ValueError("Command replay diverged")
    return True
