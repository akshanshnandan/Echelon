"""Commander and paired-evaluation tests."""
import random
import unittest
from collections import Counter

from echelon.benchmark import evaluate, game_schedule
from echelon.engine import apply_order, legal_orders, new_battle
from echelon.generals import HeuristicGeneral, RandomGeneral
from echelon.model import OrderType
from echelon.simulation import run_battle


def unit(state, unit_id):
    return next(u for u in state.units if u.id == unit_id)


class HeuristicTests(unittest.TestCase):
    def test_always_chooses_legal_orders_and_terminates(self):
        for seed in range(10):
            state = new_battle("Blue" if seed % 2 == 0 else "Red")
            generals = {"Blue": HeuristicGeneral(),
                        "Red": RandomGeneral(random.Random(seed))}
            while not state.finished:
                order = generals[state.active_army].choose(state)
                self.assertIn(order, legal_orders(state))
                apply_order(state, order)
            self.assertLessEqual(state.completed_rounds, 30)
            self.assertLessEqual(len(state.history), 60)

    def test_favorable_attack_and_artillery_range(self):
        state = new_battle()
        unit(state, "B-C").row = 6
        unit(state, "R-C").health = 7
        order = HeuristicGeneral().choose(state)
        self.assertEqual((order.kind, order.target), (OrderType.ATTACK, "R-C"))

        state = new_battle()
        unit(state, "B-A").row = 4
        order = HeuristicGeneral().choose(state)
        self.assertEqual((order.kind, order.unit_id, order.target),
                         (OrderType.ATTACK, "B-A", "R-A"))

    def test_retreat_from_lethal_threat(self):
        state = new_battle()
        unit(state, "B-C").row = 6
        unit(state, "B-C").health = 4
        order = HeuristicGeneral().choose(state)
        self.assertEqual((order.kind, order.unit_id), (OrderType.RETREAT, "B-C"))

    def test_hold_when_advance_is_too_dangerous(self):
        state = new_battle()
        for unit_id in ("B-C", "B-A", "R-I", "R-C"):
            unit(state, unit_id).health = 0
        blue = unit(state, "B-I")
        blue.row, blue.column, blue.health = 3, 5, 1
        red = unit(state, "R-A")
        red.column, red.health, red.morale = 5, 1, 30
        self.assertEqual(HeuristicGeneral().choose(state).kind, OrderType.HOLD)

    def test_mirrored_heuristics_engage(self):
        for first in ("Blue", "Red"):
            state = new_battle(first)
            generals = {"Blue": HeuristicGeneral(), "Red": HeuristicGeneral()}
            attacks = 0
            while not state.finished:
                order = generals[state.active_army].choose(state)
                attacks += order.kind == OrderType.ATTACK
                apply_order(state, order)
            self.assertGreater(attacks, 0)
            self.assertEqual(state.reason, "elimination")


class BenchmarkTests(unittest.TestCase):
    def test_paired_schedule_balances_side_and_first_turn(self):
        games = list(game_schedule(8, 42))
        self.assertEqual(Counter(seed for seed, _, _ in games), {42: 4, 43: 4})
        self.assertEqual(Counter((side, first) for _, side, first in games),
                         {(side, first): 2 for side in ("Blue", "Red")
                          for first in ("Blue", "Red")})

    def test_seed_reproducibility_and_counts(self):
        first = evaluate("heuristic", "random", 8, 42)
        replay = evaluate("heuristic", "random", 8, 42)
        self.assertEqual(first, replay)
        self.assertEqual(first.a.wins + first.a.losses + first.a.draws, 8)
        self.assertEqual(first.b.wins, first.a.losses)
        self.assertEqual(first.a.decisive_wins + first.a.time_wins, first.a.wins)
        self.assertEqual(sum(first.a.actions.values()) + sum(first.b.actions.values()), first.orders)
        self.assertLessEqual(first.rounds, 8 * 30)
        self.assertLessEqual(first.a.destroyed + first.a.routed, 8 * 3)

    def test_evaluation_does_not_change_single_battle(self):
        before = run_battle(42, "Red").history
        evaluate("heuristic", "random", 8, 42)
        after = run_battle(42, "Red").history
        self.assertEqual(before, after)

    def test_all_matchups_run(self):
        for a, b in (("random", "random"), ("heuristic", "random"),
                     ("heuristic", "heuristic")):
            result = evaluate(a, b, 4, 7)
            self.assertEqual(result.a.wins + result.a.losses + result.a.draws, 4)
            self.assertEqual(result.b.wins + result.b.losses + result.b.draws, 4)


if __name__ == "__main__":
    unittest.main()
