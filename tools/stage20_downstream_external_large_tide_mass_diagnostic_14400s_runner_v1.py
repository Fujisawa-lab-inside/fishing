#!/usr/bin/env python3
"""Diagnose the first mass-guard crossing in the two large-tide scenarios.

The hydraulic path and hourly time-step clipping match the failed six-scenario
batch.  Every 600 model seconds the runner records float64 and long-double
volume accounting.  It stops at the first original float64 guard crossing,
without continuing an unaccepted trajectory and without retrying.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_downstream_external_six_scenario_37_snapshot_runner_v1 as full


VERSION = "stage20-downstream-external-large-tide-mass-diagnostic-14400s-runner-v1"
SCHEMA = "onga-stage20-downstream-external-large-tide-mass-diagnostic-14400s-runner-v1-contract"
CONTRACT_PATH = ROOT / "config/stage20_downstream_external_large_tide_mass_diagnostic_14400s_runner_v1.json"
ACTIVATION_PATH = ROOT / "config/stage20_downstream_external_large_tide_mass_diagnostic_14400s_activation_20260901_v1.json"
SCENARIO_IDS = (
    "release-reference_tide-large",
    "release-high_tide-large",
)
DURATION_SECONDS = 14_400.0
CHECK_INTERVAL_SECONDS = 600.0
ORIGINAL_RELATIVE_MASS_THRESHOLD = 1.0e-10
MAXIMUM_WORKER_WALL_SECONDS = 3600.0
MAXIMUM_BATCH_WALL_SECONDS = 4200.0
MAXIMUM_ACCEPTED_STEPS_PER_WORKER = 2_500_000
SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ACTIVE_WORKERS: dict[str, subprocess.Popen[Any]] = {}


class MassDiagnosticStop(RuntimeError):
    """A deliberate fail-closed diagnostic stop."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MassDiagnosticStop(f"[{VERSION}] {message}")


def _binding(contract: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [item for item in contract["bindings"] if item.get("role") == role]
    require(len(matches) == 1, f"binding role is not unique: {role}")
    return matches[0]


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("schema") == SCHEMA, "contract schema changed")
    require(contract.get("version") == 1, "contract version changed")
    require(
        contract.get("status") == "READY_PREPARE_ONLY_MASS_DIAGNOSTIC_ACTIVATION_REQUIRED",
        "contract status changed",
    )
    scope = contract.get("scope", {})
    require(tuple(scope.get("scenarioIds", [])) == SCENARIO_IDS, "scenario set changed")
    require(scope.get("durationModelSeconds") == 14400, "duration changed")
    require(scope.get("checkIntervalModelSeconds") == 600, "check interval changed")
    require(scope.get("originalRelativeMassThreshold") == ORIGINAL_RELATIVE_MASS_THRESHOLD, "threshold changed")
    require(scope.get("stopAtFirstOriginalThresholdCrossing") is True, "stop rule changed")
    require(scope.get("usesUpstreamDonorVolume") is False, "upstream donor was re-enabled")
    runtime = contract.get("runtime", {})
    require(runtime.get("requiredHostname") == "yoda", "target host changed")
    require(runtime.get("automaticRetryCount") == 0, "automatic retry enabled")
    require(runtime.get("maximumWorkerWallSeconds") == 3600, "worker wall guard changed")
    require(runtime.get("maximumBatchWallSeconds") == 4200, "batch wall guard changed")
    require(
        runtime.get("maximumAcceptedStepCountPerWorker") == MAXIMUM_ACCEPTED_STEPS_PER_WORKER,
        "step guard changed",
    )
    require(
        runtime.get("requiredActivationPath") == str(ACTIVATION_PATH.relative_to(ROOT)),
        "activation path changed",
    )
    require(
        runtime.get("executeWithoutActivation")
        == "FAIL_BEFORE_CONTEXT_LOAD_KERNEL_CALL_OR_OUTPUT_CREATION",
        "missing-activation behavior changed",
    )
    bindings = contract.get("bindings")
    require(isinstance(bindings, list) and len(bindings) >= 11, "bindings are incomplete")
    seen: set[str] = set()
    for item in bindings:
        path = item.get("path")
        digest = item.get("sha256")
        require(isinstance(path, str) and path not in seen, f"duplicate binding: {path}")
        require(
            isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None,
            f"invalid binding SHA: {path}",
        )
        seen.add(path)
    for role in (
        "runner",
        "target_test",
        "full_batch_runner",
        "full_batch_contract",
        "scenario_input",
        "external_inflow_adapter",
        "proven_canary_runner",
        "matched_runner",
        "same_pass_limiter_kernel",
        "candidate_mesh",
        "candidate_fields",
    ):
        _binding(contract, role)


