from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/stage20_regularized_multizone_900s_runner_v1.py"
SPEC = importlib.util.spec_from_file_location("regularized_multizone_900s_runner_v1", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class RegularizedMultizone900sRunnerV1Tests(unittest.TestCase):
    def test_preflight_is_read_only_and_unadopted(self) -> None:
        report = RUNNER.build_preflight()
        self.assertEqual(report["status"], "PASS_LOCAL_FAIL_CLOSED_MATCHED_CANARY_BLOCKED")
        self.assertFalse(report["launchPermitted"])
        self.assertFalse(report["meshAdopted"])
        self.assertEqual(report["cellCount"], 28746)
        self.assertTrue(report["allBindingsVerified"])

    def test_missing_activation_stops_before_context_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "activation.json"
            with (
                mock.patch.object(RUNNER, "ACTIVATION_PATH", missing),
                mock.patch.object(RUNNER, "load_numerical_context") as load_context,
            ):
                with self.assertRaisesRegex(RUNNER.RegularizedRunnerStop, "activation is missing"):
                    RUNNER.execute()
                load_context.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_activation_stops_before_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            activation = Path(directory) / "activation.json"
            activation.write_text("{}\n", encoding="utf-8")
            with (
                mock.patch.object(RUNNER, "ACTIVATION_PATH", activation),
                mock.patch.object(RUNNER, "load_numerical_context") as load_context,
            ):
                with self.assertRaisesRegex(RUNNER.RegularizedRunnerStop, "activation schema"):
                    RUNNER.execute()
                load_context.assert_not_called()

    def test_contract_separates_numerical_performance_and_adoption(self) -> None:
        contract = json.loads(RUNNER.CONTRACT_PATH.read_text(encoding="utf-8"))
        acceptance = contract["acceptance"]
        self.assertIn("numericalSafety", acceptance)
        self.assertIn("minimumUsefulPerformance", acceptance)
        self.assertIn("postRunDynamicEquivalenceRequiredForMeshAdoption", acceptance)
        self.assertIn("UNADOPTED", contract["classification"])

    def test_contract_rejects_retry_or_relaxed_performance(self) -> None:
        contract = json.loads(RUNNER.CONTRACT_PATH.read_text(encoding="utf-8"))
        contract["runtime"]["automaticRetryCount"] = 1
        with self.assertRaisesRegex(RUNNER.RegularizedRunnerStop, "automatic retry"):
            RUNNER.validate_contract(contract)
        contract["runtime"]["automaticRetryCount"] = 0
        contract["acceptance"]["minimumUsefulPerformance"]["maximumAcceptedSteps"] = 170000
        with self.assertRaisesRegex(RUNNER.RegularizedRunnerStop, "step target"):
            RUNNER.validate_contract(contract)

    def test_module_has_no_remote_import(self) -> None:
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse([name for name in imported if any(token in name.lower() for token in ("paramiko", "fabric", "ssh"))])

    def test_context_has_exact_candidate_arrays_and_closed_interfaces(self) -> None:
        context = RUNNER.load_numerical_context()
        self.assertEqual(context["state"].shape, (28746, 3))
        self.assertTrue((context["donor"] == 0.0).all())
        self.assertTrue((context["receiver"] == 0.0).all())
        RUNNER.base.require_structure_closed(
            context["kernel"], context["geometry"]["internalMarkers"], context["multipliers"]
        )

    def test_local_one_step_is_bit_exact_and_full_scan(self) -> None:
        report = RUNNER.run_local_one_step_equivalence()
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_ONE_STEP_BIT_EXACT_REGULARIZED_FULL_LIMITER_SCAN",
        )
        self.assertEqual(report["cellCount"], 28746)
        self.assertTrue(report["limiterCoverageComplete"])
        self.assertEqual(report["effectiveFishwayDischargeM3S"], 0.0)
        self.assertEqual(report["outputCreationCount"], 0)
        self.assertEqual(report["yodaConnectionCount"], 0)


if __name__ == "__main__":
    unittest.main()
