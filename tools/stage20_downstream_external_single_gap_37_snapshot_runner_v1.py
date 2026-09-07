#!/usr/bin/env python3
"""Run one additional downstream-only 37-hour release anchor.

The numerical step and all hydraulic safety guards are reused from the proven
six-condition runner.  This wrapper only narrows execution to one new release
anchor and requires a fresh, single-use YODA activation.  It never retries.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
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

import stage20_downstream_external_six_scenario_37_snapshot_runner_v1 as base


VERSION = "stage20-downstream-external-single-gap-37-snapshot-runner-v1"
SCENARIO_ID = "release-6p2_tide-large"
AUTHORIZED_ID = "stage20-downstream-external-release-6p2-large-yoda-20260907-01"
AUTHORIZED_RUN_ID = "scenario-stage20-downstream-external-release-6p2-large-20260907-v1"
INPUT_PATH = ROOT / "config/stage20_downstream_external_release_6p2_tide_large_37_snapshot_input_v1.json"
ACTIVATION_PATH = ROOT / "config/stage20_downstream_external_release_6p2_tide_large_37_snapshot_activation_20260907_v1.json"
OUTPUT_BASE = Path(
    ".stage20-local-only/stage20-downstream-external-single-gap-37-snapshot-20260907"
)
MAXIMUM_WALL_SECONDS = 33_600.0
_ACTIVE_WORKER: subprocess.Popen[Any] | None = None


class SingleGapStop(RuntimeError):
    """A deliberate fail-closed stop for the single gap scenario."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SingleGapStop(f"[{VERSION}] {message}")


def load_scenario() -> dict[str, Any]:
    base.verified_contract()
    document = base.canary.read_json(INPUT_PATH)
    require(
        document.get("schema")
        == "onga-stage20-downstream-external-single-gap-scenario-input-v1",
        "input schema changed",
    )
    require(document.get("scenarioId") == SCENARIO_ID, "scenario id changed")
    require(document.get("barrageReleaseM3S") == 6.2, "release anchor changed")
    require(document.get("tideRangeClass") == "large", "tide class changed")
    require(document.get("durationModelSeconds") == int(base.FULL_SECONDS), "duration changed")
    require(document.get("snapshotCount") == base.SNAPSHOT_COUNT, "snapshot count changed")
    require(document.get("intervalHours") == 1, "snapshot interval changed")
    require(document.get("currentConditionReferenceAllowed") is False, "input was promoted")
    require(document.get("usesUpstreamDonorVolume") is False, "upstream donor was enabled")
    require(document.get("reverseFlowPermitted") is False, "reverse flow was enabled")
    offsets = np.asarray(document.get("snapshotOffsetsHours"), dtype=np.int64)
    require(
        offsets.shape == (base.SNAPSHOT_COUNT,)
        and bool(np.array_equal(offsets, np.arange(-12, 25, dtype=np.int64))),
        "snapshot offsets changed",
    )
    source_path = str(document.get("sourceTideInputPath"))
    require(source_path == str(base.INPUT_PATH.relative_to(ROOT)), "source tide input changed")
    source = base.canary.read_json(ROOT / source_path)
    tides = [item for item in source.get("tideRanges", []) if item.get("id") == "large"]
    require(len(tides) == 1, "large-tide source is missing")
    tide = tides[0]
    heights = np.asarray(tide.get("astronomicalTideHeightMByOffset"), dtype=np.float64)
    require(
        heights.shape == (base.SNAPSHOT_COUNT,) and bool(np.isfinite(heights).all()),
        "large-tide source is invalid",
    )
    return {
        "id": SCENARIO_ID,
        "releaseBand": "low-mid-gap",
        "tideRangeClass": "large",
        "currentConditionReferenceAllowed": False,
        "boundaryInputs": {
            "barrageReleaseM3S": 6.2,
            "snapshotOffsetsHours": offsets.tolist(),
            "astronomicalTideHeightMByOffset": heights.tolist(),
            "tideStationCode": tide["tideStationCode"],
            "tideCenterTimeJst": tide["representativeCenterTimeJst"],
        },
    }