def verified_contract() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = full.canary.read_json(CONTRACT_PATH)
    validate_contract(contract)
    verified: list[dict[str, Any]] = []
    for item in contract["bindings"]:
        path = ROOT / item["path"]
        require(path.is_file() and not path.is_symlink(), f"binding is missing: {item['path']}")
        require(full.canary.sha256_file(path) == item["sha256"], f"binding SHA changed: {item['path']}")
        verified.append(item)
    full.verified_contract()
    return contract, verified


def load_scenarios() -> dict[str, dict[str, Any]]:
    all_scenarios = full.load_scenarios()
    selected = {scenario_id: all_scenarios[scenario_id] for scenario_id in SCENARIO_IDS}
    require(tuple(selected) == SCENARIO_IDS, "large-tide scenarios changed")
    require(
        [selected[item]["boundaryInputs"]["barrageReleaseM3S"] for item in SCENARIO_IDS]
        == [24.5, 73.0],
        "release values changed",
    )
    require(all(selected[item]["tideRangeClass"] == "large" for item in SCENARIO_IDS), "tide class changed")
    return selected


def classify_checkpoint(row: dict[str, Any]) -> str:
    float_crossed = bool(row["float64ThresholdCrossed"])
    long_crossed = bool(row["longDoubleThresholdCrossed"])
    if float_crossed and not long_crossed:
        return "FLOAT64_ACCOUNTING_ACCUMULATION_ONLY_AT_ORIGINAL_THRESHOLD"
    if float_crossed and long_crossed:
        return "MASS_MISMATCH_PERSISTS_WITH_LONG_DOUBLE_ACCOUNTING"
    return "BELOW_OR_EQUAL_TO_ORIGINAL_THRESHOLD"


