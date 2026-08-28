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
        self.assertEqual((verification["passed"], verification["failed"]), (32, 0))
        self.assertFalse(verification["untrackedOfficialPdfsRequired"])
        self.assertFalse(verification["untrackedLegacyGate5CandidateRequired"])

    def test_next_grid_is_explicitly_not_a_rating(self):
        decision = self.payload["recommendedNextDecision"]
        self.assertEqual(decision["proposedExternalDischargeGridM3S"], [0.0, 6.0, 12.0, 18.0, 24.0])
        self.assertIn("not a claim", decision["gridMeaning"])
        self.assertIn("LOCAL_DIAGNOSTIC_ONLY", decision["recommendedAnswer"])

    def test_release_boundary_is_all_false(self):
        for key, value in self.payload["releaseBoundary"].items():
            self.assertFalse(value, key)


if __name__ == "__main__":
    unittest.main()
