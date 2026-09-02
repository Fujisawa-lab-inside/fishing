#!/usr/bin/env python3
"""Continue the high-release/large-tide state across the prior dry-face stop."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_downstream_external_six_scenario_37_snapshot_runner_v1 as batch


VERSION = "stage20-downstream-external-boundary-dry-continuation-diagnostic-v1"
AUTHORIZATION_ID = "stage20-downstream-external-boundary-dry-continuation-yoda-20260902-01"
RUN_ID = "diagnostic-stage20-downstream-external-boundary-dry-continuation-20260902-v1"
CHECKPOINT_PATH = ROOT / "inputs/release-high_tide-large-13800-terminal-state.npy"
CHECKPOINT_SHA256 = "37de4a0979bff5179ed9d24e018b5e69b8a28936166b46ed382528075c228987"
START_MODEL_SECONDS = 13800.001193044864
CONTINUATION_SECONDS = 6000.0
END_MODEL_SECONDS = START_MODEL_SECONDS + CONTINUATION_SECONDS
MAXIMUM_WALL_SECONDS = 3600.0
MAXIMUM_ACCEPTED_STEPS = 2_000_000
OUTPUT_RELATIVE = Path(
    ".stage20-local-only/stage20-downstream-external-boundary-dry-continuation-20260902"
) / RUN_ID


class ContinuationStop(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContinuationStop(f"[{VERSION}] {message}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def atomic_write_new(path: Path, data: bytes) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing to overwrite {path}")
    path.write_bytes(data)


def atomic_save_npy_new(path: Path, value: np.ndarray) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing to overwrite {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    require(not temporary.exists(), "temporary final-state path exists")
    with temporary.open("xb") as stream:
        np.save(stream, value, allow_pickle=False)
    os.replace(temporary, path)


def build_preflight() -> dict[str, Any]:
    return {
        "schema": "onga-stage20-downstream-external-boundary-dry-continuation-preflight-v1",
        "status": "READY_EXPLORATION_A_SINGLE_SCENARIO_EXECUTION_REQUIRES_EXACT_ENV_AUTHORIZATION",
        "launchPermitted": False,
        "scenarioId": "release-high_tide-large",
        "sourceCheckpointModelSeconds": START_MODEL_SECONDS,
        "continuationSeconds": CONTINUATION_SECONDS,
        "endModelSeconds": END_MODEL_SECONDS,
        "maximumWallSeconds": MAXIMUM_WALL_SECONDS,
        "maximumAcceptedSteps": MAXIMUM_ACCEPTED_STEPS,
        "automaticRetryCount": 0,
        "physicalValidation": False,
        "forecast": False,
    }


def execute() -> dict[str, Any]:
    require(socket.gethostname().lower() == "yoda", "host is not yoda")
    require(
        os.environ.get("STAGE20_CONTINUATION_AUTHORIZATION_ID") == AUTHORIZATION_ID,
        "exact continuation authorization is missing",
    )
    require(CHECKPOINT_PATH.is_file() and not CHECKPOINT_PATH.is_symlink(), "checkpoint is missing")
    require(sha256_file(CHECKPOINT_PATH) == CHECKPOINT_SHA256, "checkpoint SHA changed")
    output = ROOT / OUTPUT_RELATIVE
    require(not output.exists() and not output.is_symlink(), "output is not fresh")
    output.mkdir(parents=True, mode=0o700)

    model_seconds = START_MODEL_SECONDS
    accepted_steps = 0
    try:
        context = batch.load_context()
        scenario = batch.load_scenarios()["release-high_tide-large"]
        state = np.load(CHECKPOINT_PATH, allow_pickle=False)
        require(state.shape == (batch.CELL_COUNT, 3) and state.dtype == np.float64, "checkpoint shape or dtype changed")
        geometry = context["geometry"]
        areas = np.asarray(geometry["areas"], dtype=np.float64)
        areas_longdouble = areas.astype(np.longdouble)
        initial_volume_float64 = float(np.sum(state[:, 0] * areas))
        initial_volume_longdouble = np.sum(
            state[:, 0].astype(np.longdouble) * areas_longdouble,
            dtype=np.longdouble,
        )
        expected_volume_float64 = initial_volume_float64
        expected_volume_longdouble = initial_volume_longdouble
        maximum_cfl = 0.0
        maximum_mass_error = 0.0
        maximum_mass_error_float64 = 0.0
        maximum_source_residual = 0.0
        maximum_dry_faces_by_tag = np.zeros(5, dtype=np.int64)
        minimum_wet_faces_by_tag = np.zeros(5, dtype=np.int64)
        minimum_wet_faces_by_tag[2:] = np.iinfo(np.int64).max
        dry_face_step_count = 0
        next_safety_check = model_seconds + 600.0
        wall_started = time.monotonic()

        atomic_write_new(
            output / "start-receipt.json",
            canonical_bytes({
                "schema": "onga-stage20-downstream-external-boundary-dry-continuation-start-v1",
                "status": "STARTED_SINGLE_SCENARIO_EXPLORATION_A_NO_RETRY",
                "authorizationId": AUTHORIZATION_ID,
                "runId": RUN_ID,
                "scenarioId": "release-high_tide-large",
                "sourceCheckpointSha256": CHECKPOINT_SHA256,
                "startedAtUtc": datetime.now(timezone.utc).isoformat(),
                "processId": os.getpid(),
            }),
        )

        while model_seconds < END_MODEL_SECONDS - 1.0e-12:
            require(time.monotonic() - wall_started <= MAXIMUM_WALL_SECONDS, "wall-time limit exceeded")
            require(accepted_steps < MAXIMUM_ACCEPTED_STEPS, "accepted-step limit exceeded")
            maximum_dt = min(0.05, END_MODEL_SECONDS - model_seconds)
            step, external = batch.advance_once(
                state,
                context,
                scenario,
                model_seconds,
                maximum_dt,
            )
            dt = float(step.accepted_dt_s)
            state = np.asarray(external["nextState"], dtype=np.float64)
            model_seconds += dt
            accepted_steps += 1
            expected_volume_float64 -= dt * float(step.boundary_outflow_m3_s)
            expected_volume_float64 += float(external["addedVolumeM3"])
            expected_volume_longdouble -= np.longdouble(dt) * np.longdouble(step.boundary_outflow_m3_s)
            expected_volume_longdouble += np.longdouble(external["addedVolumeM3"])
            maximum_cfl = max(maximum_cfl, float(step.maximum_cfl))
            maximum_source_residual = max(
                maximum_source_residual,
                abs(float(external["sourceResidualM3S"])),
            )
            dry_faces = np.asarray(external["riverBoundaryDryFaceCountByTag"], dtype=np.int64)
            wet_faces = np.asarray(external["riverBoundaryWetFaceCountByTag"], dtype=np.int64)
            maximum_dry_faces_by_tag = np.maximum(maximum_dry_faces_by_tag, dry_faces)
            if bool(np.any(dry_faces[2:] > 0)):
                dry_face_step_count += 1
            for tag in (2, 3, 4):
                minimum_wet_faces_by_tag[tag] = min(minimum_wet_faces_by_tag[tag], wet_faces[tag])

            if model_seconds >= next_safety_check - 1.0e-9 or model_seconds >= END_MODEL_SECONDS - 1.0e-9:
                require(bool(np.isfinite(state).all()), "nonfinite state")
                require(bool(np.all(state[:, 0] >= 0.0)), "negative depth")
                errors = batch.mass_balance_errors(
                    state,
                    areas,
                    areas_longdouble,
                    initial_volume_float64=initial_volume_float64,
                    initial_volume_longdouble=initial_volume_longdouble,
                    expected_volume_float64=expected_volume_float64,
                    expected_volume_longdouble=expected_volume_longdouble,
                )
                maximum_mass_error = max(maximum_mass_error, errors["relativeMassBalanceErrorLongDouble"])
                maximum_mass_error_float64 = max(
                    maximum_mass_error_float64,
                    errors["relativeMassBalanceErrorFloat64Diagnostic"],
                )
                require(maximum_mass_error <= batch.MASS_BALANCE_THRESHOLD, "long-double mass balance guard failed")
                next_safety_check += 600.0

        require(math.isclose(model_seconds, END_MODEL_SECONDS, abs_tol=1.0e-8), "continuation duration changed")
        require(dry_face_step_count > 0, "continuation never exercised the dry-face policy")
        require(bool(np.all(minimum_wet_faces_by_tag[[2, 4]] > 0)), "nonzero tributary section became fully dry")
        result = {
            "schema": "onga-stage20-downstream-external-boundary-dry-continuation-result-v1",
            "status": "PASS_NUMERICAL_EXPLORATION_A_PARTIAL_DRY_FACE_CONTINUATION_NOT_PHYSICAL_VALIDATION_NOT_FORECAST",
            "authorizationId": AUTHORIZATION_ID,
            "runId": RUN_ID,
            "scenarioId": "release-high_tide-large",
            "sourceCheckpointModelSeconds": START_MODEL_SECONDS,
            "endModelSeconds": model_seconds,
            "continuationSeconds": model_seconds - START_MODEL_SECONDS,
            "acceptedSteps": accepted_steps,
            "wallSeconds": time.monotonic() - wall_started,
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "maximumRelativeMassBalanceErrorFloat64Diagnostic": maximum_mass_error_float64,
            "maximumSourceResidualM3S": maximum_source_residual,
            "dryFaceStepCount": dry_face_step_count,
            "maximumDryRiverBoundaryFaceCountByTag": maximum_dry_faces_by_tag.tolist(),
            "minimumWetRiverBoundaryFaceCountByTag": minimum_wet_faces_by_tag.tolist(),
            "negativeDepthCount": int(np.sum(state[:, 0] < 0.0)),
            "nonFiniteValueCount": int(state.size - np.count_nonzero(np.isfinite(state))),
            "automaticRetryCount": 0,
            "physicalValidation": False,
            "forecast": False,
        }
        atomic_write_new(output / "result.json", canonical_bytes(result))
        atomic_save_npy_new(output / "final-state.npy", state)
        completion = {
            "schema": "onga-stage20-downstream-external-boundary-dry-continuation-completion-v1",
            "status": result["status"],
            "authorizationId": AUTHORIZATION_ID,
            "runId": RUN_ID,
            "resultSha256": sha256_file(output / "result.json"),
            "finalStateSha256": sha256_file(output / "final-state.npy"),
        }
        atomic_write_new(output / "completion-receipt.json", canonical_bytes(completion))
        manifest = {
            "schema": "onga-stage20-downstream-external-boundary-dry-continuation-manifest-v1",
            "files": [
                {"path": name, "sha256": sha256_file(output / name)}
                for name in ("start-receipt.json", "result.json", "final-state.npy", "completion-receipt.json")
            ],
        }
        atomic_write_new(output / "manifest.json", canonical_bytes(manifest))
        return result
    except BaseException as exc:
        failure = output / "failure-receipt.json"
        if not failure.exists():
            atomic_write_new(
                failure,
                canonical_bytes({
                    "schema": "onga-stage20-downstream-external-boundary-dry-continuation-failure-v1",
                    "status": "FAILED_NO_RETRY",
                    "authorizationId": AUTHORIZATION_ID,
                    "runId": RUN_ID,
                    "modelSeconds": model_seconds,
                    "acceptedSteps": accepted_steps,
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                    "failedAtUtc": datetime.now(timezone.utc).isoformat(),
                }),
            )
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(build_preflight(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(json.dumps(execute(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
