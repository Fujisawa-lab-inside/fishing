#!/usr/bin/env python3
"""Fail-closed matched 900 s canary for the regularized multizone mesh."""

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
import stage20_continuous_all_closed_successor_runner_v1 as base


CONTRACT_PATH = ROOT / "config/stage20_regularized_multizone_900s_runner_v1.json"
ACTIVATION_PATH = ROOT / "config/stage20_regularized_multizone_900s_activation_20260828_v1.json"
FORCING_PATH = ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
SCHEMA = "onga-stage20-regularized-multizone-900s-runner-v1-contract"
CELL_COUNT = 28746


class RegularizedRunnerStop(RuntimeError):
    """A deliberate fail-closed stop."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RegularizedRunnerStop(
            f"[stage20-regularized-multizone-900s-runner-v1] {message}"
        )


def _binding(contract: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [item for item in contract["bindings"] if item.get("role") == role]
    require(len(matches) == 1, f"binding role is not unique: {role}")
    return matches[0]


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("schema") == SCHEMA, "contract schema changed")
    require(contract.get("version") == 1, "contract version changed")
    require(
        contract.get("status")
        == "MATCHED_CANARY_RUNNER_READY_EXTERNAL_ACTIVATION_REQUIRED",
        "contract status broadened",
    )
    require(
        contract.get("classification")
        == "UNADOPTED_NUMERICAL_MESH_COMPARISON_NOT_PHYSICAL_VALIDATION_NOT_FORECAST_NOT_RELEASE",
        "classification changed",
    )
    scope = contract.get("scope", {})
    require(scope.get("cellCount") == CELL_COUNT, "cell count changed")
    require(scope.get("durationModelSeconds") == 900, "duration changed")
    require(scope.get("cflTarget") == 0.12, "CFL target changed")
    require(scope.get("maximumKernelDtSeconds") == 0.05, "maximum dt changed")
    require(scope.get("mainGateCapacityByGateId1To8") == [0.0] * 8, "gates opened")
    require(
        scope.get("fishwayMode") == "DISABLED_FOR_MATCHED_MESH_COMPARISON",
        "fishway mode changed",
    )
    require(scope.get("fishwayDischargeM3S") == 0.0, "fishway flow enabled")
    runtime = contract.get("runtime", {})
    require(runtime.get("requiredHostname") == "yoda", "target host changed")
    require(runtime.get("automaticRetryCount") == 0, "automatic retry enabled")
    require(runtime.get("maximumWallSeconds") == 1800, "wall guard changed")
    require(runtime.get("maximumAcceptedStepCount") == 500000, "step guard changed")
    require(
        runtime.get("requiredActivationPath")
        == "config/stage20_regularized_multizone_900s_activation_20260828_v1.json",
        "activation path changed",
    )
    require(
        runtime.get("executeWithoutActivation")
        == "FAIL_BEFORE_CONTEXT_LOAD_KERNEL_CALL_OR_OUTPUT_CREATION",
        "missing activation behavior changed",
    )
    safety = contract.get("acceptance", {}).get("numericalSafety", {})
    require(safety.get("simulatedSecondsExactly") == 900.0, "time acceptance changed")
    require(safety.get("maximumCfl") == 0.120000000001, "CFL acceptance changed")
    require(
        safety.get("maximumRelativeMassBalanceError") == 1e-10,
        "mass acceptance changed",
    )
    performance = contract.get("acceptance", {}).get("minimumUsefulPerformance", {})
    require(performance.get("baselineAcceptedSteps") == 179804, "step baseline changed")
    require(
        performance.get("baselineWallSeconds") == 348.18228123150766,
        "wall baseline changed",
    )
    require(performance.get("maximumAcceptedSteps") == 135000, "step target changed")
    require(performance.get("maximumWallSeconds") == 280.0, "wall target changed")
    equivalence = contract.get("acceptance", {}).get(
        "postRunDynamicEquivalenceRequiredForMeshAdoption", {}
    )
    require(equivalence.get("maximumWaterSurfaceRmseM") == 0.1, "eta gate changed")
    require(
        equivalence.get("maximumVelocityVectorRmseMPerS") == 0.01,
        "velocity gate changed",
    )
    bindings = contract.get("bindings")
    require(isinstance(bindings, list) and len(bindings) >= 8, "bindings are incomplete")
    paths: set[str] = set()
    for item in bindings:
        path = item.get("path")
        digest = item.get("sha256")
        require(isinstance(path, str) and path not in paths, f"duplicate binding: {path}")
        require(
            isinstance(digest, str) and base.SHA256_RE.fullmatch(digest) is not None,
            f"invalid binding SHA: {path}",
        )
        paths.add(path)
    for role in (
        "base_fail_closed_runner",
        "diagnostic_forcing",
        "same_pass_limiter_kernel",
        "bounded_telemetry",
        "candidate_mesh",
        "candidate_fields",
    ):
        _binding(contract, role)


def verified_contract() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = base.read_json(CONTRACT_PATH)
    validate_contract(contract)
    bindings = base.verify_bindings(contract)
    return contract, bindings


def _raw_sha(values: np.ndarray) -> str:
    return base.raw_float64_sha256(values)


def _raw_native_sha(values: np.ndarray) -> str:
    return base.hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def load_numerical_context() -> dict[str, Any]:
    """Load the SHA-bound candidate arrays without advancing model time."""

    contract, _ = verified_contract()
    import stage20_depth_weighted_boundary_kernel_candidate_v2 as kernel

    mesh_path = ROOT / _binding(contract, "candidate_mesh")["path"]
    fields_path = ROOT / _binding(contract, "candidate_fields")["path"]
    mesh = kernel.mesh_arrays(mesh_path)
    geometry = kernel.build_review_geometry(mesh)
    with np.load(fields_path, allow_pickle=False) as archive:
        depth = np.asarray(archive["continuous_depth_m"], dtype=np.float64).copy()
        bed = np.asarray(archive["continuous_bed_elevation_m"], dtype=np.float64).copy()
        manning = np.asarray(archive["manning_n"], dtype=np.float64).copy()
        upstream = np.asarray(archive["upstream_component_mask"], dtype=np.uint8).copy()
        p2_donor = np.asarray(archive["p2_donor_overlap_area_m2"], dtype=np.float64)
        p2_receiver = np.asarray(archive["p2_receiver_overlap_area_m2"], dtype=np.float64)
    expected = contract["expectedArrays"]
    require(len(depth) == CELL_COUNT, "candidate cell count changed")
    require(len(depth) == len(bed) == len(manning) == len(geometry["areas"]), "array length mismatch")
    require(np.isfinite(depth).all() and np.all(depth > 0.0), "invalid depth")
    require(np.isfinite(bed).all(), "invalid bed")
    require(np.isfinite(manning).all() and np.all(manning > 0.0), "invalid Manning array")
    checks = {
        "depthRawSha256": _raw_sha(depth),
        "bedRawSha256": _raw_sha(bed),
        "manningRawSha256": _raw_sha(manning),
        "areasRawSha256": _raw_sha(geometry["areas"]),
        "internalMarkersRawSha256": _raw_native_sha(geometry["internalMarkers"]),
        "upstreamMaskRawSha256": _raw_native_sha(upstream),
        "p2DonorRawSha256": _raw_sha(p2_donor),
        "p2ReceiverRawSha256": _raw_sha(p2_receiver),
    }
    require(checks == {key: expected[key] for key in checks}, "candidate array identity changed")
    multipliers = kernel.interface_multiplier(geometry, [])
    base.require_structure_closed(kernel, geometry["internalMarkers"], multipliers)
    zeros = np.zeros(CELL_COUNT, dtype=np.float64)
    return {
        "kernel": kernel,
        "contract": contract,
        "state": np.column_stack((depth, zeros, zeros)).astype(np.float64),
        "bed": bed,
        "manning": manning,
        "geometry": geometry,
        "multipliers": multipliers,
        "donor": zeros.copy(),
        "receiver": zeros.copy(),
    }


def one_step_arguments(context: dict[str, Any]) -> tuple[Any, ...]:
    forcing = base.read_json(FORCING_PATH)
    base.validate_forcing(forcing)
    geometry = context["geometry"]
    discharge = np.zeros(5, dtype=np.float64)
    rivers = forcing["series"]["riverDischargeM3S"]
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        length = float(geometry["boundaryTagLengthSums"][tag])
        require(length > 0.0, f"boundary {boundary_id} has zero length")
        discharge[tag] = -float(rivers[boundary_id][0]) / length
    return (
        context["state"], context["bed"], context["manning"],
        geometry["areas"], geometry["inverseAreas"], geometry["left"], geometry["right"],
        geometry["internalLengths"], geometry["internalNormals"], context["multipliers"],
        geometry["boundaryCells"], geometry["boundaryLengths"], geometry["boundaryNormals"],
        geometry["boundaryTags"], float(forcing["series"]["relativeTideM"][0]), discharge,
        context["donor"], context["receiver"], 0.0, 0.12, 0.05,
    )


def run_local_one_step_equivalence() -> dict[str, Any]:
    context = load_numerical_context()
    kernel = context["kernel"]
    arguments = one_step_arguments(context)
    legacy = kernel.advance_h2_step_depth_weighted_boundary(*arguments)
    traced = kernel.advance_h2_step_depth_weighted_boundary_with_trace_v1(*arguments)
    require(legacy[0].tobytes() == traced.next_state.tobytes(), "state is not bit exact")
    require(
        legacy[1:] == (
            traced.accepted_dt_s, traced.maximum_cfl, traced.boundary_outflow_m3_s,
            traced.effective_fishway_discharge_m3_s, traced.fishway_source_residual_m3_s,
        ),
        "scalar results are not bit exact",
    )
    sample = traced.limiter_sample
    require(sample.coverage_complete, "limiter scan is incomplete")
    require(
        sample.expected_candidate_count == sample.evaluated_candidate_count == CELL_COUNT,
        "limiter scan does not cover every candidate cell",
    )
    require(traced.effective_fishway_discharge_m3_s == 0.0, "fishway flow is nonzero")
    require(traced.fishway_source_residual_m3_s == 0.0, "fishway residual is nonzero")
    return {
        "status": "PASS_LOCAL_ONE_STEP_BIT_EXACT_REGULARIZED_FULL_LIMITER_SCAN",
        "cellCount": CELL_COUNT,
        "acceptedDtSeconds": traced.accepted_dt_s,
        "maximumCfl": traced.maximum_cfl,
        "limitingCellId": sample.cell_id,
        "limiterCoverageComplete": True,
        "mainGateCapacityByGateId1To8": [0.0] * 8,
        "effectiveFishwayDischargeM3S": 0.0,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
    }


def build_preflight() -> dict[str, Any]:
    contract, bindings = verified_contract()
    forcing = base.read_json(FORCING_PATH)
    base.validate_forcing(forcing)
    return {
        "schema": "onga-stage20-regularized-multizone-900s-runner-v1-preflight",
        "status": "PASS_LOCAL_FAIL_CLOSED_MATCHED_CANARY_BLOCKED",
        "launchPermitted": False,
        "activationPresent": ACTIVATION_PATH.is_file(),
        "contractSha256": base.sha256_file(CONTRACT_PATH),
        "bindingCount": len(bindings),
        "allBindingsVerified": True,
        "cellCount": CELL_COUNT,
        "meshAdopted": False,
        "nextRequiredPermission": "SEPARATE_SINGLE_USE_YODA_RUN_AUTHORIZATION",
    }


def validate_activation(activation: dict[str, Any]) -> dict[str, Any]:
    contract, _ = verified_contract()
    require(
        activation.get("schema")
        == "onga-stage20-regularized-multizone-900s-single-use-activation-v1",
        "activation schema changed",
    )
    require(activation.get("status") == "AUTHORIZED", "activation is not authorized")
    require(activation.get("mode") == "EXECUTE_ONCE", "activation mode changed")
    authorization_id = activation.get("authorizationId")
    require(
        isinstance(authorization_id, str)
        and authorization_id.startswith("stage20-regularized-multizone-900s-"),
        "authorization id changed",
    )
    run_id = activation.get("runId")
    require(
        isinstance(run_id, str)
        and re.fullmatch(r"canary-stage20-regularized-multizone-900s-[a-z0-9-]+", run_id),
        "run id changed",
    )
    require(activation.get("requiredHostname") == "yoda", "activation host changed")
    require(activation.get("maximumUseCount") == 1, "activation is not single use")
    require(activation.get("retryCount") == 0, "activation permits retry")
    require(activation.get("durationModelSeconds") == 900, "duration changed")
    require(activation.get("maximumWallSeconds") == 1800, "wall limit changed")
    require(activation.get("mainGateCapacityByGateId1To8") == [0.0] * 8, "gates opened")
    require(activation.get("fishwayDischargeM3S") == 0.0, "fishway enabled")
    require(
        activation.get("runnerSha256") == base.sha256_file(Path(__file__).resolve()),
        "runner SHA mismatch",
    )
    require(
        activation.get("contractSha256") == base.sha256_file(CONTRACT_PATH),
        "contract SHA mismatch",
    )
    require(
        activation.get("forcingSha256") == base.sha256_file(FORCING_PATH),
        "forcing SHA mismatch",
    )
    now = datetime.now(timezone.utc)
    require(base._parse_utc(activation.get("notBefore"), "notBefore") <= now, "activation not active")
    require(now <= base._parse_utc(activation.get("expiresAt"), "expiresAt"), "activation expired")
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
    activation = base.read_json(ACTIVATION_PATH)
    validated = validate_activation(activation)
    require(socket.gethostname().lower() == "yoda", "runtime host is not yoda")
    output = ROOT / validated["outputRelativePath"]
    require(not output.exists() and not output.is_symlink(), "fresh output root required")
    contract = validated["contract"]
    forcing = base.read_json(FORCING_PATH)
    base.validate_forcing(forcing)
    context = load_numerical_context()
    import stage20_dynamic_mesh_comparison_telemetry_v1 as telemetry_module

    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.parent.is_symlink(), "output base is a symlink")
    output.mkdir(mode=0o700)
    activation_sha = base.sha256_file(ACTIVATION_PATH)
    claim = {
        "schema": "onga-stage20-regularized-multizone-900s-claim-v1",
        "authorizationId": activation["authorizationId"],
        "runId": validated["runId"],
        "activationSha256": activation_sha,
        "claimedAtUtc": datetime.now(timezone.utc).isoformat(),
        "processId": os.getpid(),
        "hostname": socket.gethostname(),
        "retryCount": 0,
    }
    base.atomic_write_new(output / "claim.json", base.canonical_bytes(claim))
    base.atomic_write_new(
        output / "start-receipt.json",
        base.canonical_bytes({
            "schema": "onga-stage20-regularized-multizone-900s-start-v1",
            "status": "STARTED_SINGLE_USE_UNADOPTED_MESH_COMPARISON",
            "runId": validated["runId"],
            "durationModelSeconds": 900,
            "cellCount": CELL_COUNT,
            "classification": contract["classification"],
        }),
    )
    collector = telemetry_module.DynamicMeshTelemetry(
        telemetry_module.TelemetryConfig(
            run_id=validated["runId"],
            mesh_id=contract["scope"]["meshId"],
            run_manifest_sha256=activation_sha,
            mesh_sha256=_binding(contract, "candidate_mesh")["sha256"],
            checkpoint_sha256=contract["expectedArrays"]["depthRawSha256"],
            forcing_sha256=base.sha256_file(FORCING_PATH),
            solver_source_sha256=_binding(contract, "same_pass_limiter_kernel")["sha256"],
            control_contract_sha256=base.sha256_file(CONTRACT_PATH),
            bathymetry_sha256=_binding(contract, "candidate_fields")["sha256"],
            approved_limiter_formula_id=telemetry_module.APPROVED_LIMITER_FORMULA_ID,
            required_dt_bound_names=telemetry_module.APPROVED_DT_BOUND_NAMES,
            cfl_target=0.12,
            expected_candidate_count=CELL_COUNT,
            max_accepted_step_count=500000,
            max_accepted_dt_storage_bytes=4000000,
            zero_phase_time_exceptions=(
                ("source", "source work is part of the monolithic numerical kernel"),
                ("wetdry", "wet-dry work is part of the monolithic numerical kernel"),
            ),
        )
    )
    collector.add_phase_wall_ns("source", 0)
    collector.add_phase_wall_ns("wetdry", 0)
    kernel = context["kernel"]
    geometry = context["geometry"]
    state = context["state"].copy()
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_mass_error = 0.0
    maximum_cfl = 0.0
    model_seconds = 0.0
    accepted_steps = 0
    next_check = 60.0
    wall_started = time.monotonic()
    timeline = forcing["timeline"]["modelSeconds"]
    try:
        while model_seconds < 900.0 - 1e-12:
            require(time.monotonic() - wall_started <= 1800.0, "wall-time limit exceeded")
            require(accepted_steps < 500000, "accepted-step limit exceeded")
            with collector.time_phase("control"):
                base.require_structure_closed(kernel, geometry["internalMarkers"], context["multipliers"])
            discharge = np.zeros(5, dtype=np.float64)
            for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
                q = base._interpolate(
                    forcing["series"]["riverDischargeM3S"][boundary_id], timeline, model_seconds
                )
                discharge[tag] = -q / float(geometry["boundaryTagLengthSums"][tag])
            tide = base._interpolate(forcing["series"]["relativeTideM"], timeline, model_seconds)
            maximum_dt = min(0.05, 900.0 - model_seconds)
            with collector.time_phase("flux"):
                step = kernel.advance_h2_step_depth_weighted_boundary_with_trace_v1(
                    state, context["bed"], context["manning"], geometry["areas"],
                    geometry["inverseAreas"], geometry["left"], geometry["right"],
                    geometry["internalLengths"], geometry["internalNormals"],
                    context["multipliers"], geometry["boundaryCells"], geometry["boundaryLengths"],
                    geometry["boundaryNormals"], geometry["boundaryTags"], tide, discharge,
                    context["donor"], context["receiver"], 0.0, 0.12, maximum_dt,
                )
            require(step.effective_fishway_discharge_m3_s == 0.0, "fishway flow became nonzero")
            require(step.fishway_source_residual_m3_s == 0.0, "fishway residual became nonzero")
            collector.record_accepted_step(step.accepted_dt_s, step.limiter_sample)
            state = step.next_state
            model_seconds += step.accepted_dt_s
            accepted_steps += 1
            expected_volume -= step.accepted_dt_s * step.boundary_outflow_m3_s
            maximum_cfl = max(maximum_cfl, step.maximum_cfl)
            if model_seconds >= next_check - 1e-10 or model_seconds >= 900.0 - 1e-10:
                with collector.time_phase("output"):
                    require(np.isfinite(state).all(), "nonfinite state")
                    require(np.all(state[:, 0] >= 0.0), "negative depth")
                    actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
                    mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
                    maximum_mass_error = max(maximum_mass_error, mass_error)
                next_check += 60.0
        runner_wall = time.monotonic() - wall_started
        telemetry_report = collector.finalize(total_runner_wall_seconds=runner_wall)
        safety = contract["acceptance"]["numericalSafety"]
        numerical_pass = (
            math.isclose(model_seconds, safety["simulatedSecondsExactly"], abs_tol=1e-9)
            and maximum_cfl <= safety["maximumCfl"]
            and maximum_mass_error <= safety["maximumRelativeMassBalanceError"]
            and np.isfinite(state).all()
            and not np.any(state[:, 0] < 0.0)
        )
        require(numerical_pass, "frozen numerical acceptance failed")
        performance = contract["acceptance"]["minimumUsefulPerformance"]
        performance_pass = (
            accepted_steps <= performance["maximumAcceptedSteps"]
            and runner_wall <= performance["maximumWallSeconds"]
        )
        result = {
            "schema": "onga-stage20-regularized-multizone-900s-result-v1",
            "status": "PASS_NUMERICAL_900S_UNADOPTED_MESH_COMPARISON_NOT_PHYSICAL_VALIDATION",
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
            "performanceComparisonStatus": "PASS_MINIMUM_USEFUL" if performance_pass else "FAIL_MINIMUM_USEFUL",
            "acceptedStepRatioToR1C": accepted_steps / performance["baselineAcceptedSteps"],
            "wallRatioToR1C": runner_wall / performance["baselineWallSeconds"],
            "mainGateCapacityByGateId1To8": [0.0] * 8,
            "fishwayDischargeM3S": 0.0,
            "meshAdopted": False,
            "dynamicEquivalenceEvaluated": False,
            "classification": contract["classification"],
        }
        base.atomic_save_array_new(output / "final-state.npy", state)
        base.atomic_write_new(output / "telemetry.json", base.canonical_bytes(telemetry_report))
        base.atomic_write_new(output / "result.json", base.canonical_bytes(result))
        completion = {
            "schema": "onga-stage20-regularized-multizone-900s-completion-v1",
            "status": result["status"],
            "runId": validated["runId"],
            "resultSha256": base.sha256_file(output / "result.json"),
            "telemetrySha256": base.sha256_file(output / "telemetry.json"),
            "finalStateSha256": base.sha256_file(output / "final-state.npy"),
        }
        base.atomic_write_new(output / "completion-receipt.json", base.canonical_bytes(completion))
        manifest = {
            "schema": "onga-stage20-regularized-multizone-900s-manifest-v1",
            "runId": validated["runId"],
            "files": [
                {"path": path.name, "sha256": base.sha256_file(path)}
                for path in sorted(output.iterdir()) if path.is_file()
            ],
        }
        base.atomic_write_new(output / "manifest.json", base.canonical_bytes(manifest))
        return result
    except Exception as error:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            base.atomic_write_new(failure, base.canonical_bytes({
                "schema": "onga-stage20-regularized-multizone-900s-failure-v1",
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
        report = run_local_one_step_equivalence()
    else:
        report = build_preflight()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegularizedRunnerStop, base.SuccessorRunnerStop) as error:
        raise SystemExit(str(error)) from error
