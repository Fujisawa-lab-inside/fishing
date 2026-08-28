from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_one_way_stage4_hold_60s_canary_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_one_way_stage4_hold_60s_canary_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
CANARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARY)


class Stage20BarrageOneWayStage4Hold60sCanaryV1Tests(unittest.TestCase):
    def test_contract_is_local_60_seconds_only(self) -> None:
        contract = CANARY.verified_contract()
        self.assertEqual(contract["scope"]["canaryDurationSeconds"], 60.0)
        self.assertEqual(contract["scope"]["capacityByGateId1To8"], [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
        self.assertFalse(contract["decisionBoundary"]["full300SecondHoldPermitted"])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])

    def test_saved_report_is_safe_fixed_capacity_but_not_physical(self) -> None:
        if not CANARY.REPORT.is_file():
            self.skipTest("local 60 s one-way report has not been generated")
        report = json.loads(CANARY.REPORT.read_text())
        self.assertEqual(report["simulatedHoldSeconds"], 60.0)
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
        self.assertFalse(report["full300SecondHoldEvaluated"])
        self.assertEqual(report["yodaConnectionCount"], 0)
        self.assertFalse(report["physicalValidation"])


if __name__ == "__main__":
    unittest.main()
