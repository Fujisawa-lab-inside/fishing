from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_observation_intake_readiness_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_observation_intake_readiness_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
READINESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READINESS)


class Stage20BarrageObservationIntakeReadinessV1Tests(unittest.TestCase):
    def test_gate_order_and_first_blocker_are_explicit(self) -> None:
        report = READINESS.assess()
        self.assertEqual(report["passedGateCount"], 1)
        self.assertEqual(report["requiredGateCount"], 8)
        self.assertEqual(report["firstBlockingGate"], "G1_physical_observation_pack")
        self.assertEqual([gate["id"] for gate in report["gates"]], READINESS.verified_contract()["requiredGateOrder"])

    def test_physical_evidence_remains_two_of_eleven(self) -> None:
        report = READINESS.assess()
        self.assertEqual(report["physicalReadinessPassedChecks"], 2)
        self.assertEqual(report["physicalReadinessRequiredChecks"], 11)

    def test_no_calibration_solver_yoda_or_release_authority(self) -> None:
        report = READINESS.assess()
        self.assertFalse(report["offlineCalibrationPermitted"])
        self.assertFalse(report["parameterFitPermitted"])
        self.assertFalse(report["solverRunPermitted"])
        self.assertFalse(report["yodaLaunchPermitted"])
        self.assertFalse(report["releasePermitted"])


if __name__ == "__main__":
    unittest.main()
