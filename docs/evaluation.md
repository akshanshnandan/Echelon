# Phase 3: tactical commander and evaluation

## Baseline diagnosis before changing code

The Phase 2 random commander gives every legal attack weight 8, advance 3, retreat 1, and hold 1. On the original 100 games (seeds 42 through 141, alternating first army), 88 reached the time limit. Of 5,894 orders, 3,151 were advances, 1,385 retreats, 590 holds, and only 768 attacks. An attack was available on 2,300 turns, but taken on 768 of them (33%). Eighty-four games ended with at least three effective formations still on the board.

Likely causes: armies start seven rows apart; a commander orders only one formation each turn; the random commander spreads orders across formations and often retreats or holds despite having an attack; and moving back and forth consumes the 30-round budget. These are policy and pacing effects. The benchmark keeps the 8x8 map, initial units, combat, routing, 30-round cap, and tiebreak unchanged. The only engine refactor is a shared `damage_at_distance` function so tactical estimates use the exact existing damage formula.

## HeuristicGeneral

The rule-based commander scores the engine's legal orders and takes the highest. It has no special-case map coordinates or seed answers. Its main rules are:

- An attack receives credit for actual health damage, a large bonus for destroying or routing its target, and a small bonus for targeting artillery. A likely fatal counterattack reduces its score.
- An advance gets credit for reducing distance to the nearest enemy and entering its own attack range. It gets a small bonus for nearby friendly support, and penalties for nearby enemy numbers, immediate incoming damage, or exposing vulnerable artillery at adjacent range.
- A retreat is considered worthwhile only if an enemy can currently destroy or rout the formation and the destination reduces that threat. Recently visited cells carry a large penalty to prevent retreat loops. A trailing army discounts retreats, especially after round 20, because endless flight cannot recover a losing tiebreak.
- A hold has a neutral score when safe. When the army trails on the published tiebreak, holding is penalized and advances get an urgency bonus, so the losing army seeks a fight before the clock expires.
- The commander remembers a few recent cells for each formation. Returning to one is penalized, but still legal if it is the best available order.

The threat estimate looks only at enemies in range *now* and uses the largest single possible incoming hit. It does not search future turns or assume the enemy is random. This keeps the policy inspectable, but it can still miss traps and can stall when protecting a lead.

## Paired benchmark

Use `python -m echelon.benchmark --battles 500 --seed 42`. Each four-game group uses one seed and these assignments, where A is the first named commander:

| Game | A controls | First army |
| --- | --- | --- |
| 1 | Blue | Blue |
| 2 | Red | Red |
| 3 | Blue | Red |
| 4 | Red | Blue |

Thus 500 games use 125 paired seeds, 42 through 166. A and B each control both colors equally and act first equally often. A random commander uses a private `random.Random` stream keyed by the scenario seed and role A or B, so swapping colors does not swap its random stream. Every matchup uses the same scenario seeds. A heuristic commander is deterministic, so repeated paired seeds do not create new behavior in heuristic-vs-heuristic games; those games mainly check side and first-turn symmetry.

The tables count wins, losses, draws, decisive and time-limit wins, average duration, remaining effective health and morale, destroyed and routed formations, order types, and health damage dealt. Win rate gives half credit to a draw. The benchmark observes state changes but does not alter engine rules or consume a commander's random numbers.

### Reference run: 500 games per matchup, seed 42

| Matchup (A vs B) | A wins | B wins | Draws | Time limits | Avg rounds | A decisive wins | A time-limit wins |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Random vs Random | 258 | 230 | 12 | 449 | 29.64 | 22 | 236 |
| Heuristic vs Random | 489 | 11 | 0 | 89 | 21.93 | 405 | 84 |
| Heuristic vs Heuristic | 250 | 250 | 0 | 0 | 20.00 | 250 | 0 |

The heuristic scored 97.8% against random when draws count half, dealt an average of 27.76 health damage per game versus 10.14 for random, and used 3,051 of 3,713 attack opportunities. Random used 1,412 of 3,354 opportunities in that matchup. The heuristic-vs-heuristic row is exactly balanced by the side/first-turn schedule. Because the heuristic uses no randomness and the setup is fixed, its 500 games repeat the same four assignments 125 times; this row checks symmetry and behavior, not performance across diverse battlefield setups.

## Recommendation before training

Keep 30 rounds for now and use the benchmark as a regression baseline. The high random-vs-random time-limit rate reflects weak action selection, while a better commander can produce more decisive battles under the same rules. A time-limit victory is still determined by the documented tiebreak. Before training, decide whether the learning objective should reward that tiebreak or prioritize elimination, and test any proposed round-cap or pacing change with side-swapped benchmarks. A longer cap would give more engagement time but could reward prolonged avoidance and make each training episode more expensive; changing it now would confound the Phase 3 comparison.