def _binding_inventory() -> list[dict[str, Any]]:
    _, verified = base.verified_contract()
    return [
        *verified,
        {
            "role": "single_gap_runner",
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": base.canary.sha256_file(Path(__file__).resolve()),
        },
        {
            "role": "single_gap_input",
            "path": str(INPUT_PATH.relative_to(ROOT)),
            "sha256": base.canary.sha256_file(INPUT_PATH),
        },
    ]


def build_preflight() -> dict[str, Any]:
    scenario = load_scenario()
    bindings = _binding_inventory()
    return {
        "schema": "onga-stage20-downstream-external-single-gap-37-snapshot-preflight-v1",
        "status": "PASS_PREPARE_ONLY_SINGLE_GAP_BLOCKED_PENDING_ACTIVATION",
        "launchPermitted": False,
        "activationPresent": ACTIVATION_PATH.is_file(),
        "allBindingsVerified": True,
        "bindingCount": len(bindings),
        "scenarioId": scenario["id"],
        "barrageReleaseM3S": scenario["boundaryInputs"]["barrageReleaseM3S"],
        "tideRangeClass": scenario["tideRangeClass"],
        "durationModelSeconds": int(base.FULL_SECONDS),
        "hourlySnapshotCount": base.SNAPSHOT_COUNT,
        "parallelWorkerCount": 1,
        "maximumWallSeconds": int(MAXIMUM_WALL_SECONDS),
        "automaticRetryCount": 0,
        "currentConditionReferenceAllowed": False,
        "forecastProvided": False,
        "catchProbabilityProvided": False,
    }


def _parse_utc(value: Any, field: str) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), f"{field} is not UTC")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    require(parsed.tzinfo is not None, f"{field} is timezone-naive")
    return parsed.astimezone(timezone.utc)


def validate_activation(activation: dict[str, Any]) -> Path:
    load_scenario()
    require(
        activation.get("schema")
        == "onga-stage20-downstream-external-single-gap-37-snapshot-activation-v1",
        "activation schema changed",
    )
    require(activation.get("status") == "AUTHORIZED", "activation is not authorized")
    require(
        activation.get("mode") == "EXECUTE_DIAGNOSTIC_SINGLE_GAP_ONCE",
        "activation mode changed",
    )
    require(activation.get("authorizationId") == AUTHORIZED_ID, "authorization id changed")
    require(activation.get("runId") == AUTHORIZED_RUN_ID, "run id changed")
    require(activation.get("requiredHostname") == "yoda", "activation host changed")
    require(activation.get("maximumUseCount") == 1, "activation is not single-use")
    require(activation.get("retryCount") == 0, "retry was enabled")
    require(activation.get("scenarioId") == SCENARIO_ID, "activation scenario changed")
    require(activation.get("durationModelSeconds") == int(base.FULL_SECONDS), "activation duration changed")
    require(activation.get("snapshotCount") == base.SNAPSHOT_COUNT, "activation snapshot count changed")
    require(
        activation.get("runnerSha256") == base.canary.sha256_file(Path(__file__).resolve()),
        "runner SHA changed",
    )
    require(
        activation.get("scenarioInputSha256") == base.canary.sha256_file(INPUT_PATH),
        "input SHA changed",
    )
    require(
        activation.get("baseRunnerSha256")
        == base.canary.sha256_file(Path(base.__file__).resolve()),
        "base runner SHA changed",
    )
    require(
        activation.get("baseContractSha256") == base.canary.sha256_file(base.CONTRACT_PATH),
        "base contract SHA changed",
    )
    now = datetime.now(timezone.utc)
    require(_parse_utc(activation.get("notBefore"), "notBefore") <= now, "activation is not active")
    require(now <= _parse_utc(activation.get("expiresAt"), "expiresAt"), "activation expired")
    output_relative = activation.get("outputRelativePath")
    expected = f"{OUTPUT_BASE.as_posix()}/{activation['runId']}"
    require(output_relative == expected, "output path changed")
    relative = Path(str(output_relative))
    require(not relative.is_absolute() and ".." not in relative.parts, "output escapes package")
    return ROOT / relative


