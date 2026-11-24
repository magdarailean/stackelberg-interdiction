from itertools import combinations
import unittest

import networkx as nx

from interdiction import Scenario, Site, expected_flow, greedy, optimize, synthetic_network


class InterdictionTest(unittest.TestCase):
    def test_sites_can_help_only_in_combination(self):
        graph = nx.DiGraph()
        graph.add_weighted_edges_from(
            [(0, 1, 5), (1, 2, 5), (1, 3, 5), (2, 4, 5), (3, 4, 5)],
            weight="capacity",
        )
        scenarios = [Scenario(graph, 0, 4)]
        sites = (Site((1, 2), 1, 5), Site((1, 3), 1, 5))
        self.assertEqual(greedy(scenarios, sites, 2), ())
        result = optimize(scenarios, sites, 2, 5)
        self.assertEqual(result.status, "optimal")
        self.assertEqual(expected_flow(scenarios, result.schedule), 0)
        self.assertEqual(expected_flow(scenarios), 5)

    def test_milp_matches_enumeration_on_weighted_scenarios(self):
        sites, make = synthetic_network(4, 6)
        first, second = make(7), make(8, shift=True)
        scenarios = [first, Scenario(second.graph, second.source, second.sink, 3)]
        budget = 3
        exact = min(
            expected_flow(scenarios, plan)
            for size in range(len(sites) + 1)
            for plan in combinations(sites, size)
            if sum(s.hours for s in plan) <= budget
        )
        result = optimize(scenarios, sites, budget, 5)
        self.assertEqual(result.status, "optimal")
        self.assertLessEqual(sum(s.hours for s in result.schedule), budget)
        self.assertAlmostEqual(expected_flow(scenarios, result.schedule), exact)
        self.assertAlmostEqual(result.bound, exact)


if __name__ == "__main__":
    unittest.main()
