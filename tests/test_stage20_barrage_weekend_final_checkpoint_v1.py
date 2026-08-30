from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/results/stage20-barrage-weekend-final-checkpoint-v1/report.json"


class Stage20BarrageWeekendFinalCheckpointV1Tests(unittest.TestCase):
    def test_checkpoint_binds_final_handoff_evidence(self) -> None:
        report = json.loads(REPORT.read_text())
        for binding in report["evidenceBindings"]:
            path = ROOT / binding["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), binding["sha256"])

    def test_commit_sequence_and_first_blocker_are_fixed(self) -> None:
        report = json.loads(REPORT.read_text())
        self.assertEqual(len(report["weekendCanonicalCommits"]), 12)
        self.assertEqual(report["weekendCanonicalCommits"][-1], "e36abe0")
        self.assertEqual(report["currentGate"]["firstBlockingGate"], "G1_physical_observation_pack")
        self.assertFalse(report["nextMinimumAction"]["solverRunNeeded"])
        self.assertFalse(report["nextMinimumAction"]["yodaNeeded"])

    def test_checkpoint_grants_no_execution_or_promotion(self) -> None:
        report = json.loads(REPORT.read_text())
        boundary = report["decisionBoundary"]
        forbidden = [key for key, value in boundary.items() if key != "checkpointComplete" and value]
        self.assertEqual(forbidden, [])


if __name__ == "__main__":
    unittest.main()
