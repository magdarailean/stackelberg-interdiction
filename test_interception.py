import unittest

import networkx as nx

from checkpoints.defender import Rules
from checkpoints.evaluate import Sample
from checkpoints.interception import accounting_totals, expected_interception, optimize_interception
from checkpoints.follower import Scenario


class InterceptionOptimizerTest(unittest.TestCase):
    def setUp(self):
        graph = nx.DiGraph()
        graph.add_edge("S", "A", capacity=5.0)
        graph.add_edge("A", "T", capacity=5.0)
        graph.add_edge("S", "B", capacity=5.0)
        graph.add_edge("B", "T", capacity=5.0)
        self.scenario = Scenario(graph, "S", "T")
        self.sample = Sample(((self.scenario,),), factor=0.3)
        self.rules = Rules(((('A', 'T'), ('B', 'T')),), budget=1, crews=1)
        self.cfg = {
            "processing_per_crew_hour": 10.0,
            "detection_probability": 0.25,
            "civilian_arrivals": 0,
            "minutes_per_arrival": 0,
            "officers_per_site": 1,
        }

    def test_cut_milp_matches_exhaustive_fixed_hour_optimum(self):
        feasible = [frozenset({(0, edge)}) for edge in self.rules.allowed[0]]
        values = [expected_interception(self.sample, plan, self.cfg) for plan in feasible]
        result = optimize_interception(
            self.sample, self.rules, self.cfg, 5.0, incumbent=feasible[0], target_hours=1,
        )
        self.assertAlmostEqual(result.value, max(values), places=6)
        self.assertAlmostEqual(result.lower_bound, max(values), places=6)
        self.assertLessEqual(result.upper_bound, max(values) + 1e-6)
        self.assertAlmostEqual(result.absolute_gap, 0.0, places=6)
        self.assertEqual(len(result.plan), 1)
        self.assertGreater(result.cuts, 0)

    def test_deferral_is_separate_from_interception(self):
        plan = frozenset({(0, ('A', 'T'))})
        totals = accounting_totals(self.sample, plan, self.cfg)
        self.assertAlmostEqual(
            totals["supply"], totals["delivered"] + totals["intercepted"]
            + totals["deferred"] + totals["undeparted"], places=6,
        )
        self.assertGreater(totals["deferred"], 0.0)
        self.assertGreater(totals["intercepted"], 0.0)


if __name__ == "__main__":
    unittest.main()
