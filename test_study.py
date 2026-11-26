import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from checkpoints.study import learn, observed_choices
from scripts.osm_inventory import inventory


class StudyTest(unittest.TestCase):
    def test_information(self) -> None:
        matrix = [[2., 0.], [0., 2.]]
        mass = {0: .5, 1: .5}
        for revealed, expected in [(True, 2.), (False, 1.)]:
            choices = observed_choices(matrix, mass, revealed)
            self.assertEqual(sum(p * matrix[i][choices[i]] for i,p in mass.items()), expected)

    def test_learning_sees_only_history(self) -> None:
        matrix = [[2., 0.], [0., 2.]]
        self.assertEqual(learn(matrix, matrix, {1: 1.}, 3, 1., 42), [0., 2., 2.])
        self.assertEqual(learn(matrix,matrix,{0:.3,1:.7},3,1.,33),
                         learn(matrix,matrix,{0:.3,1:.7},12,1.,33)[:3])

    def test_local_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"roads.xml"
            path.write_text('<osm><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/>'
                            '<tag k="oneway" v="-1"/></way></osm>')
            report = inventory(path)
        self.assertEqual(report["explicit_direction_tags"], {"-1": 1})
        self.assertEqual(report["road_segments"], {"primary": 1})

    def test_json_csv_and_balances(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([sys.executable, "-m", "checkpoints.study", "--slots", "1", "--train", "1",
                            "--test", "1", "--output", folder], check=True)
            result = json.loads((Path(folder)/"results.json").read_text())
            with (Path(folder)/"results.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), len(result["measured"]))
            with (Path(folder)/"frontier.csv").open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))),len(result["frontier"]))
            for point in result["frontier"]:
                self.assertLessEqual(point["civilian_delay"],point["delay_cap"])
            self.assertIn(result["selected_alpha"],result["assumptions"]["study"]["alpha_candidates"])
            self.assertEqual(len(result["heldout_replication"]["heldout"]),5)
            self.assertTrue(result["complete_schedule_set"])
            self.assertAlmostEqual(result["proofs"]["training"]["upper"],result["proofs"]["training"]["lower"])
            for row in result["measured"]:
                greedy = next(r for r in result["measured"] if r["policy"]=="greedy" and
                              (r["split"],r["information"])==(row["split"],row["information"]))
                self.assertAlmostEqual(row["gain_over_greedy"],greedy["delivered"]-row["delivered"])
                for prefix in ("", "utility_follower_"):
                    self.assertAlmostEqual(row[prefix+"supply"], sum(row[prefix+k] for k in
                                           ("delivered", "intercepted", "deferred", "undeparted")))
                self.assertLessEqual(row["civilian_delay"], result["assumptions"]["study"]["delay_cap_minutes"])
