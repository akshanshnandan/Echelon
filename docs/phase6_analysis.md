# Phase 6: tactical analysis and mixed-opponent continuation

## How the experiment is controlled

The combat engine, 30-round tiebreak, observations, action encoding, sparse
terminal reward, PPO architecture, and PPO hyperparameters are unchanged.
`recording.py` observes the orders applied by `EchelonEnv`; its replay starts
from the saved deployment, reapplies each order through `engine.apply_order`,
and checks every before/after state and legal-order count. A recorded JSON
battle includes all unit positions, health, and morale for every order. A text
file shows the initial board, orders, final board, and tiebreak scores.

The tactical sample uses development seed base 2027, ten distinct randomized
deployments, and all four side/first-turn assignments per deployment: 40
paired battles for each policy against HeuristicGeneral. The untrained and
Phase 5 policies are loaded from their original checkpoints. The heuristic
agent uses its ordinary commander logic. Each comparison uses the same maps,
assignments, and environment opponent seed. When policies make different
orders, later opponent legal choices can differ even though its random stream
started from the same seed.

For the larger evaluation, `--split dev --deployment-seeds 100 --seed 2027`
creates 100 distinct deployment seeds per opponent. Each seed has four
mirrored games, for 400 games per opponent and checkpoint. `by_seed` in the
JSON reports the four games together, including outcomes and rounds; these
are 100 map clusters, not 400 independent maps. The `by_side` and `actions`
fields provide side-specific and order distributions. The old Phase 5 `eval`
pool and its files remain intact. `train` seeds are below 2^64 and even;
legacy `eval` seeds are below 2^64 and odd; `dev` uses [2^64, 2^65), and
the reserved `final` pool uses [2^65, 2^65 + 2^63). No battle in this phase
uses the final pool; its reserved base seed is 3037 with 100 deployment
indexes (0 through 99). We should evaluate it only after choosing the next model
and analysis method, with no tuning on its results.

## Recorded tactical behavior before continuation

These numbers are from the 40 matched development battles against
HeuristicGeneral. An attack opportunity means at least one legal ATTACK on
that turn. “First damage” counts the first hit by either army. Position is
the mean acting unit's distance in rows from its home edge, so Blue and Red
are comparable. It measures orders issued from a row, not territorial control.

| Agent | Attack opportunities taken | Damage dealt / received per battle | First damage round | End effective units | Destroyed / routed per battle | End mean morale, all units | HOLD / ADVANCE / ATTACK / RETREAT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Untrained | 58/232 (25%) | 4.43 / 23.68 | 9.08 | 0.60 | 1.88 / 0.53 | 30.14 | 64 / 417 / 58 / 423 |
| Phase 5 final | 85/100 (85%) | 7.78 / 15.10 | 15.30 | 1.53 | 1.15 / 0.33 | 57.13 | 418 / 294 / 85 / 349 |
| HeuristicGeneral | 120/193 (62%) | 13.05 / 13.05 | 13.40 | 1.90 | 0.85 / 0.25 | 66.42 | 428 / 376 / 120 / 102 |

Three observable differences:

1. The trained policy takes a far higher share of its available attacks than
   the untrained policy (85% vs 25%) and loses fewer formations. This is
   compatible with learning when to attack and preserve units, although this
   sample does not isolate which network feature caused the decisions.
2. The trained policy creates fewer attack opportunities than the heuristic
   (100 vs 193) and makes far fewer attacks (85 vs 120). First damage happens
   later (round 15.3 vs 13.4). Its acting cavalry averages only 0.50 rows
   from its home edge, versus 3.07 for the heuristic. This is direct evidence
   of much less forward cavalry positioning in this sample.
3. The trained policy holds 418 times, including 312 cavalry holds, and makes
   459 consecutive agent HOLD or RETREAT pairs. The heuristic also has many
   holds (428), chiefly infantry (426), but advances more (376 vs 294) and
   retreats far less (102 vs 349). Total hold count alone therefore does not
   establish passivity; unit type, movement, and contact rate show the
   difference.

