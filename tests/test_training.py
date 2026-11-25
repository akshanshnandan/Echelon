"""Small checks for masked inference, model files, and held-out evaluation."""
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from echelon.env import EchelonEnv
from echelon.evaluate import Results, evaluate_model, test_situations
from echelon.scenarios import SIDE_FIRST, scenario_seed
from echelon.train import TrainingEnv


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_training_env_rotates_side_first_and_deployments(self):
        env = TrainingEnv(42, "random", "random")
        assignments = []
        layouts = set()
        for _ in range(8):
            observation, info = env.reset()
            self.assertTrue(env.observation_space.contains(observation))
            assignments.append((info["agent_army"], info["first_army"]))
            self.assertEqual(info["episode_seed"] % 2, 0)
            layouts.add(tuple((u.row, u.column) for u in env.state.units))
        self.assertEqual(assignments, list(SIDE_FIRST) * 2)
        self.assertGreater(len(layouts), 2)

    def test_held_out_seeds_and_assignments(self):
        train_seeds = {scenario_seed("train", 42, i) for i in range(1000)}
        situations = list(test_situations(8, 2026))
        eval_seeds = {seed for seed, _, _ in situations}
        self.assertTrue(all(seed % 2 == 1 for seed in eval_seeds))
        self.assertTrue(train_seeds.isdisjoint(eval_seeds))
        self.assertEqual(Counter((side, first) for _, side, first in situations),
                         {assignment: 2 for assignment in SIDE_FIRST})

    def test_masked_inference_save_load_reproducible(self):
        env = EchelonEnv(deployment="random")
        observation, _ = env.reset(seed=12)
        model = MaskablePPO("MlpPolicy", env, seed=12, device="cpu", verbose=0,
                            n_steps=16, batch_size=8, n_epochs=1)
        mask = env.action_masks()
        action, _ = model.predict(observation, action_masks=mask, deterministic=True)
        self.assertTrue(mask[int(np.asarray(action).item())])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model"
            model.save(path)
            loaded = MaskablePPO.load(path, device="cpu")
            replay, _ = loaded.predict(observation, action_masks=mask, deterministic=True)
            self.assertEqual(int(np.asarray(action).item()), int(np.asarray(replay).item()))
            situations = list(test_situations(4, 2026))
            results = evaluate_model(loaded, "random", situations)
            self.assertEqual(results, evaluate_model(loaded, "random", situations))
            self.assertEqual(results.wins + results.losses + results.draws, 4)
            self.assertEqual(results.invalid_actions, 0)
            self.assertEqual(results.decisive_wins + results.decisive_losses +
                             results.time_wins + results.time_losses + results.time_draws, 4)

    def test_outcome_reporting(self):
        row = Results(episodes=4, wins=2, losses=1, draws=1, decisions=100)
        self.assertEqual(row.win_rate, 0.625)
        self.assertEqual(row.average_length, 25.0)


if __name__ == "__main__":
    unittest.main()
