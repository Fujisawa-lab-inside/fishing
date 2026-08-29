from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_gate_physics_observation_pack_v1.py"
FIXTURES = ROOT / "tests/fixtures/stage20-barrage-gate-physics-observation-pack-v1"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_gate_physics_observation_pack_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)


def complete_pack(classification: str = "physical_observation"):
    states = [
        "closed_positive_outward_head",
        "open_measured_outward_discharge",
        "near_zero_or_adverse_head_closure_response",
    ]
    rows = []
    index = 0
    for state in states:
        for split_role in ("calibration", "independent_validation"):
            for sample in range(3):
                index += 1
                rows.append(
                    {
                        "timestampJst": f"2026-08-29T{index:02d}:00:00+09:00",
                        "eventId": f"event-{index}",
                        "splitRole": split_role,
                        "operatingState": state,
                        "upstreamLevelM": 1.5,
                        "downstreamLevelM": 1.0 + sample * 0.1,
                        "totalReleaseM3S": 1.0 if state == "open_measured_outward_discharge" else 0.0,
                        "verticalDatumName": "synthetic-common-datum",
                        "mainGateOpeningFractionById1To8": [0.0] * 8,
                        "microAdjustmentGate": {"state": "closed", "openingFraction": 0.0},
                        "actuatorState": "closing" if state == "near_zero_or_adverse_head_closure_response" else "stable",
                        "releaseSourceClass": "direct_observation",
                    }
                )
    return {
        "schema": "onga-stage20-barrage-gate-physics-observation-pack-v1",
        "classification": classification,
        "dataset": {
            "verticalDatumName": "synthetic-common-datum",
            "clockSource": "synthetic synchronized clock",
            "sourceSha256": "1" * 64,
            "sourceClass": "instrument_export" if classification == "physical_observation" else "synthetic_fixture",
            "sourceManifestSha256": "2" * 64,
            "instrumentIds": ["instrument-1"],
            "units": {
                "upstreamLevelM": "m",
                "downstreamLevelM": "m",
                "totalReleaseM3S": "m3/s",
                "mainGateOpeningFractionById1To8": "fraction",
                "microAdjustmentGateOpeningFraction": "fraction",
            },
            "wholeEventSplit": True,
            "splitFrozenBeforeCalibration": True,
            "saltIntrusionOrAdverseVolumeCriterion": "synthetic criterion",
        },
        "rows": rows,
    }


class Stage20BarrageGatePhysicsObservationPackV1Tests(unittest.TestCase):
    def test_tracked_public_summary_fixture_is_rejected_without_invention(self) -> None:
        candidate = json.loads((FIXTURES / "public-summary-illegal-pack.json").read_text())
        result = PACK.assess(candidate)
        self.assertFalse(result["structuralPass"])
        self.assertFalse(result["physicalObservationReady"])
        self.assertIn("SOURCE_CLASS_CLASSIFICATION_MISMATCH", result["issues"])
        self.assertIn("VERTICAL_DATUM_MISSING", result["issues"])
        self.assertIn("ROW_0_MAIN_GATE_OPENINGS_INVALID", result["issues"])
        self.assertIn("ROW_0_MICRO_GATE_INVALID", result["issues"])
        self.assertIn("DISTINCT_EVENT_COUNT_INSUFFICIENT", result["issues"])

    def test_tracked_complete_synthetic_fixture_is_never_physical(self) -> None:
        candidate = json.loads((FIXTURES / "synthetic-complete-pack.json").read_text())
        result = PACK.assess(candidate)
        self.assertTrue(result["structuralPass"])
        self.assertFalse(result["physicalObservationReady"])
        self.assertFalse(result["solverRunPermitted"])

    def test_empty_template_fails_closed(self) -> None:
        contract = PACK.verified_contract()
        result = PACK.assess(contract["template"], contract)
        self.assertFalse(result["structuralPass"])
        self.assertFalse(result["physicalObservationReady"])
        self.assertIn("OBSERVATION_ROWS_MISSING", result["issues"])
        self.assertFalse(result["solverRunPermitted"])
        self.assertFalse(result["yodaLaunchPermitted"])

    def test_complete_physical_pack_is_ready_for_design_not_execution(self) -> None:
        result = PACK.assess(complete_pack())
        self.assertTrue(result["structuralPass"])
        self.assertTrue(result["physicalObservationReady"])
        self.assertFalse(result["parameterCalibrationPermitted"])
        self.assertFalse(result["solverRunPermitted"])

    def test_synthetic_fixture_never_becomes_physical_observation(self) -> None:
        result = PACK.assess(complete_pack("synthetic_fixture"))
        self.assertTrue(result["structuralPass"])
        self.assertFalse(result["physicalObservationReady"])

    def test_duplicate_timestamp_and_event_split_leak_fail(self) -> None:
        candidate = complete_pack()
        candidate["rows"][1]["timestampJst"] = candidate["rows"][0]["timestampJst"]
        candidate["rows"][1]["eventId"] = candidate["rows"][0]["eventId"]
        candidate["rows"][1]["splitRole"] = "independent_validation"
        result = PACK.assess(candidate)
        self.assertIn("DUPLICATE_TIMESTAMP", result["issues"])
        self.assertIn("EVENT_SPLIT_LEAKAGE", result["issues"])
        self.assertFalse(result["physicalObservationReady"])

    def test_missing_gate_opening_fails(self) -> None:
        candidate = complete_pack()
        candidate["rows"][0]["mainGateOpeningFractionById1To8"] = [0.0] * 7
        result = PACK.assess(candidate)
        self.assertIn("ROW_0_MAIN_GATE_OPENINGS_INVALID", result["issues"])

    def test_each_state_and_split_requires_three_independent_events(self) -> None:
        candidate = complete_pack()
        candidate["rows"] = candidate["rows"][:-1]
        result = PACK.assess(candidate)
        self.assertIn("DISTINCT_EVENT_COUNT_INSUFFICIENT", result["issues"])
        self.assertTrue(any(issue.startswith("EVENT_CELL_COUNT_INSUFFICIENT_") for issue in result["issues"]))

    def test_relabelled_synthetic_source_class_fails(self) -> None:
        candidate = complete_pack("synthetic_fixture")
        candidate["classification"] = "physical_observation"
        result = PACK.assess(candidate)
        self.assertIn("SOURCE_CLASS_CLASSIFICATION_MISMATCH", result["issues"])
        self.assertFalse(result["physicalObservationReady"])


if __name__ == "__main__":
    unittest.main()
