"""Rules and simulation checks using only the standard library."""
import unittest
from echelon.engine import apply_order, legal_orders, living, new_battle, score
from echelon.model import Order, OrderType
from echelon.simulation import run_batch, run_battle


def unit(state, unit_id):
    return next(u for u in state.units if u.id == unit_id)


class BattleTests(unittest.TestCase):
    def test_initial_armies(self):
        state = new_battle()
        self.assertEqual(len(state.units), 6)
        self.assertEqual({u.kind for u in living(state, "Blue")},
                         {"infantry", "cavalry", "artillery"})
        self.assertEqual({u.kind for u in living(state, "Red")},
                         {"infantry", "cavalry", "artillery"})
        self.assertEqual({u.row for u in living(state, "Blue")}, {0})
        self.assertEqual({u.row for u in living(state, "Red")}, {7})
        self.assertEqual(len({(u.row, u.column) for u in state.units}), 6)

    def test_movement_and_boundaries(self):
        state = new_battle()
        self.assertIn(Order("B-C", OrderType.ADVANCE, (2, 3)), legal_orders(state))
        self.assertNotIn(Order("B-I", OrderType.ADVANCE, (-1, 1)), legal_orders(state))
        self.assertNotIn(Order("B-I", OrderType.ADVANCE, (2, 1)), legal_orders(state))
        with self.assertRaises(ValueError):
            apply_order(state, Order("B-I", OrderType.ADVANCE, (-1, 1)))
        apply_order(state, Order("B-C", OrderType.ADVANCE, (2, 3)))
        self.assertEqual((unit(state, "B-C").row, unit(state, "B-C").column), (2, 3))

    def test_range_and_damage(self):
        state = new_battle()
        blue = unit(state, "B-I")
        blue.row = 6
        self.assertIn(Order("B-I", OrderType.ATTACK, "R-I"), legal_orders(state))
        self.assertNotIn(Order("B-A", OrderType.ATTACK, "R-I"), legal_orders(state))
        apply_order(state, Order("B-I", OrderType.ATTACK, "R-I"))
        self.assertEqual((unit(state, "R-I").health, unit(state, "R-I").morale), (8, 68))

        state = new_battle()
        artillery = unit(state, "B-A")
        artillery.row = 4
        self.assertIn(Order("B-A", OrderType.ATTACK, "R-A"), legal_orders(state))
        artillery.row = 5
        artillery.morale = 60
        apply_order(state, Order("B-A", OrderType.ATTACK, "R-A"))
        self.assertEqual(unit(state, "R-A").health, 5)  # 5 power - 2 lost to morale

    def test_destruction_and_routing(self):
        state = new_battle()
        cavalry = unit(state, "B-C")
        cavalry.row = 6
        red_cavalry = unit(state, "R-C")
        red_cavalry.health = 7
        apply_order(state, Order("B-C", OrderType.ATTACK, "R-C"))
        self.assertEqual(red_cavalry.health, 0)
        self.assertNotIn(red_cavalry, living(state))

        state = new_battle()
        cavalry = unit(state, "B-C")
        cavalry.row = 6
        red_cavalry = unit(state, "R-C")
        red_cavalry.morale = 70
        apply_order(state, Order("B-C", OrderType.ATTACK, "R-C"))
        self.assertGreater(red_cavalry.health, 0)
        self.assertLess(red_cavalry.morale, 30)
        self.assertNotIn(red_cavalry, living(state))

    def test_turn_switching_with_red_first(self):
        state = new_battle("Red")
        self.assertEqual(state.active_army, "Red")
        apply_order(state, Order("R-I", OrderType.HOLD))
        self.assertEqual((state.active_army, state.completed_rounds), ("Blue", 0))
        apply_order(state, Order("B-I", OrderType.HOLD))
        self.assertEqual((state.active_army, state.completed_rounds), ("Red", 1))

    def test_elimination_and_time_limit(self):
        state = new_battle()
        unit(state, "R-C").health = 0
        unit(state, "R-A").health = 0
        blue = unit(state, "B-I")
        blue.row = 6
        unit(state, "R-I").health = 4
        apply_order(state, Order("B-I", OrderType.ATTACK, "R-I"))
        self.assertTrue(state.finished)
        self.assertEqual((state.winner, state.reason), ("Blue", "elimination"))
        self.assertEqual(legal_orders(state), [])

        state = new_battle()
        unit(state, "R-I").health = 11
        for _ in range(30):
            apply_order(state, Order("B-I", OrderType.HOLD))
            apply_order(state, Order("R-I", OrderType.HOLD))
        self.assertEqual((state.completed_rounds, state.reason, state.winner),
                         (30, "time limit", "Blue"))
        self.assertGreater(score(state, "Blue"), score(state, "Red"))

    def test_seed_replay(self):
        first = run_battle(42, "Red")
        replay = run_battle(42, "Red")
        self.assertEqual((first.history, first.winner, score(first, "Blue")),
                         (replay.history, replay.winner, score(replay, "Blue")))

    def test_batch_of_100(self):
        results, states = run_batch(100, 42)
        self.assertEqual(len(states), 100)
        self.assertEqual(sum(results.values()), 100)
        self.assertTrue(all(s.finished and s.completed_rounds <= 30 for s in states))
        self.assertEqual([s.first_army for s in states[:2]], ["Blue", "Red"])


if __name__ == "__main__":
    unittest.main()
