from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/stage20_regularized_stage4_ramp_hold_600s_runner_v1.py"
SPEC = importlib.util.spec_from_file_location(
    "stage20_regularized_stage4_ramp_hold_600s_runner_v1", RUNNER_PATH
)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class RegularizedStage4RampHold600sRunnerV1Tests(unittest.TestCase):
    def test_schedule_opens_only_gates_3_to_6_and_holds(self) -> None:
        self.assertEqual(RUNNER.requested_capacity(0.0).tolist(), [0.0] * 8)
        midpoint = RUNNER.requested_capacity(150.0)
        self.assertTrue(np.allclose(midpoint, [0, 0, 0.5, 0.5, 0.5, 0.5, 0, 0]))
        self.assertEqual(RUNNER.requested_capacity(300.0).tolist(), RUNNER.STAGE4.tolist())
        self.assertEqual(RUNNER.requested_capacity(600.0).tolist(), RUNNER.STAGE4.tolist())

    def test_preflight_is_read_only_and_not_physical_validation(self) -> None:
        report = RUNNER.build_preflight()
        self.assertEqual(report["status"], "PASS_LOCAL_FAIL_CLOSED_STAGE4_DIAGNOSTIC_BLOCKED")
        self.assertFalse(report["launchPermitted"])
        self.assertFalse(report["meshAdopted"])
        self.assertFalse(report["physicalValidation"])
        self.assertTrue(report["allBindingsVerified"])

    def test_context_starts_from_bound_all_closed_state_with_fishway_off(self) -> None:
        context = RUNNER.load_runtime_context()
        self.assertEqual(context["state"].shape, (28746, 3))
        self.assertTrue(np.isfinite(context["state"]).all())
        self.assertTrue((context["donor"] == 0.0).all())
        self.assertTrue((context["receiver"] == 0.0).all())
        self.assertGreater(float(np.max(np.abs(context["state"][:, 1:]))), 0.0)

    def test_mid_ramp_one_step_has_outward_flux_and_zero_fishway(self) -> None:
        report = RUNNER.run_local_one_step_test()
        self.assertEqual(
            report["status"],
            "PASS_LOCAL_STAGE4_MIDRAMP_ONE_STEP_FAIL_CLOSED_GUARD",
        )
        self.assertEqual(report["capacityByGateId1To8"], [0, 0, 0.5, 0.5, 0.5, 0.5, 0, 0])
        self.assertGreater(report["activeFaceCount"], 0)
        self.assertGreaterEqual(report["minimumSignedOutwardDischargeM3S"], -1.0e-10)
        self.assertEqual(report["effectiveFishwayDischargeM3S"], 0.0)
        self.assertEqual(report["outputCreationCount"], 0)
        self.assertEqual(report["yodaConnectionCount"], 0)

    def test_near_dry_requested_gate_stops_before_flux_or_step(self) -> None:
        context = RUNNER.load_runtime_context()
        untrusted = {
            "trustedForPositiveMotionByGateId1To8": [True, True, False, True, True, True, True, False]
        }
        with (
            mock.patch.object(RUNNER.observation, "observe_per_gate", return_value=untrusted),
            mock.patch.object(RUNNER.flux_adapter, "signed_outward_gate_discharge_m3_s") as flux,
        ):
            with self.assertRaisesRegex(RUNNER.Stage4RunnerStop, "dry or near-dry"):
                RUNNER.prepare_gate_step(context["state"], context, 150.0)
            flux.assert_not_called()

    def test_adverse_head_is_rejected_before_numerical_step(self) -> None:
        context = RUNNER.load_runtime_context()
        state = context["state"].copy()
        selected = np.isin(context["gate"]["gateIds"], [3, 4, 5, 6])
        downstream = np.unique(context["gate"]["downstream"][selected])
        # The SHA-bound all-closed state retains about 0.247 m of outward head.
        # Raise the downstream side by 0.30 m so every active face is adverse.
        state[downstream, 0] += 0.30
        with self.assertRaisesRegex(ValueError, "rejected without clipping"):
            RUNNER.prepare_gate_step(state, context, 150.0)

    def test_missing_activation_stops_before_context_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "activation.json"
            with (
                mock.patch.object(RUNNER, "ACTIVATION_PATH", missing),
                mock.patch.object(RUNNER, "load_runtime_context") as load_context,
            ):
                with self.assertRaisesRegex(RUNNER.Stage4RunnerStop, "activation is missing"):
                    RUNNER.execute()
                load_context.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_contract_rejects_retry_and_stage_change(self) -> None:
        contract = json.loads(RUNNER.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            [row["role"] for row in contract["bindings"]].count("operational_control"),
            1,
        )
        contract["runtime"]["automaticRetryCount"] = 1
        with self.assertRaisesRegex(RUNNER.Stage4RunnerStop, "automatic retry"):
            RUNNER.validate_contract(contract)
        contract["runtime"]["automaticRetryCount"] = 0
        contract["scope"]["targetMainGateCapacityByGateId1To8"][1] = 1.0
        with self.assertRaisesRegex(RUNNER.Stage4RunnerStop, "stage4 target"):
            RUNNER.validate_contract(contract)

    def test_module_has_no_remote_import(self) -> None:
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse(
            [
                name
                for name in imported
                if any(token in name.lower() for token in ("paramiko", "fabric", "ssh"))
            ]
        )


if __name__ == "__main__":
    unittest.main()
