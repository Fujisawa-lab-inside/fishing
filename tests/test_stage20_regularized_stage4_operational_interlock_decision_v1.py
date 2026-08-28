#!/usr/bin/env python3

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "config/stage20_regularized_stage4_operational_interlock_decision_v1.json"
ANY_FACE_PATH = ROOT / "docs/results/stage20-regularized-stage4-per-gate-interlock-probe-v1/report.json"
GATE_NET_PATH = ROOT / "docs/results/stage20-regularized-stage4-gate-net-flux-probe-v1/report.json"
FORCING_PATH = ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
SEQUENCE_PATH = ROOT / "config/stage20_barrage_sequential_operation_candidate_v1.json"


class OperationalInterlockDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision = json.loads(DECISION_PATH.read_text())
        cls.any_face = json.loads(ANY_FACE_PATH.read_text())
        cls.gate_net = json.loads(GATE_NET_PATH.read_text())
        cls.forcing = json.loads(FORCING_PATH.read_text())
        cls.sequence = json.loads(SEQUENCE_PATH.read_text())

    def test_decision_rejects_both_fixed_hold_and_any_face_rule(self):
        decision = self.decision["decision"]
        self.assertFalse(decision["fixedThreeHundredSecondFullStage4HoldAccepted"])
        self.assertFalse(decision["anySingleFaceReverseHardRejectAccepted"])
        self.assertTrue(decision["gateIntegratedNetFlowInterlockAcceptedForDiagnostics"])
        self.assertTrue(decision["predictiveClosureRequiredBeforeNetFlowCrossesZero"])

    def test_gate_net_evidence_is_exactly_bound(self):
        evidence = self.decision["numericalEvidence"]["localGateNetInterlock"]
        self.assertEqual(
            self.gate_net["status"],
            "PASS_LOCAL_GATE_NET_INTERLOCK_STAGE4_HOLD_NOT_ACHIEVED",
        )
        self.assertTrue(self.gate_net["allAcceptedActiveGateNetFluxOutward"])
        self.assertFalse(self.gate_net["stage4HeldThroughRequestedHold"])
        actual = {
            str(event["gateIds"][0]): event["modelSeconds"]
            for event in self.gate_net["interlockEvents"]
        }
        self.assertEqual(evidence["closureModelSecondsByGateId"], actual)
        self.assertEqual(evidence["closureOrder"], [6, 5, 4, 3])

    def test_any_face_evidence_records_outward_gate_totals(self):
        evidence = self.decision["numericalEvidence"]["localAnyFaceInterlock"]
        order = [event["gateIds"][0] for event in self.any_face["interlockEvents"]]
        self.assertEqual(evidence["closureOrder"], order)
        self.assertTrue(
            all(
                all(
                    row["totalSignedOutwardDischargeM3S"] > 0.0
                    for row in event["preTripGateDiagnostics"]
                )
                for event in self.any_face["interlockEvents"]
            )
        )

    def test_unknown_operational_values_remain_unknown(self):
        decision = self.decision["decision"]
        boundary = self.decision["meaningBoundary"]
        self.assertIsNone(decision["predictiveClosureLeadTimeSeconds"])
        self.assertIsNone(decision["closureHeadMarginM"])
        self.assertFalse(boundary["physicalActuatorClosureTimeKnown"])
        self.assertFalse(boundary["officialOperatingMarginKnown"])
        self.assertFalse(boundary["gateNetOutwardProvesNoSaltIntrusion"])
        self.assertFalse(boundary["salinityTransportEvaluated"])

    def test_public_sources_do_not_smuggle_an_exact_threshold(self):
        sources = self.decision["publicOperationalBasis"]
        self.assertGreaterEqual(len(sources), 3)
        self.assertTrue(
            all(
                row["url"].startswith(("https://www.qsr.mlit.go.jp/", "https://www.mlit.go.jp/"))
                for row in sources
            )
        )
        exact = [row for row in sources if row["exactControlThresholdProvided"]]
        self.assertEqual(len(exact), 1)
        self.assertIn("24-270", exact[0]["supportedFact"])

    def test_bound_forcing_is_in_regulating_gate_not_stage4_band(self):
        applicability = self.decision["scenarioApplicability"]
        inflow = self.forcing["series"]["riverDischargeM3S"]
        totals = [sum(values) for values in zip(inflow["N"], inflow["O"], inflow["G"])]
        self.assertTrue(all(value == 38.0 for value in totals))
        self.assertEqual(applicability["constantBoundaryInflowM3S"]["total"], 38.0)
        bands = self.sequence["authority"]["officialOperationalAnchors"]
        selected = [
            row for row in bands
            if row["minimumDischargeM3S"] <= 38.0
            and (row["maximumDischargeM3S"] is None or 38.0 < row["maximumDischargeM3S"])
        ]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["control"], "regulating_main_gate")
        self.assertEqual(applicability["publishedOperationBandM3S"]["control"], "regulating_main_gate")
        self.assertFalse(applicability["stage4A3ToA6OpeningApplicableToThisBand"])
        self.assertFalse(applicability["exactNumberedRegulatingMainGateKnown"])
        resolution_path = applicability["localCompositeRegulatingMainGateResolution"].split("#", 1)[0]
        resolution = json.loads((ROOT / resolution_path).read_text())
        self.assertEqual(resolution["resolution"]["regulatingMainGateId"], 8)
        self.assertIn("REJECTED", applicability["existingGate5Mapping"])

    def test_downstream_promotions_remain_blocked(self):
        boundary = self.decision["meaningBoundary"]
        for key in (
            "meshAdopted",
            "forecastAuthorized",
            "guiIntegrationAuthorized",
            "fishingDecisionAuthorized",
            "releaseAuthorized",
        ):
            self.assertFalse(boundary[key])
        self.assertEqual(
            self.decision["nextGate"]["status"],
            "LOCAL_A8_ONLY_DIAGNOSTIC_PREPARATION_ALLOWED_MICRO_GATE_GEOMETRY_UNRESOLVED_NO_YODA_LAUNCH",
        )
        for key in ("parameterizedInterlockImplementation", "parameterizedInterlockTargetTest"):
            self.assertTrue((ROOT / self.decision["nextGate"][key]).is_file())


if __name__ == "__main__":
    unittest.main()
