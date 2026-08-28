#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
READINESS_PATH = ROOT / "config/stage20_micro_adjustment_gate_readiness_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MicroAdjustmentGateReadinessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(READINESS_PATH.read_text())

    def test_official_inventory_and_operation_band_are_separate(self):
        facts = self.payload["officialFacts"]
        self.assertTrue(facts["facilityIsSeparateFromMainGatesAndFishway"])
        self.assertEqual((facts["count"], facts["widthM"], facts["heightM"]), (1, 10.0, 2.8))
        self.assertEqual(facts["operationBandM3S"], [2.0, 24.0])
        self.assertTrue(all(url.startswith("https://www.qsr.mlit.go.jp/") for url in facts["sourceUrls"]))

    def test_bound_38_flow_requires_a8_and_micro_effects(self):
        scenario = self.payload["boundScenario"]
        self.assertEqual(sum(scenario["forcingByBoundaryM3S"].values()), scenario["totalM3S"])
        self.assertEqual(scenario["totalM3S"], 38.0)
        self.assertEqual(scenario["mainGateCandidate"], "PARAMETERIZED_A8_ONLY")
        self.assertEqual(scenario["microAdjustmentGateExpected"], "FULLY_OPEN")
        self.assertFalse(scenario["a8OnlyScenarioIsCompletePhysicalScenario"])

    def test_tracked_evidence_is_self_contained(self):
        for row in self.payload["trackedEvidence"]:
            path = ROOT / row["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(sha256(path), row["sha256"])

    def test_legacy_working_tree_files_are_not_runtime_bindings(self):
        rows = self.payload["legacyWorkingTreeEvidence"]
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertFalse(row["repositoryBindingRequired"])
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")

    def test_preferred_candidate_preserves_facility_truth(self):
        decision = self.payload["representationDecision"]
        self.assertTrue(decision["facilityTruthPreservedAsSeparate"])
        self.assertIn("MASS_CONSERVATIVE", decision["preferredNextDiagnosticCandidate"])
        self.assertTrue(decision["fishwayAndMicroDischargesMustRemainSeparatelyReported"])
        self.assertTrue(decision["noDoubleCountingRequired"])
        self.assertFalse(decision["legacyPositionAdopted"])
        self.assertFalse(decision["legacyDischargeLawAdopted"])
        self.assertFalse(decision["solverConnectionPermitted"])

    def test_fail_closed_boundary(self):
        boundary = self.payload["decisionBoundary"]
        self.assertTrue(boundary["readinessContractCreated"])
        for key, value in boundary.items():
            if key != "readinessContractCreated":
                self.assertFalse(value, key)


if __name__ == "__main__":
    unittest.main()
