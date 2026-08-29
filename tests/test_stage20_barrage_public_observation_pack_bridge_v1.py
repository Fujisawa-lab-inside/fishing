from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_public_observation_pack_bridge_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_public_observation_pack_bridge_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


class Stage20BarragePublicObservationPackBridgeV1Tests(unittest.TestCase):
    def test_public_summaries_emit_no_invented_observation_rows(self) -> None:
        report = BRIDGE.audit_bridge()
        self.assertFalse(report["observationPackCreated"])
        self.assertEqual(report["observationRowsEmitted"], 0)
        self.assertEqual(report["inventedValueCount"], 0)
        self.assertTrue(all(report["blockingReasons"].values()))

    def test_public_flow_transition_is_preserved_but_not_calibration(self) -> None:
        report = BRIDGE.audit_bridge()
        self.assertEqual(report["publicHistoryRowCount"], 12)
        self.assertEqual(report["publicHistoryDistinctReleaseM3S"], [0.0, 0.3])
        self.assertFalse(report["parameterCalibrationPermitted"])
        self.assertFalse(report["physicalValidation"])

    def test_no_execution_or_promotion(self) -> None:
        report = BRIDGE.audit_bridge()
        self.assertEqual(report["solverRunCount"], 0)
        self.assertEqual(report["yodaConnectionCount"], 0)
        self.assertTrue(all(value is False for value in report["promotion"].values()))

    def test_saved_report_matches_fail_closed_audit(self) -> None:
        if not BRIDGE.OUTPUT.is_file():
            self.skipTest("bridge report has not been generated")
        report = json.loads(BRIDGE.OUTPUT.read_text())
        self.assertEqual(report["status"], "BLOCKED_PUBLIC_SUMMARIES_NOT_GATE_PHYSICS_OBSERVATION_PACK")
        self.assertEqual(report["observationRowsEmitted"], 0)


if __name__ == "__main__":
    unittest.main()
