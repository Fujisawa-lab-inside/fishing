from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_observation_intake_prepare_only_package_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_observation_intake_prepare_only_package_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class Stage20BarrageObservationIntakePrepareOnlyPackageV1Tests(unittest.TestCase):
    def test_static_closure_is_sha_verified(self) -> None:
        result = PACKAGE.validate_package()
        self.assertEqual(result["status"], "PASS_PREPARE_ONLY_STATIC_CLOSURE")
        self.assertEqual(result["bindingCount"], 26)
        self.assertTrue(result["allBindingsVerified"])

    def test_package_grants_no_execution_or_release_authority(self) -> None:
        result = PACKAGE.validate_package()
        self.assertEqual(result["parameterFitCount"], 0)
        self.assertEqual(result["solverRunCount"], 0)
        self.assertEqual(result["yodaConnectionCount"], 0)
        self.assertEqual(result["packageTransferCount"], 0)
        self.assertFalse(result["releaseAuthorized"])


if __name__ == "__main__":
    unittest.main()
