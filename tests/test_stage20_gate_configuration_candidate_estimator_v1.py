from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_gate_configuration_candidate_estimator_v1 as estimator


def point_values(inflow: float = 60.0, release: float = 50.0) -> dict:
    return {
        "barrageInflowM3S": inflow,
        "barrageReleaseM3S": release,
        "barrageUpstreamLevelM": 1.48,
        "barrageDownstreamLevelM": 0.61,
    }


class GateConfigurationCandidateEstimatorTests(unittest.TestCase):
    def estimate(self, **overrides):
        values = point_values()
        values.update(overrides)
        return estimator.rank_candidates(
            inflow_m3_s=values["barrageInflowM3S"],
            release_m3_s=values["barrageReleaseM3S"],
            upstream_level_m=values["barrageUpstreamLevelM"],
            downstream_level_m=values["barrageDownstreamLevelM"],
        )

    def test_01_release_alone_never_claims_unique_gate_state(self) -> None:
        result = self.estimate()
        self.assertEqual(result["status"], estimator.STATUS)
        self.assertEqual(len(result["topConfigurations"]), 3)
        self.assertFalse(result["ambiguity"]["singleConfigurationEstablished"])
        self.assertFalse(result["boundary"]["perGateStateLabelGenerated"])
        self.assertFalse(result["boundary"]["candidateWeightsAreCalibratedProbabilities"])

    def test_02_release_and_head_form_only_an_aggregate_constraint(self) -> None:
        result = self.estimate(barrageReleaseM3S=50.0)
        expected = 50.0 / math.sqrt(2.0 * estimator.GRAVITY_M_S2 * (1.48 - 0.61))
        self.assertAlmostEqual(
            result["aggregateHydraulicConstraint"]["equivalentDischargeCoefficientTimesAreaM2"],
            expected,
        )
        self.assertFalse(result["aggregateHydraulicConstraint"]["gateIdentityResolvedByConstraint"])
        self.assertFalse(result["aggregateHydraulicConstraint"]["perGateCapacityCalibrationApplied"])

    def test_03_regulating_band_uses_a8_as_weak_candidate_not_ground_truth(self) -> None:
        result = self.estimate(barrageInflowM3S=60.0)
        self.assertEqual(result["operationBand"]["controlClass"], "REGULATING_MAIN_GATE_CONTROL_BAND")
        self.assertIn("A8", result["topConfigurations"][0]["openGateIds"])
        self.assertFalse(result["evidenceSummary"]["weakOpeningOrderAppliedAsGroundTruth"])
        self.assertFalse(result["boundary"]["physicalGateStateEstablished"])

    def test_04_visible_paired_orange_lamps_are_positive_open_evidence(self) -> None:
        result = estimator.rank_candidates(
            inflow_m3_s=8.0,
            release_m3_s=7.0,
            upstream_level_m=1.4,
            downstream_level_m=0.7,
            image_evidence={"byGateId": {"A5": {"pairedOrangeLampsVisible": True}}},
        )
        self.assertIn("A5", result["topConfigurations"][0]["openGateIds"])
        self.assertIn("A5", result["evidenceSummary"]["positivePairedOrangeLampGateIds"])
        self.assertGreater(result["gateOpenSupportByGateId"]["A5"], 0.99)

    def test_05_unlit_lamp_is_unknown_and_does_not_suppress_gate(self) -> None:
        absent = estimator.rank_candidates(
            inflow_m3_s=60.0,
            release_m3_s=50.0,
            upstream_level_m=1.4,
            downstream_level_m=0.7,
            image_evidence={"byGateId": {"A8": {"pairedOrangeLampsVisible": False}}},
        )
        missing = estimator.rank_candidates(
            inflow_m3_s=60.0,
            release_m3_s=50.0,
            upstream_level_m=1.4,
            downstream_level_m=0.7,
        )
        self.assertEqual(absent["gateOpenSupportByGateId"]["A8"], missing["gateOpenSupportByGateId"]["A8"])
        self.assertFalse(absent["evidenceSummary"]["unlitOrMissingLampInterpretedAsClosed"])

    def test_06_previous_state_support_improves_temporal_continuity(self) -> None:
        previous = {gate_id: (0.94 if gate_id == "A5" else 0.06) for gate_id in estimator.GATE_IDS}
        result = estimator.rank_candidates(
            inflow_m3_s=400.0,
            release_m3_s=380.0,
            upstream_level_m=1.7,
            downstream_level_m=0.5,
            previous_support=previous,
        )
        self.assertIn("A5", result["topConfigurations"][0]["openGateIds"])
        self.assertTrue(result["evidenceSummary"]["previousStateSupportApplied"])

    def test_07_all_open_published_band_ranks_all_main_gates_first(self) -> None:
        result = self.estimate(barrageInflowM3S=2200.0, barrageReleaseM3S=2100.0)
        self.assertEqual(result["topConfigurations"][0]["openGateIds"], list(estimator.GATE_IDS))
        self.assertFalse(result["ambiguity"]["singleConfigurationEstablished"])

    def test_08_nonpositive_head_does_not_invent_equivalent_area(self) -> None:
        result = self.estimate(barrageUpstreamLevelM=0.5, barrageDownstreamLevelM=0.6)
        self.assertIsNone(result["aggregateHydraulicConstraint"]["equivalentDischargeCoefficientTimesAreaM2"])

    def test_09_cli_reads_collector_observation_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            observation = root / "observation.json"
            output = root / "candidate.json"
            observation.write_text(
                json.dumps(
                    {
                        "runId": "20260913T1200+0900",
                        "parsed": {
                            "barragePoint": {
                                "observedAt": "2026-09-13T12:00+09:00",
                                "values": point_values(),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "stage20_gate_configuration_candidate_estimator_v1.py"),
                    "--observation",
                    str(observation),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["observation"]["runId"], "20260913T1200+0900")
            self.assertEqual(report["status"], estimator.STATUS)

    def test_10_invalid_gate_evidence_fails_closed(self) -> None:
        with self.assertRaisesRegex(estimator.CandidateEstimatorError, "unknown image-evidence gate"):
            estimator.rank_candidates(
                inflow_m3_s=60.0,
                release_m3_s=50.0,
                upstream_level_m=1.4,
                downstream_level_m=0.7,
                image_evidence={"A9": {"pairedOrangeLampsVisible": True}},
            )


if __name__ == "__main__":
    unittest.main()
