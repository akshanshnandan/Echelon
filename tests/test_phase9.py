"""Expanded drafting, battle, UI, replay, and Classic isolation tests."""
import copy
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"

from echelon.army_builder import ArmyBuilder
from echelon.doctrines import WEIGHTS, draft
from echelon.drafting import legal_compositions, purchase, remaining, remove, validate
from echelon.engine import legal_orders, new_battle as classic_battle
from echelon.env import EchelonEnv
from echelon.expanded import apply_order, new_battle, strength
from echelon.expanded_game import ExpandedGame, ai_battle
from echelon.expanded_recording import load, save, verify
from echelon.expanded_tournament import summary, tournament
from echelon.live_game import LiveGame
from echelon.model import Order, OrderType
from echelon.replay_data import load_recordings


class Phase9Tests(unittest.TestCase):
    def test_purchase_refund_and_limits(self):
        roster = purchase((), "infantry")
        roster = purchase(roster, "cavalry")
        self.assertEqual(remaining(roster), (7500, 25, 2))
        self.assertEqual(remove(roster, 1), ("infantry",))
        self.assertEqual(remove(("infantry",), 0), ())
        with self.assertRaises(ValueError):
            validate(())
        with self.assertRaises(ValueError):
            validate(("infantry",) * 4)  # manpower
        with self.assertRaises(ValueError):
            validate(("artillery",) * 4)  # gold
        with self.assertRaises(ValueError):
            validate(("cavalry",) * 5)  # formations
        with self.assertRaises(ValueError):
            purchase(("artillery",) * 3, "cavalry")
        with self.assertRaises(ValueError):
            purchase((), "archer")

    def test_legal_compositions_and_seeded_doctrines(self):
        self.assertEqual(len(legal_compositions()), 24)
        for name in WEIGHTS:
            rosters = [draft(name, seed) for seed in range(40)]
            self.assertTrue(all(validate(roster) == roster for roster in rosters))
            self.assertGreater(len(set(rosters)), 1)
            self.assertEqual(rosters, [draft(name, seed) for seed in range(40)])
        self.assertTrue(all(len(set(draft("balanced", seed))) == 3
                            for seed in range(40)))
        self.assertTrue(all(draft("cavalry", seed).count("cavalry") >= 3
                            for seed in range(40)))

    def test_variable_setup_duplicate_ids_and_deployment(self):
        blue = ("cavalry", "cavalry", "cavalry", "infantry")
        red = ("infantry", "infantry", "cavalry", "artillery")
        a, b = new_battle(blue, red, 19), new_battle(blue, red, 19)
        self.assertEqual(a, b)
        self.assertEqual(len({u.id for u in a.units}), 8)
        self.assertEqual(len({(u.row, u.column) for u in a.units}), 8)
        self.assertEqual(Counter(u.kind for u in a.units if u.army == "Blue"),
                         Counter(blue))
        self.assertTrue(all(u.row in (0, 1) if u.army == "Blue" else u.row in (6, 7)
                            for u in a.units))
        self.assertNotEqual(a, new_battle(blue, red, 20))

    def test_movement_attack_turns_and_illegal_rejection(self):
        state = new_battle(("infantry",), ("artillery", "artillery"), 8, "Red")
        self.assertEqual(state.active_army, "Red")
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            apply_order(state, Order("B-I1", OrderType.HOLD))
        self.assertEqual(state, before)
        red_order = next(o for o in legal_orders(state) if o.kind == OrderType.ADVANCE)
        apply_order(state, red_order)
        self.assertEqual(state.active_army, "Blue")
        blue = next(u for u in state.units if u.army == "Blue")
        red = next(u for u in state.units if u.army == "Red")
        blue.row, blue.column = 3, 3
        red.row, red.column = 4, 3
        attack = Order(blue.id, OrderType.ATTACK, red.id)
        self.assertIn(attack, legal_orders(state))
        hp = red.health
        apply_order(state, attack)
        self.assertLess(red.health, hp)
        self.assertEqual(state.completed_rounds, 1)

    def test_strength_tiebreak_avoids_formation_count_bias(self):
        state = new_battle(("artillery",), ("infantry", "infantry"), 4)
        self.assertEqual(strength(state, "Blue"), strength(state, "Red"))
        for _ in range(60):
            apply_order(state, Order(state.active_army[0] +
                                     ("-A1" if state.active_army == "Blue" else "-I1"),
                                     OrderType.HOLD))
            if state.finished:
                break
        self.assertEqual((state.winner, state.reason), (None, "time limit"))
        state = new_battle(("artillery",), ("infantry", "infantry"), 4)
        state.units[1].health = 0  # cheap extra formation cannot win by its count
        self.assertGreater(strength(state, "Blue"), strength(state, "Red"))
        state.units[0].morale = 20
        self.assertEqual(strength(state, "Blue"), 0)

    def test_human_sides_and_battle_completion(self):
        for army in ("Blue", "Red"):
            game = ExpandedGame(("cavalry", "cavalry", "infantry"), "balanced",
                                army, "Red", 13)
            self.assertEqual(game.state.active_army, army)
            prior = copy.deepcopy(game.state)
            self.assertFalse(game.submit(Order("missing", OrderType.HOLD)))
            self.assertEqual(game.state, prior)
            turns = 0
            while not game.state.finished:
                orders = game.human_orders()
                order = next((o for o in orders if o.kind == OrderType.ATTACK),
                             next((o for o in orders if o.kind == OrderType.ADVANCE), orders[0]))
                self.assertTrue(game.submit(order))
                turns += 1
                self.assertLessEqual(turns, 30)
            self.assertIn(game.state.reason, ("elimination", "time limit"))
            self.assertEqual(verify(game.recording())["final"]["winner"], game.state.winner)

    def test_versioned_record_and_viewer_loader(self):
        record = ai_battle(("infantry",), ("cavalry", "cavalry"), 25)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "expanded.json"
            save(record, path)
            self.assertEqual(load(path)["version"], 2)
            self.assertEqual(load_recordings([path])[0][1]["final"], record["final"])
            with self.assertRaises(FileExistsError):
                save(record, path)
            corrupted = json.loads(path.read_text(encoding="utf-8"))
            corrupted["decisions"][0]["action"] = "ATTACK"
            with self.assertRaises(ValueError):
                verify(corrupted)
            corrupted = json.loads(path.read_text(encoding="utf-8"))
            corrupted["decisions"][0]["damage"] += 1
            with self.assertRaises(ValueError):
                verify(corrupted)
            with self.assertRaises(ValueError):
                load(Path(folder) / "missing.json")

    def test_mouse_builder_and_custom_board(self):
        app = ArmyBuilder(42)
        app.draw()
        app.handle_click((54 + 20, 339 + 20))  # add infantry via card
        self.assertEqual(app.roster.count("infantry"), 2)
        app.draw()
        app.handle_click((54 + 20, 339 + 20))  # manpower limit
        self.assertEqual(app.roster.count("infantry"), 2)
        self.assertIn("cap", app.status)
        app.draw()
        app.handle_click((54 + 20, 523 + 20))  # remove first slot
        self.assertEqual(len(app.roster), 3)
        app.draw()
        app.handle_click((830 + 20, 110 + 20))  # Red army
        app.draw()
        app.handle_click((966 + 20, 720 + 20))  # start
        self.assertFalse(app.builder_open)
        self.assertEqual(app.game.human_army, "Red")
        self.assertEqual(app.game.state.active_army, "Red")
        app.command("setup")
        self.assertTrue(app.builder_open)
        app.command("mode:Classic")
        app.command("start")
        self.assertIsInstance(app.game, LiveGame)
        import pygame
        pygame.quit()

    def test_tournament_counts_and_classic_isolation(self):
        rows = tournament(4, 100)
        self.assertEqual(len(rows), 24)
        report = summary(rows)
        for name in WEIGHTS:
            stats = report[f"{name} / all"]
            self.assertEqual(stats["battles"], 12)
            self.assertEqual(stats["wins"] + stats["losses"] + stats["draws"], 12)
        classic = classic_battle()
        self.assertEqual(len(classic.units), 6)
        env = EchelonEnv()
        observation, _ = env.reset(seed=2)
        self.assertEqual((len(observation), env.action_space.n), (63, 396))
        env.close()


if __name__ == "__main__":
    unittest.main()
