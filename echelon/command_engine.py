"""Deterministic, fixed-step Command battlefield. No web or graphics dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, cos, hypot, pi, sin
from random import Random

WIDTH, HEIGHT, DT = 1200.0, 800.0, 0.1
STATS = {
    "infantry": (100.0, 48.0, 62.0, 76.0, 8.0, 1.2),
    "cavalry": (85.0, 94.0, 52.0, 64.0, 11.0, 1.5),
    "artillery": (65.0, 30.0, 48.0, 390.0, 13.0, 3.0),
}
MAPS = ("open_field", "ridge_forest")


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def angle_delta(a, b):
    return (a - b + pi) % (2 * pi) - pi


@dataclass
class Formation:
    id: str
    army: str
    kind: str
    x: float
    y: float
    heading: float
    health: float
    morale: float = 100.0
    cooldown: float = 0.0
    order: str = "HOLD"
    target: str | None = None
    destination: tuple[float, float] | None = None
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    charge: float = 0.0

    @property
    def effective(self):
        return self.health > 0 and self.morale >= 25

    def snapshot(self):
        return {"id": self.id, "army": self.army, "kind": self.kind,
                "x": round(self.x, 4), "y": round(self.y, 4),
                "heading": round(self.heading, 5), "health": round(self.health, 3),
                "morale": round(self.morale, 3), "effective": self.effective,
                "order": self.order, "target": self.target,
                "destination": self.destination, "waypoints": self.waypoints.copy(),
                "width": STATS[self.kind][2]}


class CommandBattle:
    def __init__(self, seed=42, map_name="open_field", roster=None):
        if map_name not in MAPS:
            raise ValueError("Unknown battlefield map")
        self.seed, self.map_name = seed, map_name
        self.roster = tuple(roster or ("infantry", "infantry", "cavalry", "artillery"))
        if not 2 <= len(self.roster) <= 8 or any(k not in STATS for k in self.roster):
            raise ValueError("Command needs 2–8 infantry, cavalry, or artillery formations")
        rng = Random(seed)
        self.units = {}
        for army, x in (("Blue", 145.0), ("Red", 1055.0)):
            for i, kind in enumerate(self.roster):
                y = (i + 1) * HEIGHT / (len(self.roster) + 1) + rng.uniform(-16, 16)
                unit = Formation(f"{army[0]}{i+1}", army, kind, x + rng.uniform(-10, 10), y,
                                 0.0 if army == "Blue" else pi, STATS[kind][0])
                self.units[unit.id] = unit
        self.tick = 0
        self.hold = {"Blue": 0.0, "Red": 0.0}
        self.finished = False
        self.winner = None
        self.reason = None
        self.events = []

    def terrain(self, x, y):
        if self.map_name == "ridge_forest":
            if 570 <= x <= 670 and 160 <= y <= 640:
                return "ridge"
            if (x - 420) ** 2 / 120 ** 2 + (y - 250) ** 2 / 135 ** 2 <= 1 or (x - 790) ** 2 / 120 ** 2 + (y - 550) ** 2 / 135 ** 2 <= 1:
                return "forest"
        return "open"

    def command(self, army, ids, kind, target=None, waypoints=None):
        if self.finished or kind not in ("MOVE", "ATTACK", "HOLD", "DEFEND", "RETREAT", "STOP"):
            raise ValueError("Invalid command or finished battle")
        if not ids or len(ids) > 8 or len(set(ids)) != len(ids):
            raise ValueError("Select one to eight distinct formations")
        units = [self.units.get(uid) for uid in ids]
        if any(u is None or u.army != army or not u.effective for u in units):
            raise ValueError("Formation is unavailable or belongs to the other army")
        if kind == "ATTACK":
            enemy = self.units.get(target)
            if enemy is None or enemy.army == army or not enemy.effective:
                raise ValueError("Attack target must be an effective enemy")
        if kind in ("MOVE", "DEFEND"):
            if not isinstance(target, (list, tuple)) or len(target) != 2 or not all(isinstance(v, (float, int)) and 0 <= v <= bound for v, bound in zip(target, (WIDTH, HEIGHT))):
                raise ValueError("Destination must be inside the battlefield")
        if waypoints is None:
            waypoints = []
        if len(waypoints) > 6 or any(not isinstance(p, (tuple, list)) or len(p) != 2 or not all(isinstance(v, (int, float)) and 0 <= v <= bound for v, bound in zip(p, (WIDTH, HEIGHT))) for p in waypoints):
            raise ValueError("Invalid waypoints")
        for index, unit in enumerate(units):
            unit.order = kind
            unit.target = target if kind == "ATTACK" else None
            unit.waypoints = [tuple(p) for p in waypoints]
            if kind in ("MOVE", "DEFEND"):
                # Preserve spacing for group moves.
                offset = (index - (len(units) - 1) / 2) * 70
                unit.destination = (max(30, min(WIDTH - 30, target[0])), max(30, min(HEIGHT - 30, target[1] + offset)))
            elif kind == "RETREAT":
                unit.destination = (75 if army == "Blue" else WIDTH - 75, unit.y)
            else:
                unit.destination = None
            self.events.append({"tick": self.tick, "type": "order", "unit": unit.id, "kind": kind})

    def _visible(self, attacker, target):
        if attacker.kind != "artillery" or distance((attacker.x, attacker.y), (target.x, target.y)) < 110:
            return True
        # Forest conceals ranged targets; ridge blocks a low trajectory across it.
        if self.terrain(target.x, target.y) == "forest" and distance((attacker.x, attacker.y), (target.x, target.y)) > 180:
            return False
        if self.map_name == "ridge_forest" and (attacker.x - 620) * (target.x - 620) < 0 and self.terrain(attacker.x, attacker.y) != "ridge" and self.terrain(target.x, target.y) != "ridge":
            return False
        return True

    def step(self):
        if self.finished:
            return
        self.tick += 1
        active = [u for u in self.units.values() if u.effective]
        for u in active:
            u.cooldown = max(0.0, u.cooldown - DT)
            target = self.units.get(u.target) if u.target else None
            goal = u.destination
            if u.order == "ATTACK" and target and target.effective:
                goal = (target.x, target.y)
            elif u.order == "ATTACK":
                u.order, u.target = "HOLD", None
            if u.waypoints:
                goal = u.waypoints[0]
            if goal and u.order in ("MOVE", "ATTACK", "DEFEND", "RETREAT"):
                d = distance((u.x, u.y), goal)
                stop = (STATS[u.kind][3] * 0.82 if u.order == "ATTACK" and target and u.kind == "artillery" else 42 if u.order == "ATTACK" else 4)
                if d > stop:
                    desired = atan2(goal[1] - u.y, goal[0] - u.x)
                    u.heading += max(-0.22, min(0.22, angle_delta(desired, u.heading)))
                    speed = STATS[u.kind][1] * (0.65 if self.terrain(u.x, u.y) == "forest" else 1)
                    move = min(speed * DT, d - stop)
                    u.x = max(25, min(WIDTH - 25, u.x + cos(u.heading) * move))
                    u.y = max(25, min(HEIGHT - 25, u.y + sin(u.heading) * move))
                    u.charge = min(2, u.charge + DT) if u.kind == "cavalry" else 0
                elif u.waypoints:
                    u.waypoints.pop(0)
                elif u.order in ("MOVE", "RETREAT"):
                    u.order, u.destination = "HOLD", None
            elif u.order != "ATTACK":
                u.charge = 0
        # Stable pair order and symmetric separation.
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = hypot(dx, dy)
                minimum = (STATS[a.kind][2] + STATS[b.kind][2]) * 0.48
                if d < minimum:
                    if d < 1e-9:
                        dx, dy, d = 1.0, 0.0, 1.0
                    push = (minimum - d) / 2
                    a.x = max(25, min(WIDTH - 25, a.x - dx / d * push))
                    a.y = max(25, min(HEIGHT - 25, a.y - dy / d * push))
                    b.x = max(25, min(WIDTH - 25, b.x + dx / d * push))
                    b.y = max(25, min(HEIGHT - 25, b.y + dy / d * push))
        # Collect attacks before applying damage so simultaneous exchanges survive.
        hits = []
        for u in active:
            foes = [v for v in active if v.army != u.army and distance((u.x, u.y), (v.x, v.y)) <= STATS[u.kind][3] and self._visible(u, v)]
            if not foes or u.cooldown > 1e-9 or u.order == "RETREAT":
                continue
            v = self.units.get(u.target) if u.target else None
            if v not in foes:
                v = min(foes, key=lambda f: (distance((u.x, u.y), (f.x, f.y)), f.id))
            bearing = atan2(u.y - v.y, u.x - v.x)
            flank = abs(angle_delta(bearing, v.heading))
            modifier = 1.4 if flank > 2.35 else 1.2 if flank > 1.15 else 1.0
            if v.order in ("HOLD", "DEFEND"):
                modifier *= 0.82
            if self.terrain(v.x, v.y) == "ridge":
                modifier *= 0.8
            if self.terrain(v.x, v.y) == "forest":
                modifier *= 0.85
            if u.kind == "cavalry" and u.charge >= 1 and distance((u.x, u.y), (v.x, v.y)) < 65:
                modifier *= 1.65 if v.kind != "infantry" or v.order not in ("HOLD", "DEFEND") else 0.9
                u.charge = 0
            if u.kind == "artillery" and distance((u.x, u.y), (v.x, v.y)) < 90:
                modifier *= 0.4
            hits.append((u, v, STATS[u.kind][4] * modifier * max(0.5, u.morale / 100)))
            u.cooldown = STATS[u.kind][5]
        for u, v, damage in hits:
            v.health = max(0.0, v.health - damage)
            v.morale = max(0.0, v.morale - damage * (2.2 if u.kind == "cavalry" else 1.7))
            self.events.append({"tick": self.tick, "type": "hit", "unit": u.id, "target": v.id, "damage": round(damage, 3)})
            if not v.effective:
                self.events.append({"tick": self.tick, "type": "destroyed" if v.health <= 0 else "routed", "unit": v.id})
        center = (WIDTH / 2, HEIGHT / 2)
        for army in ("Blue", "Red"):
            friendly = any(u.effective and u.army == army and distance((u.x, u.y), center) <= 105 for u in self.units.values())
            enemy = any(u.effective and u.army != army and distance((u.x, u.y), center) <= 105 for u in self.units.values())
            self.hold[army] = self.hold[army] + DT if friendly and not enemy else max(0, self.hold[army] - DT * 0.5)
        alive = {army: any(u.effective and u.army == army for u in self.units.values()) for army in ("Blue", "Red")}
        if not all(alive.values()):
            self.finished, self.reason = True, "elimination"
            self.winner = "Blue" if alive["Blue"] else "Red" if alive["Red"] else None
        elif max(self.hold.values()) >= 35:
            self.finished, self.reason = True, "objective"
            self.winner = max(self.hold, key=self.hold.get)
        elif self.tick >= 9000:
            self.finished, self.reason = True, "time_limit"
            scores = {army: self.hold[army] + sum(u.health / 10 for u in self.units.values() if u.army == army and u.effective) for army in ("Blue", "Red")}
            self.winner = max(scores, key=scores.get) if scores["Blue"] != scores["Red"] else None
        if self.finished:
            self.events.append({"tick": self.tick, "type": "victory", "winner": self.winner, "reason": self.reason})

    def snapshot(self):
        return {"tick": self.tick, "time": round(self.tick * DT, 1), "map": self.map_name,
                "units": {uid: u.snapshot() for uid, u in self.units.items()},
                "objective": {k: round(v, 2) for k, v in self.hold.items()},
                "finished": self.finished, "winner": self.winner, "reason": self.reason,
                "events": self.events[-30:]}
