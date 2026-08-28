from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_stage4_facewise_capacity_backoff_real_context_probe_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_stage4_facewise_capacity_backoff_real_context_probe_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class Stage4FacewiseCapacityBackoffRealContextProbeV1Tests(unittest.TestCase):
    def test_contract_bindings_and_fail_closed_boundary(self) -> None:
        contract = PROBE.verified_contract()
        self.assertTrue(
            contract["decisionBoundary"]["singleLocalReconstructionAndCandidateProbePermitted"]
        )
        self.assertFalse(contract["decisionBoundary"]["durationRunPermitted"])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])
        self.assertFalse(contract["decisionBoundary"]["physicalValidation"])

    def test_saved_report_is_single_state_evidence_only(self) -> None:
        if not PROBE.REPORT.is_file():
            self.skipTest("one-state report has not been generated")
        report = json.loads(PROBE.REPORT.read_text())
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_SINGLE_PRETRIP_STATE_BACKOFF_PROBE_NOT_DURATION_CONTROL",
        )
        self.assertFalse(report["durationControlEvaluated"])
        self.assertFalse(report["physicalValidation"])
        self.assertEqual(report["yodaConnectionCount"], 0)
        self.assertEqual(report["selection"]["trialKernelCallCount"], 18)
        self.assertTrue(report["selection"]["acceptedStateMustComeFromSelectedCandidateTrial"])
        self.assertFalse(report["selection"]["fluxClipped"])
        self.assertEqual(report["selectedStepNegativeDepthCount"], 0)
        self.assertEqual(report["selectedStepNonFiniteValueCount"], 0)


if __name__ == "__main__":
    unittest.main()
