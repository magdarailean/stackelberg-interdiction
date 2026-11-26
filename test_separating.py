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
