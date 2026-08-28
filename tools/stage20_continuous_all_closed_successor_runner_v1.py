#!/usr/bin/env python3
"""Fail-closed entrypoint for a future all-closed Stage 20 canary.

The current milestone permits a bounded local one-step equivalence test.  Full
canary execution still stops before output creation or YODA connection.  The
numerical modules are imported lazily only by the explicit one-step test path.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
CONTRACT_PATH = ROOT / "config/stage20_continuous_all_closed_successor_runner_v1.json"
ACTIVATION_PATH = (
    ROOT / "config/stage20_continuous_all_closed_canary_activation_20260828_v1.json"
)
SCHEMA = "onga-stage20-continuous-all-closed-successor-runner-v1-contract"
FORCING_SCHEMA = "onga-stage20-continuous-all-closed-forcing-manifest-v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class SuccessorRunnerStop(RuntimeError):
    """A deliberate stop before any numerical or remote side effect."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SuccessorRunnerStop(
            f"[stage20-continuous-all-closed-successor-runner-v1] {message}"
        )


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                SuccessorRunnerStop(f"nonfinite JSON token: {token}")
            ),
        )
    except (OSError, json.JSONDecodeError) as error:
        raise SuccessorRunnerStop(f"cannot read JSON {path}: {error}") from error
    require(isinstance(value, dict), f"{path} must contain one JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise SuccessorRunnerStop(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def relative_regular_file(relative: Any) -> Path:
    require(isinstance(relative, str) and relative, "binding path is empty")
    candidate = Path(relative)
    require(not candidate.is_absolute(), f"absolute binding forbidden: {relative}")
    require(".." not in candidate.parts, f"parent traversal forbidden: {relative}")
    full = ROOT / candidate
    require(full.is_file() and not full.is_symlink(), f"invalid binding: {relative}")
    require(
        full.resolve().is_relative_to(ROOT.resolve()),
        f"binding escapes workspace: {relative}",
    )
    return full


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("schema") == SCHEMA, "contract schema changed")
    require(contract.get("version") == 1, "contract version changed")
    require(
        contract.get("status")
        == "FULL_CANARY_RUNNER_READY_EXTERNAL_ACTIVATION_REQUIRED",
        "contract status broadened",
    )
    require(
        contract.get("classification")
        == "DIAGNOSTIC_ALL_CLOSED_BASELINE_NOT_FORECAST_NOT_PHYSICAL_VALIDATION_NOT_RELEASE",
        "classification changed",
    )
    scope = contract.get("scope", {})
    require(scope.get("cellCount") == 37724, "cell count changed")
    require(scope.get("durationModelSeconds") == 900, "duration changed")
    require(scope.get("cflTarget") == 0.12, "CFL target changed")
    require(scope.get("maximumKernelDtSeconds") == 0.05, "maximum dt changed")
    require(
        scope.get("mainGateCapacityByGateId1To8") == [0.0] * 8,
        "main gates are not all closed",
    )
    require(scope.get("fishwayMode") == "DISABLED", "fishway is not disabled")
    require(scope.get("fishwayDischargeM3S") == 0.0, "fishway flow is not zero")
    runtime = contract.get("runtime", {})
    require(runtime.get("requiredHostname") == "yoda", "target host changed")
    require(runtime.get("automaticRetryCount") == 0, "automatic retry enabled")
    require(
        runtime.get("localOneStepTestPermitted") is True
        and runtime.get("fullCanaryExecutionConnected") is True,
        "numerical connection scope changed",
    )
    require(
        runtime.get("requiredActivationPath")
        == "config/stage20_continuous_all_closed_canary_activation_20260828_v1.json",
        "activation path changed",
    )
    require(
        runtime.get("executeWithoutActivation")
        == "FAIL_BEFORE_CONTEXT_LOAD_KERNEL_CALL_OR_OUTPUT_CREATION",
        "missing-activation behavior changed",
    )
    bindings = contract.get("bindings")
    require(isinstance(bindings, list) and bindings, "bindings are empty")
    seen: set[str] = set()
    for index, binding in enumerate(bindings):
        require(isinstance(binding, dict), f"binding {index} is not an object")
        path = binding.get("path")
        expected = binding.get("sha256")
        require(isinstance(path, str) and path not in seen, f"duplicate binding: {path}")
        require(
            isinstance(expected, str)
            and SHA256_RE.fullmatch(expected) is not None
            and expected != "0" * 64,
            f"binding {path} has invalid SHA256",
        )
        seen.add(path)


