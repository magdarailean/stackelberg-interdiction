import unittest
from itertools import product
from random import Random

import networkx as nx

from checkpoints.defender import Rules, greedy
from checkpoints.evaluate import Sample
from checkpoints.experiment import experiment
from checkpoints.follower import Scenario
from checkpoints.milp import optimize


def instance(seed: int, slots: int = 3) -> Sample:
    rng = Random(seed)

    def hour() -> Scenario:
        graph = nx.DiGraph()
        graph.add_weighted_edges_from(
            [(0, 1, rng.randint(4, 8)), (1, 2, rng.randint(4, 8)),
             (1, 3, rng.randint(4, 8)), (2, 4, 10), (3, 4, 10)], weight="capacity")
        return Scenario(graph, 0, 4)

    return Sample(tuple(tuple(hour() for _ in range(slots)) for _ in range(2)))


A, B = (1, 2), (1, 3)


class InterdictionTest(unittest.TestCase):
    def test_enumeration(self) -> None:
        sample = instance(17)
        rules = Rules(((A, B), (A,), (A, B)), 2)
        exact = min(sample.mean(frozenset((t, e) for t, e in enumerate(seq) if e))
                    for seq in product((None, A, B), (None, A), (None, A, B))
                    if sum(e is not None for e in seq) <= 2)
        result = optimize(sample, rules, 5)
        self.assertEqual(result.status, "optimal")
        self.assertAlmostEqual(result.lower, exact)
        self.assertAlmostEqual(sample.mean(result.plan), exact)

    def test_twenty_against_greedy(self) -> None:
        rules = Rules(((A, B),)*2, 2, 2)
        strict = False
        for seed in range(20):
            sample = instance(seed, 2)
            heuristic = sample.mean(greedy(rules, sample.mean))
            result = optimize(sample, rules, 5)
            self.assertEqual(result.status, "optimal")
            optimal = sample.mean(result.plan)
            self.assertLessEqual(optimal, heuristic + 1e-8)
            strict |= optimal < heuristic - 1e-8
        self.assertTrue(strict)

    def test_plain_flow(self) -> None:
        for hour in instance(5).days[0]:
            self.assertAlmostEqual(hour.delivered(), nx.maximum_flow_value(hour.graph, 0, 4))

    def test_budget_monotonicity(self) -> None:
        sample = instance(19)
        previous = float("inf")
        for budget in range(5):
            result = optimize(sample, Rules(((A, B),)*3, budget, 2), 5)
            self.assertEqual(result.status, "optimal")
            current = sample.mean(result.plan)
            self.assertLessEqual(current, previous + 1e-8)
            previous = current

    def test_shift_and_crew(self) -> None:
        sample = instance(11, 4)
        for day in sample.days:
            for hour in day:
                hour.graph[0][1]["capacity"] = 20
        rules = Rules(((A,), (A, B), (B,), (B,)), 4, 1, 2)
        result = optimize(sample, rules, 5)
        self.assertTrue(result.plan)
        for t, e in result.plan:
            self.assertIn(e, rules.allowed[t])
            self.assertEqual(sum(h == t for h, _ in result.plan), 1)
            self.assertTrue((t-1, e) in result.plan or (t+1, e) in result.plan)

    def test_oracle(self) -> None:
        train, test = instance(21, 2), instance(12, 2)
        report = experiment(train, {"test": test}, Rules(((A, B),)*2, 2, 2),
                            train.days[0][0].graph, 42, 5)
        split = report["splits"]["test"]
        self.assertEqual(split["oracle_solver"]["status"], "optimal")
        scores = split["policies"]
        oracle = scores["hindsight_oracle_unattainable"]["mean_delivered"]
        for policy in scores.values():
            self.assertLessEqual(oracle, policy["mean_delivered"] + 1e-8)
