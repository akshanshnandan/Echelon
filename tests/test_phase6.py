"""Regression checks for recording, paired scenarios, and continuation."""
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import torch
from sb3_contrib import MaskablePPO

from echelon.env import EchelonEnv
from echelon.evaluate import evaluate_model, test_situations
from echelon.recording import record_battle, replay_battle, summarize
from echelon.scenarios import FINAL_TEST_BASE_SEED, SIDE_FIRST, scenario_seed
from echelon.train import TrainingEnv, continue_training


class Phase6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_record_replay_and_seeded_determinism(self):
        seed = scenario_seed("dev", 2027, 0)
        args = ("heuristic", "random", seed, "Red", "Blue")
        first = record_battle(*args)
        second = record_battle(*args)
        self.assertEqual(first, second)
        self.assertIn("Result:", replay_battle(first))
        self.assertEqual(first["classification"],
                         "decisive" if first["final"]["reason"] == "elimination" else "tiebreak")
        self.assertEqual(first["invalid_actions"], 0)
        self.assertEqual(summarize([first])["battles"], 1)
        altered = json.loads(json.dumps(first))
        altered["decisions"][0]["legal_count"] += 1
        with self.assertRaises(ValueError):
            replay_battle(altered)

    def test_disjoint_seed_pools_and_mirrors(self):
        pools = [{scenario_seed(split, FINAL_TEST_BASE_SEED if split == "final" else 2027, i)
                  for i in range(100)}
                 for split in ("train", "eval", "dev", "final")]
        for i in range(4):
            for j in range(i + 1, 4):
                self.assertTrue(pools[i].isdisjoint(pools[j]))
        situations = list(test_situations(400, 2027, "dev"))
        self.assertEqual(len({x[0] for x in situations}), 100)
        self.assertEqual(Counter((side, first) for _, side, first in situations),
                         {assignment: 100 for assignment in SIDE_FIRST})

    def test_mixed_opponent_is_reproducible_and_balanced(self):
        first = TrainingEnv(77, "random", "random", 0.30)
        second = TrainingEnv(77, "random", "random", 0.30)
        names = []
        for _ in range(400):
            _, info = first.reset()
            _, duplicate = second.reset()
            self.assertEqual(info["opponent"], duplicate["opponent"])
            self.assertEqual(info["episode_seed"], duplicate["episode_seed"])
            names.append(info["opponent"])
        self.assertTrue(90 <= names.count("random") <= 150)
        self.assertEqual(set(first.assignments.values()), {100})
        first.close()
        second.close()

    def test_masked_eval_counts_and_outcomes(self):
        env = EchelonEnv()
        model = MaskablePPO("MlpPolicy", env, seed=2, device="cpu", verbose=0,
                           n_steps=16, batch_size=8, n_epochs=1)
        result = evaluate_model(model, "heuristic", list(test_situations(4, 3, "dev")))
        self.assertEqual(result.episodes, 4)
        self.assertEqual(result.invalid_actions, 0)
        self.assertEqual(sum(result.actions.values()), result.decisions)
        self.assertEqual(sum(result.by_seed[next(iter(result.by_seed))][key]
                             for key in ("wins", "losses", "draws")), 4)
        self.assertEqual(result.decisive_wins + result.decisive_losses +
                         result.time_wins + result.time_losses + result.time_draws, 4)
        env.close()

    def test_checkpoint_continuation(self):
        env = TrainingEnv(3, "random", "random")
        model = MaskablePPO("MlpPolicy", env, seed=3, device="cpu", verbose=0,
                           n_steps=16, batch_size=8, n_epochs=1)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.zip"
            model.save(source)
            original = source.read_bytes()
            report = continue_training(source, 16, 4, Path(folder) / "continued")
            repeated = continue_training(source, 16, 4, Path(folder) / "repeated")
            self.assertEqual(source.read_bytes(), original)
            self.assertGreater(report["actual_additional_timesteps"], 0)
            self.assertEqual(report["training_seeds"], repeated["training_seeds"])
            loaded = MaskablePPO.load(Path(folder) / "continued" / "train_final.zip",
                                      device="cpu")
            again = MaskablePPO.load(Path(folder) / "repeated" / "train_final.zip",
                                     device="cpu")
            self.assertEqual(loaded.num_timesteps, report["final_timesteps"])
            for name, value in loaded.policy.state_dict().items():
                self.assertTrue(torch.equal(value, again.policy.state_dict()[name]), name)
        env.close()


if __name__ == "__main__":
    unittest.main()