def run_local_one_step() -> dict[str, Any]:
    scenario = load_scenario()
    context = base.load_context()
    state = np.asarray(context["state"], dtype=np.float64)
    step, external = base.advance_once(state, context, scenario, 0.0, 0.05)
    next_state = np.asarray(external["nextState"], dtype=np.float64)
    require(bool(np.isfinite(next_state).all()), "one-step state is nonfinite")
    require(bool(np.all(next_state[:, 0] >= 0.0)), "one-step depth is negative")
    return {
        "schema": "onga-stage20-downstream-external-single-gap-one-step-v1",
        "status": "PASS_LOCAL_SINGLE_GAP_ONE_STEP_NOT_LONG_RUN",
        "scenarioId": SCENARIO_ID,
        "barrageReleaseM3S": 6.2,
        "acceptedDtS": float(step.accepted_dt_s),
        "maximumCfl": float(step.maximum_cfl),
        "effectiveReleaseM3S": float(external["effectiveReleaseM3S"]),
        "upstreamStateChangedBySource": bool(external["upstreamStateChanged"]),
        "negativeDepthCount": 0,
        "nonFiniteValueCount": 0,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
    }


def _worker(output_text: str) -> int:
    require(socket.gethostname().lower() == "yoda", "worker host is not yoda")
    require(ACTIVATION_PATH.is_file() and not ACTIVATION_PATH.is_symlink(), "activation is missing")
    validate_activation(base.canary.read_json(ACTIVATION_PATH))
    scenario = load_scenario()
    original_activation_path = base.ACTIVATION_PATH
    original_validate_activation = base.validate_activation
    original_load_scenarios = base.load_scenarios
    original_version = base.VERSION
    try:
        base.ACTIVATION_PATH = ACTIVATION_PATH
        base.validate_activation = lambda activation: ({}, validate_activation(activation))
        base.load_scenarios = lambda: {SCENARIO_ID: scenario}
        base.VERSION = VERSION
        return base._run_scenario(SCENARIO_ID, output_text)
    finally:
        base.ACTIVATION_PATH = original_activation_path
        base.validate_activation = original_validate_activation
        base.load_scenarios = original_load_scenarios
        base.VERSION = original_version


def _manifest(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "manifest.json"):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "byteLength": path.stat().st_size,
            "sha256": base.canary.sha256_file(path),
        })
    return {
        "schema": "onga-stage20-downstream-external-single-gap-37-snapshot-manifest-v1",
        "runId": AUTHORIZED_RUN_ID,
        "files": files,
    }


def _terminate_worker() -> None:
    global _ACTIVE_WORKER
    if _ACTIVE_WORKER is not None and _ACTIVE_WORKER.poll() is None:
        _ACTIVE_WORKER.terminate()


