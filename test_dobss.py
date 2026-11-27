import random
import unittest

from checkpoints.dobss import best_pure_value, multiple_lp, solve_dobss


class DOBSSolverTest(unittest.TestCase):
    def test_twenty_random_tiny_games_match_multiple_lp(self):
        rng = random.Random(20261126)
        for game_index in range(20):
            schedule_count = rng.randint(2, 5)
            type_count = rng.randint(1, 3)
            priors = [rng.random() for _ in range(type_count)]
            priors = [p / sum(priors) for p in priors]
            leader, follower = [], []
            for _ in range(type_count):
                action_count = rng.randint(2, 3)
                leader.append([[rng.randint(-5, 12) for _ in range(schedule_count)]
                               for _ in range(action_count)])
                follower.append([[rng.randint(-5, 12) for _ in range(schedule_count)]
                                 for _ in range(action_count)])
            with self.subTest(game=game_index):
                milp = solve_dobss(priors, leader, follower, seconds=10)
                reference = multiple_lp(priors, leader, follower)
                self.assertEqual(milp["status"], "optimal")
                self.assertAlmostEqual(milp["value"], reference["value"], delta=1e-6)

    def test_randomization_has_strictly_positive_value_in_constructed_game(self):
        priors = [1.0]
        leader = [[[0.0, 1.0], [1.0, 0.0]]]
        follower = [[[1.0, 0.0], [0.0, 1.0]]]
        mixed = solve_dobss(priors, leader, follower, seconds=10)
        reference = multiple_lp(priors, leader, follower)
        pure = best_pure_value(priors, leader, follower)
        self.assertAlmostEqual(mixed["value"], 0.5, places=6)
        self.assertAlmostEqual(reference["value"], mixed["value"], delta=1e-6)
        self.assertAlmostEqual(pure, 0.0, places=6)
        self.assertGreater(mixed["value"] - pure, 0.49)


class DistributionTest(unittest.TestCase):
    def test_response_precedes_schedule_draw(self):
        from checkpoints.dobss import distribution_value
        rewards = [[[6, 6], [1, 1]]]
        utilities = [[[4, -2], [0, 0]]]
        self.assertEqual(distribution_value([1], rewards, utilities, {0: .5, 1: .5}), 6)
        self.assertEqual(distribution_value([1], rewards, utilities, {1: 1}), 1)

    def test_complete_schedule_reference(self):
        import json
        from unittest.mock import patch
        from checkpoints.geo import DATA
        from checkpoints.separating import CELLS, run_seed
        config = json.loads((DATA / "research.json").read_text())
        with patch("checkpoints.separating.GRID_SIZE", 6):
            game = run_seed(CELLS[0], 42, 2, config)["game"]
        heldout = game["heldout"]
        self.assertEqual(heldout["complete_schedules"], 7)
        self.assertAlmostEqual(heldout["gain"], heldout["mixed"] - heldout["pure"])
        self.assertGreaterEqual(heldout["training_pool_to_global_upper_gap"], 0)


if __name__ == "__main__":
    unittest.main()
