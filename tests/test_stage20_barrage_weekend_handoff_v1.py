from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/results/stage20-barrage-weekend-handoff-v1/report.json"


class Stage20BarrageWeekendHandoffV1Tests(unittest.TestCase):
    def test_handoff_binds_exact_evidence_inventory(self) -> None:
        report = json.loads(REPORT.read_text())
        for binding in report["evidenceInventory"]:
            path = ROOT / binding["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), binding["sha256"])

    def test_first_blocker_and_minimum_authority_are_explicit(self) -> None:
        report = json.loads(REPORT.read_text())
        self.assertEqual(report["confirmed"]["firstBlockingGate"], "G1_physical_observation_pack")
        decision = report["recommendedMondayDecision"]
        self.assertEqual(decision["minimumNextAuthorityIdCandidate"], "stage20-local-observation-intake-validate-only-v1")
        self.assertTrue(decision["authorityUsefulOnlyWhenPhysicalFilesAreAvailable"])
        self.assertIn("parameter fitting", decision["explicitlyForbidden"])
        self.assertIn("solver execution", decision["explicitlyForbidden"])
        self.assertIn("YODA transfer or launch", decision["explicitlyForbidden"])

    def test_handoff_grants_no_execution_or_promotion(self) -> None:
        report = json.loads(REPORT.read_text())
        boundary = report["decisionBoundary"]
        forbidden = [key for key, value in boundary.items() if key != "handoffPrepared" and value]
        self.assertEqual(forbidden, [])


if __name__ == "__main__":
    unittest.main()
