#!/usr/bin/env python3
"""Fail-closed 300 s ramp + 300 s hold diagnostic on the regularized mesh."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_stage20_barrage_C1_local_transition_600s_v1 as mapping
import stage20_barrage_fractional_motion_r1c_adapter_v1 as fractional
import stage20_barrage_operational_control_r1c_adapter_v1 as flux_adapter
import stage20_regularized_multizone_900s_runner_v1 as matched
import stage20_regularized_multizone_gate_observation_v1 as observation


CONTRACT_PATH = ROOT / "config/stage20_regularized_stage4_ramp_hold_600s_runner_v1.json"
ACTIVATION_PATH = ROOT / "config/stage20_regularized_stage4_ramp_hold_600s_activation_20260828_v1.json"
FORCING_PATH = ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
SCHEMA = "onga-stage20-regularized-stage4-ramp-hold-600s-runner-v1-contract"
CELL_COUNT = 28746
RAMP_SECONDS = 300.0
TOTAL_SECONDS = 600.0
FORCING_OFFSET_SECONDS = 900.0
STAGE4 = np.asarray([0, 0, 1, 1, 1, 1, 0, 0], dtype=np.float64)
RAMPING = np.asarray([2, 3, 4, 5], dtype=np.int64)
REVERSE_TOLERANCE_M3_S = 1.0e-10


class Stage4RunnerStop(RuntimeError):
    """A deliberate fail-closed stop."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Stage4RunnerStop(
            f"[stage20-regularized-stage4-ramp-hold-600s-runner-v1] {message}"
        )


def _binding(contract: dict[str, Any], role: str) -> dict[str, Any]:
    rows = [item for item in contract["bindings"] if item.get("role") == role]
    require(len(rows) == 1, f"binding role is not unique: {role}")
    return rows[0]


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("schema") == SCHEMA, "contract schema changed")
    require(contract.get("version") == 1, "contract version changed")
    require(
        contract.get("status") == "DIAGNOSTIC_RUNNER_READY_EXTERNAL_ACTIVATION_REQUIRED",
        "contract status broadened",
    )
    require("NOT_OPERATIONAL_CONTROL" in contract.get("classification", ""), "classification broadened")
    scope = contract.get("scope", {})
    require(scope.get("cellCount") == CELL_COUNT, "cell count changed")
    require(scope.get("durationModelSeconds") == 600, "duration changed")
    require(scope.get("rampDurationModelSeconds") == 300, "ramp duration changed")
    require(scope.get("holdDurationModelSeconds") == 300, "hold duration changed")
    require(
        scope.get("forcingContinuationPolicy")
        == "HOLD_FINAL_900S_FORCING_VALUE_DURING_600S_DIAGNOSTIC",
        "forcing continuation changed",
    )
    require(scope.get("targetMainGateCapacityByGateId1To8") == STAGE4.tolist(), "stage4 target changed")
    require(scope.get("fishwayDischargeM3S") == 0.0, "fishway enabled")
    require(scope.get("reverseFluxToleranceM3S") == REVERSE_TOLERANCE_M3_S, "reverse tolerance changed")
    runtime = contract.get("runtime", {})
    require(runtime.get("requiredHostname") == "yoda", "target host changed")
    require(runtime.get("automaticRetryCount") == 0, "automatic retry enabled")
    require(runtime.get("maximumWallSeconds") == 1200, "wall limit changed")
    require(runtime.get("maximumAcceptedStepCount") == 250000, "step limit changed")
    require(
        runtime.get("requiredActivationPath")
        == "config/stage20_regularized_stage4_ramp_hold_600s_activation_20260828_v1.json",
        "activation path changed",
    )
    bindings = contract.get("bindings")
    require(isinstance(bindings, list) and len(bindings) >= 10, "bindings are incomplete")
    paths: set[str] = set()
    for item in bindings:
        path = item.get("path")
        digest = item.get("sha256")
        require(isinstance(path, str) and path not in paths, f"duplicate binding: {path}")
        require(
            isinstance(digest, str) and matched.base.SHA256_RE.fullmatch(digest) is not None,
            f"invalid binding SHA: {path}",
        )
        paths.add(path)
    for role in (
        "all_closed_runner",
        "diagnostic_forcing",
        "gate_observation",
        "mapping_runtime",
        "fractional_flux_guard",
        "signed_flux_adapter",
        "initial_all_closed_state",
        "candidate_mesh",
        "candidate_fields",
    ):
        _binding(contract, role)


