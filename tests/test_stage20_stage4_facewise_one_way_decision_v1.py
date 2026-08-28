#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "config/stage20_stage4_facewise_one_way_decision_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage4FacewiseOneWayDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision = json.loads(DECISION_PATH.read_text())
        report_binding = next(row for row in cls.decision["bindings"] if row["role"] == "facewise_probe_report")
        cls.report = json.loads((ROOT / report_binding["path"]).read_text())

    def test_all_bound_evidence_matches_sha(self):
        for row in self.decision["bindings"]:
            path = ROOT / row["path"]
            self.assertTrue(path.is_file(), row["path"])
            self.assertEqual(sha256(path), row["sha256"], row["path"])

    def test_schedule_is_exact_300_second_ramp_and_hold(self):
        schedule = self.decision["diagnosticSchedule"]
        self.assertEqual(schedule["gateIds"], [3, 4, 5, 6])
        self.assertEqual(schedule["rampSeconds"], 300.0)
        self.assertEqual(schedule["requestedHoldSeconds"], 300.0)
        self.assertEqual(self.report["simulatedSeconds"], 600.0)

    def test_each_gate_tripped_on_one_adverse_face_hidden_by_positive_sum(self):
        events = self.report["interlockEvents"]
        self.assertEqual([event["gateIds"][0] for event in events], [6, 5, 3, 4])
        self.assertEqual([event["modelSeconds"] for event in events], self.decision["observedResult"]["tripModelSeconds"])
        for event in events:
            row = event["preTripGateDiagnostics"][0]
            self.assertEqual(row["adverseFaceCount"], 1)
            self.assertLess(row["minimumSignedOutwardDischargeM3S"], -1e-10)
            self.assertGreater(row["totalSignedOutwardDischargeM3S"], 0.0)

    def test_hold_failed_closed_with_all_stage4_gates_closed(self):
        self.assertEqual(self.report["latchedClosedGateIds"], [3, 4, 5, 6])
        self.assertEqual(self.report["effectiveFinalCapacityByGateId1To8"], [0.0] * 8)
        self.assertFalse(self.decision["observedResult"]["requestedHoldAchieved"])

    def test_numerical_safety_does_not_promote_physical_or_yoda_gate(self):
        self.assertEqual(self.report["negativeDepthCount"], 0)
        self.assertEqual(self.report["nonFiniteValueCount"], 0)
        self.assertLessEqual(self.report["maximumCfl"], 0.120000000001)
        self.assertFalse(self.decision["decision"]["fixedStage4ScheduleEligibleForYoda"])
        for key in ("physicalValidation", "meshAdopted", "forecastAuthorized", "guiAuthorized", "pushAuthorized", "releaseAuthorized"):
            self.assertFalse(self.decision["decision"][key], key)


if __name__ == "__main__":
    unittest.main()
