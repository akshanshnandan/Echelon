"""Authoritative monotonic clock and Command session lifecycle."""
import time

from .command_engine import CommandBattle, DT
from .command_general import CommandGeneral


class CommandGame:
    def __init__(self, human_army="Blue", opponent="balanced", map_name="open_field", seed=42, roster=None, clock=None):
        self.battle = CommandBattle(seed, map_name, roster)
        self.human_army, self.opponent = human_army, opponent
        self.general = CommandGeneral("Red" if human_army == "Blue" else "Blue", opponent)
        self.clock = clock or time.monotonic
        self.last_clock = self.clock()
        self.accumulator = 0.0
        self.paused = False
        self.speed = 1.0
        self.commands = []
        self.checkpoints = []
        self.initial = self.battle.snapshot()

    def advance(self):
        now = self.clock()
        elapsed = max(0, min(2.0, now - self.last_clock))
        self.last_clock = now
        if self.paused or self.battle.finished:
            return
        self.accumulator += elapsed * self.speed
        count = min(80, int((self.accumulator + 1e-9) / DT))
        self.accumulator -= count * DT
        for _ in range(count):
            self.general.decide(self.battle)
            self.battle.step()
            if self.battle.tick % 20 == 0:
                state = self.battle.snapshot()
                state.pop("events")  # Events are stored once in the replay, not in every checkpoint.
                self.checkpoints.append({"tick": self.battle.tick, "state": state})
            if self.battle.finished:
                break

    def order(self, ids, kind, target=None, waypoints=None):
        self.advance()
        self.battle.command(self.human_army, ids, kind, target, waypoints)
        self.commands.append({"tick": self.battle.tick, "ids": ids, "kind": kind,
                              "target": target, "waypoints": waypoints or []})

    def control(self, paused=None, speed=None):
        self.advance()
        if paused is not None:
            self.paused = paused
        if speed is not None:
            if speed not in (0.5, 1.0, 2.0, 4.0):
                raise ValueError("Speed must be 0.5, 1, 2, or 4")
            self.speed = speed
        self.last_clock = self.clock()

    def state(self):
        self.advance()
        return {"ruleset": "Command", "human_army": self.human_army,
                "opponent": self.opponent, "seed": self.battle.seed,
                "paused": self.paused, "speed": self.speed,
                "battle": self.battle.snapshot()}

    def recording(self):
        self.advance()
        return {"version": 3, "ruleset": "Command", "seed": self.battle.seed,
                "map": self.battle.map_name, "roster": self.battle.roster,
                "human_army": self.human_army, "opponent": self.opponent,
                "initial": self.initial, "commands": self.commands,
                "events": self.battle.events, "checkpoints": self.checkpoints,
                "final": self.battle.snapshot()}
