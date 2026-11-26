import json
import math
import unittest

from fastapi.testclient import TestClient

from echelon.command_engine import CommandBattle, distance
from echelon.command_game import CommandGame
from echelon.command_recording import verify
from echelon.web_api import sample_replay
from echelon.web_api import app


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class CommandTests(unittest.TestCase):
    def test_deterministic_simultaneous_movement_and_replay(self):
        results = []
        for _ in range(2):
            b = CommandBattle(7)
            b.command("Blue", ["B1", "B2"], "MOVE", [550, 400], [[350, 350]])
            b.command("Red", ["R1"], "ATTACK", "B1")
            for _ in range(100):
                b.step()
            results.append(b.snapshot())
        self.assertEqual(*results)
        self.assertGreater(results[0]["units"]["B1"]["x"], 145)
        self.assertNotEqual(results[0]["units"]["B1"]["y"], results[0]["units"]["B2"]["y"])

    def test_terrain_flank_and_auto_combat(self):
        open_b = CommandBattle(1)
        ridge_b = CommandBattle(1, "ridge_forest")
        for b in (open_b, ridge_b):
            b.units["B4"].x, b.units["B4"].y = 410, 250
            b.units["R1"].x, b.units["R1"].y = 620, 250
            b.units["R1"].heading = 0
            for uid, u in b.units.items():
                if uid not in ("B4", "R1"):
                    u.x, u.y = (50 if u.army == "Blue" else 1150), 750 - int(uid[1:]) * 100
            b.step()
        self.assertLess(open_b.units["R1"].health, ridge_b.units["R1"].health)
        self.assertLess(open_b.units["R1"].health, 100)

    def test_reaching_destination_and_facing(self):
        b = CommandBattle(5)
        u = b.units["B1"]
        start = (u.x, u.y)
        b.command("Blue", [u.id], "MOVE", [250, 650])
        for _ in range(150):
            b.step()
            if u.order == "HOLD":
                break
        self.assertEqual(u.order, "HOLD")
        self.assertLess(distance((u.x, u.y), (250, 650)), 5)
        self.assertGreater(u.y, start[1])
        self.assertGreater(u.heading, 0)

    def test_forest_speed_and_line_of_sight(self):
        open_b = CommandBattle(2)
        forest_b = CommandBattle(2, "ridge_forest")
        for b in (open_b, forest_b):
            u = b.units["B1"]
            u.x, u.y = 390, 250
            b.command("Blue", ["B1"], "MOVE", [480, 250])
            b.step()
        self.assertLess(forest_b.units["B1"].x - 390, open_b.units["B1"].x - 390)
        gun = forest_b.units["B4"]
        target = forest_b.units["R1"]
        gun.x, gun.y = 340, 250
        target.x, target.y = 420, 250
        self.assertTrue(forest_b._visible(gun, target))
        gun.x = 160
        self.assertFalse(forest_b._visible(gun, target))

    def test_rear_attack_causes_more_damage_than_front(self):
        damage = []
        for heading in (0, math.pi):
            b = CommandBattle(3)
            for uid, u in b.units.items():
                if uid not in ("B1", "R1"):
                    u.x, u.y = (50 if u.army == "Blue" else 1150), 750 - int(uid[1:]) * 100
            b.units["B1"].x, b.units["B1"].y = 500, 400
            b.units["R1"].x, b.units["R1"].y = 565, 400
            b.units["R1"].heading = heading
            b.step()
            damage.append(100 - b.units["R1"].health)
        self.assertGreater(damage[0], damage[1])

    def test_replay_detects_tampering(self):
        clock = FakeClock()
        game = CommandGame(clock=clock)
        game.order(["B1"], "MOVE", [600, 400])
        clock.now = 1
        record = json.loads(json.dumps(game.recording()))
        self.assertTrue(verify(record))
        record["final"]["units"]["B1"]["health"] -= 1
        with self.assertRaises(ValueError):
            verify(record)

    def test_bundled_command_replay_has_seekable_checkpoints(self):
        record = sample_replay("command")
        self.assertTrue(verify(record))
        self.assertGreater(len(record["checkpoints"]), 1)
        self.assertTrue(all(b["tick"] - a["tick"] <= 20 for a, b in zip(record["checkpoints"], record["checkpoints"][1:])))
        altered = json.loads(json.dumps(record))
        altered["checkpoints"][0]["state"]["units"]["B1"]["x"] += 1
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            verify(altered)

    def test_clock_pause_speed_and_recording(self):
        clock = FakeClock()
        g = CommandGame(clock=clock)
        g.order(["B1"], "MOVE", [600, 400])
        clock.now = 1
        self.assertEqual(g.state()["battle"]["tick"], 10)
        g.control(paused=True)
        clock.now = 2
        self.assertEqual(g.state()["battle"]["tick"], 10)
        g.control(paused=False, speed=2)
        clock.now = 3
        self.assertEqual(g.state()["battle"]["tick"], 30)
        self.assertTrue(verify(json.loads(json.dumps(g.recording()))))

    def test_routing_objective_collision(self):
        b = CommandBattle()
        b.units["B1"].x = b.units["B2"].x = 400
        b.units["B1"].y = b.units["B2"].y = 300
        b.step()
        self.assertGreater(distance((b.units["B1"].x, b.units["B1"].y), (b.units["B2"].x, b.units["B2"].y)), 0)
        for u in b.units.values():
            if u.army == "Red":
                u.morale = 0
        b.step()
        self.assertEqual((b.winner, b.reason), ("Blue", "elimination"))
        c = CommandBattle()
        c.units["B1"].x, c.units["B1"].y = 600, 400
        for _ in range(350):
            c.step()
        self.assertEqual((c.winner, c.reason), ("Blue", "objective"))

    def test_api_validation_and_isolation(self):
        client = TestClient(app)
        a = client.post("/api/command", json={"seed": 4}).json()
        b = client.post("/api/command", json={"seed": 4}).json()
        self.assertNotEqual(a["id"], b["id"])
        key = a["id"]
        self.assertEqual(client.post(f"/api/command/{key}/orders", json={"ids": ["R1"], "kind": "HOLD"}).status_code, 409)
        self.assertEqual(client.post(f"/api/command/{key}/orders", json={"ids": ["B1"], "kind": "MOVE", "target": [5000, 0]}).status_code, 409)
        self.assertEqual(client.post(f"/api/command/{key}/orders", json={"ids": ["B1"], "kind": "MOVE", "target": [500, 400]}).status_code, 200)
        self.assertEqual(client.get(f"/api/command/{b['id']}").json()["battle"]["units"]["B1"]["order"], "HOLD")


if __name__ == "__main__":
    unittest.main()
