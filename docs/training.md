# Phase 5: first masked PPO experiment

## Why the earlier random smoke agent lost

`RandomGeneral` does **not** sample legal orders uniformly. It weights each legal ATTACK 8, ADVANCE 3, HOLD 1, and RETREAT 1. The Phase 4 smoke agent chose uniformly among legal action indexes, giving many more turns to HOLD and RETREAT. In a paired diagnostic with 500 games per row, each side and first-turn assignment appeared 125 times:

| Deployment | Agent choice rule | W/L/D vs RandomGeneral | Win rate (draw half) | Attacks / opportunities | Time limits |
| --- | --- | --- | ---: | ---: | ---: |
| Fixed | Uniform masked | 81/369/50 | 21.2% | 496/4,980 | 492 |
| Fixed | RandomGeneral weights | 258/225/17 | 53.3% | 1,902/5,596 | 461 |
| Randomized | Uniform masked | 67/397/36 | 17.0% | 593/5,863 | 490 |
| Randomized | RandomGeneral weights | 261/222/17 | 53.9% | 2,250/6,186 | 402 |

The diagnostic uses seeds 10000–10124, four mirrored side/first-turn assignments per seed, and the same opponent seeding for the two agent rules. The agent win counts by assignment were fairly similar within each rule. Those 125 seeds produced one fixed layout and 123 distinct randomized layouts. Full-episode tests replayed the wrapper against direct engine calls and found matching turns, masks, states, rewards, and results. Thus the earlier 5–43–2 result reflects a weaker uniform sampler plus a small 50-game sample, not a verified environment bug. `python -m echelon.baseline --episodes 500 --seed 10000` reproduces the comparison.

## What PPO learns

PPO (Proximal Policy Optimization) is a method for improving a policy a little at a time from experience. The neural network receives Echelon's 63 observation values and produces scores for 396 action indexes. MaskablePPO removes illegal indexes before it samples or predicts an order. During training it records observations, chosen orders, and eventual rewards, then updates network weights to make useful choices more likely. A second network output estimates future reward and helps calculate those updates. The network learns patterns in numeric observations; it is not given hand-written tactical rules.

One **timestep** is one environment `step()`: one agent decision and any needed opponent response. It is not one battle or one full round. The reward stays sparse: 0 until the battle ends, then +1 for a win, -1 for a loss, or 0 for a draw. This makes credit assignment difficult because many orders precede the final reward.

The experiment uses the library's default `MlpPolicy` and PPO hyperparameters: 2,048 steps per rollout, batch size 64, ten update epochs, learning rate 0.0003, and discount factor 0.99. It runs on CPU with one PyTorch thread for this small network. [SB3-Contrib's MaskablePPO documentation](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html) describes its masking behavior. We use `MaskablePPO`, not a custom PPO implementation.

## Dependencies