def build_preflight() -> dict[str, Any]:
    _, bindings = verified_contract()
    scenarios = load_scenarios()
    return {
        "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-preflight-v1",
        "status": "PASS_PREPARE_ONLY_DIAGNOSTIC_BLOCKED_PENDING_ACTIVATION",
        "launchPermitted": False,
        "activationPresent": ACTIVATION_PATH.is_file(),
        "allBindingsVerified": True,
        "bindingCount": len(bindings),
        "scenarioCount": len(scenarios),
        "durationModelSeconds": DURATION_SECONDS,
        "checkIntervalModelSeconds": CHECK_INTERVAL_SECONDS,
        "originalRelativeMassThreshold": ORIGINAL_RELATIVE_MASS_THRESHOLD,
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
        activation.get("schema")
        == "onga-stage20-downstream-external-large-tide-mass-diagnostic-single-use-activation-v1",
        "activation schema changed",
    )
    require(activation.get("status") == "AUTHORIZED", "activation is not authorized")
    require(activation.get("mode") == "EXECUTE_MASS_DIAGNOSTIC_ONCE", "activation mode changed")
    require(
        activation.get("authorizationId")
        == "stage20-downstream-external-large-tide-mass-diagnostic-yoda-20260901-01",
        "authorization id changed",
    )
    require(
        activation.get("runId")
        == "diagnostic-stage20-downstream-external-large-tide-mass-14400s-20260901-v1",
        "run id changed",
    )
    require(activation.get("requiredHostname") == "yoda", "activation host changed")
    require(activation.get("maximumUseCount") == 1 and activation.get("retryCount") == 0, "single-use/no-retry changed")
    require(tuple(activation.get("scenarioIds", [])) == SCENARIO_IDS, "activation scenarios changed")
    require(activation.get("durationModelSeconds") == 14400, "activation duration changed")
    require(activation.get("runnerSha256") == full.canary.sha256_file(Path(__file__).resolve()), "runner SHA changed")
    require(activation.get("contractSha256") == full.canary.sha256_file(CONTRACT_PATH), "contract SHA changed")
    require(
        activation.get("fullBatchRunnerSha256") == full.canary.sha256_file(Path(full.__file__).resolve()),
        "full batch runner SHA changed",
    )
    now = datetime.now(timezone.utc)
    require(_parse_utc(activation.get("notBefore"), "notBefore") <= now, "activation is not active")
    require(now <= _parse_utc(activation.get("expiresAt"), "expiresAt"), "activation expired")
    relative = Path(str(activation.get("outputRelativePath")))
    expected = f"{contract['runtime']['outputBase']}/{activation['runId']}"
    require(relative.as_posix() == expected, "output path changed")
    require(not relative.is_absolute() and ".." not in relative.parts, "output escapes package")
    return contract, ROOT / relative


def _checkpoint(
    *,
    state: np.ndarray,
    areas_float64: np.ndarray,
    areas_longdouble: np.ndarray,
    initial_volume_float64: float,
    initial_volume_longdouble: np.longdouble,
    expected_volume_float64: float,
    expected_volume_longdouble: np.longdouble,
    boundary_volume_float64: float,
    boundary_volume_longdouble: np.longdouble,
    external_volume_float64: float,
    external_volume_longdouble: np.longdouble,
    cumulative_source_residual_m3: np.longdouble,
    model_seconds: float,
    accepted_steps: int,
    scenario: dict[str, Any],
    last_step: Any,
    last_external: dict[str, Any],
) -> dict[str, Any]:
    actual_volume_float64 = float(np.sum(state[:, 0] * areas_float64))
    actual_volume_longdouble = np.sum(
        state[:, 0].astype(np.longdouble) * areas_longdouble,
        dtype=np.longdouble,
    )
    signed_float64 = actual_volume_float64 - expected_volume_float64
    signed_longdouble = actual_volume_longdouble - expected_volume_longdouble
    relative_float64 = abs(signed_float64) / max(abs(initial_volume_float64), 1.0)
    relative_longdouble = abs(signed_longdouble) / max(abs(initial_volume_longdouble), np.longdouble(1.0))
    requested_volume = np.longdouble(
        float(scenario["boundaryInputs"]["barrageReleaseM3S"])
    ) * np.longdouble(model_seconds)
    row = {
        "modelSeconds": float(model_seconds),
        "acceptedSteps": int(accepted_steps),
        "tideTargetM": full.tide_at(scenario, model_seconds),
        "actualVolumeFloat64M3": actual_volume_float64,
        "actualVolumeLongDoubleM3": float(actual_volume_longdouble),
        "expectedVolumeFloat64M3": expected_volume_float64,
        "expectedVolumeLongDoubleM3": float(expected_volume_longdouble),
        "signedErrorFloat64M3": signed_float64,
        "signedErrorLongDoubleM3": float(signed_longdouble),
        "absoluteErrorFloat64M3": abs(signed_float64),
        "absoluteErrorLongDoubleM3": float(abs(signed_longdouble)),
        "relativeErrorFloat64": relative_float64,
        "relativeErrorLongDouble": float(relative_longdouble),
        "float64ThresholdCrossed": bool(relative_float64 > ORIGINAL_RELATIVE_MASS_THRESHOLD),
        "longDoubleThresholdCrossed": bool(relative_longdouble > ORIGINAL_RELATIVE_MASS_THRESHOLD),
        "expectedAccumulatorPrecisionDeltaM3": float(
            expected_volume_longdouble - np.longdouble(expected_volume_float64)
        ),
        "actualReductionPrecisionDeltaM3": float(
            actual_volume_longdouble - np.longdouble(actual_volume_float64)
        ),
        "cumulativeBoundaryOutflowVolumeFloat64M3": boundary_volume_float64,
        "cumulativeBoundaryOutflowVolumeLongDoubleM3": float(boundary_volume_longdouble),
        "cumulativeExternalAddedVolumeFloat64M3": external_volume_float64,
        "cumulativeExternalAddedVolumeLongDoubleM3": float(external_volume_longdouble),
        "requestedExternalVolumeM3": float(requested_volume),
        "externalAddedMinusRequestedM3": float(external_volume_longdouble - requested_volume),
        "cumulativeSourceResidualM3": float(cumulative_source_residual_m3),
        "instantBoundaryOutflowM3S": float(last_step.boundary_outflow_m3_s),
        "instantSourceResidualM3S": float(last_external["sourceResidualM3S"]),
        "instantInflowVelocityMPS": float(last_external["inflowVelocityMPS"]),
        "minimumDepthM": float(np.min(state[:, 0])),
        "maximumDepthM": float(np.max(state[:, 0])),
        "negativeDepthCount": int(np.sum(state[:, 0] < 0.0)),
        "nonFiniteValueCount": int(state.size - np.count_nonzero(np.isfinite(state))),
    }
    row["classification"] = classify_checkpoint(row)
    return row