def verified_contract() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = matched.base.read_json(CONTRACT_PATH)
    validate_contract(contract)
    return contract, matched.base.verify_bindings(contract)


def requested_capacity(model_seconds: float) -> np.ndarray:
    require(math.isfinite(model_seconds) and model_seconds >= 0.0, "invalid model time")
    result = np.empty(8, dtype=np.float64)
    mapping.set_capacity_at_time(
        result,
        np.zeros(8, dtype=np.float64),
        RAMPING,
        1.0,
        min(float(model_seconds), RAMP_SECONDS),
        RAMP_SECONDS,
    )
    require(np.all((result >= 0.0) & (result <= 1.0)), "capacity escaped 0..1")
    require(np.all(result[[0, 1, 6, 7]] == 0.0), "non-stage4 gate opened")
    return result


def load_runtime_context() -> dict[str, Any]:
    contract, _ = verified_contract()
    numerical = matched.load_numerical_context()
    gate = observation.load_bound_context()
    initial_path = ROOT / _binding(contract, "initial_all_closed_state")["path"]
    initial = np.asarray(np.load(initial_path, allow_pickle=False), dtype=np.float64)
    require(initial.shape == (CELL_COUNT, 3), "initial state shape changed")
    require(np.isfinite(initial).all() and np.all(initial[:, 0] >= 0.0), "initial state invalid")
    require(np.array_equal(numerical["bed"], gate["bed"]), "observation bed differs")
    for name in ("left", "right", "internalMarkers", "internalLengths", "internalNormals"):
        require(
            np.array_equal(numerical["geometry"][name], gate["geometry"][name]),
            f"observation geometry differs: {name}",
        )
    workspace = mapping.build_mapping_workspace(numerical["geometry"])
    require(np.all(numerical["donor"] == 0.0), "fishway donor is nonzero")
    require(np.all(numerical["receiver"] == 0.0), "fishway receiver is nonzero")
    return {
        **numerical,
        "contract": contract,
        "state": initial.copy(),
        "gate": gate,
        "workspace": workspace,
    }


def prepare_gate_step(
    state: np.ndarray,
    context: dict[str, Any],
    model_seconds: float,
) -> dict[str, Any]:
    requested = requested_capacity(model_seconds)
    observed = observation.observe_per_gate(state, context["gate"])
    effective = observation.fail_closed_requested_capacity(requested, observed)
    require(
        np.array_equal(effective, requested),
        "requested gate is dry or near-dry; capacity rejected before numerical step",
    )
    workspace = context["workspace"]
    mapping.update_mapping_workspace(workspace, effective)
    signed_flux = flux_adapter.signed_outward_gate_discharge_m3_s(
        state,
        context["bed"],
        context["geometry"],
        context["gate"]["gateFaces"],
        context["gate"]["upstream"],
        workspace["effectiveLengths"],
        workspace["multipliers"],
    )
    validation = fractional.validate_fractional_active_flux(
        signed_flux,
        workspace["gateIndexBySelectedFace"],
        effective,
        tolerance_m3_s=REVERSE_TOLERANCE_M3_S,
    )
    return {
        "requestedCapacity": requested,
        "effectiveCapacity": effective,
        "observation": observed,
        "signedOutwardFluxM3S": signed_flux,
        "validation": validation,
    }


def _forcing_values(
    forcing: dict[str, Any], geometry: dict[str, Any], model_seconds: float
) -> tuple[float, np.ndarray]:
    timeline = forcing["timeline"]["modelSeconds"]
    forcing_seconds = FORCING_OFFSET_SECONDS + model_seconds
    discharge = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        value = matched.base._interpolate(
            forcing["series"]["riverDischargeM3S"][boundary_id],
            timeline,
            forcing_seconds,
        )
        discharge[tag] = -value / float(geometry["boundaryTagLengthSums"][tag])
    tide = matched.base._interpolate(
        forcing["series"]["relativeTideM"], timeline, forcing_seconds
    )
    return tide, discharge


