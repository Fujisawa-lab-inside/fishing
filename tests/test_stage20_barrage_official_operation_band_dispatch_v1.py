from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_official_operation_band_dispatch_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_official_operation_band_dispatch_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
DISPATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DISPATCH)


class Stage20BarrageOfficialOperationBandDispatchV1Tests(unittest.TestCase):
    def test_published_boundaries_are_half_open_and_exact(self) -> None:
        expected = {
            0.0: "BELOW_PUBLISHED_TABLE_RANGE_NO_INFERENCE",
            1.999: "BELOW_PUBLISHED_TABLE_RANGE_NO_INFERENCE",
            2.0: "MICRO_ADJUSTMENT_GATE_CONTROL_BAND",
            23.999: "MICRO_ADJUSTMENT_GATE_CONTROL_BAND",
            24.0: "REGULATING_MAIN_GATE_CONTROL_BAND",
            269.999: "REGULATING_MAIN_GATE_CONTROL_BAND",
            270.0: "STAGED_CONTROL_MAIN_GATE_DRIVE_BAND",
            1800.0: "FULL_OPENING_DRIVE_BAND",
            2100.0: "ALL_MAIN_GATES_FULLY_OPEN_PUBLISHED_BAND",
        }
        for inflow, control in expected.items():
            with self.subTest(inflow=inflow):
                self.assertEqual(DISPATCH.classify_inflow(inflow)["controlClass"], control)

    def test_current_observation_is_not_stage4(self) -> None:
        report = DISPATCH.current_report()
        self.assertEqual(report["observedInflowM3S"], 9.6)
        self.assertEqual(report["controlClass"], "MICRO_ADJUSTMENT_GATE_CONTROL_BAND")
        self.assertNotIn("STAGE4", report["controlClass"])
        self.assertIsNone(report["gateByGateOpening"])
        self.assertIsNone(report["predictedReleaseM3S"])
        self.assertFalse(report["physicalValidation"])

    def test_saved_report_preserves_unknown_gate_state(self) -> None:
        if not DISPATCH.OUTPUT.is_file():
            self.skipTest("report has not been generated")
        report = json.loads(DISPATCH.OUTPUT.read_text())
        self.assertIsNone(report["gateByGateOpening"])
        self.assertIsNone(report["hydraulicLaw"])
        self.assertFalse(report["forecast"])

    def test_invalid_inflow_fails_closed(self) -> None:
        for value in (-1.0, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(DISPATCH.OperationBandDispatchError):
                    DISPATCH.classify_inflow(value)


if __name__ == "__main__":
    unittest.main()
