from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "docs/results/stage20-regularized-multizone-mesh-candidate-v1"
REPORT = RESULT / "report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class RegularizedMultizoneMeshCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.mesh_path = ROOT / cls.report["artifact"]["path"]

    def test_identity_and_static_gates(self) -> None:
        self.assertEqual(sha256(self.mesh_path), self.report["artifact"]["sha256"])
        self.assertTrue(all(self.report["checks"].values()))
        self.assertFalse(self.report["decision"]["adopted"])
        self.assertFalse(self.report["decision"]["YodaRunAuthorized"])

    def test_candidate_improves_cell_and_edge_cost_components(self) -> None:
        mesh = self.report["candidate"]["mesh"]
        proxy = self.report["costProxy"]
        self.assertLess(mesh["cellCount"], proxy["referenceR1CCellCount"])
        self.assertGreaterEqual(mesh["minimumCellEdgeM"], 0.75)
        self.assertLess(proxy["conservativeCellTimesInverseEdgeWorkRatio"], 0.5)
        self.assertGreater(proxy["estimatedSpeedup"], 2.0)

    def test_hydraulic_topology_is_preserved(self) -> None:
        hydraulic = self.report["candidate"]["hydraulic"]
        self.assertEqual(hydraulic["allClosedMainCutComponents"], 2)
        self.assertTrue(hydraulic["anyOpenMainCutOne"])
        self.assertTrue(hydraulic["fishwayAll256One"])

    def test_mesh_arrays_are_finite_and_positive(self) -> None:
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
