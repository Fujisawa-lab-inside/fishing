from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_local_observation_intake_validate_only_authority_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_local_observation_intake_validate_only_authority_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
AUTHORITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTHORITY)


class Stage20LocalObservationIntakeValidateOnlyAuthorityV1Tests(unittest.TestCase):
    def test_template_is_valid_but_unissued(self) -> None:
        result = AUTHORITY.validate_template()
        self.assertEqual(result["status"], "PASS_TEMPLATE_ONLY_NO_AUTHORITY")
        self.assertFalse(result["authorityIssued"])
        self.assertEqual(result["inputFileCount"], 0)
        self.assertEqual(result["quarantineCreationCount"], 0)
        self.assertEqual(result["fileCopyCount"], 0)

    def test_scope_is_local_validation_only(self) -> None:
        contract = json.loads(AUTHORITY.CONTRACT.read_text())
        forbidden = set(contract["forbiddenActions"])
        self.assertIn("invent or impute missing values", forbidden)
        self.assertIn("parameter fitting or coefficient selection", forbidden)
        self.assertIn("numerical solver execution", forbidden)
        self.assertIn("YODA connection, transfer, activation, or launch", forbidden)
        self.assertIn("GUI integration or promotion", forbidden)
        self.assertIn("git push or release", forbidden)

    def test_no_solver_yoda_or_release_authority(self) -> None:
        result = AUTHORITY.validate_template()
        self.assertEqual(result["solverRunCount"], 0)
        self.assertEqual(result["yodaConnectionCount"], 0)
        self.assertFalse(result["releaseAuthorized"])


if __name__ == "__main__":
    unittest.main()
