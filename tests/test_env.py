"""Gymnasium interface and battle-engine equivalence tests."""
import copy
import random
import unittest

import numpy as np
from gymnasium.utils.env_checker import check_env

from echelon.deployment import randomize_deployment
from echelon.engine import apply_order, legal_orders, new_battle
from echelon.env import ACTION_COUNT, EchelonEnv
from echelon.model import Order, OrderType
from echelon.smoke import run_smoke


class EnvironmentTests(unittest.TestCase):
    def test_checker_and_reset_step_api(self):
        env = EchelonEnv()
        check_env(env, skip_render_check=True)
        observation, info = env.reset(seed=42)
        self.assertEqual(observation.dtype, np.float32)
        self.assertTrue(env.observation_space.contains(observation))
        self.assertEqual(info["agent_army"], "Blue")
        action = int(np.flatnonzero(env.action_masks())[0])
        next_observation, reward, terminated, truncated, next_info = env.step(action)
        self.assertTrue(env.observation_space.contains(next_observation))
        self.assertIn(reward, (-1.0, 0.0, 1.0))
        self.assertIsInstance(terminated, bool)
        self.assertFalse(truncated)
        self.assertFalse(next_info["invalid_action"])

    def test_observations_finite_and_perspective_normalized(self):
        blue = EchelonEnv(agent_army="Blue")
        red = EchelonEnv(agent_army="Red", first_army="Red")
        blue_obs, _ = blue.reset(seed=8)
        red_obs, _ = red.reset(seed=8)
        self.assertEqual(blue_obs.shape, (63,))
        self.assertTrue(np.isfinite(blue_obs).all())
        self.assertTrue(np.isfinite(red_obs).all())
        self.assertTrue(blue.observation_space.contains(blue_obs))
        self.assertTrue(red.observation_space.contains(red_obs))
        np.testing.assert_array_equal(blue_obs[:60], red_obs[:60])

    def test_fixed_encoding_and_masks_match_engine(self):
        for army in ("Blue", "Red"):
            env = EchelonEnv(agent_army=army, first_army=army)
            env.reset(seed=1)
            initial = army[0]
            enemy = "R" if army == "Blue" else "B"
            self.assertEqual(env.action_space.n, ACTION_COUNT)
            self.assertEqual(ACTION_COUNT, 396)
            self.assertEqual(env.encode_order(Order(f"{initial}-I", OrderType.HOLD)), 0)
            self.assertEqual(env.encode_order(Order(f"{initial}-C", OrderType.HOLD)), 132)
            self.assertEqual(env.encode_order(Order(f"{initial}-I", OrderType.ATTACK, f"{enemy}-A")), 131)
            perspective_top = 0 if army == "Blue" else 7
            self.assertEqual(env.encode_order(Order(f"{initial}-I", OrderType.ADVANCE,
                                                    (perspective_top, 0))), 1)
            expected = {env.encode_order(order) for order in legal_orders(env.state)}
            actual = set(np.flatnonzero(env.action_masks()))
            self.assertEqual(actual, expected)
            self.assertTrue(actual)
            for index in actual:
                self.assertEqual(env.encode_order(env.decode_action(int(index))), int(index))

    def test_legal_action_matches_engine_and_opponent_response(self):
        for opponent in ("random", "heuristic"):
            env = EchelonEnv(agent_army="Red", first_army="Red", opponent=opponent)
            env.reset(seed=22)
            order = next(o for o in legal_orders(env.state) if o.kind == OrderType.ADVANCE)
            action = env.encode_order(order)
            expected = copy.deepcopy(env.state)
            expected_opponent = copy.deepcopy(env._opponent)
            apply_order(expected, order)
            if not expected.finished:
                apply_order(expected, expected_opponent.choose(expected))
            _, reward, terminated, truncated, info = env.step(action)
            self.assertEqual(env.state, expected)
            self.assertEqual(terminated, expected.finished)
            self.assertFalse(truncated)
            self.assertEqual(reward, 0.0)
            self.assertEqual(info["agent_order"], expected.history[0])

    def test_invalid_action_is_noop(self):
        env = EchelonEnv()
        before_obs, _ = env.reset(seed=1)
        before_state = copy.deepcopy(env.state)
        invalid = int(np.flatnonzero(~env.action_masks())[0])
        observation, reward, terminated, truncated, info = env.step(invalid)
        np.testing.assert_array_equal(observation, before_obs)
        self.assertEqual(env.state, before_state)
        self.assertEqual((reward, terminated, truncated, info["invalid_action"]),
                         (0.0, False, False, True))
        env.step(ACTION_COUNT + 10)
        self.assertEqual(env.state, before_state)

    def test_both_sides_and_opponent_first(self):
        for army in ("Blue", "Red"):
            other = "Red" if army == "Blue" else "Blue"
            for first in (army, other):
                env = EchelonEnv(agent_army=army, first_army=first)
                _, info = env.reset(seed=5)
                self.assertEqual(env.state.active_army, army)
                self.assertEqual(len(info["opponent_orders"]), int(first != army))
                self.assertEqual(len(env.state.history), int(first != army))
                action = int(np.flatnonzero(env.action_masks())[0])
                _, _, _, _, step_info = env.step(action)
                self.assertEqual(len(step_info["opponent_orders"]), 1)

    def test_reset_options_do_not_change_constructor_defaults(self):
        env = EchelonEnv()
        _, changed = env.reset(seed=5, options={"agent_army": "Red",
                                                 "first_army": "Red",
                                                 "deployment": "random"})
        self.assertEqual((changed["agent_army"], changed["deployment"]), ("Red", "random"))
        _, default = env.reset(seed=5)
        self.assertEqual((default["agent_army"], default["first_army"],
                          default["deployment"]), ("Blue", "Blue", "fixed"))

    def test_seeded_episodes_terminate_and_replay(self):
        def episode(seed, opponent):
            env = EchelonEnv(agent_army="Red", first_army="Blue",
                             opponent=opponent, deployment="random")
            observations = []
            rewards = []
            obs, _ = env.reset(seed=seed)
            rng = random.Random(77)
            while True:
                self.assertTrue(env.observation_space.contains(obs))
                self.assertTrue(np.isfinite(obs).all())
                observations.append(obs.copy())
                valid = np.flatnonzero(env.action_masks())
                action = int(valid[rng.randrange(len(valid))])
                obs, reward, terminated, truncated, info = env.step(action)
                rewards.append(reward)
                if terminated or truncated:
                    self.assertTrue(terminated)
                    self.assertFalse(truncated)
                    self.assertLessEqual(len(rewards), 30)
                    self.assertEqual(reward, 1.0 if info["winner"] == "Red" else
                                     -1.0 if info["winner"] == "Blue" else 0.0)
                    self.assertTrue(all(r == 0.0 for r in rewards[:-1]))
                    self.assertFalse(env.action_masks().any())
                    break
            return observations, rewards, env.state

        for opponent in ("random", "heuristic"):
            first = episode(42, opponent)
            replay = episode(42, opponent)
            self.assertEqual(first[1:], replay[1:])
            for a, b in zip(first[0], replay[0]):
                np.testing.assert_array_equal(a, b)

    def test_builtin_time_limit_is_termination(self):
        env = EchelonEnv(agent_army="Blue", first_army="Blue")
        env.reset(seed=3)
        env.state.completed_rounds = 29
        observation, reward, terminated, truncated, info = env.step(0)  # Blue infantry HOLD
        self.assertTrue(env.observation_space.contains(observation))
        self.assertEqual((reward, terminated, truncated), (0.0, True, False))
        self.assertEqual(info["reason"], "time limit")
        self.assertEqual(info["completed_rounds"], 30)

    def test_random_deployment_valid_reproducible_and_fixed_preserved(self):
        first = new_battle()
        second = new_battle()
        randomize_deployment(first, random.Random(33))
        randomize_deployment(second, random.Random(33))
        self.assertEqual(first, second)
        positions = {(u.row, u.column) for u in first.units}
        self.assertEqual(len(positions), 6)
        for unit in first.units:
            self.assertIn(unit.row, (0, 1) if unit.army == "Blue" else (6, 7))
            self.assertTrue(0 <= unit.column < 8)
            counterpart = next(u for u in first.units if u.army != unit.army and u.kind == unit.kind)
            self.assertEqual((unit.row + counterpart.row, unit.column),
                             (7, counterpart.column))
            self.assertTrue(unit.effective)
        fixed = EchelonEnv()
        fixed.reset(seed=33)
        self.assertEqual(fixed.state, new_battle())
        varied = EchelonEnv(deployment="random")
        varied.reset(seed=33)
        self.assertNotEqual([(u.row, u.column) for u in varied.state.units],
                            [(u.row, u.column) for u in fixed.state.units])

    def test_smoke_counts(self):
        results = run_smoke(8, 9, "both", "random")
        self.assertEqual(sum(row["episodes"] for row in results.values()), 8)
        for row in results.values():
            self.assertEqual(row["wins"] + row["losses"] + row["draws"], row["episodes"])
            self.assertEqual(row["decisive"] + row["time_limits"], row["episodes"])


if __name__ == "__main__":
    unittest.main()
