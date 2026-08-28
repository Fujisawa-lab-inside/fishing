#!/usr/bin/env python3

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "config/stage20_regularized_stage4_operational_interlock_decision_v1.json"
ANY_FACE_PATH = ROOT / "docs/results/stage20-regularized-stage4-per-gate-interlock-probe-v1/report.json"
GATE_NET_PATH = ROOT / "docs/results/stage20-regularized-stage4-gate-net-flux-probe-v1/report.json"


class OperationalInterlockDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision = json.loads(DECISION_PATH.read_text())
        cls.any_face = json.loads(ANY_FACE_PATH.read_text())
        cls.gate_net = json.loads(GATE_NET_PATH.read_text())

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
        self.assertTrue(all(not row["exactControlThresholdProvided"] for row in sources))

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
            "LOCAL_PARAMETER_BRACKET_REQUIRED_NO_YODA_LAUNCH",
        )


if __name__ == "__main__":
    unittest.main()
