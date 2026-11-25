"""Live human commands, PPO compatibility, and recorded replay checks."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from gymnasium import spaces
from sb3_contrib import MaskablePPO

from echelon import encoding
from echelon.engine import legal_orders
from echelon.env import EchelonEnv
from echelon.live_game import LiveGame
from echelon.model import Order, OrderType
from echelon.ppo_general import PPOGeneral
from echelon.recording import replay_battle
from echelon.replay_data import load_recordings


def useful_order(orders):
    return next((o for o in orders if o.kind == OrderType.ATTACK),
                next((o for o in orders if o.kind == OrderType.ADVANCE), orders[0]))


class Phase8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    def test_shared_codec_matches_environment_for_both_armies(self):
        for army in ("Blue", "Red"):
            env = EchelonEnv(agent_army=army, first_army=army,
                             deployment="random")
            observation, _ = env.reset(seed=17)
            np.testing.assert_array_equal(
                observation, encoding.observation(env.state, army, army))
            np.testing.assert_array_equal(
                env.action_masks(), encoding.action_masks(env.state, army))
            for order in legal_orders(env.state):
                index = encoding.encode_order(env.state, army, order)
                self.assertEqual(env.encode_order(order), index)
                self.assertEqual(encoding.decode_action(env.state, army, index), order)
            env.close()

    def test_human_validation_and_turn_switching(self):
        for human in ("Blue", "Red"):
            other = "Red" if human == "Blue" else "Blue"
            for first in (human, other):
                game = LiveGame(human, "heuristic", first, "fixed", 9)
                self.assertEqual(game.state.active_army, human)
                self.assertEqual(len(game.decisions), int(first == other))
                before = copy.deepcopy(game.state)
                count = len(game.decisions)
                self.assertFalse(game.submit(Order(f"{other[0]}-I", OrderType.HOLD)))
                self.assertFalse(game.submit(Order(f"{human[0]}-I", OrderType.ADVANCE,
                                                   (99, 99))))
                self.assertEqual(game.state, before)
                self.assertEqual(len(game.decisions), count)
                self.assertTrue(game.submit(useful_order(game.human_orders())))
                self.assertEqual(game.state.active_army, human)
                self.assertEqual(len(game.decisions), count + 2)

    def test_seeded_deployments_and_restart(self):
        a = LiveGame("Red", "random", "Blue", "random", 11)
        b = LiveGame("Red", "random", "Blue", "random", 11)
        self.assertEqual(a.initial, b.initial)
        self.assertEqual(a.state, b.state)
        a.submit(useful_order(a.human_orders()))
        a.reset()
        self.assertEqual(a.state, b.state)
        a.new_seed()
        self.assertEqual(a.seed, 12)
        self.assertNotEqual(a.initial, b.initial)

    def test_all_opponents_finish_and_records_open_in_viewer(self):
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / "model.zip"
            env = EchelonEnv()
            model = MaskablePPO("MlpPolicy", env, seed=5, device="cpu", verbose=0,
                                n_steps=16, batch_size=8, n_epochs=1)
            model.save(checkpoint)
            env.close()
            for opponent in ("random", "heuristic", "ppo"):
                game = LiveGame("Red", opponent, "Blue", "random", 21,
                                checkpoint if opponent == "ppo" else None)
                turns = 0
                while not game.state.finished:
                    self.assertTrue(game.submit(useful_order(game.human_orders())))
                    turns += 1
                    self.assertLessEqual(turns, 30)
                path = Path(folder) / f"{opponent}.json"
                game.save(path)
                loaded = load_recordings([path])[0][1]
                self.assertEqual(loaded["final"]["winner"], game.state.winner)
                self.assertEqual(loaded["seed"], 21)
                self.assertEqual(loaded["agent_army"], "Red")
                self.assertEqual(len(loaded["decisions"]), len(game.state.history))
                self.assertIn("Result:", replay_battle(loaded))
                with self.assertRaises(FileExistsError):
                    game.save(path)

    def test_ppo_masks_both_sides_and_rejects_bad_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / "valid.zip"
            env = EchelonEnv()
            model = MaskablePPO("MlpPolicy", env, seed=8, device="cpu", verbose=0,
                                n_steps=16, batch_size=8, n_epochs=1)
            model.save(checkpoint)
            with self.assertRaisesRegex(FileNotFoundError, "not found"):
                PPOGeneral(Path(folder) / "missing.zip", "Blue")
            for army in ("Blue", "Red"):
                game = LiveGame("Red" if army == "Blue" else "Blue",
                                "ppo", army, "random", 32, checkpoint)
                state = game.state
                # AI acted first; reset to a fresh active state for direct adapter check.
                from echelon.engine import new_battle
                state = new_battle(army)
                general = PPOGeneral(checkpoint, army)
                self.assertIn(general.choose(state), legal_orders(state))
            model.observation_space = spaces.Box(0.0, 1.0, shape=(62,), dtype=np.float32)
            bad = Path(folder) / "incompatible.zip"
            model.save(bad)
            with self.assertRaisesRegex(ValueError, "incompatible"):
                PPOGeneral(bad, "Blue")
            env.close()

    def test_pygame_selection_uses_only_highlighted_engine_orders(self):
        from echelon.play import BOARD_X, BOARD_Y, CELL, LiveInterface
        with tempfile.TemporaryDirectory() as folder:
            game = LiveGame("Blue", "heuristic", "Blue", "fixed", 42)
            interface = LiveInterface(game, Path(folder))
            unit = next(u for u in game.state.units
                        if u.army == "Blue" and u.kind == "cavalry")
            self.assertTrue(interface.click_board((BOARD_X + unit.column * CELL + 36,
                                                   BOARD_Y + unit.row * CELL + 36)))
            self.assertEqual(interface.selected_id, unit.id)
            options = interface.targets()
            self.assertTrue(options)
            before = copy.deepcopy(game.state)
            self.assertFalse(interface.click_board((BOARD_X + 7 * CELL + 36,
                                                    BOARD_Y + 4 * CELL + 36)))
            self.assertEqual(game.state, before)
            row, col = options[0].target
            self.assertTrue(interface.click_board((BOARD_X + col * CELL + 36,
                                                   BOARD_Y + row * CELL + 36)))
            self.assertEqual(len(game.decisions), 2)
            screenshot = Path(folder) / "smoke.png"
            interface.run(screenshot=screenshot)
            self.assertGreater(screenshot.stat().st_size, 10_000)

    def test_pygame_hold_attack_and_retreat_controls(self):
        from echelon.play import BOARD_X, BOARD_Y, CELL, LiveInterface
        with tempfile.TemporaryDirectory() as folder:
            hold = LiveGame("Blue", "random", "Blue", "fixed", 4)
            ui = LiveInterface(hold, Path(folder))
            self.assertTrue(ui.select("B-I"))
            self.assertTrue(ui.set_mode(OrderType.HOLD))
            self.assertEqual(hold.decisions[0]["action"], "HOLD")

            attack = LiveGame("Blue", "random", "Blue", "fixed", 5)
            blue = next(u for u in attack.state.units if u.id == "B-I")
            red = next(u for u in attack.state.units if u.id == "R-I")
            blue.row, blue.column = 3, 3
            red.row, red.column = 4, 3
            ui = LiveInterface(attack, Path(folder))
            ui.select("B-I")
            ui.set_mode(OrderType.ATTACK)
            self.assertEqual([o.target for o in ui.targets()], ["R-I"])
            self.assertTrue(ui.click_board((BOARD_X + red.column * CELL + 36,
                                            BOARD_Y + red.row * CELL + 36)))
            self.assertEqual(attack.decisions[0]["action"], "ATTACK")

            retreat = LiveGame("Red", "random", "Red", "fixed", 6)
            red_cavalry = next(u for u in retreat.state.units if u.id == "R-C")
            blue_cavalry = next(u for u in retreat.state.units if u.id == "B-C")
            red_cavalry.row, red_cavalry.column = 4, 4
            blue_cavalry.row, blue_cavalry.column = 3, 4
            ui = LiveInterface(retreat, Path(folder))
            ui.select("R-C")
            ui.set_mode(OrderType.RETREAT)
            destination = ui.targets()[0].target
            self.assertTrue(ui.click_board((BOARD_X + destination[1] * CELL + 36,
                                            BOARD_Y + destination[0] * CELL + 36)))
            self.assertEqual(retreat.decisions[0]["action"], "RETREAT")

    def test_pygame_save_finished_game_uses_unique_filename(self):
        from echelon.play import LiveInterface
        with tempfile.TemporaryDirectory() as folder:
            game = LiveGame("Blue", "heuristic", "Blue", "fixed", 12)
            while not game.state.finished:
                game.submit(useful_order(game.human_orders()))
            ui = LiveInterface(game, Path(folder))
            first = ui.save()
            second = ui.save()
            self.assertNotEqual(first, second)
            self.assertEqual(load_recordings([first])[0][1]["final"]["winner"],
                             game.state.winner)

    def test_setup_panel_switches_options_and_rejects_missing_ppo(self):
        from echelon.play import LiveInterface
        game = LiveGame("Blue", "heuristic", "Blue", "fixed", 10)
        ui = LiveInterface(game)
        ui.open_setup()
        ui.command("set:human_army:Red")
        ui.command("set:opponent:random")
        ui.command("set:first_army:Blue")
        ui.command("set:deployment:random")
        ui.command("seed_up")
        self.assertTrue(ui.start_setup())
        self.assertEqual((ui.game.human_army, ui.game.opponent_name,
                          ui.game.first_army, ui.game.deployment, ui.game.seed),
                         ("Red", "random", "Blue", "random", 11))
        self.assertEqual(len(ui.game.decisions), 1)  # AI had the first move.
        ui.open_setup()
        ui.settings["opponent"] = "ppo"
        ui.settings["checkpoint"] = Path("missing-model.zip")
        self.assertFalse(ui.start_setup())
        self.assertTrue(ui.setup_open)
        self.assertEqual(ui.game.opponent_name, "random")
        self.assertIn("not found", ui.status)


if __name__ == "__main__":
    unittest.main()
