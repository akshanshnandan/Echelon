# Phase 4: Gymnasium environment

## The basic vocabulary

An **environment** is the interface a learning program uses to interact with a game. An **observation** is the numeric state it sees before choosing an **action**. An action is an order for one formation. The **reward** tells it whether the battle ended in a win, loss, or draw. An **episode** is one complete battle, from `reset()` through a terminal `step()`.

`EchelonEnv` wraps the existing engine in `env.py`. `engine.py` still owns movement, combat, morale, routing, turn order, and the 30-round tiebreak. The environment handles numeric encoding, opponent turns, and Gymnasium return values. It does not train a model.

## Dependencies and setup

Use Python 3.11 through 3.14. `requirements.txt` pins `gymnasium==1.4.0` and `numpy==2.3.5`, along with the Phase 5 training packages; the full set is tested on Python 3.14. The [Gymnasium 1.4.0 package page](https://pypi.org/project/gymnasium/1.4.0/) and [NumPy 2.3.5 package page](https://pypi.org/project/numpy/2.3.5/) list their supported Python versions. Gymnasium's [custom environment guide](https://gymnasium.farama.org/main/introduction/create_custom_env/) describes the API used here.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m echelon.smoke --episodes 100 --seed 42
```

The smoke command runs 100 complete episodes total, 50 against RandomGeneral and 50 against HeuristicGeneral. It alternates agent side and first army and samples only legal indexes from the mask. `--opponent random` or `--opponent heuristic` uses all episodes against one opponent; `--deployment fixed` keeps the old layout. No learning occurs.

## Reset and turns

```python
from echelon.env import EchelonEnv
import numpy as np

env = EchelonEnv(agent_army="Blue", opponent="random",
                 first_army="Red", deployment="random")
observation, info = env.reset(seed=42)
mask = env.action_masks()
action = int(np.flatnonzero(mask)[0])
observation, reward, terminated, truncated, info = env.step(action)
```

The agent controls one army. `agent_army`, `first_army`, `opponent`, and `deployment` can also be supplied in `reset(options={...})` for one episode; the next plain reset returns to constructor defaults. If the opponent acts first, `reset()` plays its first order and returns the observation at the agent's first decision. Each legal `step()` applies one agent order and, if the battle is still ongoing, one opponent order. The next observation is therefore at the next agent decision. `info` includes sides, opponent, deployment, winner, reason, completed rounds, and order text.

## Observation: 63 float32 values

The first 30 values describe the agent's infantry, cavalry, and artillery. The next 30 describe the opposing infantry, cavalry, and artillery, in that order. Each formation has ten features:

| Offset within a formation | Meaning |
| ---: | --- |
| 0, 1 | Row and column divided by 7 |
| 2, 3, 4 | One-hot type: infantry, cavalry, artillery |
| 5 | Health divided by that type's starting health |
| 6 | Morale divided by 100 |
| 7, 8, 9 | One-hot status: effective, routed, destroyed |

The final three values are completed rounds divided by 30, whether the agent's army acted first (1 or 0), and whether an agent decision is available (1 while ongoing, 0 after termination). A routed or destroyed formation retains its last coordinates, but its status makes clear that it no longer occupies the board. All values are finite and between 0 and 1.

The perspective is normalized: the agent's formations come first and appear at the top of the board. When the agent controls Red, rows are flipped (`7 - row`) in observations. Columns are unchanged. All unit positions, health, morale, and round information are visible. The opponent's private random-generator state and HeuristicGeneral's short movement memory are not included, so the physical battle is fully visible but the opponent's next choice is not completely predictable from one observation.

## Actions and legal-action masks

`action_space` is `Discrete(396)`. It has three 132-index blocks, one for each agent formation in infantry, cavalry, artillery order. In each block, let `base = 132 * formation_slot`:

| Index within block | Order |
| ---: | --- |
| 0 | HOLD |
| 1–64 | ADVANCE to one of 64 cells, row-major (`1 + 8*row + column`) |
| 65–128 | RETREAT to one of 64 cells, row-major (`65 + 8*row + column`) |
| 129–131 | ATTACK enemy infantry, cavalry, or artillery |

For Red, destination rows in the index are perspective rows: index row 0 means absolute row 7. This keeps the action meaning aligned with the flipped observation. The index always means the same formation, order type, and destination or target, even though only a few indexes are legal in a given state. `encode_order()` and `decode_action()` convert between indexes and engine orders.

`action_masks()` returns a NumPy boolean array of length 396. It marks `True` exactly for indexes encoded from `engine.legal_orders(state)`. Every ongoing agent decision has at least one valid index (HOLD for a living formation). A finished episode has an all-false mask. This matches the `action_masks` convention described by [sb3-contrib's MaskablePPO documentation](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html). See [training.md](training.md) for its first use.

An invalid index, including an in-space index masked `False`, returns the same observation, reward 0, `terminated=False`, `truncated=False`, and `info["invalid_action"]=True`. It does not advance the turn, change the battle, or silently choose another order. Repeated invalid choices can stall an episode, so clients should use the mask. Gymnasium's checker may sample unmasked actions, which is why this safe no-op behavior exists. Calling `step()` before `reset()` or after termination raises a clear error.

## Rewards and endings

Legal intermediate actions return reward 0. A terminal win returns +1, loss -1, and draw 0, always from the agent's side. The engine's elimination and 30-full-round tiebreak are both game outcomes, so they return `terminated=True` and `truncated=False`. There is no added outside cutoff.

This sparse reward is easy to interpret but gives little feedback until battle end. It also treats a time-limit win like an elimination win. Future work could compare reward variants, but changing rewards before a baseline training run would make comparisons harder.

## Seeded deployments

The default is the original fixed layout from `new_battle()`. With `deployment="random"`, three distinct Blue cells are sampled from rows 0–1 and mirrored by row into Red rows 7–6. Corresponding types share a column and have equal starting stats; no positions overlap or leave the board. No terrain or combat rule changes. `reset(seed=...)` seeds Gymnasium's generator, which supplies separate seeds for deployment and the automated opponent. The same seed, options, and legal action sequence reproduce the same episode.

## Remaining research decisions

The 396-slot space is deliberately simple, but many slots are invalid on each turn; a trained policy must use masking. The fixed board and modest deployment variation are still a narrow curriculum. The first experiment mixes both sides and randomized deployments against RandomGeneral. Later experiments can test opponent mixes and whether the current sparse reward and time-limit tiebreak produce the behavior you want. Keep those decisions separate from this validated environment wrapper.
