"""Viewer inputs and locked final-test bookkeeping; no final battles run here."""
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from echelon.final_test import paired_difference, verify_selection
from echelon.recording import record_battle, replay_battle
from echelon.replay_data import battle_stats, load_recordings, terminal_caption, validate_record
from echelon.scenarios import FINAL_TEST_BASE_SEED, scenario_seed


class ReplayDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = record_battle("heuristic", "heuristic",
                                   scenario_seed("dev", 2027, 0), "Blue", "Blue")

    def test_existing_format_and_comparison_bundle(self):
        old = copy.deepcopy(self.record)
        for step in old["decisions"]:
            step.pop("legal_orders", None)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "phase6.json"
            path.write_text(json.dumps([old]), encoding="utf-8")
            loaded = load_recordings([path])
            self.assertEqual(loaded[0][1], json.loads(json.dumps(old)))
            self.assertIn("Result:", replay_battle(old))
            bundle = Path(folder) / "comparison.json"
            bundle.write_text(json.dumps({"recordings": [
                {"label": "Old", "record": old},
                {"label": "New", "record": self.record}]}), encoding="utf-8")
            self.assertEqual([x[0] for x in load_recordings([bundle])], ["Old", "New"])
            self.assertEqual(battle_stats(old)["survivors"], sum(
                u["effective"] for u in old["final"]["units"].values()
                if u["army"] == old["agent_army"]))

    def test_missing_malformed_and_inconsistent_terminal(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing.json"
            with self.assertRaisesRegex(ValueError, "not found"):
                load_recordings([missing])
            bad = Path(folder) / "bad.json"
            bad.write_text("{wrong", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Could not read"):
                load_recordings([bad])
            broken = copy.deepcopy(self.record)
            broken["final"]["winner"] = "Green"
            with self.assertRaises(ValueError):
                validate_record(broken)
            broken = copy.deepcopy(self.record)
            broken["decisions"][1]["before"]["units"]["B-I"]["health"] = 999
            with self.assertRaisesRegex(ValueError, "continuity"):
                validate_record(broken)

    def test_headless_viewer_renders_real_record(self):
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        from echelon.viewer import ReplayViewer
        with tempfile.TemporaryDirectory() as folder:
            screenshot = Path(folder) / "replay.png"
            ReplayViewer([("Heuristic", self.record)]).run(
                screenshot=screenshot, action_index=len(self.record["decisions"]))
            self.assertGreater(screenshot.stat().st_size, 10_000)

    def test_terminal_caption_uses_agent_perspective_and_reason(self):
        record = {"agent_army": "Blue"}
        self.assertEqual(terminal_caption(record, {"winner": "Blue", "reason": "elimination"}),
                         "Victory  |  Blue by elimination")
        self.assertEqual(terminal_caption(record, {"winner": "Red", "reason": "time limit"}),
                         "Defeat  |  Red by 30-round tiebreak")
        self.assertEqual(terminal_caption(record, {"winner": None, "reason": "time limit"}),
                         "Draw  |  Draw by 30-round tiebreak")


class FinalTestBookkeepingTests(unittest.TestCase):
    def test_frozen_hash_and_seed_separation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "runs/first_25000").mkdir(parents=True)
            (root / "runs/phase6_mixed_50000").mkdir(parents=True)
            for name in ("first_25000", "phase6_mixed_50000"):
                (root / "runs" / name / "run.json").write_text(
                    json.dumps({"training_seeds": [scenario_seed("train", 42, 0)]}))
            (root / "old.zip").write_bytes(b"old")
            (root / "chosen.zip").write_bytes(b"chosen")
            manifest = {"final_seed_split": "final", "final_seed_base": FINAL_TEST_BASE_SEED,
                        "deployment_indices": "0..99", "assignments_per_seed": 4,
                        "opponents": ["random", "heuristic"],
                        "reference_model": "old.zip", "selected_model": "chosen.zip",
                        "reference_sha256": hashlib.sha256(b"old").hexdigest(),
                        "selected_sha256": hashlib.sha256(b"chosen").hexdigest()}
            self.assertTrue(verify_selection(manifest, root)[
                "disjoint_from_recorded_training_and_evaluation"])
            manifest["selected_sha256"] = "wrong"
            with self.assertRaisesRegex(ValueError, "checkpoint differs"):
                verify_selection(manifest, root)

    def test_paired_difference_groups_four_games(self):
        old = {"by_seed": {"a": {"wins": 1, "draws": 1},
                            "b": {"wins": 2, "draws": 0}}}
        new = {"by_seed": {"a": {"wins": 2, "draws": 0},
                            "b": {"wins": 1, "draws": 0}}}
        result = paired_difference(old, new)
        self.assertEqual(result["deployment_groups"], 2)
        self.assertEqual(result["groups_better"], 1)
        self.assertEqual(result["groups_worse"], 1)
        self.assertEqual(result["score_difference"], -0.0625)


if __name__ == "__main__":
    unittest.main()
