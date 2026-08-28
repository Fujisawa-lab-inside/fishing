from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "docs/results/stage20-regularized-multizone-continuous-fields-v1"
REPORT = RESULT / "report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class RegularizedMultizoneContinuousFieldsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.fields_path = ROOT / cls.report["candidate"]["fieldArtifact"]["path"]

    def test_artifact_and_checks(self) -> None:
        self.assertEqual(sha256(self.fields_path), self.report["candidate"]["fieldArtifact"]["sha256"])
        self.assertTrue(all(self.report["checks"].values()))
        self.assertFalse(self.report["decision"]["adopted"])
        self.assertFalse(self.report["decision"]["YodaRunAuthorized"])

    def test_fields_are_constant_surface_and_volume_matched(self) -> None:
        with np.load(self.fields_path, allow_pickle=False) as archive:
            depth = np.asarray(archive["continuous_depth_m"], dtype=np.float64)
            bed = np.asarray(archive["continuous_bed_elevation_m"], dtype=np.float64)
            eta = float(np.asarray(archive["reference_eta_m"])[0])
        self.assertTrue(np.all(np.isfinite(depth)))
        self.assertGreaterEqual(float(np.min(depth)), 0.05)
        self.assertLessEqual(float(np.max(np.abs(depth + bed - eta))), 1e-14)
        for side in ("upstream", "downstream"):
            target = self.report["targetVolumeM3"][side]
            final = self.report["finalVolumeM3"][side]
            self.assertLessEqual(abs(final - target) / target, 1e-12)

    def test_structure_and_p2_arrays_are_explicit(self) -> None:
        with np.load(self.fields_path, allow_pickle=False) as archive:
            upstream = np.asarray(archive["upstream_component_mask"], dtype=np.uint8)
            donor = np.asarray(archive["p2_donor_overlap_area_m2"], dtype=np.float64)
            receiver = np.asarray(archive["p2_receiver_overlap_area_m2"], dtype=np.float64)
            gate_faces = np.asarray(archive["gate_face_id"], dtype=np.int64)
            upstream_cells = np.asarray(archive["barrage_upstream_cell_id"], dtype=np.int64)
        self.assertEqual(set(np.unique(upstream).tolist()), {0, 1})
        self.assertGreater(int(np.count_nonzero(donor)), 0)
        self.assertGreater(int(np.count_nonzero(receiver)), 0)
        self.assertFalse(np.any((donor > 0.0) & (receiver > 0.0)))
        self.assertEqual(len(gate_faces), len(upstream_cells))


if __name__ == "__main__":
    unittest.main()
