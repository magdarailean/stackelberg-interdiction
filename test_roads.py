import json
import sys
import tempfile
import unittest
from pathlib import Path

import networkx as nx

from scripts.build_osm import build


class RoadTest(unittest.TestCase):
    def test_snapshot_checksum_rejects_modified_graph(self):
        from checkpoints.snapshot import inspect_snapshot
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            metadata = build(Path("data/fictional_roads.osm.xml"),output)
            self.assertEqual(inspect_snapshot(output)["directed_edges"],5)
            with (output/metadata["graphml"]).open("ab") as graph:
                graph.write(b"\n")
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                inspect_snapshot(output)
    def test_core_import_does_not_load_optional_geo_packages(self):
        import checkpoints.study  # noqa: F401
        self.assertNotIn("osmium", sys.modules)
        self.assertNotIn("osmnx", sys.modules)
        self.assertNotIn("geopandas", sys.modules)

    def test_road_reduction(self):
        from checkpoints.roadcheck import road_check
        cfg = dict(width=4,segments=4,scenarios=4,capacity=10,closure_probability=.01,factor=.3,tolerance=0.)
        report = road_check(cfg,42)
        self.assertEqual(report["max_relative_error"],0.)
        self.assertEqual(report["comparisons"],16)
        self.assertLess(report["reduced_edges"],report["detailed_edges"])

    def test_direction_parallel_speed_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            metadata = build(Path("data/fictional_roads.osm.xml"),output)
            path = output/metadata["graphml"]
            graph = nx.read_graphml(path,force_multigraph=True)
            self.assertEqual(graph.number_of_edges("2","3"),2)
            self.assertFalse(graph.has_edge("3","2"))
            self.assertTrue(graph.has_edge("4","3"))
            record = graph["2"]["3"]["12:0"]
            self.assertAlmostEqual(record["speed_kmh"],48.28032)
            self.assertAlmostEqual(record["length_m"],111.195,places=2)
            self.assertEqual(metadata,json.loads(path.with_suffix(".json").read_text()))

    def test_fictional_corridor_stress(self):
        from checkpoints.snapshot import corridor_report
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            build(Path("data/fictional_roads.osm.xml"), output)
            report = corridor_report(output, 42)
        self.assertEqual(report["detailed_edges"], 10005)
        self.assertEqual(report["comparisons"], 60)
        self.assertEqual(report["max_flow_error"], 0)
        self.assertEqual(report["max_gap"], 0)
