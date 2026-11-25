"""Regression checks for the Phase 5 baseline diagnostic."""
import copy
import random
import unittest

import numpy as np

from echelon.baseline import ASSIGNMENTS, compare
from echelon.engine import apply_order, legal_orders
from echelon.env import EchelonEnv


class BaselineTests(unittest.TestCase):
    def test_paired_assignments_and_action_distributions(self):
        results = compare(8, 9000)
        self.assertEqual(len(results), 4)
        for (deployment, policy), (totals, assignments) in results.items():
            self.assertEqual(sum(totals[k] for k in ("win", "loss", "draw")), 8)
            self.assertEqual(sum(totals[k] for k in ("HOLD", "ADVANCE", "ATTACK", "RETREAT")),
                             totals["decisions"])
            self.assertEqual(set(assignments), set(ASSIGNMENTS))
            self.assertTrue(all(sum(row.values()) == 2 for row in assignments.values()))
            self.assertGreater(totals["layouts"], 0)

    def test_full_episode_matches_engine_both_sides_and_first_turns(self):
        for deployment in ("fixed", "random"):
            for army, first in ASSIGNMENTS:
                env = EchelonEnv(agent_army=army, first_army=first,
                                 opponent="random", deployment=deployment)
                observation, _ = env.reset(seed=1234)
                expected = copy.deepcopy(env.state)
                expected_opponent = copy.deepcopy(env._opponent)
                agent_rng = random.Random(17)
                while not expected.finished:
                    self.assertEqual(env.state.active_army, army)
                    self.assertTrue(env.observation_space.contains(observation))
                    legal = legal_orders(expected)
                    mask = env.action_masks()
                    self.assertEqual(set(np.flatnonzero(mask)),
                                     {env.encode_order(o) for o in legal})
                    valid = np.flatnonzero(mask)
                    action = int(valid[agent_rng.randrange(len(valid))])
                    order = env.decode_action(action)
                    apply_order(expected, order)
                    if not expected.finished:
                        apply_order(expected, expected_opponent.choose(expected))
                    observation, reward, terminated, truncated, info = env.step(action)
                    self.assertEqual(env.state, expected)
                    self.assertEqual((terminated, truncated), (expected.finished, False))
                    self.assertEqual(info["winner"], expected.winner)
                    self.assertEqual(reward,
                        (1.0 if expected.winner == army else
                         -1.0 if expected.winner else 0.0) if expected.finished else 0.0)
                self.assertLessEqual(expected.completed_rounds, 30)


if __name__ == "__main__":
    unittest.main()
