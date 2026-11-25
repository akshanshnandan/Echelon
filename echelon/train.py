"""First MaskablePPO experiment; the battle engine and sparse reward stay fixed."""
import argparse
import csv
import json
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import sb3_contrib
import stable_baselines3
import torch
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList, CheckpointCallback
from stable_baselines3.common.logger import configure

from .env import EchelonEnv
from .scenarios import SIDE_FIRST, scenario_seed


class TrainingEnv(EchelonEnv):
    """Choose a new seeded scenario and balanced assignment each episode."""

    def __init__(self, base_seed: int, opponent: str, deployment: str,
                 opponent_mix: float | None = None):
        super().__init__(opponent=opponent, deployment=deployment)
        if opponent_mix is not None and not 0 <= opponent_mix <= 1:
            raise ValueError("opponent_mix must be a probability from 0 to 1")
        self.base_seed = base_seed
        self.opponent_mix = opponent_mix  # Probability of RandomGeneral.
        self.episode_index = 0
        self.current_seed = None
        self.assignments = Counter()
        self.opponents = Counter()
        self.used_seeds = []

    def reset(self, *, seed=None, options=None):
        index = self.episode_index
        side, first = SIDE_FIRST[index % len(SIDE_FIRST)]
        self.current_seed = scenario_seed("train", self.base_seed, index)
        selected = ("random" if random.Random(self.current_seed ^ 0xEC4E10).random()
                    < self.opponent_mix else "heuristic") if self.opponent_mix is not None else self.opponent_name
        self.used_seeds.append(self.current_seed)
        self.assignments[(side, first)] += 1
        self.opponents[selected] += 1
        self.episode_index += 1
        return super().reset(seed=self.current_seed,
                             options={"agent_army": side, "first_army": first,
                                      "opponent": selected})

    def _info(self, **extra):
        return super()._info(episode_index=self.episode_index - 1,
                             episode_seed=self.current_seed, **extra)


