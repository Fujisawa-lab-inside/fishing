#!/usr/bin/env python3
"""Fail-closed 2 h canary for the downstream external-inflow correction."""

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
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_downstream_external_inflow_adapter_v1 as external_adapter


VERSION = "stage20-downstream-external-high-large-7200s-runner-v1"
SCHEMA = "onga-stage20-downstream-external-high-large-7200s-runner-v1-contract"
CONTRACT_PATH = ROOT / "config/stage20_downstream_external_high_large_7200s_runner_v1.json"
ACTIVATION_PATH = ROOT / "config/stage20_downstream_external_high_large_7200s_activation_20260901_v1.json"
PILOT_INPUT_PATH = (
    ROOT / "config/stage20_downstream_external_high_large_7200s_input_v1.json"
)
FIELDS_PATH = (
    ROOT
    / "docs/results/stage20-regularized-multizone-continuous-fields-v1/continuous-fields.npz"
)
SCENARIO_ID = "release-high_tide-large"
DURATION_SECONDS = 7200.0
CELL_COUNT = 28746
DOWNSTREAM_CELL_COUNT = 24250
MAXIMUM_WALL_SECONDS = 1800.0
MAXIMUM_ACCEPTED_STEPS = 2_000_000
COMMANDED_SOURCE_RESIDUAL_RELATIVE_THRESHOLD = 1.0e-13
STATE_DELTA_SOURCE_RESIDUAL_TREATMENT = "FLOAT64_DIAGNOSTIC_ONLY"
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ExternalInflowCanaryStop(RuntimeError):
    """A deliberate fail-closed stop."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExternalInflowCanaryStop(f"[{VERSION}] {message}")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_new(path: Path, payload: bytes) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing to overwrite {path}")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def atomic_save_npy_new(path: Path, value: np.ndarray) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing to overwrite {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp.npy")
    require(not temporary.exists(), "temporary final-state path already exists")
    np.save(temporary, value, allow_pickle=False)
    os.replace(temporary, path)


def _binding(contract: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [item for item in contract["bindings"] if item.get("role") == role]
    require(len(matches) == 1, f"binding role is not unique: {role}")
    return matches[0]


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("schema") == SCHEMA, "contract schema changed")
    require(contract.get("version") == 1, "contract version changed")
    require(
        contract.get("status") == "READY_PREPARE_ONLY_EXTERNAL_ACTIVATION_REQUIRED",
        "contract status changed",
    )
    require(
        contract.get("classification")
        == "DIAGNOSTIC_EXTERNAL_DOWNSTREAM_INFLOW_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
        "classification changed",
    )
    scope = contract.get("scope", {})
    require(scope.get("scenarioId") == SCENARIO_ID, "scenario changed")
    require(scope.get("durationModelSeconds") == 7200, "duration changed")
    require(scope.get("releaseM3S") == 73.0, "release changed")
    require(scope.get("tideRangeClass") == "large", "tide class changed")
    require(scope.get("cellCount") == CELL_COUNT, "cell count changed")
    require(scope.get("downstreamCellCount") == DOWNSTREAM_CELL_COUNT, "downstream count changed")
    require(scope.get("usesUpstreamDonorVolume") is False, "upstream donor was re-enabled")
    require(scope.get("reverseFlowPermitted") is False, "reverse flow was enabled")
    require(scope.get("maximumInflowVelocityMPS") == 5.0, "velocity guard changed")
    runtime = contract.get("runtime", {})
    require(runtime.get("requiredHostname") == "yoda", "target host changed")
    require(runtime.get("automaticRetryCount") == 0, "automatic retry enabled")
    require(runtime.get("maximumWallSeconds") == 1800, "wall guard changed")
    require(runtime.get("maximumAcceptedStepCount") == MAXIMUM_ACCEPTED_STEPS, "step guard changed")
    require(
        runtime.get("requiredActivationPath") == str(ACTIVATION_PATH.relative_to(ROOT)),
        "activation path changed",
    )
    require(
        runtime.get("executeWithoutActivation")
        == "FAIL_BEFORE_CONTEXT_LOAD_KERNEL_CALL_OR_OUTPUT_CREATION",
        "missing-activation behavior changed",
    )
    acceptance = contract.get("acceptance", {})
    require(
        acceptance.get("stateDeltaSourceResidualTreatment")
        == STATE_DELTA_SOURCE_RESIDUAL_TREATMENT,
        "state-delta source residual became an acceptance guard",
    )
    require(
        acceptance.get("maximumCommandedSourceResidualRelative")
        == COMMANDED_SOURCE_RESIDUAL_RELATIVE_THRESHOLD,
        "commanded source residual threshold changed",
    )
    require(
        "maximumSourceResidualM3S" not in acceptance,
        "state-delta source residual threshold was reintroduced",
    )
    bindings = contract.get("bindings")
    require(isinstance(bindings, list) and len(bindings) >= 9, "bindings are incomplete")
    seen: set[str] = set()
    for item in bindings:
        path = item.get("path")
        digest = item.get("sha256")
        require(isinstance(path, str) and path not in seen, f"duplicate binding: {path}")
        require(isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None, f"invalid binding SHA: {path}")
        seen.add(path)
    for role in (
        "runner",
        "target_test",
        "external_inflow_adapter",
        "external_inflow_adapter_test",
        "matched_runner",
        "matched_contract",
        "same_pass_limiter_kernel",
        "candidate_mesh",
        "candidate_fields",
        "pilot_inputs",
    ):
        _binding(contract, role)


def verified_contract() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = read_json(CONTRACT_PATH)
    validate_contract(contract)
    verified: list[dict[str, Any]] = []
    for item in contract["bindings"]:
        path = ROOT / item["path"]
        require(path.is_file() and not path.is_symlink(), f"binding is missing: {item['path']}")
        require(sha256_file(path) == item["sha256"], f"binding SHA changed: {item['path']}")
        verified.append(item)
    return contract, verified


def load_scenario() -> dict[str, Any]:
    document = read_json(PILOT_INPUT_PATH)
    matches = [item for item in document.get("scenarios", []) if item.get("id") == SCENARIO_ID]
    require(len(matches) == 1, "high-release/large-tide scenario is missing")
    scenario = matches[0]
    boundary = scenario.get("boundaryInputs", {})
    offsets = np.asarray(boundary.get("snapshotOffsetsHours"), dtype=np.float64)
    tide = np.asarray(boundary.get("astronomicalTideHeightMByOffset"), dtype=np.float64)
    require(offsets.shape == (37,) and tide.shape == (37,), "37-hour input shape changed")
    require(bool(np.all(offsets == np.arange(-12.0, 25.0))), "hour offsets changed")
    require(bool(np.isfinite(tide).all()), "tide input is nonfinite")
    require(float(boundary.get("barrageReleaseM3S", -1.0)) == 73.0, "release input changed")
    require(scenario.get("tideRangeClass") == "large", "tide range changed")
    require(scenario.get("currentConditionReferenceAllowed") is False, "scenario was promoted")
    return scenario


def tide_at(scenario: dict[str, Any], model_seconds: float) -> float:
    values = np.asarray(scenario["boundaryInputs"]["astronomicalTideHeightMByOffset"], dtype=np.float64)
    return float(np.interp(model_seconds, np.arange(37, dtype=np.float64) * 3600.0, values))


def require_external_source_conservation(
    external: dict[str, Any],
    release_m3_s: float,
) -> None:
    """Use commanded volume for acceptance and state deltas for diagnostics."""

    release = float(release_m3_s)
    requested = float(external["requestedReleaseM3S"])
    commanded_relative_residual = float(
        external["commandedSourceResidualRelative"]
    )
    require(
        math.isfinite(requested) and math.isfinite(commanded_relative_residual),
        "external source conservation telemetry is nonfinite",
    )
    require(
        math.isclose(requested, release, rel_tol=0.0, abs_tol=0.0),
        "external release request changed",
    )
    require(
        external.get("stateDeltaSourceResidualTreatment")
        == STATE_DELTA_SOURCE_RESIDUAL_TREATMENT,
        "state-delta source residual treatment changed",
    )
    require(
        abs(commanded_relative_residual)
        <= COMMANDED_SOURCE_RESIDUAL_RELATIVE_THRESHOLD,
        "commanded external source is not conservative",
    )


def build_discharge(geometry: dict[str, np.ndarray]) -> np.ndarray:
    """Keep Onga upstream inflow at zero; release is an external downstream source."""

    result = np.zeros(5, dtype=np.float64)
    for tag, discharge_m3_s in ((2, 0.7), (4, 0.5)):
        length = float(geometry["boundaryTagLengthSums"][tag])
        require(length > 0.0, f"boundary tag {tag} has zero length")
        result[tag] = -discharge_m3_s / length
    require(result[3] == 0.0, "Onga upstream boundary must not supply the barrage release")
    return result


def load_context() -> dict[str, Any]:
    import stage20_regularized_multizone_900s_runner_v1 as matched

    context = matched.load_numerical_context()
    geometry = context["geometry"]
    with np.load(FIELDS_PATH, allow_pickle=False) as archive:
        layout = external_adapter.build_external_inflow_layout(
            geometry,
            np.asarray(archive["gate_face_id"], dtype=np.int64),
            np.asarray(archive["barrage_upstream_cell_id"], dtype=np.int64),
            np.asarray(archive["upstream_component_mask"], dtype=np.uint8),
            np.asarray(geometry["areas"], dtype=np.float64),
        )
        upstream_reference = np.asarray(archive["p2_donor_overlap_area_m2"], dtype=np.float64).copy()
        downstream_reference = np.asarray(archive["p2_receiver_overlap_area_m2"], dtype=np.float64).copy()
    require(layout["downstreamCellCount"] == DOWNSTREAM_CELL_COUNT, "downstream count changed")
    require(layout["upstreamExcludedCellCount"] == 4496, "upstream exclusion changed")
    require(layout["usesUpstreamDonorVolume"] is False, "external source gained an upstream donor")
    return {
        **context,
        "externalLayout": layout,
        "upstreamLevelReferenceM2": upstream_reference,
        "downstreamLevelReferenceM2": downstream_reference,
    }


def _weighted_eta(state: np.ndarray, bed: np.ndarray, weights: np.ndarray) -> float:
    active = weights > 0.0
    require(bool(np.any(active)), "water-level reference is empty")
    return float(np.average(state[active, 0] + bed[active], weights=weights[active]))


def condition_snapshot(state: np.ndarray, context: dict[str, Any]) -> dict[str, float]:
    return {
        "barrageInflowM3S": 73.0,
        "barrageReleaseM3S": 73.0,
        "barrageUpstreamLevelM": _weighted_eta(
            state, context["bed"], context["upstreamLevelReferenceM2"]
        ),
        "barrageDownstreamLevelM": _weighted_eta(
            state, context["bed"], context["downstreamLevelReferenceM2"]
        ),
    }


def _require_closed(context: dict[str, Any]) -> None:
    kernel = context["kernel"]
    markers = np.asarray(context["geometry"]["internalMarkers"], dtype=np.int64)
    structure = (markers == kernel.FIXED_MARKER) | (
        (markers >= kernel.GATE_MARKER_BASE + 1) & (markers <= kernel.GATE_MARKER_BASE + 8)
    )
    require(bool(np.all(np.asarray(context["multipliers"])[structure] == 0.0)), "structure opened")


def advance_once(
    state: np.ndarray,
    context: dict[str, Any],
    scenario: dict[str, Any],
    model_seconds: float,
    maximum_dt_s: float,
) -> tuple[Any, dict[str, Any]]:
    _require_closed(context)
    geometry = context["geometry"]
    kernel = context["kernel"]
    zeros = np.zeros(CELL_COUNT, dtype=np.float64)
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
        tide_at(scenario, model_seconds),
        build_discharge(geometry),
        zeros,
        zeros,
        0.0,
        0.12,
        maximum_dt_s,
    )
    external = external_adapter.apply_external_inflow(
        step.next_state,
        geometry["areas"],
        context["externalLayout"],
        73.0,
        float(step.accepted_dt_s),
        minimum_flow_depth_m=0.05,
        maximum_inflow_velocity_m_s=5.0,
    )
    require_external_source_conservation(external, 73.0)
    require(external["upstreamStateChanged"] is False, "external source changed upstream state")
    return step, external


def run_local_one_step() -> dict[str, Any]:
    verified_contract()
    scenario = load_scenario()
    context = load_context()
    state = np.asarray(context["state"], dtype=np.float64)
    areas = np.asarray(context["geometry"]["areas"], dtype=np.float64)
    initial_volume = float(np.sum(state[:, 0] * areas))
    step, external = advance_once(state, context, scenario, 0.0, 0.05)
    next_state = external["nextState"]
    expected_volume = (
        initial_volume
        - float(step.accepted_dt_s) * float(step.boundary_outflow_m3_s)
        + float(external["addedVolumeM3"])
    )
    actual_volume = float(np.sum(next_state[:, 0] * areas))
    mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
    require(mass_error <= 1.0e-10, "one-step mass balance failed")
    require(bool(np.isfinite(next_state).all()) and bool(np.all(next_state[:, 0] >= 0.0)), "unsafe one-step state")
    return {
        "status": "PASS_LOCAL_ONE_STEP_EXTERNAL_DOWNSTREAM_INFLOW_HIGH_LARGE",
        "requestedReleaseM3S": 73.0,
        "effectiveReleaseM3S": external["effectiveReleaseM3S"],
        "inflowVelocityMPS": external["inflowVelocityMPS"],
        "relativeMassBalanceError": mass_error,
        "upstreamStateChangedBySource": external["upstreamStateChanged"],
        "negativeDepthCount": int(np.sum(next_state[:, 0] < 0.0)),
        "nonFiniteValueCount": int(next_state.size - np.count_nonzero(np.isfinite(next_state))),
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
    }


def build_preflight() -> dict[str, Any]:
    _, bindings = verified_contract()
    load_scenario()
    return {
        "schema": "onga-stage20-downstream-external-high-large-7200s-preflight-v1",
        "status": "PASS_PREPARE_ONLY_CANARY_BLOCKED_PENDING_ACTIVATION",
        "launchPermitted": False,
        "activationPresent": ACTIVATION_PATH.is_file(),
        "allBindingsVerified": True,
        "bindingCount": len(bindings),
        "scenarioId": SCENARIO_ID,
        "durationModelSeconds": DURATION_SECONDS,
        "automaticRetryCount": 0,
    }


def _parse_utc(value: Any, field: str) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), f"{field} is not UTC")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    require(parsed.tzinfo is not None, f"{field} is timezone-naive")
    return parsed.astimezone(timezone.utc)


def validate_activation(activation: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    contract, _ = verified_contract()
    require(
        activation.get("schema") == "onga-stage20-downstream-external-high-large-7200s-single-use-activation-v1",
        "activation schema changed",
    )
    require(activation.get("status") == "AUTHORIZED", "activation is not authorized")
    require(activation.get("mode") == "EXECUTE_DIAGNOSTIC_CANARY_ONCE", "activation mode changed")
    require(
        activation.get("authorizationId")
        == "stage20-downstream-external-high-large-7200s-yoda-20260901-01",
        "authorization id changed",
    )
    require(
        activation.get("runId") == "canary-stage20-downstream-external-high-large-7200s-20260901-v1",
        "run id changed",
    )
    require(activation.get("requiredHostname") == "yoda", "activation host changed")
    require(activation.get("maximumUseCount") == 1 and activation.get("retryCount") == 0, "single-use/no-retry changed")
    require(activation.get("scenarioId") == SCENARIO_ID, "activation scenario changed")
    require(activation.get("durationModelSeconds") == 7200, "activation duration changed")
    require(activation.get("runnerSha256") == sha256_file(Path(__file__).resolve()), "runner SHA changed")
    require(activation.get("contractSha256") == sha256_file(CONTRACT_PATH), "contract SHA changed")
    require(activation.get("externalAdapterSha256") == sha256_file(Path(external_adapter.__file__).resolve()), "adapter SHA changed")
    now = datetime.now(timezone.utc)
    require(_parse_utc(activation.get("notBefore"), "notBefore") <= now, "activation is not active")
    require(now <= _parse_utc(activation.get("expiresAt"), "expiresAt"), "activation expired")
    output_relative = activation.get("outputRelativePath")
    expected = f"{contract['runtime']['outputBase']}/{activation['runId']}"
    require(output_relative == expected, "output path changed")
    output = ROOT / output_relative
    require(not Path(output_relative).is_absolute() and ".." not in Path(output_relative).parts, "output escapes package")
    return contract, output


def execute() -> dict[str, Any]:
    require(ACTIVATION_PATH.is_file() and not ACTIVATION_PATH.is_symlink(), "activation is missing")
    activation = read_json(ACTIVATION_PATH)
    _, output = validate_activation(activation)
    require(socket.gethostname().lower() == "yoda", "runner host is not yoda")
    require(not output.exists() and not output.is_symlink(), "output root is not fresh")
    context = load_context()
    scenario = load_scenario()
    output.mkdir(parents=True, mode=0o700)
    atomic_write_new(
        output / "claim.json",
        canonical_bytes({
            "schema": "onga-stage20-downstream-external-high-large-7200s-claim-v1",
            "status": "CLAIMED_SINGLE_USE_NO_RETRY",
            "authorizationId": activation["authorizationId"],
            "runId": activation["runId"],
            "claimedAtUtc": datetime.now(timezone.utc).isoformat(),
            "processId": os.getpid(),
        }),
    )
    atomic_write_new(
        output / "start-receipt.json",
        canonical_bytes({
            "schema": "onga-stage20-downstream-external-high-large-7200s-start-v1",
            "status": "STARTED_DIAGNOSTIC_NOT_FORECAST",
            "scenarioId": SCENARIO_ID,
            "durationModelSeconds": DURATION_SECONDS,
            "startedAtUtc": datetime.now(timezone.utc).isoformat(),
        }),
    )

    state = np.asarray(context["state"], dtype=np.float64).copy()
    areas = np.asarray(context["geometry"]["areas"], dtype=np.float64)
    initial_volume = float(np.sum(state[:, 0] * areas))
    expected_volume = initial_volume
    model_seconds = 0.0
    accepted_steps = 0
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_source_residual = 0.0
    maximum_commanded_source_residual_relative = 0.0
    minimum_inflow_velocity = math.inf
    maximum_inflow_velocity = -math.inf
    next_safety_check = 600.0
    wall_started = time.monotonic()
    try:
        while model_seconds < DURATION_SECONDS - 1.0e-12:
            require(time.monotonic() - wall_started <= MAXIMUM_WALL_SECONDS, "wall-time limit exceeded")
            require(accepted_steps < MAXIMUM_ACCEPTED_STEPS, "accepted-step limit exceeded")
            maximum_dt = min(0.05, DURATION_SECONDS - model_seconds)
            step, external = advance_once(state, context, scenario, model_seconds, maximum_dt)
            dt = float(step.accepted_dt_s)
            state = external["nextState"]
            model_seconds += dt
            accepted_steps += 1
            expected_volume -= dt * float(step.boundary_outflow_m3_s)
            expected_volume += float(external["addedVolumeM3"])
            maximum_cfl = max(maximum_cfl, float(step.maximum_cfl))
            maximum_source_residual = max(maximum_source_residual, abs(float(external["sourceResidualM3S"])))
            maximum_commanded_source_residual_relative = max(
                maximum_commanded_source_residual_relative,
                abs(float(external["commandedSourceResidualRelative"])),
            )
            minimum_inflow_velocity = min(minimum_inflow_velocity, float(external["inflowVelocityMPS"]))
            maximum_inflow_velocity = max(maximum_inflow_velocity, float(external["inflowVelocityMPS"]))
            if model_seconds >= next_safety_check - 1.0e-9 or model_seconds >= DURATION_SECONDS - 1.0e-9:
                require(bool(np.isfinite(state).all()), "nonfinite state")
                require(bool(np.all(state[:, 0] >= 0.0)), "negative depth")
                actual_volume = float(np.sum(state[:, 0] * areas))
                mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
                maximum_mass_error = max(maximum_mass_error, mass_error)
                require(mass_error <= 1.0e-10, "mass balance guard failed")
                next_safety_check += 600.0

        require(math.isclose(model_seconds, DURATION_SECONDS, abs_tol=1.0e-9), "duration changed")
        result = {
            "schema": "onga-stage20-downstream-external-high-large-7200s-result-v1",
            "status": "PASS_NUMERICAL_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
            "scenarioId": SCENARIO_ID,
            "simulatedSeconds": model_seconds,
            "acceptedSteps": accepted_steps,
            "wallSeconds": time.monotonic() - wall_started,
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "maximumSourceResidualM3S": maximum_source_residual,
            "stateDeltaSourceResidualTreatment": STATE_DELTA_SOURCE_RESIDUAL_TREATMENT,
            "maximumCommandedSourceResidualRelative": (
                maximum_commanded_source_residual_relative
            ),
            "minimumInflowVelocityMPS": minimum_inflow_velocity,
            "maximumInflowVelocityMPS": maximum_inflow_velocity,
            "requestedReleaseM3S": 73.0,
            "effectiveReleaseM3S": 73.0,
            "negativeDepthCount": int(np.sum(state[:, 0] < 0.0)),
            "nonFiniteValueCount": int(state.size - np.count_nonzero(np.isfinite(state))),
            "conditionAtEnd": condition_snapshot(state, context),
            "usesUpstreamDonorVolume": False,
            "reverseFlowPermitted": False,
            "forecastProvided": False,
        }
        atomic_write_new(output / "result.json", canonical_bytes(result))
        atomic_save_npy_new(output / "final-state.npy", state)
        artifacts = {}
        for name in ("claim.json", "start-receipt.json", "result.json", "final-state.npy"):
            path = output / name
            artifacts[name] = {"sha256": sha256_file(path), "byteLength": path.stat().st_size}
        completion = {
            "schema": "onga-stage20-downstream-external-high-large-7200s-completion-v1",
            "status": result["status"],
            "authorizationId": activation["authorizationId"],
            "runId": activation["runId"],
            "completedAtUtc": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifacts,
        }
        atomic_write_new(output / "completion-receipt.json", canonical_bytes(completion))
        artifacts["completion-receipt.json"] = {
            "sha256": sha256_file(output / "completion-receipt.json"),
            "byteLength": (output / "completion-receipt.json").stat().st_size,
        }
        manifest = {
            "schema": "onga-stage20-downstream-external-high-large-7200s-manifest-v1",
            "runId": activation["runId"],
            "artifacts": artifacts,
        }
        atomic_write_new(output / "manifest.json", canonical_bytes(manifest))
        return result
    except BaseException as exc:
        failure = {
            "schema": "onga-stage20-downstream-external-high-large-7200s-failure-v1",
            "status": "FAILED_NO_RETRY",
            "authorizationId": activation.get("authorizationId"),
            "runId": activation.get("runId"),
            "failedAtUtc": datetime.now(timezone.utc).isoformat(),
            "errorType": type(exc).__name__,
            "message": str(exc),
            "simulatedSeconds": model_seconds,
            "acceptedSteps": accepted_steps,
        }
        if not (output / "failure-receipt.json").exists():
            atomic_write_new(output / "failure-receipt.json", canonical_bytes(failure))
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--local-one-step", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    selected = int(args.preflight) + int(args.local_one_step) + int(args.execute)
    require(selected <= 1, "choose at most one mode")
    if args.execute:
        report = execute()
    elif args.local_one_step:
        report = run_local_one_step()
    else:
        report = build_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
