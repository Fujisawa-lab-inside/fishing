from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_one_way_stage4_hold_300s_canary_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_one_way_stage4_hold_300s_canary_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
CANARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARY)


class Stage20BarrageOneWayStage4Hold300sCanaryV1Tests(unittest.TestCase):
    def test_contract_is_local_full_hold_without_yoda_or_release(self) -> None:
        contract = CANARY.verified_contract()
        self.assertEqual(contract["scope"]["canaryDurationSeconds"], 300.0)
        self.assertEqual(contract["scope"]["endModelSeconds"], 600.0)
        self.assertEqual(contract["scope"]["capacityByGateId1To8"], [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])
        self.assertFalse(contract["decisionBoundary"]["physicalValidation"])
        self.assertFalse(contract["decisionBoundary"]["releaseAuthorized"])

    def test_saved_report_completes_full_hold_numerically_only(self) -> None:
        if not CANARY.REPORT.is_file():
            self.skipTest("local full-hold report has not been generated")
        report = json.loads(CANARY.REPORT.read_text())
        self.assertEqual(report["simulatedHoldSeconds"], 300.0)
        self.assertEqual(report["endModelSeconds"], 600.0)
        self.assertEqual(report["capacityByGateId1To8"], [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
        self.assertGreater(report["blockedStepCount"], 0)
        self.assertGreater(report["cumulativeBlockedPotentialReverseVolumeM3"], 0.0)
        self.assertLessEqual(report["maximumRelativeMassBalanceError"], 1.0e-12)
        self.assertEqual(report["negativeDepthCount"], 0)
        self.assertEqual(report["nonFiniteValueCount"], 0)
        self.assertEqual(report["fishwayDischargeM3S"], 0.0)
        self.assertEqual(report["limiterExpectedCandidateCount"], 28746)
        self.assertEqual(report["limiterEvaluatedCandidateCount"], 28746)
        self.assertTrue(report["limiterCoverageCompleteEveryStep"])
        self.assertTrue(report["full300SecondHoldEvaluated"])
        self.assertEqual(report["yodaConnectionCount"], 0)
        self.assertFalse(report["physicalValidation"])
        self.assertFalse(report["releaseAuthorized"])


if __name__ == "__main__":
    unittest.main()
