import unittest

from checkpoints.accounting import account
from checkpoints.follower import Scenario
from checkpoints.network import toy_graph
from checkpoints.risk import upper_tail
from checkpoints.scale import subdivision_check


class ResearchTest(unittest.TestCase):
    def test_same_hours_different_delay_feasibility(self):
        from checkpoints.defender import Rules
        e = ("a","b")
        rules = Rules(((e,),(e,)),delay_per_slot=(3.,7.5),delay_cap=6.)
        self.assertTrue(rules.feasible(frozenset([(0,e)])))
        self.assertFalse(rules.feasible(frozenset([(1,e)])))
    def test_mixed_risk_objectives(self) -> None:
        from checkpoints.risk import risk_mixture
        matrix = [[0., 8.], [8., 0.]]
        for contamination in (None, 0.2, 1.):
            mass = risk_mixture([matrix], .75, contamination)
            self.assertAlmostEqual(mass[0], .5)
            self.assertAlmostEqual(mass[1], .5)
    def test_weighted_tail(self) -> None:
        self.assertAlmostEqual(upper_tail([2, 10], [.9, .1], .75), 5.2)
        self.assertAlmostEqual(upper_tail([2, 10], [.9, .1], 0), 2.8)

    def test_conservation(self) -> None:
        cfg = dict(processing_per_crew_hour=2, detection_probability=.25, officers_per_site=2,
                   civilian_arrivals=4, minutes_per_arrival=1.5)
        result = account(10, 9, 5, 2, cfg)
        self.assertEqual([result[k] for k in ("delivered", "intercepted", "deferred", "undeparted")],
                         [4, 1, 4, 1])
        self.assertEqual(result["civilian_delay"], 12)
        self.assertEqual(account(10,9,0,2,cfg)["civilian_delay"],6)

    def test_subdivision_capacity(self) -> None:
        result = subdivision_check(Scenario(toy_graph(), "S", "T"), 5)
        self.assertEqual(result["edges"], 5*result["base_edges"])
        self.assertEqual(result["absolute_error"], 0)