def advance_one_step(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
) -> tuple[Any, dict[str, Any]]:
    guard = prepare_gate_step(state, context, model_seconds)
    tide, discharge = _forcing_values(forcing, context["geometry"], model_seconds)
    geometry = context["geometry"]
    workspace = context["workspace"]
    step = context["kernel"].advance_h2_step_depth_weighted_boundary_with_trace_v1(
        state,
        context["bed"],
        context["manning"],
        geometry["areas"],
        geometry["inverseAreas"],
        geometry["left"],
        geometry["right"],
        workspace["effectiveLengths"],
        geometry["internalNormals"],
        workspace["multipliers"],
        geometry["boundaryCells"],
        geometry["boundaryLengths"],
        geometry["boundaryNormals"],
        geometry["boundaryTags"],
        tide,
        discharge,
        context["donor"],
        context["receiver"],
        0.0,
        0.12,
        maximum_dt,
    )
    require(step.effective_fishway_discharge_m3_s == 0.0, "fishway flow became nonzero")
    require(step.fishway_source_residual_m3_s == 0.0, "fishway residual became nonzero")
    return step, guard


def run_local_one_step_test() -> dict[str, Any]:
    context = load_runtime_context()
    forcing = matched.base.read_json(FORCING_PATH)
    matched.base.validate_forcing(forcing)
    step, guard = advance_one_step(context["state"], context, forcing, 150.0, 0.05)
    require(np.isfinite(step.next_state).all(), "one-step state is nonfinite")
    require(not np.any(step.next_state[:, 0] < 0.0), "one-step depth is negative")
    return {
        "status": "PASS_LOCAL_STAGE4_MIDRAMP_ONE_STEP_FAIL_CLOSED_GUARD",
        "acceptedDtSeconds": step.accepted_dt_s,
        "maximumCfl": step.maximum_cfl,
        "capacityByGateId1To8": guard["effectiveCapacity"].tolist(),
        "activeFaceCount": guard["validation"]["activeFaceCount"],
        "minimumSignedOutwardDischargeM3S": guard["validation"]["minimumSignedOutwardDischargeM3S"],
        "effectiveFishwayDischargeM3S": step.effective_fishway_discharge_m3_s,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
    }


def build_preflight() -> dict[str, Any]:
    contract, bindings = verified_contract()
    return {
        "schema": "onga-stage20-regularized-stage4-ramp-hold-600s-preflight-v1",
        "status": "PASS_LOCAL_FAIL_CLOSED_STAGE4_DIAGNOSTIC_BLOCKED",
        "launchPermitted": False,
        "activationPresent": ACTIVATION_PATH.is_file(),
        "bindingCount": len(bindings),
        "allBindingsVerified": True,
        "durationModelSeconds": 600,
        "targetMainGateCapacityByGateId1To8": STAGE4.tolist(),
        "meshAdopted": False,
        "physicalValidation": False,
        "classification": contract["classification"],
        "nextRequiredPermission": "SEPARATE_SINGLE_USE_YODA_RUN_AUTHORIZATION",
    }


