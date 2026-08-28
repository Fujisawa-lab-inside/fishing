from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_one_way_kernel_one_step_probe_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_one_way_kernel_one_step_probe_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class Stage20BarrageOneWayKernelOneStepProbeV1Tests(unittest.TestCase):
    def test_contract_is_one_step_local_only(self) -> None:
        contract = PROBE.verified_contract()
        self.assertTrue(contract["decisionBoundary"]["singleLocalRealContextProbePermitted"])
        self.assertFalse(contract["decisionBoundary"]["durationRunPermitted"])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])
        self.assertFalse(contract["decisionBoundary"]["legacyKernelMutationPermitted"])

    def test_saved_report_covers_real_outward_and_adverse_cases(self) -> None:
        if not PROBE.REPORT.is_file():
            self.skipTest("real-context one-step report has not been generated")
        report = json.loads(PROBE.REPORT.read_text())
        self.assertTrue(report["outwardCase"]["stateBitExactToLegacy"])
        self.assertTrue(report["outwardCase"]["scalarsBitExactToLegacy"])
        self.assertTrue(report["outwardCase"]["limiterBitExactToLegacy"])
        self.assertEqual(report["outwardCase"]["blockedReverseFaceCount"], 0)
        self.assertGreater(report["adverseCase"]["blockedReverseFaceCount"], 0)
        self.assertLessEqual(report["adverseCase"]["relativeMassBalanceError"], 1.0e-12)
        self.assertEqual(report["adverseCase"]["negativeDepthCount"], 0)
        self.assertEqual(report["adverseCase"]["nonFiniteValueCount"], 0)
        self.assertEqual(report["adverseCase"]["limiterExpectedCandidateCount"], 28746)
        self.assertEqual(report["adverseCase"]["limiterEvaluatedCandidateCount"], 28746)
        self.assertTrue(report["adverseCase"]["limiterCoverageComplete"])
        self.assertFalse(report["durationRunPerformed"])
        self.assertEqual(report["yodaConnectionCount"], 0)
        self.assertFalse(report["physicalValidation"])


if __name__ == "__main__":
    unittest.main()