The Phase 5 policy's 40 outcomes were 0 decisive wins, 13 decisive losses,
1 time-limit win, 14 time-limit losses, and 12 draws. All 14 time-limit losses
were decided by the first tiebreak component: the heuristic still had more
combat-effective formations. The policy's sole time-limit win came from
health after equal effective-unit counts. This suggests that delaying contact
often preserves some friendly units but leaves the opponent with a unit-count
lead. It is an observed association, not proof that every HOLD was wrong.

## Development evaluation and continuation

Before continuation, the original Phase 5 policy produced:

| Opponent | W/L/D | Score | Decisive W/L | Time-limit W/L/D | Mean rounds | Blue W/L/D | Red W/L/D |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| RandomGeneral | 363/14/23 | 93.6% | 106/0 | 257/14/23 | 28.12 | 183/6/11 | 180/8/12 |
| HeuristicGeneral | 51/199/150 | 31.5% | 42/73 | 9/126/150 | 27.39 | 30/103/67 | 21/96/83 |

The continued run loads `runs/first_25000/train_final.zip` and uses a fresh,
separate output directory. Every training episode reset independently chooses
RandomGeneral with probability 0.30 and HeuristicGeneral with probability
0.70, using that episode's training seed. Side/first-turn assignments rotate
through all four combinations; deployments remain randomized. Checkpoints are
saved at approximately 10,000 additional steps. PPO rollout boundaries may
make the final additional count slightly larger than requested.

The actual run collected **51,200 additional timesteps** in **395.3 seconds**,
reaching 77,824 total. It started 1,920 episodes: 480 for each assignment.
The seeded opponent choice selected RandomGeneral 619 times (32.2%) and
HeuristicGeneral 1,301 times (67.8%); sampling need not equal the configured
30/70 split exactly. Five checkpoints were saved after 10k, 20k, 30k, 40k,
and 50k additional steps. All 25 PPO progress rows had finite diagnostics.
The short same-checkpoint/same-seed regression run produced identical policy
weights twice on this CPU setup.

All checkpoints used the same 100 development deployments and four mirrored
games per deployment against **each** opponent. Score gives half credit to a
draw. “Additional steps” names the checkpoint save point, not a new run.

| Policy | Additional steps | Random W/L/D | Random score | Heuristic W/L/D | Heuristic score |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase 5 original | 0 | 363/14/23 | 93.6% | 51/199/150 | 31.5% |
| Checkpoint 1 | 10,000 | 369/11/20 | 94.8% | 70/202/128 | 33.5% |
| Checkpoint 2 | 20,000 | 379/11/10 | 96.0% | 83/227/90 | 32.0% |
| Checkpoint 3 | 30,000 | 371/12/17 | 94.9% | 76/206/118 | 33.8% |
| Checkpoint 4 | 40,000 | 371/11/18 | 95.0% | 85/233/82 | 31.5% |
| Checkpoint 5 | 50,000 | 378/10/12 | 96.0% | 104/175/121 | 41.1% |
| Final | 51,200 | 382/7/11 | 96.9% | 86/189/125 | 37.1% |

| Opponent and policy | Decisive W/L | Time-limit W/L/D | Mean rounds | Blue W/L/D | Red W/L/D |
| --- | ---: | ---: | ---: | ---: | ---: |
| Random, original | 106/0 | 257/14/23 | 28.12 | 183/6/11 | 180/8/12 |
| Random, final | 135/0 | 247/7/11 | 27.73 | 190/5/5 | 192/2/6 |
| Heuristic, original | 42/73 | 9/126/150 | 27.39 | 30/103/67 | 21/96/83 |
| Heuristic, checkpoint 5 | 71/96 | 33/79/121 | 26.73 | 47/102/51 | 57/73/70 |
| Heuristic, final | 68/104 | 18/85/125 | 26.61 | 36/111/53 | 50/78/72 |

Agent order counts across each 400-battle row:

| Opponent and policy | HOLD | ADVANCE | ATTACK | RETREAT |
| --- | ---: | ---: | ---: | ---: |
| Random, original | 3,055 | 2,960 | 1,590 | 3,749 |
| Random, final | 1,890 | 3,170 | 1,792 | 4,374 |
| Heuristic, original | 4,877 | 2,407 | 750 | 3,004 |
| Heuristic, final | 1,850 | 3,423 | 1,051 | 4,444 |

