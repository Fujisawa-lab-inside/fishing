from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_stage4_facewise_hysteresis_hold_canary_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_stage4_facewise_hysteresis_hold_canary_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
CANARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARY)


class Stage4FacewiseHysteresisHoldCanaryV1Tests(unittest.TestCase):
    def test_contract_is_local_60_seconds_only(self) -> None:
        contract = CANARY.verified_contract()
        self.assertEqual(contract["scope"]["reconstructionTargetModelSeconds"], 300.0)
        self.assertEqual(contract["scope"]["localCanaryDurationSeconds"], 60.0)
        self.assertEqual(contract["scope"]["increaseDwellSeconds"], 10.0)
        self.assertFalse(contract["decisionBoundary"]["full300SecondHoldPermitted"])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])

    def test_capacity_grid_neighbors_are_asymmetric(self) -> None:
        self.assertEqual(CANARY.lower_scales(1.0)[0], 0.875)
        self.assertEqual(CANARY.lower_scales(0.5)[-1], 0.0)
        self.assertEqual(CANARY.next_higher_scale(0.5), 0.625)
        self.assertIsNone(CANARY.next_higher_scale(1.0))

    def test_saved_report_never_accepts_adverse_pre_or_post_face(self) -> None:
        if not CANARY.REPORT.is_file():
            self.skipTest("local 60 s hold report has not been generated")
        report = json.loads(CANARY.REPORT.read_text())
        self.assertEqual(
            report["status"],
            "PASS_NUMERICAL_FACEWISE_SAFETY_FAIL_NONZERO_HOLD_ALL_CLOSED",
        )
        self.assertGreaterEqual(report["minimumAcceptedPreStepSignedOutwardFluxM3S"], -1.0e-10)
        self.assertGreaterEqual(report["minimumAcceptedPostStepSignedOutwardFluxM3S"], -1.0e-10)
        self.assertEqual(report["negativeDepthCount"], 0)
        self.assertEqual(report["nonFiniteValueCount"], 0)
        self.assertEqual(report["finalScale"], 0.0)
        self.assertFalse(report["nonzeroHoldUtilityPassed"])
        self.assertFalse(report["oscillationDetected"])
        self.assertFalse(report["full300SecondHoldEvaluated"])
        self.assertFalse(report["physicalValidation"])
        self.assertEqual(report["yodaConnectionCount"], 0)


if __name__ == "__main__":
    unittest.main()
