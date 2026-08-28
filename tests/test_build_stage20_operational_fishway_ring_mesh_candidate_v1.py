from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "docs/results/stage20-operational-fishway-ring-5p5m-mesh-candidate-v1"
REPORT = RESULT / "report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class OperationalFishwayRingMeshCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.mesh_path = ROOT / cls.report["artifact"]["path"]

    def test_artifact_identity_and_static_checks(self) -> None:
        self.assertEqual(sha256(self.mesh_path), self.report["artifact"]["sha256"])
        self.assertTrue(all(self.report["checks"].values()))
        self.assertFalse(self.report["decision"]["adopted"])
        self.assertFalse(self.report["decision"]["longRunPermitted"])
        self.assertFalse(self.report["decision"]["runThis44734CellCandidateNext"])
        self.assertGreater(
            self.report["candidate"]["mesh"]["cellCount"],
            self.report["currentR1C"]["cellCount"],
        )

    def test_small_cell_is_removed(self) -> None:
        candidate = self.report["candidate"]["mesh"]
        baseline = self.report["baselineR20"]
        self.assertLess(baseline["minimumCellEdgeM"], 0.4)
        self.assertGreaterEqual(candidate["minimumCellEdgeM"], 0.75)
        self.assertEqual(candidate["cellMinimumEdgeBelow0_25MCount"], 0)
        self.assertEqual(candidate["cellAreaBelow0_25M2Count"], 0)

    def test_physical_anchors_are_not_moved(self) -> None:
        change = self.report["change"]
        self.assertEqual(change["fishwayCentresMovedM"], 0.0)
        self.assertEqual(change["physicalP2FootprintsMovedM"], 0.0)
        self.assertEqual(change["barrageAndGateGeometryMovedM"], 0.0)
        self.assertEqual(change["openBoundaryEndpointsMovedM"], 0.0)
        self.assertGreater(min(change["minimumP2FootprintClearanceM"].values()), 0.0)

    def test_mesh_contains_only_finite_positive_triangles(self) -> None:
        with np.load(self.mesh_path, allow_pickle=False) as archive:
            vertices = np.asarray(archive["vertices_m"], dtype=np.float64)
            triangles = np.asarray(archive["triangles"], dtype=np.int64)
        points = vertices[triangles]
        twice_area = np.abs(
            (points[:, 1, 0] - points[:, 0, 0])
            * (points[:, 2, 1] - points[:, 0, 1])
            - (points[:, 1, 1] - points[:, 0, 1])
            * (points[:, 2, 0] - points[:, 0, 0])
        )
        self.assertTrue(np.all(np.isfinite(vertices)))
        self.assertTrue(np.all(twice_area > 0.0))


if __name__ == "__main__":
    unittest.main()
