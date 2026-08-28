from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/diagnose_stage20_continuous_all_closed_limiter_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("limiter_diagnosis", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LimiterDiagnosisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = load_module().build_report()

    def test_manifest_and_limiter_identity(self) -> None:
        self.assertTrue(
            all(row["passed"] for row in self.report["source"]["manifestChecks"])
        )
        self.assertEqual(self.report["limiter"]["cellId"], 2554)
        self.assertEqual(
            self.report["limiter"]["selectionCount"],
            self.report["limiter"]["proposalCount"],
        )

    def test_limiter_is_wet_small_refinement_ring_cell(self) -> None:
        diagnosis = self.report["diagnosis"]
        limiter = self.report["limiter"]
        self.assertTrue(diagnosis["smallWetCell"])
        self.assertTrue(diagnosis["onFishwayRefinementRing"])
        self.assertTrue(diagnosis["meshGeometryCauseSupported"])
        self.assertFalse(diagnosis["naturalShallowWaterCauseSupported"])
        self.assertGreater(limiter["depthM"], 0.2)
        self.assertLess(limiter["minimumEdgeM"], 0.5)
        self.assertIn("main_channel_200m_patch", limiter["fixedRoles"])
        self.assertIn(
            "fishway_upstream_refinement_ring",
            {row["meaning"] for row in limiter["constraintEdges"]},
        )

    def test_report_does_not_promote_mesh(self) -> None:
        self.assertIn("NOT_MESH_ADOPTION", self.report["classification"])
        self.assertIn(
            "start_a_36_hour_run_on_the_current_mesh",
            self.report["recommendation"]["doNot"],
        )


if __name__ == "__main__":
    unittest.main()