def _require_output_in_package(path: Path) -> None:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise MassDiagnosticStop(f"[{VERSION}] worker output escapes package") from exc


def _run_scenario(scenario_id: str, output_text: str) -> int:
    require(socket.gethostname().lower() == "yoda", "worker host is not yoda")
    require(ACTIVATION_PATH.is_file() and not ACTIVATION_PATH.is_symlink(), "activation is missing")
    validate_activation(full.canary.read_json(ACTIVATION_PATH))
    scenarios = load_scenarios()
    require(scenario_id in scenarios, "worker scenario is not authorized")
    output = Path(output_text)
    require(output.is_absolute(), "worker output is not absolute")
    _require_output_in_package(output)
    require(not output.exists() and not output.is_symlink(), "worker output is not fresh")
    output.mkdir(parents=True, mode=0o700)

    scenario = scenarios[scenario_id]
    context = full.load_context()
    state = np.asarray(context["state"], dtype=np.float64).copy()
    areas_float64 = np.asarray(context["geometry"]["areas"], dtype=np.float64)
    areas_longdouble = areas_float64.astype(np.longdouble)
    initial_volume_float64 = float(np.sum(state[:, 0] * areas_float64))
    initial_volume_longdouble = np.sum(
        state[:, 0].astype(np.longdouble) * areas_longdouble,
        dtype=np.longdouble,
    )
    expected_volume_float64 = initial_volume_float64
    expected_volume_longdouble = initial_volume_longdouble
    boundary_volume_float64 = 0.0
    boundary_volume_longdouble = np.longdouble(0.0)
    external_volume_float64 = 0.0
    external_volume_longdouble = np.longdouble(0.0)
    cumulative_source_residual_m3 = np.longdouble(0.0)
    model_seconds = 0.0
    accepted_steps = 0
    next_check = CHECK_INTERVAL_SECONDS
    next_hour_boundary = 3600.0
    telemetry: list[dict[str, Any]] = []
    terminal_reason = "DURATION_REACHED_WITHOUT_ORIGINAL_THRESHOLD_CROSSING"
    wall_started = time.monotonic()

    full.canary.atomic_write_new(
        output / "start-receipt.json",
        full.canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-start-v1",
            "status": "STARTED_DIAGNOSTIC_NO_RETRY",
            "scenarioId": scenario_id,
            "durationModelSeconds": DURATION_SECONDS,
            "originalRelativeMassThreshold": ORIGINAL_RELATIVE_MASS_THRESHOLD,
            "processId": os.getpid(),
            "startedAtUtc": datetime.now(timezone.utc).isoformat(),
        }),
    )
    try:
        while model_seconds < DURATION_SECONDS - 1.0e-12:
            require(time.monotonic() - wall_started <= MAXIMUM_WORKER_WALL_SECONDS, "worker wall-time limit exceeded")
            require(accepted_steps < MAXIMUM_ACCEPTED_STEPS_PER_WORKER, "worker accepted-step limit exceeded")
            maximum_dt = min(0.05, DURATION_SECONDS - model_seconds, next_hour_boundary - model_seconds)
            require(maximum_dt > 0.0, "nonpositive worker time step")
            step, external = full.advance_once(state, context, scenario, model_seconds, maximum_dt)
            dt = float(step.accepted_dt_s)
            boundary_delta = dt * float(step.boundary_outflow_m3_s)
            external_delta = float(external["addedVolumeM3"])
            expected_volume_float64 -= boundary_delta
            expected_volume_float64 += external_delta
            expected_volume_longdouble -= np.longdouble(dt) * np.longdouble(step.boundary_outflow_m3_s)
            expected_volume_longdouble += np.longdouble(external_delta)
            boundary_volume_float64 += boundary_delta
            boundary_volume_longdouble += np.longdouble(dt) * np.longdouble(step.boundary_outflow_m3_s)
            external_volume_float64 += external_delta
            external_volume_longdouble += np.longdouble(external_delta)
            cumulative_source_residual_m3 += np.longdouble(external["sourceResidualM3S"]) * np.longdouble(dt)
            state = np.asarray(external["nextState"], dtype=np.float64)
            model_seconds += dt
            accepted_steps += 1
            if model_seconds >= next_hour_boundary - 1.0e-9:
                next_hour_boundary += 3600.0
            if model_seconds >= next_check - 1.0e-9 or model_seconds >= DURATION_SECONDS - 1.0e-9:
                require(bool(np.isfinite(state).all()), "nonfinite state")
                require(bool(np.all(state[:, 0] >= 0.0)), "negative depth")
                row = _checkpoint(
                    state=state,
                    areas_float64=areas_float64,
                    areas_longdouble=areas_longdouble,
                    initial_volume_float64=initial_volume_float64,
                    initial_volume_longdouble=initial_volume_longdouble,
                    expected_volume_float64=expected_volume_float64,
                    expected_volume_longdouble=expected_volume_longdouble,
                    boundary_volume_float64=boundary_volume_float64,
                    boundary_volume_longdouble=boundary_volume_longdouble,
                    external_volume_float64=external_volume_float64,
                    external_volume_longdouble=external_volume_longdouble,
                    cumulative_source_residual_m3=cumulative_source_residual_m3,
                    model_seconds=model_seconds,
                    accepted_steps=accepted_steps,
                    scenario=scenario,
                    last_step=step,
                    last_external=external,
                )
                telemetry.append(row)
                if row["float64ThresholdCrossed"]:
                    terminal_reason = "ORIGINAL_FLOAT64_THRESHOLD_CROSSING_CAPTURED"
                    break
                next_check += CHECK_INTERVAL_SECONDS

        terminal = telemetry[-1]
        result = {
            "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-result-v1",
            "status": "PASS_DIAGNOSTIC_EVIDENCE_CAPTURED_NOT_NUMERICAL_ACCEPTANCE",
            "scenarioId": scenario_id,
            "terminalReason": terminal_reason,
            "terminalClassification": terminal["classification"],
            "simulatedSeconds": model_seconds,
            "acceptedSteps": accepted_steps,
            "wallSeconds": time.monotonic() - wall_started,
            "checkpointCount": len(telemetry),
            "originalRelativeMassThreshold": ORIGINAL_RELATIVE_MASS_THRESHOLD,
            "terminalRelativeErrorFloat64": terminal["relativeErrorFloat64"],
            "terminalRelativeErrorLongDouble": terminal["relativeErrorLongDouble"],
            "terminalAbsoluteErrorFloat64M3": terminal["absoluteErrorFloat64M3"],
            "terminalAbsoluteErrorLongDoubleM3": terminal["absoluteErrorLongDoubleM3"],
            "negativeDepthCount": terminal["negativeDepthCount"],
            "nonFiniteValueCount": terminal["nonFiniteValueCount"],
            "usesUpstreamDonorVolume": False,
            "automaticRetryCount": 0,
            "physicalValidationProvided": False,
            "forecastProvided": False,
        }
        full.canary.atomic_write_new(output / "telemetry.json", full.canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-telemetry-v1",
            "scenarioId": scenario_id,
            "rows": telemetry,
        }))
        full.canary.atomic_save_npy_new(output / "terminal-state.npy", state)
        full.canary.atomic_write_new(output / "result.json", full.canary.canonical_bytes(result))
        full.canary.atomic_write_new(output / "completion-receipt.json", full.canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-completion-v1",
            "status": result["status"],
            "scenarioId": scenario_id,
            "resultSha256": full.canary.sha256_file(output / "result.json"),
            "telemetrySha256": full.canary.sha256_file(output / "telemetry.json"),
            "terminalStateSha256": full.canary.sha256_file(output / "terminal-state.npy"),
        }))
        return 0
    except BaseException as exc:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            full.canary.atomic_write_new(failure, full.canary.canonical_bytes({
                "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-failure-v1",
                "status": "FAILED_NO_RETRY",
                "scenarioId": scenario_id,
                "modelSeconds": model_seconds,
                "acceptedSteps": accepted_steps,
                "errorType": type(exc).__name__,
                "message": str(exc),
                "telemetryRowsBeforeFailure": telemetry,
            }))
        raise


