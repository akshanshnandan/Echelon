# Battle design and rules (Phase 2)

Echelon uses an 8x8 open battlefield. Positions are `(row, column)`, numbered 0 through 7. Blue starts on row 0 and Red on row 7. Each army has one infantry at column 1, cavalry at column 3, and artillery at column 5. The setup is mirrored. A cell holds at most one combat-effective formation.

## Formations

| Kind | Health | Movement | Attack power | Range | Role |
| --- | ---: | ---: | ---: | ---: | --- |
| Infantry | 12 | 1 | 4 | 1 | Balanced |
| Cavalry | 10 | 2 | 5 | 1 | Fast; +2 damage when adjacent |
| Artillery | 8 | 1 | 5 | 3 | Long range; -2 damage when adjacent |

All units start with 100 morale. A unit is combat-effective while its health is above 0 and morale is at least 30. A unit with zero health is destroyed; a unit below 30 morale is routed. Either stops occupying a cell, acting, and counting toward the result. Units do not return after routing.

## Orders and turns

Blue and Red alternate one order per turn. The first army can be selected. A full round is complete when both armies have acted. Each order names one effective formation belonging to the active army. The engine generates valid orders and rejects anything else.

- `HOLD`: remain in place.
- `ADVANCE`: move to an empty reachable cell that decreases Manhattan distance to the nearest effective enemy.
- `RETREAT`: move to an empty reachable cell that increases that distance; restore 5 morale, to a maximum of 100.
- `ATTACK`: target an effective enemy within range.

Distance is `abs(row difference) + abs(column difference)`. Movement uses only horizontal or vertical steps through empty cells. Cavalry may take up to two such steps; other units take one. Diagonal movement, occupied destinations, occupied paths, and off-board positions are illegal. A move that leaves the nearest-enemy distance unchanged is not an advance or retreat.

## Combat

An attack always hits. Base damage is `max(1, attack_power - (100 - attacker_morale) // 20)`. When attacker and target are adjacent, cavalry adds 2 damage and artillery subtracts 2 (still at least 1). The target loses that much health and eight times that amount of morale; both values stop at zero. This makes morale visibly affect attack strength and allows routing before health reaches zero. There are no hidden rolls or random damage.

## End and tiebreak

If one army has no combat-effective formations after an order, the other wins immediately. Otherwise the battle ends after 30 full rounds. At the time limit, compare these values in order for each army:

1. Number of combat-effective formations.
2. Total health of those formations.
3. Total morale of those formations.

The first unequal value decides the winner; exact equality is a draw. The report prints these three values for both armies. Destroyed and routed units score zero. This is a lexicographic tiebreak, not a weighted sum.

## Code boundaries

`model.py` holds plain data records. `engine.py` owns setup, valid-order generation, state changes, and scoring; it does not use randomness. `generals.py` contains random and rule-based commanders that choose from valid orders. `simulation.py` loops through turns and formats reports. This division will let a future commander choose orders through the same engine without changing battle rules.

Phase 3 adds a rule-based commander and paired benchmark without changing these battle rules. The damage formula is also available as `engine.damage_at_distance` so commander estimates and combat execution stay consistent. See [evaluation.md](evaluation.md) for the policy, pairing, metrics, and time-limit diagnosis.
