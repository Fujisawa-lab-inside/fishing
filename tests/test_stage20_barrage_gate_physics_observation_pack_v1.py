from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_gate_physics_observation_pack_v1.py"
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
    for index, state in enumerate(states):
        rows.append(
            {
                "timestampJst": f"2026-08-29T0{index + 1}:00:00+09:00",
                "eventId": f"event-{index + 1}",
                "splitRole": "calibration" if index < 2 else "independent_validation",
                "operatingState": state,
                "upstreamLevelM": 1.5,
                "downstreamLevelM": 1.0 + index * 0.25,
                "totalReleaseM3S": float(index),
                "verticalDatumName": "synthetic-common-datum",
                "mainGateOpeningFractionById1To8": [0.0] * 8,
                "microAdjustmentGate": {"state": "closed", "openingFraction": 0.0},
                "actuatorState": "stable" if index < 2 else "closing",
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
            "wholeEventSplit": True,
            "splitFrozenBeforeCalibration": True,
            "saltIntrusionOrAdverseVolumeCriterion": "synthetic criterion",
        },
        "rows": rows,
    }


class Stage20BarrageGatePhysicsObservationPackV1Tests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
