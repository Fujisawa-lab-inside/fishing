from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/stage20_continuous_all_closed_successor_runner_v1.py"
SPEC = importlib.util.spec_from_file_location("all_closed_successor_runner_v1", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class AllClosedSuccessorRunnerV1Tests(unittest.TestCase):
    def test_preflight_is_read_only_blocked_and_all_closed(self) -> None:
        report = RUNNER.build_preflight()
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_FAIL_CLOSED_ENTRYPOINT_FULL_CANARY_BLOCKED",
        )
        self.assertFalse(report["launchPermitted"])
        self.assertTrue(report["allBindingsVerified"])
        self.assertEqual(report["mainGateCapacityByGateId1To8"], [0.0] * 8)
        self.assertEqual(report["fishwayDischargeM3S"], 0.0)
        self.assertTrue(all(value == 0 for value in report["effects"].values()))

    def test_missing_activation_stops_before_any_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "activation.json"
            with mock.patch.object(RUNNER, "ACTIVATION_PATH", missing):
                with self.assertRaisesRegex(
                    RUNNER.SuccessorRunnerStop,
                    "external single-use activation is missing",
                ):
                    RUNNER.execute()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_present_activation_stops_before_context_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            activation = Path(directory) / "activation.json"
            activation.write_text("{}\n", encoding="utf-8")
            with (
                mock.patch.object(RUNNER, "ACTIVATION_PATH", activation),
                mock.patch.object(RUNNER, "load_numerical_context") as load_context,
            ):
                with self.assertRaisesRegex(RUNNER.SuccessorRunnerStop, "activation schema"):
                    RUNNER.execute()
                load_context.assert_not_called()
            self.assertEqual([path.name for path in Path(directory).iterdir()], ["activation.json"])

    def test_module_has_no_numerical_or_remote_import(self) -> None:
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        # Numerical imports must remain lazy inside the explicit one-step path;
        # remote libraries are forbidden everywhere.
        forbidden_fragments = ("paramiko", "fabric", "ssh")
        self.assertFalse(
            [name for name in imported if any(part in name.lower() for part in forbidden_fragments)]
        )

    def test_local_one_step_is_bit_exact_all_closed_and_fishway_zero(self) -> None:
        report = RUNNER.run_local_one_step_equivalence()
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_ONE_STEP_BIT_EXACT_FULL_LIMITER_SCAN",
        )
        self.assertEqual(report["cellCount"], 37724)
        self.assertTrue(report["limiterCoverageComplete"])
        self.assertEqual(report["effectiveFishwayDischargeM3S"], 0.0)
        self.assertEqual(report["fishwaySourceResidualM3S"], 0.0)
        self.assertEqual(report["mainGateCapacityByGateId1To8"], [0.0] * 8)
        self.assertEqual(report["outputCreationCount"], 0)
        self.assertEqual(report["yodaConnectionCount"], 0)

    def test_runtime_structure_guard_ignores_other_nonzero_markers(self) -> None:
        kernel = SimpleNamespace(FIXED_MARKER=200, GATE_MARKER_BASE=100)
        markers = RUNNER.np.asarray([0, 7, 101, 108, 109, 200, 240])
        multipliers = RUNNER.np.asarray([1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0])
        RUNNER.require_structure_closed(kernel, markers, multipliers)
        multipliers[2] = 1.0
        with self.assertRaisesRegex(RUNNER.SuccessorRunnerStop, "structure opened"):
            RUNNER.require_structure_closed(kernel, markers, multipliers)

    def test_forcing_rejects_positive_gate_or_fishway_flow(self) -> None:
        forcing = json.loads(
            (ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json")
            .read_text(encoding="utf-8")
        )
        forcing["runCompatibility"]["mainGateCapacityByGateId1To8"][3] = 0.1
        with self.assertRaisesRegex(RUNNER.SuccessorRunnerStop, "nonzero main gate"):
            RUNNER.validate_forcing(forcing)
        forcing["runCompatibility"]["mainGateCapacityByGateId1To8"][3] = 0.0
        forcing["runCompatibility"]["fishwayDischargeM3S"] = 0.01
        with self.assertRaisesRegex(RUNNER.SuccessorRunnerStop, "fishway flow"):
            RUNNER.validate_forcing(forcing)

    def test_contract_rejects_retry_or_broader_status(self) -> None:
        contract = json.loads(RUNNER.CONTRACT_PATH.read_text(encoding="utf-8"))
        contract["runtime"]["automaticRetryCount"] = 1
        with self.assertRaisesRegex(RUNNER.SuccessorRunnerStop, "automatic retry"):
            RUNNER.validate_contract(contract)
        contract["runtime"]["automaticRetryCount"] = 0
        contract["status"] = "READY_TO_RUN"
        with self.assertRaisesRegex(RUNNER.SuccessorRunnerStop, "status broadened"):
            RUNNER.validate_contract(contract)


if __name__ == "__main__":
    unittest.main()
