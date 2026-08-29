from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_minimum_calibration_validation_plan_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_minimum_calibration_validation_plan_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PLAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLAN)


class Stage20BarrageMinimumCalibrationValidationPlanV1Tests(unittest.TestCase):
    def test_plan_is_prepare_only_and_event_split_is_independent(self) -> None:
        result = PLAN.validate_plan()
        self.assertEqual(result["minimumIndependentEventCount"], 18)
        self.assertEqual(result["candidateCount"], 3)
        self.assertEqual(result["stageCount"], 5)
        self.assertEqual(result["solverRunCount"], 0)
        self.assertEqual(result["parameterFitCount"], 0)

    def test_plan_does_not_invent_accuracy_thresholds(self) -> None:
        result = PLAN.validate_plan()
        self.assertFalse(result["numericFitThresholdInvented"])
        plan = json.loads(PLAN.PLAN.read_text())
        self.assertIsNone(plan["acceptanceMetrics"]["releaseFit"]["numericThresholds"])
        self.assertIn("instrument uncertainty", plan["acceptanceMetrics"]["releaseFit"]["thresholdRule"])

    def test_one_way_clamp_is_not_a_calibrated_candidate(self) -> None:
        plan = json.loads(PLAN.PLAN.read_text())
        candidate_ids = {candidate["id"] for candidate in plan["modelCandidates"]}
        self.assertFalse(any("one_way" in candidate for candidate in candidate_ids))
        self.assertTrue(any("one_way_wall_clamp" in value for value in plan["forbiddenCandidates"]))

    def test_no_solver_yoda_or_release_authority(self) -> None:
        result = PLAN.validate_plan()
        self.assertEqual(result["yodaConnectionCount"], 0)
        self.assertFalse(result["physicalValidation"])
        self.assertFalse(result["releaseAuthorized"])


if __name__ == "__main__":
    unittest.main()