def _terminate_active_workers() -> None:
    for process in list(_ACTIVE_WORKERS.values()):
        if process.poll() is None:
            process.terminate()


def _termination_handler(signum: int, _frame: Any) -> None:
    _terminate_active_workers()
    raise MassDiagnosticStop(f"[{VERSION}] termination signal received: {signum}")


def _run_parallel(output: Path) -> list[dict[str, Any]]:
    scenario_root = output / "scenarios"
    scenario_root.mkdir(mode=0o700)
    processes: dict[str, tuple[subprocess.Popen[Any], Any]] = {}
    failed: tuple[str, int] | None = None
    try:
        for scenario_id in SCENARIO_IDS:
            log = (scenario_root / f"{scenario_id}.log").open("xb")
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--scenario",
                scenario_id,
                "--output",
                str(scenario_root / scenario_id),
            ]
            environment = dict(os.environ)
            environment.update({
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "NUMBA_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            })
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
            processes[scenario_id] = (process, log)
            _ACTIVE_WORKERS[scenario_id] = process
        while processes:
            for scenario_id, (process, log) in list(processes.items()):
                code = process.poll()
                if code is None:
                    continue
                log.close()
                del processes[scenario_id]
                _ACTIVE_WORKERS.pop(scenario_id, None)
                if code != 0 and failed is None:
                    failed = (scenario_id, code)
                    _terminate_active_workers()
            if processes:
                time.sleep(5.0)
        require(failed is None, f"diagnostic worker failed without retry: {failed}")
    finally:
        _terminate_active_workers()
        for scenario_id, (process, log) in list(processes.items()):
            try:
                process.wait(timeout=30.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10.0)
            if not log.closed:
                log.close()
            _ACTIVE_WORKERS.pop(scenario_id, None)

    results = []
    for scenario_id in SCENARIO_IDS:
        result_path = scenario_root / scenario_id / "result.json"
        require(result_path.is_file(), f"missing diagnostic result: {scenario_id}")
        result = full.canary.read_json(result_path)
        require(
            result.get("status") == "PASS_DIAGNOSTIC_EVIDENCE_CAPTURED_NOT_NUMERICAL_ACCEPTANCE",
            f"diagnostic result did not pass: {scenario_id}",
        )
        results.append(result)
    return results


def _manifest(root: Path, run_id: str) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "manifest.json"):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "byteLength": path.stat().st_size,
            "sha256": full.canary.sha256_file(path),
        })
    return {
        "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-manifest-v1",
        "runId": run_id,
        "files": files,
    }


