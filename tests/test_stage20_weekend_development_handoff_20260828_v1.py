#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "docs/results/stage20-weekend-development-handoff-20260828-v1/summary.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WeekendDevelopmentHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(SUMMARY_PATH.read_text())

    def test_tracked_bindings_match(self):
        for row in self.payload["trackedBindings"]:
            path = ROOT / row["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(sha256(path), row["sha256"])

    def test_failed_yoda_stage4_is_not_promoted(self):
        receipt = self.payload["remoteYodaReceipt"]
        self.assertEqual(receipt["terminalStatus"], "FAILED_NO_RETRY")
        self.assertEqual(receipt["modelSeconds"], 0)
        self.assertEqual(receipt["acceptedSteps"], 0)
        self.assertEqual(receipt["retryCount"], 0)
        self.assertFalse(receipt["physicalValidation"])
        self.assertIn("conversation_receipt", receipt["evidenceClass"])

    def test_a8_evidence_is_complete_local_only(self):
        row = next(item for item in self.payload["trackedBindings"] if item["role"] == "a8_gate_weighted_sweep")
        report = json.loads((ROOT / row["path"]).read_text())
        self.assertTrue(report["allCasesNumericallySafe"])
        self.assertTrue(report["allCasesHeldThroughRequestedHold"])
        self.assertFalse(report["microAdjustmentGateHydraulicRepresentationIncluded"])
        self.assertFalse(report["regulatingMainGateRolePhysicalAdopted"])

    def test_clean_archive_count_and_removed_legacy_dependencies(self):
        verification = self.payload["latestCleanArchiveVerification"]
        self.assertEqual((verification["passed"], verification["failed"]), (94, 0))
        self.assertFalse(verification["untrackedOfficialPdfsRequired"])
        self.assertFalse(verification["untrackedLegacyGate5CandidateRequired"])

    def test_zero_q_wiring_is_real_context_noop_only(self):
        contract_row = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "micro_gate_zero_q_wiring_contract"
        )
        contract = json.loads((ROOT / contract_row["path"]).read_text())
        self.assertEqual(contract["invariants"]["requestedDischargeM3S"], 0.0)
        self.assertTrue(contract["invariants"]["oneStepStateAndScalarsBitExact"])
        self.assertFalse(contract["decisionBoundary"]["nonzeroDischargeConnectionPermitted"])

    def test_micro_q_result_is_safe_but_self_limited_and_not_physical(self):
        row = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "micro_gate_local_q_sensitivity_result"
        )
        report = json.loads((ROOT / row["path"]).read_text())
        self.assertTrue(report["allCasesNumericallySafe"])
        self.assertFalse(report["physicalDischargeLawImplemented"])
        self.assertTrue(report["interpretation"]["nonzeroCommandsCreateAdverseHeadAndSelfLimit"])
        self.assertFalse(report["a8CombinedScenarioEvaluated"])

    def test_interaction_is_blocked_and_next_decision_is_one_way_flux(self):
        decision = self.payload["recommendedNextDecision"]
        interaction = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "a8_micro_interaction_result"
        )
        report = json.loads((ROOT / interaction["path"]).read_text())
        self.assertTrue(report["allCasesNumericallySafe"])
        self.assertTrue(report["scenarioOperationallyBlocked"])
        self.assertFalse(report["strictZeroLocalA8AdverseFlowSatisfied"])
        self.assertFalse(report["yodaFollowOnRecommended"])
        self.assertIn("DIAGNOSTIC_ONLY", decision["recommendedAnswer"])
        self.assertIn("Stop numerical expansion", decision["nextLocalWorkAfterDecision"])

    def test_strict_facewise_backoff_is_one_state_only(self):
        row = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "stage4_capacity_backoff_real_context_result"
        )
        report = json.loads((ROOT / row["path"]).read_text())
        self.assertEqual(report["fullCapacityPreStepAdverseFaceCount"], 1)
        self.assertEqual(report["selection"]["selectedScale"], 0.875)
        self.assertEqual(report["selection"]["evaluatedCandidateCountThroughSelection"], 2)
        self.assertFalse(report["durationControlEvaluated"])
        self.assertFalse(report["physicalValidation"])

    def test_preventive_hold_is_safe_but_all_closed(self):
        row = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "stage4_facewise_hysteresis_hold_result"
        )
        report = json.loads((ROOT / row["path"]).read_text())
        self.assertEqual(
            report["status"],
            "PASS_NUMERICAL_FACEWISE_SAFETY_FAIL_NONZERO_HOLD_ALL_CLOSED",
        )
        self.assertGreater(report["minimumAcceptedPreStepSignedOutwardFluxM3S"], 0.0)
        self.assertGreater(report["minimumAcceptedPostStepSignedOutwardFluxM3S"], 0.0)
        self.assertEqual(report["finalScale"], 0.0)
        self.assertFalse(report["nonzeroHoldUtilityPassed"])
        self.assertFalse(report["oscillationDetected"])
        self.assertFalse(report["full300SecondHoldEvaluated"])

    def test_one_way_operator_is_pure_and_not_kernel_connected(self):
        contract_row = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "one_way_face_flux_operator_contract"
        )
        contract = json.loads((ROOT / contract_row["path"]).read_text())
        self.assertTrue(
            contract["decisionBoundary"]["pureOperatorAndSyntheticTestsPermitted"]
        )
        self.assertFalse(contract["decisionBoundary"]["kernelConnectionPermitted"])
        self.assertFalse(contract["decisionBoundary"]["durationRunPermitted"])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])

    def test_one_way_kernel_real_context_one_step_passes(self):
        row = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "one_way_kernel_one_step_result"
        )
        report = json.loads((ROOT / row["path"]).read_text())
        self.assertTrue(report["outwardCase"]["stateBitExactToLegacy"])
        self.assertTrue(report["outwardCase"]["scalarsBitExactToLegacy"])
        self.assertTrue(report["outwardCase"]["limiterBitExactToLegacy"])
        self.assertEqual(report["outwardCase"]["blockedReverseFaceCount"], 0)
        self.assertEqual(report["adverseCase"]["blockedReverseFaceCount"], 29)
        self.assertEqual(report["adverseCase"]["relativeMassBalanceError"], 0.0)
        self.assertEqual(report["adverseCase"]["limiterEvaluatedCandidateCount"], 28746)
        self.assertFalse(report["durationRunPerformed"])
        self.assertFalse(report["physicalValidation"])

    def test_one_way_full_stage4_hold_is_complete_but_assumption_dominated(self):
        row = next(
            item for item in self.payload["trackedBindings"]
            if item["role"] == "one_way_stage4_hold_300s_result"
        )
        report = json.loads((ROOT / row["path"]).read_text())
        self.assertEqual(report["rampSimulatedSeconds"], 300.0)
        self.assertEqual(report["rampAcceptedSteps"], 35634)
        self.assertEqual(report["rampReverseTripCount"], 0)
        self.assertEqual(report["simulatedHoldSeconds"], 300.0)
        self.assertEqual(report["endModelSeconds"], 600.0)
        self.assertEqual(report["acceptedSteps"], 36634)
        self.assertEqual(report["capacityByGateId1To8"], [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
        self.assertEqual(report["maximumBlockedFacesInStep"], 29)
        self.assertGreater(report["cumulativeBlockedPotentialReverseVolumeM3"], 7000.0)
        self.assertLessEqual(report["maximumRelativeMassBalanceError"], 1.0e-12)
        self.assertEqual(report["negativeDepthCount"], 0)
        self.assertEqual(report["nonFiniteValueCount"], 0)
        self.assertTrue(report["full300SecondHoldEvaluated"])
        self.assertEqual(report["yodaConnectionCount"], 0)
        self.assertFalse(report["physicalValidation"])
        self.assertFalse(report["releaseAuthorized"])

    def test_release_boundary_is_all_false(self):
        for key, value in self.payload["releaseBoundary"].items():
            self.assertFalse(value, key)


if __name__ == "__main__":
    unittest.main()
