import unittest

import networkx as nx

from checkpoints.follower import Scenario
from checkpoints.separating import serial_pair


class SeparatingTest(unittest.TestCase):
    def test_serial_sites_share_the_same_capacity_loss(self):
        graph = nx.DiGraph()
        graph.add_nodes_from(("s","t"))
        scenario = Scenario(graph,"s","t")
        a,b,c = serial_pair(scenario,False)
        self.assertAlmostEqual(scenario.delivered((a,),.3),18)
        self.assertAlmostEqual(scenario.delivered((a,b),.3),7.5)
        self.assertAlmostEqual(scenario.delivered((b,c),.3),14.5)

    def test_random_layouts_are_seeded_and_unfiltered(self):
        from checkpoints.random_layouts import random_layout
        layouts = []
        for seed in range(42, 62):
            graph, sites = random_layout(seed)
            self.assertEqual(sites, random_layout(seed)[1])
            self.assertEqual(len(set(sites)), 6)
            self.assertTrue(all(graph.has_edge(*site) for site in sites))
            layouts.append(sites)
        self.assertEqual(len(set(layouts)), 20)

    def test_random_layout_milp_matches_enumeration(self):
        from itertools import combinations
        from checkpoints.defender import Rules
        from checkpoints.interception import expected_interception, optimize_interception
        from checkpoints.random_layouts import draws, random_layout
        layout, sites = random_layout(45)
        sample = draws(layout, "45:train", 4)
        rules = Rules((sites,), budget=2, crews=2)
        cfg = dict(processing_per_crew_hour=240, detection_probability=.6,
                   officers_per_site=2, civilian_arrivals=2, minutes_per_arrival=1.5)
        plans = [frozenset((0, e) for e in pair) for pair in combinations(sites, 2)]
        result = optimize_interception(sample, rules, cfg, 4, incumbent=plans[0], target_hours=2)
        self.assertAlmostEqual(result.value, max(expected_interception(sample, p, cfg) for p in plans))