def execute() -> dict[str, Any]:
    global _ACTIVE_WORKER
    require(ACTIVATION_PATH.is_file() and not ACTIVATION_PATH.is_symlink(), "activation is missing")
    activation = base.canary.read_json(ACTIVATION_PATH)
    output = validate_activation(activation)
    require(socket.gethostname().lower() == "yoda", "runner host is not yoda")
    require(not output.exists() and not output.is_symlink(), "fresh output is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    base.canary.atomic_write_new(output / "claim.json", base.canary.canonical_bytes({
        "schema": "onga-stage20-downstream-external-single-gap-37-snapshot-claim-v1",
        "status": "CLAIMED_SINGLE_USE_NO_RETRY",
        "authorizationId": AUTHORIZED_ID,
        "runId": AUTHORIZED_RUN_ID,
        "scenarioId": SCENARIO_ID,
        "claimedAtUtc": datetime.now(timezone.utc).isoformat(),
        "activationSha256": base.canary.sha256_file(ACTIVATION_PATH),
        "processId": os.getpid(),
        "retryCount": 0,
    }))
    base.canary.atomic_write_new(output / "start-receipt.json", base.canary.canonical_bytes({
        "schema": "onga-stage20-downstream-external-single-gap-37-snapshot-start-v1",
        "status": "STARTED_DIAGNOSTIC_SINGLE_GAP_NO_RETRY",
        "runId": AUTHORIZED_RUN_ID,
        "scenarioId": SCENARIO_ID,
        "durationModelSeconds": int(base.FULL_SECONDS),
        "snapshotCount": base.SNAPSHOT_COUNT,
        "automaticRetryCount": 0,
    }))
    scenario_root = output / "scenarios"
    scenario_root.mkdir(mode=0o700)
    scenario_output = scenario_root / SCENARIO_ID
    log_path = scenario_root / f"{SCENARIO_ID}.log"
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, lambda *_: (_terminate_worker(), sys.exit(143)))
    signal.signal(signal.SIGINT, lambda *_: (_terminate_worker(), sys.exit(130)))
    try:
        wall_started = time.monotonic()
        with log_path.open("xb") as log:
            _ACTIVE_WORKER = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--output",
                    str(scenario_output),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    "NUMBA_NUM_THREADS": "1",
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                },
            )
            code = _ACTIVE_WORKER.wait()
        _ACTIVE_WORKER = None
        require(code == 0, f"scenario worker failed without retry: {code}")
        wall_seconds = time.monotonic() - wall_started
        require(wall_seconds <= MAXIMUM_WALL_SECONDS, "wall-time limit exceeded")
        scenario_result = base.canary.read_json(scenario_output / "result.json")
        require(
            scenario_result.get("status")
            == "PASS_NUMERICAL_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
            "scenario result is not a numerical pass",
        )
        result = {
            "schema": "onga-stage20-downstream-external-single-gap-37-snapshot-result-v1",
            "status": "PASS_SINGLE_GAP_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
            "runId": AUTHORIZED_RUN_ID,
            "scenarioId": SCENARIO_ID,
            "wallSeconds": wall_seconds,
            "scenarioResult": scenario_result,
            "currentConditionReferenceAllowed": False,
            "forecastProvided": False,
            "catchProbabilityProvided": False,
            "guiIntegrated": False,
        }
        base.canary.atomic_write_new(output / "result.json", base.canary.canonical_bytes(result))
        base.canary.atomic_write_new(output / "completion-receipt.json", base.canary.canonical_bytes({
            "schema": "onga-stage20-downstream-external-single-gap-37-snapshot-completion-v1",
            "status": result["status"],
            "authorizationId": AUTHORIZED_ID,
            "runId": AUTHORIZED_RUN_ID,
            "completedAtUtc": datetime.now(timezone.utc).isoformat(),
            "resultSha256": base.canary.sha256_file(output / "result.json"),
            "snapshotSha256": base.canary.sha256_file(scenario_output / "hourly-downstream-state.npz"),
        }))
        base.canary.atomic_write_new(output / "manifest.json", base.canary.canonical_bytes(_manifest(output)))
        return result
    except BaseException as exc:
        _terminate_worker()
        failure = output / "failure-receipt.json"
        if not failure.exists():
            base.canary.atomic_write_new(failure, base.canary.canonical_bytes({
                "schema": "onga-stage20-downstream-external-single-gap-37-snapshot-failure-v1",
                "status": "FAILED_NO_RETRY",
                "authorizationId": AUTHORIZED_ID,
                "runId": AUTHORIZED_RUN_ID,
                "failedAtUtc": datetime.now(timezone.utc).isoformat(),
                "errorType": type(exc).__name__,
                "message": str(exc),
            }))
        raise
    finally:
        _ACTIVE_WORKER = None
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--local-one-step", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", help=argparse.SUPPRESS)
    args = parser.parse_args()
    require(
        sum((args.preflight, args.local_one_step, args.execute, args.worker)) <= 1,
        "choose at most one mode",
    )
    if args.worker:
        require(args.output is not None, "worker output is missing")
        return _worker(args.output)
    if args.execute:
        report = execute()
    elif args.local_one_step:
        report = run_local_one_step()
    else:
        report = build_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