Against HeuristicGeneral, the final policy gained 5.6 percentage points of
development score over the original; 48 deployment groups improved, 25 tied,
and 27 worsened. A paired bootstrap that resamples the **100 deployment
groups**, not individual games, gives an illustrative 95% interval of about
-0.4 to +11.8 percentage points. This interval includes zero, so the final
policy's gain is promising but not conclusive. Checkpoint 5 gained 9.6 points
with an illustrative paired interval of +3.3 to +15.6 points, but it was
identified after looking at all checkpoint development results. It needs the
reserved final-test pool for an honest confirmation. That pool remains unused.

Against RandomGeneral, the final score rose 3.3 points (363/14/23 to
382/7/11), so this development evaluation does **not** show a regression on
the easier opponent. The paired bootstrap interval for this difference is
about +1.0 to +5.6 points. All seven evaluated policies made zero invalid
actions. The per-seed JSON allows inspection of the maps behind each change.

A second 40-battle replay sample on the **same** tactical scenarios shows the
continued final policy attacked 127 times versus the original's 85, including
92 artillery attacks versus 41. It held 198 times versus 418, dealt 13.08
health damage per battle versus 7.78, and won 11 battles versus 1. Its
time-limit wins rose from 1 to 6 in that small sample. These are observable
changes in behavior, and they fit the larger improvement in time-limit wins
against the heuristic (9 to 18 for the final, 33 at checkpoint 5). They do
not establish a new general strategy: the final still retreated 450 times in
the 40 battles and still lost 85 of 400 heuristic games at the clock.

The next experiment should **freeze a checkpoint choice before opening the
final-test pool**. Checkpoint 5 is the development leader against the
heuristic while retaining a 96.0% score against random. Evaluate it and the
original on the reserved final pool once, using the same grouped, mirrored
method. If the gain repeats, record more varied deployments and investigate
why the policy still retreats so often and loses effective-unit tiebreaks.
Do not change rewards or combat rules based solely on these development
results.

## Reproduce on Windows PowerShell

From the repository root, use the installed virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m echelon.recording --models runs/first_25000/untrained.zip runs/first_25000/train_final.zip heuristic --opponent heuristic --deployment-seeds 10 --seed 2027 --output runs/phase6_analysis
.\.venv\Scripts\python.exe -m echelon.recording --replay-json runs/phase6_analysis/train_final_battles.json --battle-index 0
.\.venv\Scripts\python.exe -m echelon.evaluate --models runs/first_25000/train_final.zip --deployment-seeds 100 --split dev --seed 2027 --deployment random --output runs/phase6_dev_original.json
.\.venv\Scripts\python.exe -m echelon.train --continue-from runs/first_25000/train_final.zip --total-timesteps 50000 --seed 606 --output-dir runs/phase6_mixed_50000 --random-fraction 0.30 --deployment random
.\.venv\Scripts\python.exe -m echelon.recording --models runs/phase6_mixed_50000/train_final.zip --opponent heuristic --deployment-seeds 10 --seed 2027 --output runs/phase6_continued_analysis
.\.venv\Scripts\python.exe -m echelon.evaluate --models runs/first_25000/train_final.zip runs/phase6_mixed_50000/checkpoints/model_36624_steps.zip runs/phase6_mixed_50000/checkpoints/model_46624_steps.zip runs/phase6_mixed_50000/checkpoints/model_56624_steps.zip runs/phase6_mixed_50000/checkpoints/model_66624_steps.zip runs/phase6_mixed_50000/checkpoints/model_76624_steps.zip runs/phase6_mixed_50000/train_final.zip --deployment-seeds 100 --split dev --seed 2027 --deployment random --output runs/phase6_dev_comparison.json
```

The JSON files live under `runs/`, which is ignored by Git. The replay and
analysis files are large because they retain every state transition. The
training command protects an existing `train_final.zip`; use a fresh output
directory for a repeat run, then point evaluation at that directory. The
evaluation is deterministic on this CPU setup for a fixed checkpoint and
scenario list. Deployment seeds are clustered; the paired intervals above
resample whole deployment groups. A development result can guide the next experiment;
it is not a final untouched test result.