`requirements.txt` pins `gymnasium==1.4.0`, `numpy==2.3.5`, `stable-baselines3==2.9.2`, `sb3-contrib==2.9.2`, and `torch==2.15.0`. The [Stable-Baselines3 package metadata](https://pypi.org/project/stable-baselines3/2.9.2/) permits Gymnasium below 2, NumPy below 3, and PyTorch 2.8 through 2.x. [SB3-Contrib 2.9.2](https://pypi.org/project/sb3-contrib/2.9.2/) requires Stable-Baselines3 2.9.2 or newer; [PyTorch 2.15.0](https://pypi.org/project/torch/2.15.0/) provides a Windows CPython 3.14 wheel. The combination is checked by `pip check` and actual imports before training.

## Training schedule and seeds

`TrainingEnv` selects a new scenario on **every reset**, not once at construction. It rotates these assignments: Blue/Blue-first, Red/Red-first, Blue/Red-first, Red/Blue-first. Randomized deployments use a fresh seed each episode; `--deployment fixed` keeps the original positions. `--opponent random` is the first experiment, while `heuristic` is available for later controlled runs.

`scenario_seed("train", base_seed, episode_index)` always produces an even seed. Held-out evaluation uses `scenario_seed("eval", eval_seed, group_index)`, always odd. These sets cannot overlap. Four evaluation games share one seed while varying side and first turn, and every saved model sees the **same preselected situations**. Train seed 42 and evaluation seed 2026 are the first experiment defaults. Evaluation uses randomized deployments unless explicitly changed.

## Windows commands

From the project root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m echelon.train --total-timesteps 2000 --seed 42 --output-dir runs/smoke_2000 --opponent random --deployment random
.\.venv\Scripts\python.exe -m echelon.train --total-timesteps 25000 --seed 42 --output-dir runs/first_25000 --opponent random --deployment random
.\.venv\Scripts\python.exe -m echelon.evaluate --models runs/first_25000/untrained.zip runs/first_25000/checkpoints/model_5000_steps.zip runs/first_25000/train_final.zip --episodes-per-opponent 100 --seed 2026 --deployment random --output runs/first_25000/evaluation.json
```

Training saves `untrained.zip`, checkpoints every 5,000 timesteps, `train_final.zip`, `episodes.csv` (battle outcomes), `progress.csv` (PPO diagnostics), and `run.json` (timings, versions, assignments, training seeds). The requested timestep count may be rounded up to the next full PPO rollout; `run.json` reports the actual count. `runs/` is ignored by Git.

Evaluation calls `model.predict(..., action_masks=env.action_masks(), deterministic=True)` for **every** model decision. It records wins, losses, draws, decisive and time-limit outcomes, average agent decisions per battle, and invalid action count. We do not use the ordinary SB3 evaluation callback, which does not apply masks. The evaluator can compare `untrained.zip`, intermediate checkpoints, and `train_final.zip` on the same held-out scenarios.

## Reading the result

Evidence of learning would be a higher held-out win rate than the untrained model on the **same** scenarios, ideally on both sides and against both opponents, with zero invalid actions. A 25,000-timestep run is small; an unchanged or worse score would mean this first configuration did not show improvement, not that PPO can never work.

Possible failure modes include sparse rewards, a large mostly invalid action space, overfitting to RandomGeneral or the small deployment zone, a policy that exploits the 30-round tiebreak, and a fixed observation that does not expose the opponent's private decision memory. Check `episodes.csv` for actual wins and `progress.csv` for finite losses before interpreting evaluation. Keep the held-out scenarios fixed; do not tune on that final set.

## First experiment results

The 2,000-step smoke run collected 2,048 steps in 25.1 seconds. Its saved model reloaded, completed a masked episode, had finite parameters, and differed from the untrained weights. Repeating that smoke run with the same seed produced byte-identical episode CSVs, identical training seeds, and identical policy tensors on this CPU setup. The independent 25,000-step run collected 26,624 steps in 320.8 seconds. It started 893 episodes, evenly distributed across the four assignments (224/223/223/223); 892 finished within training. Its 13 saved PPO progress rows contained no nonfinite values. Mean reward in the recent-episode training log moved from -0.812 at the first rollout to +0.18 at the last. That training log is descriptive, not a held-out result.

The held-out evaluation used seed base 2026, 25 separate randomized deployments, and four side/first-turn assignments per deployment: 100 episodes against each opponent for each model. All models saw the same situations and used masks for every decision.

| Model | Opponent | W/L/D | Win rate (draw half) | Decisive W/L | Time-limit W/L/D | Avg agent decisions | Invalid actions |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Untrained | RandomGeneral | 6/78/16 | 14.0% | 0/7 | 6/71/16 | 29.68 | 0 |
| 5,000-step checkpoint | RandomGeneral | 56/30/14 | 63.0% | 7/2 | 49/28/14 | 29.54 | 0 |
| Final (26,624 actual steps) | RandomGeneral | 94/4/2 | 95.0% | 28/0 | 66/4/2 | 27.92 | 0 |
| Untrained | HeuristicGeneral | 0/89/11 | 5.5% | 0/66 | 0/23/11 | 23.96 | 0 |
| 5,000-step checkpoint | HeuristicGeneral | 10/69/21 | 20.5% | 6/45 | 4/24/21 | 26.32 | 0 |
| Final (26,624 actual steps) | HeuristicGeneral | 23/47/30 | 38.0% | 22/20 | 1/27/30 | 25.48 | 0 |

This supports learning on these held-out situations: the final policy improves over its own untrained baseline and an early checkpoint against both opponents. It does not show that the policy beats HeuristicGeneral; its win rate there is below 50%. Evaluation is limited to 25 deployment seeds and the existing open 8x8 map. The next controlled experiment should keep the evaluation set fixed, collect more held-out deployments, and examine action frequencies and time-limit behavior before changing reward or opponent difficulty.
