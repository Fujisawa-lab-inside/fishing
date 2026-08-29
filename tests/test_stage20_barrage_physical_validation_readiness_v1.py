from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_physical_validation_readiness_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_physical_validation_readiness_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
READINESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READINESS)


class Stage20BarragePhysicalValidationReadinessV1Tests(unittest.TestCase):
    def test_current_evidence_fails_closed_without_gate_state(self) -> None:
        result = READINESS.assess(READINESS.verified_contract())
        self.assertFalse(result["physicalValidationEvidenceReady"])
        self.assertFalse(result["checks"]["gateByGateOpeningAndTimestampPresent"])
        self.assertTrue(result["checks"]["official12hPointFlowHistoryPresent"])
        self.assertFalse(result["checks"]["timeAlignedLevelReleaseAndGateHistoryPresent"])
        self.assertEqual(result["official12hFlowHistory"]["distinctReleaseM3S"], [0.0, 0.3])
        self.assertEqual(result["official12hFlowHistory"]["releaseTransitionCount"], 1)
        self.assertFalse(result["headOnlyDischargeLawIdentifiable"])
        self.assertFalse(result["additionalNumericalExpansionRecommended"])
        self.assertGreater(result["numericalModelDependence"]["oneWayBranchBlockedStepFraction"], 0.9)
        self.assertFalse(result["numericalModelDependence"]["oneWayAssumptionNegligible"])
        self.assertTrue(all(value is False for value in result["promotion"].values()))

    def test_current_official_snapshot_is_fresh_at_recorded_assessment(self) -> None:
        result = READINESS.assess(READINESS.verified_contract())
        self.assertTrue(result["checks"]["officialPointObservationFresh"])
        self.assertAlmostEqual(result["officialObservation"]["upstreamMinusDownstreamHeadM"], 0.59)
        self.assertEqual(result["officialObservation"]["barrageReleaseM3S"], 0.0)

    def test_stale_point_observation_is_rejected(self) -> None:
        contract = copy.deepcopy(READINESS.verified_contract())
        contract["assessmentAt"] = "2026-08-30T13:00:00+09:00"
        result = READINESS.assess(contract)
        self.assertFalse(result["checks"]["officialPointObservationFresh"])
        self.assertFalse(result["physicalValidationEvidenceReady"])

    def test_saved_assessment_preserves_no_promotion_boundary(self) -> None:
        if not READINESS.OUTPUT.is_file():
            self.skipTest("assessment has not been generated")
        result = json.loads(READINESS.OUTPUT.read_text())
        self.assertEqual(
            result["status"],
            "BLOCKED_INSUFFICIENT_GATE_PHYSICS_EVIDENCE_NO_MORE_NUMERICAL_EXPANSION",
        )
        self.assertFalse(result["promotion"]["forecast"])
        self.assertFalse(result["promotion"]["gui"])
        self.assertFalse(result["promotion"]["release"])


if __name__ == "__main__":
    unittest.main()
