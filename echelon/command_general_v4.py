"""Deterministic formation-level opponent for version 4 Command battles."""
from .command_engine import distance


class CommandGeneral:
    def __init__(self, army, preference="balanced", interval=30):
        if preference not in ("balanced", "aggressive", "defensive"):
            raise ValueError("Unknown tactical preference")
        self.army, self.preference, self.interval = army, preference, interval
        self.last = {}

    def decide(self, battle):
        if battle.tick % self.interval or battle.finished:
            return
        friends = [u for u in battle.units.values() if u.army == self.army and u.effective]
        enemies = [u for u in battle.units.values() if u.army != self.army and u.effective]
        if not enemies:
            return
        assigned = {}
        for index, u in enumerate(friends):
            nearest = min(enemies, key=lambda e: (distance((u.x, u.y), (e.x, e.y)) + assigned.get(e.id, 0) * 85, e.id))
            d = distance((u.x, u.y), (nearest.x, nearest.y))
            if u.kind == "artillery":
                threat = d < 150
                kind, target = ("RETREAT", None) if threat else ("HOLD", None) if d < 360 else ("MOVE", (battle.width * (.38 if self.army == "Blue" else .62), u.y))
            elif u.kind == "cavalry":
                exposed = [e for e in enemies if e.kind == "artillery"]
                prey = min(exposed, key=lambda e: distance((u.x, u.y), (e.x, e.y))) if exposed else nearest
                kind, target = "ATTACK", prey.id
            elif u.kind == "infantry" and nearest.kind == "cavalry" and d < 165:
                kind, target = "HOLD", None
            elif self.preference == "defensive" and d < 135:
                kind, target = "HOLD", None
            elif self.preference != "aggressive" and d > 210 and battle.hold[self.army] < 30:
                kind, target = "DEFEND", (battle.width / 2, battle.height / 2 + (index - (len(friends) - 1) / 2) * 55)
            else:
                kind, target = "ATTACK", nearest.id
            if kind == "ATTACK":
                assigned[target] = assigned.get(target, 0) + 1
            choice = (kind, str(target))
            # A two-second lock prevents target churn while still reacting to a threat.
            previous, last_tick = self.last.get(u.id, (None, -1000))
            if choice != previous and (battle.tick - last_tick >= 40 or kind == "RETREAT"):
                battle.command(self.army, [u.id], kind, target)
                self.last[u.id] = (choice, battle.tick)
