from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/results/stage20-barrage-observation-intake-checkpoint-v1/report.json"


class Stage20BarrageObservationIntakeCheckpointV1Tests(unittest.TestCase):
    def test_checkpoint_binds_existing_evidence(self) -> None:
        report = json.loads(REPORT.read_text())
        for binding in report["evidenceBindings"]:
            path = ROOT / binding["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), binding["sha256"])

    def test_checkpoint_preserves_physical_block(self) -> None:
        report = json.loads(REPORT.read_text())
        self.assertEqual(report["confirmed"]["physicalReadinessPassedChecks"], 2)
        self.assertEqual(report["confirmed"]["physicalReadinessRequiredChecks"], 11)
        self.assertEqual(report["confirmed"]["publicObservationRowsEmitted"], 0)
        self.assertEqual(report["confirmed"]["inventedValueCount"], 0)
        self.assertFalse(report["decisionBoundary"]["physicalObservationPackPresent"])

    def test_checkpoint_grants_no_execution_or_promotion(self) -> None:
        report = json.loads(REPORT.read_text())
        boundary = report["decisionBoundary"]
        forbidden = [key for key, value in boundary.items() if key != "observationIntakePrepared" and value]
        self.assertEqual(forbidden, [])


if __name__ == "__main__":
    unittest.main()