def execute() -> dict[str, Any]:
    require(ACTIVATION_PATH.is_file() and not ACTIVATION_PATH.is_symlink(), "activation is missing")
    activation = full.canary.read_json(ACTIVATION_PATH)
    _, output = validate_activation(activation)
    require(socket.gethostname().lower() == "yoda", "runner host is not yoda")
    require(not output.exists() and not output.is_symlink(), "fresh diagnostic output is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    full.canary.atomic_write_new(output / "claim.json", full.canary.canonical_bytes({
        "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-claim-v1",
        "status": "CLAIMED_SINGLE_USE_NO_RETRY",
        "authorizationId": activation["authorizationId"],
        "runId": activation["runId"],
        "claimedAtUtc": datetime.now(timezone.utc).isoformat(),
        "activationSha256": full.canary.sha256_file(ACTIVATION_PATH),
        "processId": os.getpid(),
    }))
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, _termination_handler)
    signal.signal(signal.SIGINT, _termination_handler)
    try:
        wall_started = time.monotonic()
        results = _run_parallel(output)
        wall_seconds = time.monotonic() - wall_started
        require(wall_seconds <= MAXIMUM_BATCH_WALL_SECONDS, "batch wall-time limit exceeded")
        result = {
            "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-batch-result-v1",
            "status": "PASS_TWO_SCENARIO_MASS_DIAGNOSTIC_NOT_NUMERICAL_PROMOTION",
            "runId": activation["runId"],
            "scenarioCount": len(results),
            "wallSeconds": wall_seconds,
            "results": results,
            "automaticRetryCount": 0,
            "physicalValidationProvided": False,
            "forecastProvided": False,
        }
        full.canary.atomic_write_new(output / "result.json", full.canary.canonical_bytes(result))
        full.canary.atomic_write_new(output / "completion-receipt.json", full.canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-completion-v1",
            "status": result["status"],
            "authorizationId": activation["authorizationId"],
            "runId": activation["runId"],
            "resultSha256": full.canary.sha256_file(output / "result.json"),
        }))
        full.canary.atomic_write_new(
            output / "manifest.json",
            full.canary.canonical_bytes(_manifest(output, activation["runId"])),
        )
        return result
    except BaseException as exc:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            full.canary.atomic_write_new(failure, full.canary.canonical_bytes({
                "schema": "onga-stage20-downstream-external-large-tide-mass-diagnostic-batch-failure-v1",
                "status": "FAILED_NO_RETRY",
                "authorizationId": activation.get("authorizationId"),
                "runId": activation.get("runId"),
                "errorType": type(exc).__name__,
                "message": str(exc),
            }))
        raise
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", help=argparse.SUPPRESS)
    parser.add_argument("--output", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        require(args.scenario is not None and args.output is not None, "worker arguments are missing")
        return _run_scenario(args.scenario, args.output)
    require(sum((args.preflight, args.execute)) <= 1, "choose at most one mode")
    report = execute() if args.execute else build_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