class EpisodeStats(BaseCallback):
    """Write one CSV row per finished battle and reject nonfinite rewards."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.episodes = 0
        self.file = None
        self.writer = None

    def _on_training_start(self) -> None:
        self.file = self.path.open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        self.writer.writerow(("episode", "timesteps", "seed", "agent_army", "first_army",
                              "winner", "reason", "rounds", "reward"))

    def _on_step(self) -> bool:
        if not np.isfinite(self.locals["rewards"]).all():
            raise FloatingPointError("Nonfinite training reward")
        for done, reward, info in zip(self.locals["dones"], self.locals["rewards"],
                                      self.locals["infos"]):
            if done:
                self.episodes += 1
                self.writer.writerow((self.episodes, self.num_timesteps,
                    info["episode_seed"], info["agent_army"], info["first_army"],
                    info["winner"] or "Draw", info["reason"],
                    info["completed_rounds"], float(reward)))
                self.file.flush()
        return True

    def _on_training_end(self) -> None:
        if self.file is not None:
            self.file.close()


def train(total_timesteps: int, seed: int, output_dir: Path,
          opponent: str = "random", deployment: str = "random") -> dict:
    if total_timesteps < 1:
        raise ValueError("total_timesteps must be positive")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "train_final.zip").exists():
        raise FileExistsError(f"Training result already exists in {output_dir}")
    torch.set_num_threads(1)  # A small CPU MLP runs faster without thread overhead.
    env = TrainingEnv(seed, opponent, deployment)
    model = MaskablePPO("MlpPolicy", env, seed=seed, device="cpu", verbose=1)
    model.set_logger(configure(str(output_dir), ["stdout", "csv"]))
    model.save(output_dir / "untrained")
    callbacks = CallbackList([
        CheckpointCallback(save_freq=5_000, save_path=str(output_dir / "checkpoints"),
                           name_prefix="model"),
        EpisodeStats(output_dir / "episodes.csv"),
    ])
    started = time.perf_counter()
    model.learn(total_timesteps=total_timesteps, callback=callbacks,
                use_masking=True)
    elapsed = time.perf_counter() - started
    if not all(torch.isfinite(parameter).all().item() for parameter in model.policy.parameters()):
        raise FloatingPointError("Nonfinite policy parameter after training")
    model.save(output_dir / "train_final")
    metadata = {
        "requested_timesteps": total_timesteps,
        "actual_timesteps": model.num_timesteps,
        "wall_seconds": round(elapsed, 3),
        "seed": seed,
        "opponent": opponent,
        "deployment": deployment,
        "episodes_started": env.episode_index,
        "assignments": {f"{side}_first_{first}": count
                        for (side, first), count in env.assignments.items()},
        "training_seeds": env.used_seeds,
        "versions": {"torch": torch.__version__,
                     "stable_baselines3": stable_baselines3.__version__,
                     "sb3_contrib": sb3_contrib.__version__},
    }
    (output_dir / "run.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    model.logger.close()
    env.close()
    print(f"Saved {output_dir / 'train_final.zip'} | {model.num_timesteps} steps | "
          f"{elapsed:.1f} seconds | {env.episode_index} episodes started")
    return metadata


def continue_training(checkpoint: Path, total_timesteps: int, seed: int,
                      output_dir: Path, random_fraction: float = 0.30,
                      deployment: str = "random") -> dict:
    """Resume the exact saved policy; never initialize a replacement on load failure."""
    if total_timesteps < 1:
        raise ValueError("total_timesteps must be positive")
    if not 0 <= random_fraction <= 1:
        raise ValueError("random_fraction must be between 0 and 1")
    checkpoint, output_dir = Path(checkpoint), Path(output_dir)
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    if (output_dir / "train_final.zip").exists():
        raise FileExistsError(f"Training result already exists in {output_dir}")
    torch.set_num_threads(1)
    env = TrainingEnv(seed, "random", deployment, random_fraction)
    # load validates observation/action spaces and restores policy/optimizer.
    model = MaskablePPO.load(checkpoint, env=env, device="cpu", verbose=1)
    initial_steps = model.num_timesteps
    if not all(torch.isfinite(p).all().item() for p in model.policy.parameters()):
        raise FloatingPointError("Loaded checkpoint has nonfinite parameters")
    output_dir.mkdir(parents=True, exist_ok=True)
    model.set_logger(configure(str(output_dir), ["stdout", "csv"]))
    callbacks = CallbackList([
        CheckpointCallback(save_freq=10_000,
                           save_path=str(output_dir / "checkpoints"), name_prefix="model"),
        EpisodeStats(output_dir / "episodes.csv"),
    ])
    started = time.perf_counter()
    model.learn(total_timesteps=total_timesteps, callback=callbacks,
                use_masking=True, reset_num_timesteps=False)
    elapsed = time.perf_counter() - started
    if not all(torch.isfinite(p).all().item() for p in model.policy.parameters()):
        raise FloatingPointError("Nonfinite parameters after continuation")
    model.save(output_dir / "train_final")
    metadata = {
        "source_checkpoint": str(checkpoint), "initial_timesteps": initial_steps,
        "requested_additional_timesteps": total_timesteps,
        "actual_additional_timesteps": model.num_timesteps - initial_steps,
        "final_timesteps": model.num_timesteps, "wall_seconds": round(elapsed, 3),
        "seed": seed, "random_fraction": random_fraction,
        "heuristic_fraction": 1 - random_fraction, "deployment": deployment,
        "episodes_started": env.episode_index,
        "opponent_counts": dict(env.opponents),
        "assignments": {f"{side}_first_{first}": n
                        for (side, first), n in env.assignments.items()},
        "training_seeds": env.used_seeds,
        "versions": {"torch": torch.__version__,
                     "stable_baselines3": stable_baselines3.__version__,
                     "sb3_contrib": sb3_contrib.__version__},
    }
    (output_dir / "run.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    model.logger.close()
    env.close()
    print(f"Saved {output_dir / 'train_final.zip'} | +{metadata['actual_additional_timesteps']} "
          f"steps | {elapsed:.1f} seconds")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the first masked Echelon PPO policy")
    parser.add_argument("--total-timesteps", type=int, default=25_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/first_25000"))
    parser.add_argument("--opponent", choices=("random", "heuristic"), default="random")
    parser.add_argument("--deployment", choices=("fixed", "random"), default="random")
    parser.add_argument("--continue-from", type=Path,
                        help="Load this checkpoint and continue its optimizer and policy")
    parser.add_argument("--random-fraction", type=float, default=0.30)
    args = parser.parse_args()
    if args.continue_from:
        continue_training(args.continue_from, args.total_timesteps, args.seed,
                          args.output_dir, args.random_fraction, args.deployment)
    else:
        train(args.total_timesteps, args.seed, args.output_dir, args.opponent, args.deployment)


if __name__ == "__main__":
    main()
