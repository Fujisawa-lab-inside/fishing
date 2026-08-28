#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RESOLUTION_PATH = ROOT / "config/stage20_barrage_regulating_main_gate_resolution_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RegulatingMainGateResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(RESOLUTION_PATH.read_text())

    def test_all_evidence_is_sha_bound(self):
        for row in self.payload["evidence"]:
            path = ROOT / row["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(sha256(path), row["sha256"])
        superseded = self.payload["supersedes"]
        self.assertEqual(sha256(ROOT / superseded["path"]), superseded["sha256"])

    def test_numbering_authority_is_monotonic_west_to_east(self):
        row = next(item for item in self.payload["evidence"] if item["role"] == "local_numbering_orientation")
        geojson = json.loads((ROOT / row["path"]).read_text())
        features = sorted(
            geojson["features"],
            key=lambda feature: int(feature["properties"]["gate_no"]),
        )
        self.assertEqual([feature["properties"]["gate_no"] for feature in features], list(range(1, 9)))
        self.assertTrue(all(feature["properties"]["order"] == "west_1_to_east_8" for feature in features))
        longitude = [feature["geometry"]["coordinates"][0] for feature in features]
        self.assertEqual(longitude, sorted(longitude))

    def test_gate8_is_diagnostic_inference_not_direct_official_label(self):
        resolution = self.payload["resolution"]
        self.assertEqual(resolution["regulatingMainGateId"], 8)
        self.assertFalse(resolution["directOfficialNumberLabelPublished"])
        self.assertTrue(resolution["resolvedForLocalDiagnosticCandidate"])
        self.assertFalse(resolution["physicalRoleAdopted"])
        self.assertIn("REJECTED", resolution["priorGate5WorkingHypothesis"])

    def test_low_flow_scenario_rejects_stage4_and_keeps_micro_gate_unresolved(self):
        implication = self.payload["lowFlowScenarioImplication"]
        self.assertEqual(implication["boundDiagnosticTotalInflowM3S"], 38.0)
        self.assertFalse(implication["a3ToA6Stage4Applicable"])
        self.assertEqual(implication["candidateMainGateCommandById1To8"][:7], [0.0] * 7)
        self.assertEqual(implication["candidateMainGateCommandById1To8"][7], "PARAMETERIZED_A8_ONLY")
        self.assertEqual(implication["microAdjustmentGateExpectedByPublishedBand"], "OPEN")
        self.assertFalse(implication["microAdjustmentGateHydraulicGeometryKnown"])
        self.assertFalse(implication["fullPhysicalLowFlowScenarioReady"])

    def test_a8_numerical_preflight_stops_before_the_sweep(self):
        evidence = self.payload["numericalPreflightEvidence"]
        report = json.loads((ROOT / evidence["report"]).read_text())
        self.assertEqual(report["status"], evidence["status"])
        self.assertEqual(report["a8InitialObservation"]["faceCount"], 9)
        self.assertLess(
            report["a8InitialObservation"]["minimumSelectedFaceSideDepthM"],
            report["a8InitialObservation"]["minimumTrustedSelectedFaceDepthM"],
        )
        self.assertEqual(report["numericalAdvanceCount"], 0)
        self.assertEqual(report["sweepRunCount"], 0)

    def test_no_downstream_authority_is_created(self):
        boundary = self.payload["decisionBoundary"]
        self.assertTrue(boundary["a8OnlyLocalPreflightPermitted"])
        for key in (
            "a8OnlyCapacitySweepPermitted",
            "a8OnlyYodaLaunchPermitted",
            "microAdjustmentGateMayBeInvented",
            "physicalValidation",
            "meshAdopted",
            "forecastAuthorized",
            "guiAuthorized",
            "releaseAuthorized",
        ):
            self.assertFalse(boundary[key])


if __name__ == "__main__":
    unittest.main()