def validate_activation(activation: dict[str, Any]) -> dict[str, Any]:
    contract, _ = verified_contract()
    require(
        activation.get("schema")
        == "onga-stage20-regularized-stage4-ramp-hold-600s-single-use-activation-v1",
        "activation schema changed",
    )
    require(activation.get("status") == "AUTHORIZED", "activation is not authorized")
    require(activation.get("mode") == "EXECUTE_ONCE", "activation mode changed")
    authorization_id = activation.get("authorizationId")
    require(
        isinstance(authorization_id, str)
        and authorization_id.startswith("stage20-regularized-stage4-ramp-hold-600s-"),
        "authorization id changed",
    )
    run_id = activation.get("runId")
    require(
        isinstance(run_id, str)
        and re.fullmatch(r"canary-stage20-regularized-stage4-ramp-hold-600s-[a-z0-9-]+", run_id),
        "run id changed",
    )
    require(activation.get("requiredHostname") == "yoda", "activation host changed")
    require(activation.get("maximumUseCount") == 1, "activation is not single use")
    require(activation.get("retryCount") == 0, "activation permits retry")
    require(activation.get("durationModelSeconds") == 600, "duration changed")
    require(activation.get("maximumWallSeconds") == 1200, "wall limit changed")
    require(activation.get("targetMainGateCapacityByGateId1To8") == STAGE4.tolist(), "stage4 target changed")
    require(activation.get("fishwayDischargeM3S") == 0.0, "fishway enabled")
    require(
        activation.get("runnerSha256") == matched.base.sha256_file(Path(__file__).resolve()),
        "runner SHA mismatch",
    )
    require(
        activation.get("contractSha256") == matched.base.sha256_file(CONTRACT_PATH),
        "contract SHA mismatch",
    )
    require(
        activation.get("forcingSha256") == matched.base.sha256_file(FORCING_PATH),
        "forcing SHA mismatch",
    )
    now = datetime.now(timezone.utc)
    require(matched.base._parse_utc(activation.get("notBefore"), "notBefore") <= now, "activation not active")
    require(now <= matched.base._parse_utc(activation.get("expiresAt"), "expiresAt"), "activation expired")
    output_relative = activation.get("outputRelativePath")
    require(
        output_relative == f"{contract['runtime']['outputBase']}/{run_id}",
        "output path changed",
    )
    candidate = Path(output_relative)
    require(not candidate.is_absolute() and ".." not in candidate.parts, "output escapes root")
    return {"contract": contract, "runId": run_id, "outputRelativePath": output_relative}


