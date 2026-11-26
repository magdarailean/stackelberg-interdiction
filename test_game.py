import unittest

from checkpoints.game import solve_game, restricted_game


class GameTest(unittest.TestCase):
    def test_generated_columns_match_exact(self) -> None:
        from checkpoints.defender import Rules
        from checkpoints.game import generate_responses, schedules
        from test_interdiction import A, B, instance
        samples = [instance(3, 2), instance(4, 2)]
        rules = Rules(((A, B),)*2, 2, 2)
        plans, _ = schedules(rules, 1, 1000, [])
        exact = solve_game([[s.mean(p) for s in samples] for p in plans])
        pool = [frozenset()]
        generated = generate_responses(samples, rules, pool, [[s.mean(pool[0]) for s in samples]], 5, 20)
        self.assertAlmostEqual(generated["lower"], exact["upper"])
        self.assertAlmostEqual(generated["upper"], exact["upper"])

    def test_hidden_mixture_strictly_beats_revelation(self) -> None:
        from checkpoints.study import observed_choices
        matrix = [[1., 5., 2.], [5., 1., 2.]]
        game = solve_game(matrix)
        mass = game["mass"]
        self.assertAlmostEqual(game["upper"], 3.)
        self.assertLess(game["upper"], min(map(max, matrix)))
        seen = observed_choices(matrix, mass, True)
        self.assertGreater(sum(p*matrix[i][seen[i]] for i,p in mass.items()), game["upper"])

    def test_matching_and_pure_games(self) -> None:
        for matrix, exact in [([[0, 2], [2, 0]], 1), ([[4, 4], [2, 3]], 3)]:
            game = solve_game(matrix)
            self.assertAlmostEqual(game["lower"], exact)
            self.assertAlmostEqual(game["upper"], exact)
            p, _ = restricted_game(matrix, [0, 1], [0, 1])
            self.assertAlmostEqual(max(sum(p[i]*matrix[i][j] for i in range(2))
                                       for j in range(2)), exact)