def verify_bindings(contract: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for binding in contract["bindings"]:
        path = relative_regular_file(binding["path"])
        actual = sha256_file(path)
        require(actual == binding["sha256"], f"SHA256 mismatch: {binding['path']}")
        result.append(
            {
                "role": binding["role"],
                "path": binding["path"],
                "sha256": actual,
                "verified": True,
            }
        )
    return result


def validate_forcing(forcing: dict[str, Any]) -> None:
    require(forcing.get("schema") == FORCING_SCHEMA, "forcing schema changed")
    require(
        forcing.get("status")
        == "PASS_IDENTITY_BOUND_DIAGNOSTIC_FORCING_NOT_LAUNCH_AUTHORITY",
        "forcing status broadened",
    )
    compatibility = forcing.get("runCompatibility", {})
    require(compatibility.get("durationModelSeconds") == 900, "forcing duration changed")
    require(
        compatibility.get("mainGateCapacityByGateId1To8") == [0.0] * 8,
        "forcing requests a nonzero main gate",
    )
    require(
        compatibility.get("positiveGateMotionPermitted") is False,
        "forcing permits positive gate motion",
    )
    require(
        compatibility.get("fishwayDischargeM3S") == 0.0,
        "forcing requests fishway flow",
    )
    timeline = forcing.get("timeline", {})
    times = timeline.get("modelSeconds")
    require(times == list(range(0, 901, 60)), "forcing timeline changed")
    series = forcing.get("series", {})
    tide = series.get("relativeTideM")
    rivers = series.get("riverDischargeM3S")
    require(isinstance(tide, list) and len(tide) == len(times), "tide length mismatch")
    require(isinstance(rivers, dict) and set(rivers) == {"N", "O", "G"}, "river set changed")
    for label, values in {"tide": tide, **rivers}.items():
        require(isinstance(values, list) and len(values) == len(times), f"{label} length mismatch")
        require(
            all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in values
            ),
            f"{label} contains a nonfinite value",
        )


def raw_float64_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.float64)
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def structure_face_mask(kernel: Any, markers: np.ndarray) -> np.ndarray:
    """Return only fixed-barrage and main-gate faces.

    Other nonzero internal markers identify distinct mesh features and must not
    be treated as barrage openings.
    """

    marker_array = np.asarray(markers)
    return (marker_array == kernel.FIXED_MARKER) | (
        (marker_array >= kernel.GATE_MARKER_BASE + 1)
        & (marker_array <= kernel.GATE_MARKER_BASE + 8)
    )


def require_structure_closed(
    kernel: Any,
    markers: np.ndarray,
    multipliers: np.ndarray,
) -> None:
    structure = structure_face_mask(kernel, markers)
    require(np.any(structure), "barrage structure faces are missing")
    require(np.all(np.asarray(multipliers)[structure] == 0.0), "structure opened")


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SuccessorRunnerStop(f"noncanonical JSON value: {error}") from error