def execute() -> dict[str, Any]:
    require(ACTIVATION_PATH.is_file(), "external single-use activation is missing")
    activation = matched.base.read_json(ACTIVATION_PATH)
    validated = validate_activation(activation)
    require(socket.gethostname().lower() == "yoda", "runtime host is not yoda")
    output = ROOT / validated["outputRelativePath"]
    require(not output.exists() and not output.is_symlink(), "fresh output root required")
    forcing = matched.base.read_json(FORCING_PATH)
    matched.base.validate_forcing(forcing)
    context = load_runtime_context()

    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.parent.is_symlink(), "output base is a symlink")
    output.mkdir(mode=0o700)
    activation_sha = matched.base.sha256_file(ACTIVATION_PATH)
    claim = {
        "schema": "onga-stage20-regularized-stage4-ramp-hold-600s-claim-v1",
        "authorizationId": activation["authorizationId"],
        "runId": validated["runId"],
        "activationSha256": activation_sha,
        "claimedAtUtc": datetime.now(timezone.utc).isoformat(),
        "processId": os.getpid(),
        "hostname": socket.gethostname(),
        "retryCount": 0,
    }
    matched.base.atomic_write_new(output / "claim.json", matched.base.canonical_bytes(claim))
    matched.base.atomic_write_new(
        output / "start-receipt.json",
        matched.base.canonical_bytes({
            "schema": "onga-stage20-regularized-stage4-ramp-hold-600s-start-v1",
            "status": "STARTED_SINGLE_USE_PRESCRIBED_STAGE4_DIAGNOSTIC",
            "runId": validated["runId"],
            "durationModelSeconds": 600,
            "classification": validated["contract"]["classification"],
        }),
    )

    geometry = context["geometry"]
    state = context["state"].copy()
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_mass_error = 0.0
    maximum_cfl = 0.0
    minimum_active_flux = math.inf
    model_seconds = 0.0
    accepted_steps = 0
    guard_evaluations = 0
    next_check = 60.0
    wall_started = time.monotonic()
    last_capacity = np.zeros(8, dtype=np.float64)
    try:
        while model_seconds < TOTAL_SECONDS - 1e-12:
            require(time.monotonic() - wall_started <= 1200.0, "wall-time limit exceeded")
            require(accepted_steps < 250000, "accepted-step limit exceeded")
            maximum_dt = min(0.05, TOTAL_SECONDS - model_seconds)
            step, guard = advance_one_step(
                state, context, forcing, model_seconds, maximum_dt
            )
            guard_evaluations += 1
            last_capacity = guard["effectiveCapacity"].copy()
            minimum = guard["validation"]["minimumSignedOutwardDischargeM3S"]
            if minimum is not None:
                minimum_active_flux = min(minimum_active_flux, float(minimum))
            state = step.next_state
            model_seconds += step.accepted_dt_s
            accepted_steps += 1
            expected_volume -= step.accepted_dt_s * step.boundary_outflow_m3_s
            maximum_cfl = max(maximum_cfl, step.maximum_cfl)
            if model_seconds >= next_check - 1e-10 or model_seconds >= TOTAL_SECONDS - 1e-10:
                require(np.isfinite(state).all(), "nonfinite state")
                require(np.all(state[:, 0] >= 0.0), "negative depth")
                actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
                mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
                maximum_mass_error = max(maximum_mass_error, mass_error)
                next_check += 60.0
        runner_wall = time.monotonic() - wall_started
        final_capacity = requested_capacity(TOTAL_SECONDS)
        require(np.array_equal(last_capacity, final_capacity), "final capacity not reached")
        safety = validated["contract"]["acceptance"]["numericalSafety"]
        require(math.isclose(model_seconds, safety["simulatedSecondsExactly"], abs_tol=1e-9), "duration acceptance failed")
        require(maximum_cfl <= safety["maximumCfl"], "CFL acceptance failed")
        require(maximum_mass_error <= safety["maximumRelativeMassBalanceError"], "mass acceptance failed")
        result = {
            "schema": "onga-stage20-regularized-stage4-ramp-hold-600s-result-v1",
            "status": "PASS_NUMERICAL_600S_PRESCRIBED_STAGE4_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION",
            "runId": validated["runId"],
            "simulatedSeconds": model_seconds,
            "acceptedSteps": accepted_steps,
            "wallSeconds": runner_wall,
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "minimumDepthM": float(np.min(state[:, 0])),
            "maximumDepthM": float(np.max(state[:, 0])),
            "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
            "negativeDepthCount": int(np.sum(state[:, 0] < 0.0)),
            "gateGuardEvaluationCount": guard_evaluations,
            "gateGuardEvaluatedBeforeEveryAcceptedStep": guard_evaluations == accepted_steps,
            "minimumActiveFaceSignedOutwardDischargeM3S": None if math.isinf(minimum_active_flux) else minimum_active_flux,
            "finalMainGateCapacityByGateId1To8": final_capacity.tolist(),
            "effectiveFishwayDischargeM3S": 0.0,
            "meshAdopted": False,
            "physicalValidation": False,
            "classification": validated["contract"]["classification"],
        }
        matched.base.atomic_save_array_new(output / "final-state.npy", state)
        matched.base.atomic_write_new(output / "result.json", matched.base.canonical_bytes(result))
        completion = {
            "schema": "onga-stage20-regularized-stage4-ramp-hold-600s-completion-v1",
            "status": result["status"],
            "runId": validated["runId"],
            "resultSha256": matched.base.sha256_file(output / "result.json"),
            "finalStateSha256": matched.base.sha256_file(output / "final-state.npy"),
        }
        matched.base.atomic_write_new(output / "completion-receipt.json", matched.base.canonical_bytes(completion))
        manifest = {
            "schema": "onga-stage20-regularized-stage4-ramp-hold-600s-manifest-v1",
            "runId": validated["runId"],
            "files": [
                {"path": path.name, "sha256": matched.base.sha256_file(path)}
                for path in sorted(output.iterdir()) if path.is_file()
            ],
        }
        matched.base.atomic_write_new(output / "manifest.json", matched.base.canonical_bytes(manifest))
        return result
    except Exception as error:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            matched.base.atomic_write_new(failure, matched.base.canonical_bytes({
                "schema": "onga-stage20-regularized-stage4-ramp-hold-600s-failure-v1",
                "status": "FAILED_NO_RETRY",
                "runId": validated["runId"],
                "errorType": type(error).__name__,
                "message": str(error),
            }))
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--local-one-step-test", action="store_true")
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    require(sum((arguments.preflight, arguments.local_one_step_test, arguments.execute)) <= 1, "choose one mode")
    if arguments.execute:
        report = execute()
    elif arguments.local_one_step_test:
        report = run_local_one_step_test()
    else:
        report = build_preflight()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Stage4RunnerStop, matched.RegularizedRunnerStop, matched.base.SuccessorRunnerStop) as error:
        raise SystemExit(str(error)) from error
