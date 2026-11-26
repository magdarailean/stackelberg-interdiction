from itertools import combinations
import unittest

from checkpoints.geo import config, load, planning, rows, samples
from checkpoints.milp import optimize


class FixtureTest(unittest.TestCase):
    def test_snapshot_and_gates(self) -> None:
        graph = load()
        gates = {(r["from_node"], r["to_node"], r["crossing_id"]) for r in rows("crossings.csv")}
        self.assertEqual(gates, {(u,v,a["crossing_id"]) for u,v,a in graph.edges(data=True)
                                if graph.nodes[u]["country"] != graph.nodes[v]["country"]})

    def test_flow_equivalence(self) -> None:
        graph = load()
        rules = planning(graph, "coalition", 1, 2, 1)
        full, small, errors = samples(graph, rules, 50, "regression", True, .3)
        self.assertLessEqual(sum(errors)/len(errors), config()["tolerance"])
        self.assertLess(len(small.days[0][0].graph), len(full.days[0][0].graph))
        for edge in rules.allowed[0]:
            plan = frozenset([(0, edge)])
            for a, b in zip(full.flows(plan), small.flows(plan)):
                self.assertAlmostEqual(a, b)

    def test_pools_and_optimum(self) -> None:
        graph = load()
        for mode in ("single", "coalition"):
            rules = planning(graph, mode, 1, 3, 1)
            full, small, _ = samples(graph, rules, 4, "enum", False, .3)
            result = optimize(small, rules, 5)
            limits = config()["pools"][mode]
            def legal(edges: tuple) -> bool:
                return all(sum(graph.nodes[u]["country"] == country for u, v in edges) <= cap
                           for country, cap in limits.items())
            self.assertTrue(legal(tuple(e for _, e in result.plan)))
            exact = min(full.mean(frozenset((0, e) for e in edges))
                        for size in range(4) for edges in combinations(rules.allowed[0], size)
                        if legal(edges))
            self.assertEqual(result.status, "optimal")
            self.assertAlmostEqual(exact, result.lower)
            self.assertAlmostEqual(exact, full.mean(result.plan))