def atomic_write_new(path: Path, payload: bytes) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing overwrite: {path}")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    require(not temporary.exists(), f"temporary output exists: {temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_save_array_new(path: Path, values: np.ndarray) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing overwrite: {path}")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            np.save(stream, values, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_numerical_context() -> dict[str, Any]:
    """Load the identity-bound R1C arrays without advancing model time."""

    contract = read_json(CONTRACT_PATH)
    validate_contract(contract)
    verify_bindings(contract)
    tools_path = str(ROOT / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    import stage20_depth_weighted_boundary_kernel_candidate_v2 as kernel

    mesh_path = ROOT / next(
        item["path"] for item in contract["bindings"] if item["role"] == "R1C_mesh"
    )
    bathymetry_path = ROOT / next(
        item["path"]
        for item in contract["bindings"]
        if item["role"] == "continuity_bathymetry"
    )
    mesh = kernel.mesh_arrays(mesh_path)
    geometry = kernel.build_review_geometry(mesh)
    with np.load(bathymetry_path, allow_pickle=False) as archive:
        depth = np.asarray(archive["continuous_candidate_depth_m"], dtype=np.float64).copy()
        bed = np.asarray(
            archive["continuous_candidate_bed_elevation_m"], dtype=np.float64
        ).copy()
    source, _ = kernel.initial_condition_data()
    _, _, manning, _ = kernel.initialize_mesh(mesh, geometry, source)
    manning = np.asarray(manning, dtype=np.float64)

    expected = contract["expectedArrays"]
    require(len(depth) == contract["scope"]["cellCount"], "depth cell count changed")
    require(len(bed) == len(depth) == len(manning), "array length mismatch")
    require(np.isfinite(depth).all() and np.all(depth > 0.0), "invalid initial depth")
    require(np.isfinite(bed).all(), "invalid bed elevation")
    require(np.isfinite(manning).all() and np.all(manning > 0.0), "invalid Manning array")
    require(
        raw_float64_sha256(depth) == expected["depthRawFloat64Sha256"],
        "depth array identity changed",
    )
    require(
        raw_float64_sha256(bed) == expected["bedRawFloat64Sha256"],
        "bed array identity changed",
    )
    require(
        raw_float64_sha256(manning) == expected["manningRawFloat64Sha256"],
        "Manning array identity changed",
    )
    require(
        raw_float64_sha256(geometry["areas"]) == expected["areasRawFloat64Sha256"],
        "cell-area identity changed",
    )

    multipliers = kernel.interface_multiplier(geometry, [])
    markers = geometry["internalMarkers"]
    require_structure_closed(kernel, markers, multipliers)
    state = np.column_stack(
        (depth, np.zeros_like(depth), np.zeros_like(depth))
    ).astype(np.float64)
    return {
        "kernel": kernel,
        "contract": contract,
        "state": state,
        "bed": bed,
        "manning": manning,
        "geometry": geometry,
        "multipliers": multipliers,
        "donor": np.zeros(len(depth), dtype=np.float64),
        "receiver": np.zeros(len(depth), dtype=np.float64),
    }


def one_step_arguments(context: dict[str, Any]) -> tuple[Any, ...]:
    forcing = read_json(
        ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
    )
    validate_forcing(forcing)
    geometry = context["geometry"]
    discharge = np.zeros(5, dtype=np.float64)
    river = forcing["series"]["riverDischargeM3S"]
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        length = float(geometry["boundaryTagLengthSums"][tag])
        require(length > 0.0, f"boundary {boundary_id} has zero length")
        discharge[tag] = -float(river[boundary_id][0]) / length
    return (
        context["state"],
        context["bed"],
        context["manning"],
        geometry["areas"],
        geometry["inverseAreas"],
        geometry["left"],
        geometry["right"],
        geometry["internalLengths"],
        geometry["internalNormals"],
        context["multipliers"],
        geometry["boundaryCells"],
        geometry["boundaryLengths"],
        geometry["boundaryNormals"],
        geometry["boundaryTags"],
        float(forcing["series"]["relativeTideM"][0]),
        discharge,
        context["donor"],
        context["receiver"],
        0.0,
        float(context["contract"]["scope"]["cflTarget"]),
        float(context["contract"]["scope"]["maximumKernelDtSeconds"]),
    )


def run_local_one_step_equivalence() -> dict[str, Any]:
    """Advance two copies once and prove traced and legacy results are exact."""

    context = load_numerical_context()
    kernel = context["kernel"]
    arguments = one_step_arguments(context)
    legacy = kernel.advance_h2_step_depth_weighted_boundary(*arguments)
    traced = kernel.advance_h2_step_depth_weighted_boundary_with_trace_v1(*arguments)
    require(legacy[0].tobytes() == traced.next_state.tobytes(), "state is not bit exact")
    traced_values = (
        traced.accepted_dt_s,
        traced.maximum_cfl,
        traced.boundary_outflow_m3_s,
        traced.effective_fishway_discharge_m3_s,
        traced.fishway_source_residual_m3_s,
    )
    require(legacy[1:] == traced_values, "scalar step results are not exact")
    require(traced.effective_fishway_discharge_m3_s == 0.0, "fishway flow is nonzero")
    require(traced.fishway_source_residual_m3_s == 0.0, "fishway residual is nonzero")
    sample = traced.limiter_sample
    require(sample.coverage_complete, "limiter scan is incomplete")
    require(
        sample.expected_candidate_count == sample.evaluated_candidate_count == 37724,
        "limiter scan does not cover every cell",
    )
    return {
        "status": "PASS_LOCAL_ONE_STEP_BIT_EXACT_FULL_LIMITER_SCAN",
        "acceptedDtSeconds": traced.accepted_dt_s,
        "maximumCfl": traced.maximum_cfl,
        "cellCount": 37724,
        "limiterCoverageComplete": True,
        "effectiveFishwayDischargeM3S": traced.effective_fishway_discharge_m3_s,
        "fishwaySourceResidualM3S": traced.fishway_source_residual_m3_s,
        "mainGateCapacityByGateId1To8": [0.0] * 8,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
    }


def build_preflight() -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    validate_contract(contract)
    bindings = verify_bindings(contract)
    forcing_binding = next(
        binding for binding in contract["bindings"] if binding["role"] == "diagnostic_forcing"
    )
    forcing = read_json(ROOT / forcing_binding["path"])
    validate_forcing(forcing)
    return {
        "schema": "onga-stage20-continuous-all-closed-successor-runner-v1-preflight",
        "status": "PASS_LOCAL_FAIL_CLOSED_ENTRYPOINT_FULL_CANARY_BLOCKED",
        "launchPermitted": False,
        "activationPresent": ACTIVATION_PATH.is_file(),
        "contractSha256": sha256_file(CONTRACT_PATH),
        "bindingCount": len(bindings),
        "allBindingsVerified": True,
        "mainGateCapacityByGateId1To8": [0.0] * 8,
        "fishwayDischargeM3S": 0.0,
        "effects": {
            "numericalKernelImportCount": 0,
            "numericalStepCount": 0,
            "outputCreationCount": 0,
            "yodaConnectionCount": 0,
            "stageMutationCount": 0,
            "commitCount": 0,
            "pushCount": 0,
        },
        "nextRequiredPermission": (
            "SEPARATE_AUTHORIZATION_FOR_900_SECOND_CANARY_AND_YODA"
        ),
    }


def _parse_utc(value: Any, label: str) -> datetime:
    require(isinstance(value, str) and value, f"{label} is empty")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SuccessorRunnerStop(f"invalid {label}: {error}") from error
    require(parsed.tzinfo is not None, f"{label} has no timezone")
    return parsed.astimezone(timezone.utc)


def validate_activation(activation: dict[str, Any]) -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    validate_contract(contract)
    require(
        activation.get("schema")
        == "onga-stage20-continuous-all-closed-canary-single-use-activation-v1",
        "activation schema changed",
    )
    require(activation.get("status") == "AUTHORIZED", "activation is not authorized")
    require(activation.get("mode") == "EXECUTE_ONCE", "activation mode changed")
    require(
        isinstance(activation.get("authorizationId"), str)
        and activation["authorizationId"].startswith("stage20-all-closed-900s-"),
        "authorization id changed",
    )
    run_id = activation.get("runId")
    require(
        isinstance(run_id, str)
        and re.fullmatch(r"canary-stage20-all-closed-900s-[a-z0-9-]+", run_id),
        "run id changed",
    )
    require(activation.get("requiredHostname") == "yoda", "activation host changed")
    require(activation.get("maximumUseCount") == 1, "activation is not single use")
    require(activation.get("retryCount") == 0, "activation permits retry")
    require(activation.get("durationModelSeconds") == 900, "activation duration changed")
    require(activation.get("maximumWallSeconds") == 1800, "wall limit changed")
    require(
        activation.get("mainGateCapacityByGateId1To8") == [0.0] * 8,
        "activation requests a nonzero gate",
    )
    require(activation.get("fishwayDischargeM3S") == 0.0, "activation enables fishway")
    require(
        activation.get("runnerSha256") == sha256_file(Path(__file__).resolve()),
        "activation runner SHA256 mismatch",
    )
    require(
        activation.get("contractSha256") == sha256_file(CONTRACT_PATH),
        "activation contract SHA256 mismatch",
    )
    forcing_path = ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
    require(
        activation.get("forcingSha256") == sha256_file(forcing_path),
        "activation forcing SHA256 mismatch",
    )
    now = datetime.now(timezone.utc)
    require(_parse_utc(activation.get("notBefore"), "notBefore") <= now, "activation not active")
    require(now <= _parse_utc(activation.get("expiresAt"), "expiresAt"), "activation expired")
    output_relative = activation.get("outputRelativePath")
    expected_output = f"{contract['runtime']['outputBase']}/{run_id}"
    require(output_relative == expected_output, "activation output path changed")
    relative_regular = Path(output_relative)
    require(
        not relative_regular.is_absolute() and ".." not in relative_regular.parts,
        "activation output path escapes workspace",
    )
    return {"contract": contract, "runId": run_id, "outputRelativePath": output_relative}


def _interpolate(values: list[Any], times: list[Any], model_seconds: float) -> float:
    return float(np.interp(model_seconds, np.asarray(times), np.asarray(values)))


def execute() -> dict[str, Any]:
    """Run once on YODA after an external immutable activation is present."""

    require(ACTIVATION_PATH.is_file(), "external single-use activation is missing")
    activation = read_json(ACTIVATION_PATH)
    validated = validate_activation(activation)
    require(socket.gethostname().lower() == "yoda", "runtime host is not yoda")
    output = ROOT / validated["outputRelativePath"]
    require(not output.exists() and not output.is_symlink(), "fresh output root required")

    contract = validated["contract"]
    forcing_path = ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
    forcing = read_json(forcing_path)
    validate_forcing(forcing)
    context = load_numerical_context()
    tools_path = str(ROOT / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    import stage20_dynamic_mesh_comparison_telemetry_v1 as telemetry_module

    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.parent.is_symlink(), "output base is a symlink")
    output.mkdir(mode=0o700)
    activation_sha = sha256_file(ACTIVATION_PATH)
    claim = {
        "schema": "onga-stage20-continuous-all-closed-canary-claim-v1",
        "authorizationId": activation["authorizationId"],
        "runId": validated["runId"],
        "activationSha256": activation_sha,
        "claimedAtUtc": datetime.now(timezone.utc).isoformat(),
        "processId": os.getpid(),
        "hostname": socket.gethostname(),
        "retryCount": 0,
    }
    atomic_write_new(output / "claim.json", canonical_bytes(claim))
    atomic_write_new(
        output / "start-receipt.json",
        canonical_bytes(
            {
                "schema": "onga-stage20-continuous-all-closed-canary-start-v1",
                "status": "STARTED_SINGLE_USE_DIAGNOSTIC_CANARY",
                "runId": validated["runId"],
                "durationModelSeconds": 900,
                "mainGateCapacityByGateId1To8": [0.0] * 8,
                "fishwayDischargeM3S": 0.0,
                "classification": contract["classification"],
            }
        ),
    )

    kernel_binding = next(
        item for item in contract["bindings"] if item["role"] == "same_pass_limiter_kernel"
    )
    bathymetry_binding = next(
        item for item in contract["bindings"] if item["role"] == "continuity_bathymetry"
    )
    collector = telemetry_module.DynamicMeshTelemetry(
        telemetry_module.TelemetryConfig(
            run_id=validated["runId"],
            mesh_id=contract["scope"]["meshId"],
            run_manifest_sha256=activation_sha,
            mesh_sha256=next(
                item["sha256"] for item in contract["bindings"] if item["role"] == "R1C_mesh"
            ),
            checkpoint_sha256=contract["expectedArrays"]["depthRawFloat64Sha256"],
            forcing_sha256=sha256_file(forcing_path),
            solver_source_sha256=kernel_binding["sha256"],
            control_contract_sha256=sha256_file(CONTRACT_PATH),
            bathymetry_sha256=bathymetry_binding["sha256"],
            approved_limiter_formula_id=telemetry_module.APPROVED_LIMITER_FORMULA_ID,
            required_dt_bound_names=telemetry_module.APPROVED_DT_BOUND_NAMES,
            cfl_target=0.12,
            expected_candidate_count=37724,
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
        while model_seconds < 900.0 - 1.0e-12:
            require(time.monotonic() - wall_started <= 1800.0, "wall-time limit exceeded")
            with collector.time_phase("control"):
                require_structure_closed(
                    kernel,
                    geometry["internalMarkers"],
                    context["multipliers"],
                )
            discharge = np.zeros(5, dtype=np.float64)
            for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
                q = _interpolate(
                    forcing["series"]["riverDischargeM3S"][boundary_id],
                    timeline,
                    model_seconds,
                )
                discharge[tag] = -q / float(geometry["boundaryTagLengthSums"][tag])
            tide = _interpolate(
                forcing["series"]["relativeTideM"], timeline, model_seconds
            )
            maximum_dt = min(0.05, 900.0 - model_seconds)
            with collector.time_phase("flux"):
                step = kernel.advance_h2_step_depth_weighted_boundary_with_trace_v1(
                    state,
                    context["bed"],
                    context["manning"],
                    geometry["areas"],
                    geometry["inverseAreas"],
                    geometry["left"],
                    geometry["right"],
                    geometry["internalLengths"],
                    geometry["internalNormals"],
                    context["multipliers"],
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
            collector.record_accepted_step(step.accepted_dt_s, step.limiter_sample)
            state = step.next_state
            model_seconds += step.accepted_dt_s
            accepted_steps += 1
            expected_volume -= step.accepted_dt_s * step.boundary_outflow_m3_s
            maximum_cfl = max(maximum_cfl, step.maximum_cfl)
            if model_seconds >= next_check - 1.0e-10 or model_seconds >= 900.0 - 1.0e-10:
                with collector.time_phase("output"):
                    require(np.isfinite(state).all(), "nonfinite state")
                    require(np.all(state[:, 0] >= 0.0), "negative depth")
                    actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
                    mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
                    maximum_mass_error = max(maximum_mass_error, mass_error)
                next_check += 60.0

        runner_wall = time.monotonic() - wall_started
        telemetry_report = collector.finalize(total_runner_wall_seconds=runner_wall)
        result = {
            "schema": "onga-stage20-continuous-all-closed-canary-result-v1",
            "status": "PASS_NUMERICAL_900S_ALL_CLOSED_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION",
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
            "mainGateCapacityByGateId1To8": [0.0] * 8,
            "fishwayDischargeM3S": 0.0,
            "retryCount": 0,
            "classification": contract["classification"],
        }
        atomic_save_array_new(output / "final-state.npy", state)
        atomic_write_new(output / "telemetry.json", canonical_bytes(telemetry_report))
        atomic_write_new(output / "result.json", canonical_bytes(result))
        completion = {
            "schema": "onga-stage20-continuous-all-closed-canary-completion-v1",
            "status": result["status"],
            "runId": validated["runId"],
            "resultSha256": sha256_file(output / "result.json"),
            "telemetrySha256": sha256_file(output / "telemetry.json"),
            "finalStateSha256": sha256_file(output / "final-state.npy"),
        }
        atomic_write_new(output / "completion-receipt.json", canonical_bytes(completion))
        manifest = {
            "schema": "onga-stage20-continuous-all-closed-canary-manifest-v1",
            "runId": validated["runId"],
            "files": [
                {"path": path.name, "sha256": sha256_file(path)}
                for path in sorted(output.iterdir())
                if path.is_file()
            ],
        }
        atomic_write_new(output / "manifest.json", canonical_bytes(manifest))
        return result
    except Exception as error:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            atomic_write_new(
                failure,
                canonical_bytes(
                    {
                        "schema": "onga-stage20-continuous-all-closed-canary-failure-v1",
                        "status": "FAILED_NO_RETRY",
                        "runId": validated["runId"],
                        "errorType": type(error).__name__,
                        "message": str(error),
                    }
                ),
            )
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--local-one-step-test", action="store_true")
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    require(
        sum((arguments.preflight, arguments.local_one_step_test, arguments.execute)) <= 1,
        "choose one mode",
    )
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
    except SuccessorRunnerStop as error:
        raise SystemExit(str(error)) from error
