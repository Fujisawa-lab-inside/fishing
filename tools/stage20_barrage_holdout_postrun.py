#!/usr/bin/env python3
"""Offline validation and holdout metrics for the Stage 20 barrage recovery.

This module deliberately has no GitHub, network, subprocess, or numerical-solver
integration.  It only reads sealed local evidence and, after that evidence has
been validated, may write derived comparison fields.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import numpy as np


FIELD_KEYS = ("waterDepthM", "velocityUms", "velocityVms")
STATE_KEYS = (
    "state",
    "elapsed_seconds",
    "step",
    "expected_volume_m3",
    "maximum_cfl",
    "maximum_mass_error",
)
EXPECTED_REGION_IDS = ("estuary", "barrage", "confluence", "fishway")
EXPECTED_HOURS = (-12, -11, -10, -9, -8)
EXPECTED_BASES = ("barrage-closed", "barrage-open")


class NotEvaluableError(RuntimeError):
    """An evidence or input failure that prevents a holdout decision."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            record["details"] = self.details
        return record


def require(condition: bool, code: str, message: str, **details: Any) -> None:
    if not condition:
        raise NotEvaluableError(code, message, **details)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    require(path.is_file(), "E_FILE_MISSING", "required file is missing", path=str(path))
    require(not path.is_symlink(), "E_SYMLINK", "symlink evidence is forbidden", path=str(path))
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as error:
        raise NotEvaluableError("E_FILE_READ", "could not read required file", path=str(path), error=str(error)) from error


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), "E_FILE_MISSING", "required JSON file is missing", path=str(path))
    require(not path.is_symlink(), "E_SYMLINK", "symlink JSON evidence is forbidden", path=str(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise NotEvaluableError("E_JSON_INVALID", "required JSON file is invalid", path=str(path), error=str(error)) from error
    require(isinstance(value, dict), "E_JSON_TYPE", "top-level JSON value must be an object", path=str(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _finite_number(value: Any, label: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), "E_NUMBER_TYPE", "expected a number", field=label)
    result = float(value)
    require(math.isfinite(result), "E_NUMBER_NONFINITE", "number must be finite", field=label)
    return result


def _integer(value: Any, label: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), "E_INTEGER_TYPE", "expected an integer", field=label)
    return int(value)


def _hex_digest(value: Any, label: str, length: int = 64) -> str:
    require(isinstance(value, str), "E_DIGEST_TYPE", "digest must be a string", field=label)
    require(len(value) == length and all(character in "0123456789abcdef" for character in value), "E_DIGEST_FORMAT", "digest has invalid format", field=label)
    return value


def _safe_relative_path(root: Path, raw: Any, label: str) -> Path:
    require(isinstance(raw, str) and raw != "", "E_PATH_TYPE", "evidence path must be a non-empty string", field=label)
    require("\\" not in raw, "E_PATH_UNSAFE", "backslashes are forbidden in evidence paths", path=raw)
    pure = PurePosixPath(raw)
    require(not pure.is_absolute(), "E_PATH_UNSAFE", "absolute evidence path is forbidden", path=raw)
    require(all(part not in {"", ".", ".."} for part in pure.parts), "E_PATH_UNSAFE", "non-normal evidence path is forbidden", path=raw)
    require(str(pure) == raw, "E_PATH_UNSAFE", "evidence path must be normalized POSIX form", path=raw)
    candidate = root.joinpath(*pure.parts)
    try:
        require(candidate.resolve(strict=False).is_relative_to(root.resolve()), "E_PATH_ESCAPE", "evidence path escapes its artifact root", path=raw)
    except OSError as error:
        raise NotEvaluableError("E_PATH_RESOLVE", "could not resolve evidence path", path=raw, error=str(error)) from error
    return candidate


def _verify_pinned_file(repo_root: Path, record: Mapping[str, Any], label: str) -> Path:
    path = _safe_relative_path(repo_root, record.get("path"), f"{label}.path")
    expected = _hex_digest(record.get("sha256"), f"{label}.sha256")
    actual = sha256_file(path)
    require(actual == expected, "E_PINNED_SHA256", "pinned file digest mismatch", label=label, path=str(path), expected=expected, actual=actual)
    return path


def validate_manifest(
    artifact_root: Path,
    *,
    expected_schema: str | Iterable[str],
    expected_status: str = "sealed_complete_not_physical_validation",
    expected_authorization_id: str | None = None,
    expected_job_id: str | None = None,
    expected_sha256: str | None = None,
    strict_inventory: bool = True,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate every manifest entry and optionally the exact artifact inventory."""

    require(artifact_root.is_dir(), "E_ARTIFACT_MISSING", "artifact directory is missing", path=str(artifact_root))
    require(not artifact_root.is_symlink(), "E_SYMLINK", "artifact root may not be a symlink", path=str(artifact_root))
    manifest_path = artifact_root / "evidence-manifest.json"
    actual_manifest_sha = sha256_file(manifest_path)
    if expected_sha256 is not None:
        require(actual_manifest_sha == expected_sha256, "E_MANIFEST_SHA256", "evidence manifest digest mismatch", path=str(manifest_path), expected=expected_sha256, actual=actual_manifest_sha)
    manifest = load_json(manifest_path)
    schemas = {expected_schema} if isinstance(expected_schema, str) else set(expected_schema)
    require(manifest.get("schema") in schemas, "E_MANIFEST_SCHEMA", "evidence manifest schema mismatch", actual=manifest.get("schema"), expected=sorted(schemas))
    require(manifest.get("status") == expected_status, "E_MANIFEST_STATUS", "evidence manifest is not sealed complete", actual=manifest.get("status"))
    if expected_authorization_id is not None:
        require(manifest.get("authorizationId") == expected_authorization_id, "E_MANIFEST_AUTHORIZATION", "manifest authorization mismatch")
    if expected_job_id is not None:
        require(manifest.get("jobId") == expected_job_id, "E_MANIFEST_JOB", "manifest job mismatch", expected=expected_job_id, actual=manifest.get("jobId"))
    require(manifest.get("physicalValidationClaimAllowed") is False, "E_PHYSICAL_CLAIM", "manifest improperly permits a physical-validation claim")
    files = manifest.get("files")
    require(isinstance(files, list), "E_MANIFEST_FILES", "manifest files must be an array")
    recorded: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(files):
        require(isinstance(item, dict), "E_MANIFEST_ENTRY", "manifest file entry must be an object", index=index)
        raw_path = item.get("path")
        path = _safe_relative_path(artifact_root, raw_path, f"files[{index}].path")
        require(raw_path != "evidence-manifest.json", "E_MANIFEST_SELF", "manifest may not list itself")
        require(raw_path not in recorded, "E_MANIFEST_DUPLICATE", "duplicate manifest path", path=raw_path)
        require(path.is_file(), "E_MANIFEST_FILE_MISSING", "manifest-listed file is missing", path=str(path))
        require(not path.is_symlink(), "E_SYMLINK", "manifest-listed file may not be a symlink", path=str(path))
        expected_length = _integer(item.get("byteLength"), f"files[{index}].byteLength")
        require(expected_length >= 0, "E_MANIFEST_LENGTH", "manifest byte length may not be negative", path=raw_path)
        actual_length = path.stat().st_size
        require(actual_length == expected_length, "E_MANIFEST_LENGTH", "manifest file length mismatch", path=raw_path, expected=expected_length, actual=actual_length)
        expected_digest = _hex_digest(item.get("sha256"), f"files[{index}].sha256")
        actual_digest = sha256_file(path)
        require(actual_digest == expected_digest, "E_MANIFEST_FILE_SHA256", "manifest file digest mismatch", path=raw_path, expected=expected_digest, actual=actual_digest)
        recorded[raw_path] = {"path": raw_path, "byteLength": actual_length, "sha256": actual_digest}
    if strict_inventory:
        actual: set[str] = set()
        for candidate in artifact_root.rglob("*"):
            require(not candidate.is_symlink(), "E_SYMLINK", "symlink is forbidden anywhere in an artifact", path=str(candidate))
            if candidate.is_file() and candidate != manifest_path:
                actual.add(candidate.relative_to(artifact_root).as_posix())
        require(actual == set(recorded), "E_MANIFEST_INVENTORY", "manifest inventory does not exactly match artifact files", missing=sorted(set(recorded) - actual), extra=sorted(actual - set(recorded)))
    return ({
        "path": str(manifest_path),
        "sha256": actual_manifest_sha,
        "fileCount": len(recorded),
        "allFileLengthsAndDigestsVerified": True,
        "exactInventoryMatched": strict_inventory,
    }, recorded)


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    require(path.is_file(), "E_NPZ_MISSING", "required NumPy archive is missing", path=str(path))
    require(not path.is_symlink(), "E_SYMLINK", "NumPy evidence may not be a symlink", path=str(path))
    try:
        with np.load(path, allow_pickle=False) as payload:
            return {name: np.asarray(payload[name]) for name in payload.files}
    except Exception as error:
        raise NotEvaluableError("E_NPZ_INVALID", "could not read NumPy evidence", path=str(path), error=str(error)) from error


def validate_state_file(path: Path, expected_cells: int, expected_sha256: str | None = None) -> dict[str, Any]:
    actual_sha = sha256_file(path)
    if expected_sha256 is not None:
        require(actual_sha == expected_sha256, "E_STATE_SHA256", "state archive digest mismatch", path=str(path), expected=expected_sha256, actual=actual_sha)
    values = _load_npz(path)
    require(set(values) == set(STATE_KEYS), "E_STATE_KEYS", "state archive keys mismatch", path=str(path), actual=sorted(values), expected=sorted(STATE_KEYS))
    state = values["state"]
    require(state.dtype == np.dtype("float64"), "E_STATE_DTYPE", "state array must be float64", path=str(path), actual=str(state.dtype))
    require(state.shape == (expected_cells, 3), "E_STATE_SHAPE", "state array shape mismatch", path=str(path), actual=list(state.shape), expected=[expected_cells, 3])
    require(np.isfinite(state).all(), "E_STATE_NONFINITE", "state contains non-finite values", path=str(path), count=int(state.size - np.isfinite(state).sum()))
    require(np.all(state[:, 0] >= 0), "E_STATE_NEGATIVE_DEPTH", "state contains negative water depth", path=str(path), count=int(np.sum(state[:, 0] < 0)))
    scalar_float_keys = ("elapsed_seconds", "expected_volume_m3", "maximum_cfl", "maximum_mass_error")
    for key in scalar_float_keys:
        value = values[key]
        require(value.shape == () and value.dtype == np.dtype("float64"), "E_STATE_SCALAR", "state scalar must be scalar float64", path=str(path), field=key, shape=list(value.shape), dtype=str(value.dtype))
        require(math.isfinite(float(value)), "E_STATE_NONFINITE", "state scalar is non-finite", path=str(path), field=key)
    step = values["step"]
    require(step.shape == () and step.dtype == np.dtype("int64"), "E_STATE_STEP", "state step must be scalar int64", path=str(path), shape=list(step.shape), dtype=str(step.dtype))
    require(int(step) >= 0, "E_STATE_STEP", "state step may not be negative", path=str(path))
    require(float(values["elapsed_seconds"]) >= 0, "E_STATE_ELAPSED", "state elapsed time may not be negative", path=str(path))
    require(float(values["maximum_cfl"]) >= 0 and float(values["maximum_mass_error"]) >= 0, "E_STATE_DIAGNOSTIC", "state diagnostic may not be negative", path=str(path))
    return {
        "path": str(path),
        "sha256": actual_sha,
        "shape": [expected_cells, 3],
        "elapsedSeconds": float(values["elapsed_seconds"]),
        "step": int(values["step"]),
        "expectedVolumeM3": float(values["expected_volume_m3"]),
        "maximumCfl": float(values["maximum_cfl"]),
        "maximumMassError": float(values["maximum_mass_error"]),
        "nonFiniteValueCount": 0,
        "negativeDepthCount": 0,
    }


def validate_fields_file(path: Path, expected_cells: int, expected_sha256: str | None = None) -> dict[str, Any]:
    actual_sha = sha256_file(path)
    if expected_sha256 is not None:
        require(actual_sha == expected_sha256, "E_FIELDS_SHA256", "field archive digest mismatch", path=str(path), expected=expected_sha256, actual=actual_sha)
    values = _load_npz(path)
    require(set(values) == set(FIELD_KEYS), "E_FIELDS_KEYS", "field archive keys mismatch", path=str(path), actual=sorted(values), expected=sorted(FIELD_KEYS))
    for key in FIELD_KEYS:
        array = values[key]
        require(array.dtype == np.dtype("float64"), "E_FIELDS_DTYPE", "field array must be float64", path=str(path), field=key, actual=str(array.dtype))
        require(array.shape == (expected_cells,), "E_FIELDS_SHAPE", "field array shape mismatch", path=str(path), field=key, actual=list(array.shape), expected=[expected_cells])
        require(np.isfinite(array).all(), "E_FIELDS_NONFINITE", "field array contains non-finite values", path=str(path), field=key, count=int(array.size - np.isfinite(array).sum()))
    require(np.all(values["waterDepthM"] >= 0), "E_FIELDS_NEGATIVE_DEPTH", "field archive contains negative water depth", path=str(path), count=int(np.sum(values["waterDepthM"] < 0)))
    return {
        "path": str(path),
        "sha256": actual_sha,
        "shapePerComponent": [expected_cells],
        "dtype": "float64",
        "nonFiniteValueCount": 0,
        "negativeDepthCount": 0,
    }


def load_fields(path: Path, expected_cells: int) -> dict[str, np.ndarray]:
    validate_fields_file(path, expected_cells)
    return _load_npz(path)


def _archives_equal(first: Path, second: Path, keys: Iterable[str]) -> bool:
    a = _load_npz(first)
    b = _load_npz(second)
    return all(key in a and key in b and np.array_equal(a[key], b[key]) for key in keys)


def _fields_match_state(fields_path: Path, state_path: Path) -> bool:
    fields = _load_npz(fields_path)
    state = _load_npz(state_path)["state"]
    depth = state[:, 0]
    u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    return np.array_equal(fields["waterDepthM"], depth) and np.array_equal(fields["velocityUms"], u) and np.array_equal(fields["velocityVms"], v)


@dataclass
class ValidatedSegment:
    job: dict[str, Any]
    root: Path
    report: dict[str, Any]
    receipt: dict[str, Any]
    manifest_sha256: str
    restart_path: Path
    restart_sha256: str
    snapshot_paths: dict[int, Path]
    summary: dict[str, Any]


def validate_run_metadata(metadata: Mapping[str, Any], jobs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    require(metadata.get("schema") == "onga-stage20-barrage-holdout-recovery-run-metadata-v1", "E_RUN_METADATA_SCHEMA", "run metadata schema mismatch")
    run_id = _integer(metadata.get("runId"), "runId")
    require(run_id > 0, "E_RUN_ID", "run ID must be positive")
    attempt = _integer(metadata.get("runAttempt"), "runAttempt")
    require(attempt == 1, "E_RUN_ATTEMPT", "rerun evidence is forbidden", actual=attempt)
    head_sha = _hex_digest(metadata.get("headSha"), "headSha", length=40)
    require(metadata.get("status") == "completed", "E_RUN_NOT_COMPLETE", "recovery run is not complete", status=metadata.get("status"))
    require(metadata.get("conclusion") == "success", "E_RUN_UNSUCCESSFUL", "recovery run did not conclude successfully", conclusion=metadata.get("conclusion"))
    conclusions = metadata.get("jobConclusions")
    require(isinstance(conclusions, dict), "E_RUN_JOBS", "run metadata jobConclusions must be an object")
    required_jobs = {"preflight", "authorize"}
    required_jobs.update(str(job["id"]).removeprefix("barrage-").replace("-", "_") for job in jobs)
    require(set(conclusions) == required_jobs, "E_RUN_JOBS", "run job inventory mismatch", expected=sorted(required_jobs), actual=sorted(conclusions))
    require(all(value == "success" for value in conclusions.values()), "E_RUN_JOB_FAILURE", "one or more recovery jobs did not succeed", jobConclusions=conclusions)
    for field in ("createdAtUtc", "completedAtUtc", "url"):
        require(isinstance(metadata.get(field), str) and metadata.get(field), "E_RUN_METADATA_FIELD", "run metadata field is required", field=field)
    expected_url = f"https://github.com/Fujisawa-lab-inside/fishing/actions/runs/{run_id}"
    require(metadata["url"] == expected_url, "E_RUN_URL", "run metadata URL does not identify the contracted repository and run", expected=expected_url, actual=metadata["url"])
    try:
        created = dt.datetime.fromisoformat(metadata["createdAtUtc"].replace("Z", "+00:00"))
        completed = dt.datetime.fromisoformat(metadata["completedAtUtc"].replace("Z", "+00:00"))
    except ValueError as error:
        raise NotEvaluableError("E_RUN_TIMESTAMPS", "run metadata timestamps are invalid", error=str(error)) from error
    require(created.tzinfo is not None and completed.tzinfo is not None and created <= completed, "E_RUN_TIMESTAMPS", "run metadata timestamp order or timezone is invalid")
    return {
        "runId": run_id,
        "runAttempt": attempt,
        "headSha": head_sha,
        "status": "completed",
        "conclusion": "success",
        "url": metadata["url"],
        "createdAtUtc": metadata["createdAtUtc"],
        "completedAtUtc": metadata["completedAtUtc"],
        "jobConclusions": dict(conclusions),
    }


def validate_recovery_segment(
    artifact_root: Path,
    job: dict[str, Any],
    contract: Mapping[str, Any],
    authorization: Mapping[str, Any],
    run: Mapping[str, Any],
    *,
    authorization_sha256: str,
    contract_sha256: str,
) -> ValidatedSegment:
    job_id = job["id"]
    manifest_summary, manifest_files = validate_manifest(
        artifact_root,
        expected_schema="onga-stage20-barrage-holdout-recovery-segment-evidence-v1",
        expected_authorization_id=authorization["authorizationId"],
        expected_job_id=job_id,
        strict_inventory=True,
    )
    required = {"progress.json", "restart-final.npz", "segment-final-fields.npz", "segment-report.json", "execution-receipt.json"}
    require(required <= set(manifest_files), "E_ARTIFACT_REQUIRED_FILES", "artifact lacks required sealed files", jobId=job_id, missing=sorted(required - set(manifest_files)))
    report = load_json(artifact_root / "segment-report.json")
    receipt = load_json(artifact_root / "execution-receipt.json")
    progress = load_json(artifact_root / "progress.json")
    require(report.get("schema") == "onga-stage20-barrage-holdout-recovery-segment-report-v1", "E_REPORT_SCHEMA", "segment report schema mismatch", jobId=job_id)
    require(report.get("status") == "passed_numerical_checks_not_physical_validation", "E_REPORT_STATUS", "segment report status mismatch", jobId=job_id)
    require(report.get("authorizationId") == authorization["authorizationId"], "E_REPORT_AUTHORIZATION", "segment report authorization mismatch", jobId=job_id)
    platform_record = report.get("platform")
    require(isinstance(platform_record, dict), "E_REPORT_PLATFORM", "segment platform record is missing", jobId=job_id)
    require(
        platform_record.get("system") == contract["resource"]["requiredPlatform"].split()[0]
        and platform_record.get("machine") == "x86_64"
        and isinstance(platform_record.get("python"), str)
        and platform_record["python"].startswith("3.13."),
        "E_REPORT_PLATFORM",
        "segment did not run on the contracted Linux x86_64 Python 3.13 platform",
        jobId=job_id,
        actual=platform_record,
    )
    report_run = report.get("run")
    require(isinstance(report_run, dict), "E_REPORT_RUN", "segment report run is missing", jobId=job_id)
    for key in ("jobId", "basisId", "modelHourStart", "modelHourEnd"):
        require(report_run.get(key) == job[key if key != "jobId" else "id"], "E_REPORT_IDENTITY", "segment report identity mismatch", jobId=job_id, field=key, expected=job[key if key != "jobId" else "id"], actual=report_run.get(key))
    simulated = _finite_number(report_run.get("simulatedSeconds"), f"{job_id}.simulatedSeconds")
    wall = _finite_number(report_run.get("wallSeconds"), f"{job_id}.wallSeconds")
    start_step = _integer(report_run.get("startStep"), f"{job_id}.startStep")
    end_step = _integer(report_run.get("endStep"), f"{job_id}.endStep")
    require(simulated >= float(job["targetPhysicalSeconds"]), "E_SEGMENT_INCOMPLETE", "segment did not reach its target simulated time", jobId=job_id, target=job["targetPhysicalSeconds"], actual=simulated)
    require(0 <= wall <= float(job["maximumNumericalWallSeconds"]), "E_SEGMENT_WALL", "segment exceeded its numerical wall limit", jobId=job_id, limit=job["maximumNumericalWallSeconds"], actual=wall)
    require(0 <= start_step < end_step, "E_SEGMENT_STEPS", "segment step range is invalid", jobId=job_id, startStep=start_step, endStep=end_step)
    diagnostics = report.get("diagnostics")
    require(isinstance(diagnostics, dict), "E_DIAGNOSTICS", "segment diagnostics are missing", jobId=job_id)
    maximum_cfl = _finite_number(diagnostics.get("maximumCfl"), f"{job_id}.maximumCfl")
    maximum_mass = _finite_number(diagnostics.get("maximumRelativeMassBalanceError"), f"{job_id}.maximumRelativeMassBalanceError")
    input_mass = _finite_number(diagnostics.get("inputRestartRelativeMassError"), f"{job_id}.inputRestartRelativeMassError")
    maximum_speed = _finite_number(diagnostics.get("maximumSpeedMPS"), f"{job_id}.maximumSpeedMPS")
    require(0 <= maximum_cfl <= float(contract["acceptance"]["maximumCfl"]), "E_CFL", "segment CFL threshold exceeded", jobId=job_id, actual=maximum_cfl)
    require(0 <= maximum_mass <= float(contract["acceptance"]["maximumRelativeMassBalanceError"]), "E_MASS", "segment mass-balance threshold exceeded", jobId=job_id, actual=maximum_mass)
    require(0 <= input_mass <= float(contract["acceptance"]["maximumRelativeMassBalanceError"]), "E_INPUT_MASS", "segment input restart mass threshold exceeded", jobId=job_id, actual=input_mass)
    require(maximum_speed >= 0, "E_SPEED", "segment maximum speed may not be negative", jobId=job_id)
    require(diagnostics.get("nonFiniteValueCount") == 0 and diagnostics.get("negativeDepthCount") == 0, "E_DIAGNOSTIC_COUNTS", "segment report records invalid numerical values", jobId=job_id)
    safeguards = report.get("safeguards")
    require(isinstance(safeguards, dict), "E_REPORT_SAFEGUARDS", "segment report safeguards are missing", jobId=job_id)
    require(safeguards.get("automaticRetryAllowed") is False and safeguards.get("physicalValidationClaimAllowed") is False and safeguards.get("publicSimulatorConnected") is False, "E_REPORT_SAFEGUARDS", "segment report safeguard mismatch", jobId=job_id)
    report_input = report.get("input")
    require(isinstance(report_input, dict) and report_input.get("jobId") == job["input"]["jobId"], "E_REPORT_INPUT", "segment input identity mismatch", jobId=job_id)
    input_restart_sha = _hex_digest(report_input.get("restartSha256"), f"{job_id}.input.restartSha256")
    input_manifest_sha = _hex_digest(report_input.get("evidenceManifestSha256"), f"{job_id}.input.evidenceManifestSha256")
    if job["input"]["kind"] == "retained_sealed_restart":
        require(input_restart_sha == job["input"]["restartSha256"], "E_RETAINED_RESTART", "first recovery segment does not use the pinned retained restart", jobId=job_id)
        require(input_manifest_sha == job["input"]["evidenceManifestSha256"], "E_RETAINED_MANIFEST", "first recovery segment does not use the pinned retained manifest", jobId=job_id)
    outputs = report.get("outputs")
    require(isinstance(outputs, dict), "E_REPORT_OUTPUTS", "segment outputs are missing", jobId=job_id)
    restart_path = _safe_relative_path(artifact_root, outputs.get("restart"), f"{job_id}.outputs.restart")
    fields_path = _safe_relative_path(artifact_root, outputs.get("fields"), f"{job_id}.outputs.fields")
    require(outputs.get("restart") == "restart-final.npz" and outputs.get("fields") == "segment-final-fields.npz", "E_REPORT_OUTPUT_PATH", "segment final output path changed", jobId=job_id)
    restart_sha = _hex_digest(outputs.get("restartSha256"), f"{job_id}.outputs.restartSha256")
    fields_sha = _hex_digest(outputs.get("fieldsSha256"), f"{job_id}.outputs.fieldsSha256")
    cell_count = int(contract["mesh"]["cellCount"])
    restart = validate_state_file(restart_path, cell_count, restart_sha)
    fields = validate_fields_file(fields_path, cell_count, fields_sha)
    require(restart["elapsedSeconds"] == simulated and restart["step"] == end_step, "E_FINAL_STATE_METADATA", "final restart metadata does not match report", jobId=job_id)
    require(restart["maximumCfl"] == maximum_cfl and restart["maximumMassError"] == maximum_mass, "E_FINAL_STATE_DIAGNOSTICS", "final restart diagnostics do not match report", jobId=job_id)
    require(_fields_match_state(fields_path, restart_path), "E_FIELDS_STATE_MISMATCH", "final fields do not exactly match the restart state", jobId=job_id)
    state = _load_npz(restart_path)["state"]
    final_speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(state[:, 0], 1e-12)
    require(maximum_speed + 1e-12 >= float(final_speed.max(initial=0.0)), "E_SPEED_DIAGNOSTIC", "reported maximum speed is below final-state speed", jobId=job_id)
    checkpoint_records = outputs.get("checkpoints")
    snapshot_records = outputs.get("snapshots")
    require(isinstance(checkpoint_records, list) and isinstance(snapshot_records, list), "E_REPORT_OUTPUT_RECORDS", "checkpoint or snapshot records are invalid", jobId=job_id)
    interval = float(contract["acceptance"]["checkpointIntervalPhysicalSeconds"])
    expected_checkpoint_count = int(round(float(job["targetPhysicalSeconds"]) / interval))
    require(len(checkpoint_records) == expected_checkpoint_count, "E_CHECKPOINT_COUNT", "checkpoint count mismatch", jobId=job_id, expected=expected_checkpoint_count, actual=len(checkpoint_records))
    previous_step = start_step
    previous_elapsed = -1.0
    checkpoint_paths: set[str] = set()
    checkpoint_summaries = []
    for ordinal, record in enumerate(checkpoint_records, start=1):
        require(isinstance(record, dict), "E_CHECKPOINT_RECORD", "checkpoint record must be an object", jobId=job_id, ordinal=ordinal)
        raw_path = record.get("path")
        require(raw_path not in checkpoint_paths, "E_CHECKPOINT_DUPLICATE", "duplicate checkpoint path", jobId=job_id, path=raw_path)
        checkpoint_paths.add(raw_path)
        path = _safe_relative_path(artifact_root, raw_path, f"{job_id}.checkpoints[{ordinal - 1}].path")
        digest = _hex_digest(record.get("sha256"), f"{job_id}.checkpoints[{ordinal - 1}].sha256")
        state_summary = validate_state_file(path, cell_count, digest)
        record_elapsed = _finite_number(record.get("elapsedSeconds"), f"{job_id}.checkpoints[{ordinal - 1}].elapsedSeconds")
        record_step = _integer(record.get("step"), f"{job_id}.checkpoints[{ordinal - 1}].step")
        require(state_summary["elapsedSeconds"] == record_elapsed and state_summary["step"] == record_step, "E_CHECKPOINT_METADATA", "checkpoint metadata does not match its report record", jobId=job_id, ordinal=ordinal)
        require(record_elapsed >= ordinal * interval and record_elapsed > previous_elapsed, "E_CHECKPOINT_ELAPSED", "checkpoint elapsed times are invalid", jobId=job_id, ordinal=ordinal)
        require(record_step > previous_step, "E_CHECKPOINT_STEPS", "checkpoint steps are not strictly increasing", jobId=job_id, ordinal=ordinal)
        previous_elapsed = record_elapsed
        previous_step = record_step
        checkpoint_summaries.append(state_summary)
    require(
        _archives_equal(
            _safe_relative_path(artifact_root, checkpoint_records[-1]["path"], "finalCheckpoint"),
            restart_path,
            STATE_KEYS,
        ),
        "E_FINAL_CHECKPOINT",
        "final checkpoint arrays do not exactly match final restart",
        jobId=job_id,
    )
    require([record.get("modelHour") for record in snapshot_records] == list(job["snapshotModelHours"]), "E_SNAPSHOT_HOURS", "segment snapshot hours mismatch", jobId=job_id, expected=job["snapshotModelHours"], actual=[record.get("modelHour") for record in snapshot_records])
    snapshot_paths: dict[int, Path] = {}
    snapshot_summaries = []
    for index, record in enumerate(snapshot_records):
        require(isinstance(record, dict), "E_SNAPSHOT_RECORD", "snapshot record must be an object", jobId=job_id, index=index)
        hour = _integer(record.get("modelHour"), f"{job_id}.snapshots[{index}].modelHour")
        require(hour not in snapshot_paths, "E_SNAPSHOT_DUPLICATE", "duplicate snapshot hour in a segment", jobId=job_id, modelHour=hour)
        path = _safe_relative_path(artifact_root, record.get("path"), f"{job_id}.snapshots[{index}].path")
        digest = _hex_digest(record.get("sha256"), f"{job_id}.snapshots[{index}].sha256")
        summary = validate_fields_file(path, cell_count, digest)
        summary["modelHour"] = hour
        snapshot_paths[hour] = path
        snapshot_summaries.append(summary)
    if job["modelHourEnd"] in snapshot_paths:
        require(_archives_equal(snapshot_paths[job["modelHourEnd"]], fields_path, FIELD_KEYS), "E_FINAL_SNAPSHOT", "final-hour snapshot does not exactly match segment final fields", jobId=job_id)
    require(receipt.get("schema") == "onga-stage20-barrage-holdout-recovery-segment-receipt-v1", "E_RECEIPT_SCHEMA", "execution receipt schema mismatch", jobId=job_id)
    require(receipt.get("authorizationId") == authorization["authorizationId"], "E_RECEIPT_AUTHORIZATION", "execution receipt authorization mismatch", jobId=job_id)
    require(receipt.get("authorizationSha256") == authorization_sha256, "E_RECEIPT_AUTHORIZATION_SHA256", "execution receipt authorization digest mismatch", jobId=job_id)
    require(receipt.get("executionContractSha256") == contract_sha256, "E_RECEIPT_CONTRACT_SHA256", "execution receipt contract digest mismatch", jobId=job_id)
    require(receipt.get("decisionImageSha256") == authorization["decisionImage"]["sha256"], "E_RECEIPT_DECISION_SHA256", "execution receipt decision-image digest mismatch", jobId=job_id)
    require(receipt.get("jobId") == job_id and receipt.get("predecessorJobId") == job["input"]["jobId"], "E_RECEIPT_IDENTITY", "execution receipt job identity mismatch", jobId=job_id)
    require(receipt.get("inputRestartSha256") == input_restart_sha and receipt.get("inputEvidenceManifestSha256") == input_manifest_sha, "E_RECEIPT_INPUT", "execution receipt input chain does not match report", jobId=job_id)
    require(receipt.get("githubRunId") == str(run["runId"]), "E_RECEIPT_RUN_ID", "execution receipt run ID mismatch", jobId=job_id)
    require(receipt.get("githubSha") == run["headSha"], "E_RECEIPT_HEAD_SHA", "execution receipt commit mismatch", jobId=job_id)
    require(receipt.get("automaticRetryAllowed") is False, "E_RECEIPT_RETRY", "execution receipt permits automatic retry", jobId=job_id)
    require(progress.get("schema") == "onga-stage20-barrage-holdout-recovery-progress-v1" and progress.get("status") == "complete", "E_PROGRESS_STATUS", "segment progress is not complete", jobId=job_id)
    require(progress.get("authorizationId") == authorization["authorizationId"] and progress.get("jobId") == job_id, "E_PROGRESS_IDENTITY", "segment progress identity mismatch", jobId=job_id)
    require(progress.get("simulatedSeconds") == simulated and progress.get("checkpoints") == checkpoint_records and progress.get("snapshots") == snapshot_records, "E_PROGRESS_CONTENT", "segment progress does not match final report", jobId=job_id)
    progress_wall = _finite_number(progress.get("wallSeconds"), f"{job_id}.progress.wallSeconds")
    require(0 <= progress_wall <= wall, "E_PROGRESS_WALL", "segment progress wall time is invalid", jobId=job_id)
    summary = {
        "jobId": job_id,
        "basisId": job["basisId"],
        "modelHourStart": job["modelHourStart"],
        "modelHourEnd": job["modelHourEnd"],
        "startStep": start_step,
        "endStep": end_step,
        "simulatedSeconds": simulated,
        "wallSeconds": wall,
        "diagnostics": dict(diagnostics),
        "checkpointCount": len(checkpoint_summaries),
        "snapshotHours": sorted(snapshot_paths),
        "restartSha256": restart_sha,
        "fieldsSha256": fields["sha256"],
        "manifest": manifest_summary,
        "finalCheckpointMatchesRestartExactly": True,
        "finalFieldsMatchRestartExactly": True,
        "finalSnapshotMatchesFieldsExactly": True if job["modelHourEnd"] in snapshot_paths else None,
    }
    return ValidatedSegment(job, artifact_root, report, receipt, manifest_summary["sha256"], restart_path, restart_sha, snapshot_paths, summary)


def validate_restart_chain(segments: Iterable[ValidatedSegment]) -> list[dict[str, Any]]:
    segments = list(segments)
    by_id = {segment.job["id"]: segment for segment in segments}
    links: list[dict[str, Any]] = []
    for segment in segments:
        job = segment.job
        input_record = segment.report["input"]
        receipt = segment.receipt
        if job["input"]["kind"] == "retained_sealed_restart":
            expected_restart = job["input"]["restartSha256"]
            expected_manifest = job["input"]["evidenceManifestSha256"]
            require(input_record["restartSha256"] == expected_restart == receipt["inputRestartSha256"], "E_CHAIN_RETAINED_RESTART", "retained restart chain mismatch", jobId=job["id"])
            require(input_record["evidenceManifestSha256"] == expected_manifest == receipt["inputEvidenceManifestSha256"], "E_CHAIN_RETAINED_MANIFEST", "retained manifest chain mismatch", jobId=job["id"])
            links.append({"jobId": job["id"], "inputKind": "retained_sealed_restart", "predecessorJobId": job["input"]["jobId"], "restartSha256": expected_restart, "evidenceManifestSha256": expected_manifest, "passed": True})
            continue
        predecessor_id = job["input"]["jobId"]
        require(predecessor_id in by_id, "E_CHAIN_PREDECESSOR", "recovery predecessor artifact is absent", jobId=job["id"], predecessorJobId=predecessor_id)
        predecessor = by_id[predecessor_id]
        require(predecessor.job["basisId"] == job["basisId"], "E_CHAIN_BASIS", "restart chain crosses basis scenarios", jobId=job["id"])
        require(predecessor.job["modelHourEnd"] == job["modelHourStart"], "E_CHAIN_HOUR", "restart chain model hours are discontinuous", jobId=job["id"])
        require(predecessor.report["run"]["endStep"] == segment.report["run"]["startStep"], "E_CHAIN_STEP", "restart chain step is discontinuous", jobId=job["id"])
        require(predecessor.restart_sha256 == input_record["restartSha256"] == receipt["inputRestartSha256"], "E_CHAIN_RESTART_SHA256", "restart chain digest mismatch", jobId=job["id"])
        require(predecessor.manifest_sha256 == input_record["evidenceManifestSha256"] == receipt["inputEvidenceManifestSha256"], "E_CHAIN_MANIFEST_SHA256", "evidence-manifest chain digest mismatch", jobId=job["id"])
        links.append({"jobId": job["id"], "inputKind": "recovery_predecessor", "predecessorJobId": predecessor_id, "restartSha256": predecessor.restart_sha256, "evidenceManifestSha256": predecessor.manifest_sha256, "predecessorEndStep": predecessor.report["run"]["endStep"], "successorStartStep": segment.report["run"]["startStep"], "passed": True})
    return links


def validate_region_masks(repo_root: Path, contract: Mapping[str, Any]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    record = contract["regionalMasks"]
    manifest_path = _safe_relative_path(repo_root, record["manifest"], "regionalMasks.manifest")
    binary_path = _safe_relative_path(repo_root, record["binary"], "regionalMasks.binary")
    manifest_sha = sha256_file(manifest_path)
    binary_sha = sha256_file(binary_path)
    require(manifest_sha == record["manifestSha256"], "E_MASK_MANIFEST_SHA256", "regional mask manifest digest mismatch")
    require(binary_sha == record["binarySha256"], "E_MASK_BINARY_SHA256", "regional mask binary digest mismatch")
    manifest = load_json(manifest_path)
    require(manifest.get("schema") == "onga-stage20-barrage-holdout-region-masks-v1" and manifest.get("status") == "digest_locked_before_recovery_execution", "E_MASK_MANIFEST", "regional masks are not the locked recovery masks")
    binary_record = manifest.get("binary")
    require(isinstance(binary_record, dict) and binary_record.get("path") == record["binary"] and binary_record.get("sha256") == binary_sha, "E_MASK_BINARY_RECORD", "regional mask binary record mismatch")
    payload = binary_path.read_bytes()
    require(len(payload) == binary_record.get("byteLength"), "E_MASK_BINARY_LENGTH", "regional mask binary length mismatch")
    views = manifest.get("views")
    require(isinstance(views, list) and [view.get("id") for view in views] == list(EXPECTED_REGION_IDS), "E_MASK_VIEWS", "regional mask view inventory mismatch")
    require(views[0].get("legacyAlias") == "full_estuary", "E_MASK_ALIAS", "full-estuary legacy alias is missing")
    masks: dict[str, np.ndarray] = {}
    summaries = []
    expected_cells = int(contract["mesh"]["cellCount"])
    for view in views:
        region_id = view["id"]
        start = _integer(view.get("byteOffset"), f"{region_id}.byteOffset")
        length = _integer(view.get("byteLength"), f"{region_id}.byteLength")
        count = _integer(view.get("cellCount"), f"{region_id}.cellCount")
        require(view.get("dtype") == "int32-le", "E_MASK_DTYPE", "regional mask dtype mismatch", regionId=region_id)
        require(start >= 0 and length == count * 4 and start + length <= len(payload), "E_MASK_RANGE", "regional mask byte range is invalid", regionId=region_id)
        chunk = payload[start : start + length]
        require(sha256_bytes(chunk) == view.get("sha256"), "E_MASK_SLICE_SHA256", "regional mask slice digest mismatch", regionId=region_id)
        ids = np.frombuffer(chunk, dtype="<i4").astype(np.int64, copy=True)
        require(ids.shape == (count,), "E_MASK_COUNT", "regional mask cell count mismatch", regionId=region_id)
        require(count > 0 and np.array_equal(ids, np.unique(ids)), "E_MASK_UNIQUE", "regional mask IDs must be sorted and unique", regionId=region_id)
        require(int(ids[0]) >= 0 and int(ids[-1]) < expected_cells, "E_MASK_CELL_RANGE", "regional mask cell ID is outside the mesh", regionId=region_id)
        masks[region_id] = ids
        summaries.append({"id": region_id, "cellCount": count, "sha256": view["sha256"]})
    require(np.array_equal(masks["estuary"], np.arange(expected_cells, dtype=np.int64)), "E_MASK_ESTUARY", "estuary mask is not the full mesh")
    return masks, {"manifest": str(manifest_path), "manifestSha256": manifest_sha, "binary": str(binary_path), "binarySha256": binary_sha, "views": summaries}


def validate_static_inputs(repo_root: Path, contract_path: Path) -> dict[str, Any]:
    contract_file = contract_path if contract_path.is_absolute() else repo_root / contract_path
    contract = load_json(contract_file)
    contract_sha = sha256_file(contract_file)
    require(contract.get("schema") == "onga-stage20-barrage-holdout-recovery-contract-v1", "E_CONTRACT_SCHEMA", "recovery contract schema mismatch")
    require(contract.get("status") == "sealed_inactive_execution_requires_separate_visual_authorization" and contract.get("executionAuthorized") is False, "E_CONTRACT_STATUS", "recovery contract must remain sealed and non-self-authorizing")
    for key in ("sourceContract", "stoppedResult", "stoppedAnalysis"):
        _verify_pinned_file(repo_root, contract[key], key)
    source_contract = load_json(repo_root / contract["sourceContract"]["path"])
    require(contract.get("basisScenarios") == source_contract.get("basisScenarios") and contract.get("inputs") == source_contract.get("inputs"), "E_CONTRACT_PHYSICS", "recovery basis physics or inputs changed from the original holdout")
    mesh_manifest_path = _safe_relative_path(repo_root, contract["mesh"]["manifest"], "mesh.manifest")
    mesh_manifest = load_json(mesh_manifest_path)
    mesh_binary_url = mesh_manifest["binary"]["url"]
    require(isinstance(mesh_binary_url, str), "E_MESH_PATH", "mesh binary URL must be a local string")
    mesh_binary = _safe_relative_path(mesh_manifest_path.parent, mesh_binary_url.removeprefix("./"), "mesh.binary")
    require(sha256_file(mesh_binary) == contract["mesh"]["sha256"] == mesh_manifest["binary"]["sha256"], "E_MESH_SHA256", "mesh binary digest mismatch")
    require(mesh_manifest["counts"]["cells"] == contract["mesh"]["cellCount"] and mesh_manifest["counts"]["barrageFaces"] == contract["mesh"]["barrageFaces"], "E_MESH_COUNTS", "mesh count mismatch")
    for path_key, digest_key, label in (("path", "sha256", "kernel"),):
        require(sha256_file(repo_root / contract[label][path_key]) == contract[label][digest_key], "E_PINNED_SHA256", "pinned executable digest mismatch", label=label)
    require(sha256_file(repo_root / contract["runner"]["path"]) == contract["runner"]["sha256"], "E_PINNED_SHA256", "recovery runner digest mismatch")
    require(sha256_file(repo_root / contract["runner"]["workflowPath"]) == contract["runner"]["workflowSha256"], "E_PINNED_SHA256", "recovery workflow digest mismatch")
    require(sha256_file(repo_root / contract["inputs"]["tideCandidate"]) == contract["inputs"]["tideCandidateSha256"], "E_PINNED_SHA256", "tide input digest mismatch")
    require(sha256_file(repo_root / contract["inputs"]["waterMask"]) == contract["inputs"]["waterMaskSha256"], "E_PINNED_SHA256", "water-mask input digest mismatch")
    require(sha256_file(repo_root / contract["regionalMasks"]["builder"]) == contract["regionalMasks"]["builderSha256"], "E_PINNED_SHA256", "regional-mask builder digest mismatch")
    masks, mask_summary = validate_region_masks(repo_root, contract)
    del masks
    for retained in contract["retainedInputs"]:
        directory = repo_root / retained["directory"]
        require(sha256_file(directory / "restart-final.npz") == retained["restartSha256"], "E_RETAINED_RESTART", "retained restart digest mismatch", jobId=retained["jobId"])
        require(sha256_file(directory / "segment-report.json") == retained["reportSha256"], "E_RETAINED_REPORT", "retained report digest mismatch", jobId=retained["jobId"])
        validate_manifest(directory, expected_schema="onga-stage20-barrage-holdout-segment-evidence-v1", expected_job_id=retained["jobId"], expected_sha256=retained["evidenceManifestSha256"], strict_inventory=True)
    control = contract["control"]
    authorization_path = repo_root / control["authorizationPath"]
    gate_path = repo_root / control["gatePath"]
    activation_path = repo_root / control["activationPath"]
    authorization = load_json(authorization_path)
    gate = load_json(gate_path)
    activation = load_json(activation_path)
    authorization_sha = sha256_file(authorization_path)
    gate_sha = sha256_file(gate_path)
    require(authorization.get("schema") == "onga-stage20-barrage-holdout-recovery-authorization-v1" and authorization.get("authorized") is True and authorization.get("oneTime") is True, "E_AUTHORIZATION", "recovery authorization is invalid")
    try:
        contract_label = contract_file.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise NotEvaluableError("E_CONTRACT_PATH", "recovery contract must be inside the repository", path=str(contract_file)) from error
    require(authorization["executionContract"]["path"] == contract_label and authorization["executionContract"]["sha256"] == contract_sha, "E_AUTHORIZATION_CONTRACT", "authorization does not pin this recovery contract")
    decision_image = repo_root / authorization["decisionImage"]["path"]
    require(sha256_file(decision_image) == authorization["decisionImage"]["sha256"], "E_AUTHORIZATION_DECISION", "authorization decision-image digest mismatch")
    require(authorization.get("jobIds") == [job["id"] for job in contract["jobs"]], "E_AUTHORIZATION_JOBS", "authorized job scope mismatch")
    require(authorization.get("automaticRetryAllowed") is False and authorization.get("additionalRunAllowed") is False, "E_AUTHORIZATION_RETRY", "authorization improperly permits a retry or additional run")
    required_postrun = {"download_exact_run_artifacts", "verify_sha256_and_numerical_stability", "assemble_ten_endpoint_snapshots", "compare_direct_50_percent_against_50_50_endpoint_interpolation"}
    require(required_postrun <= set(authorization.get("postRunActionsAuthorized", [])), "E_AUTHORIZATION_POSTRUN", "required post-run actions are not authorized")
    require(gate.get("schema") == "onga-stage20-barrage-holdout-recovery-gate-v1" and gate.get("state") == "active_one_time", "E_GATE", "recovery gate is invalid")
    require(gate.get("authorizationId") == authorization["authorizationId"] and gate.get("authorizationSha256") == authorization_sha and gate.get("executionContractSha256") == contract_sha, "E_GATE_CHAIN", "recovery gate digest chain mismatch")
    require(activation.get("schema") == "onga-stage20-barrage-holdout-recovery-activation-v1" and activation.get("state") == "activate_exactly_once", "E_ACTIVATION", "recovery activation is invalid")
    require(activation.get("authorizationId") == authorization["authorizationId"] and activation.get("authorizationSha256") == authorization_sha and activation.get("gateSha256") == gate_sha and activation.get("executionContractSha256") == contract_sha, "E_ACTIVATION_CHAIN", "recovery activation digest chain mismatch")
    require(activation.get("preparedCommit") == authorization["reviewedCodeCommit"], "E_ACTIVATION_COMMIT", "activation prepared commit mismatch")
    require(all(contract["control"][key] is False for key in ("authorizationPresent", "gatePresent", "activationPresent")), "E_CONTRACT_CONTROL", "sealed contract control flags changed")
    for source in (contract["safeguards"], gate, activation):
        for key in ("automaticRetryAllowed", "additionalRunAllowed", "publicSimulatorConnectionAllowed", "mainMergeAllowed"):
            if key in source:
                require(source[key] is False, "E_SAFEGUARD", "recovery safeguard was enabled", field=key)
    return {
        "contract": contract,
        "contractPath": contract_file,
        "contractSha256": contract_sha,
        "authorization": authorization,
        "authorizationPath": authorization_path,
        "authorizationSha256": authorization_sha,
        "gateSha256": gate_sha,
        "activationSha256": sha256_file(activation_path),
        "regionalMasks": mask_summary,
    }


def collect_endpoint_snapshots(
    repo_root: Path,
    contract: Mapping[str, Any],
    segments: Iterable[ValidatedSegment],
) -> tuple[dict[tuple[str, int], Path], list[dict[str, Any]]]:
    endpoints: dict[tuple[str, int], Path] = {}
    records: list[dict[str, Any]] = []
    cell_count = int(contract["mesh"]["cellCount"])
    for segment in segments:
        basis = segment.job["basisId"]
        for hour, path in segment.snapshot_paths.items():
            key = (basis, hour)
            require(key not in endpoints, "E_ENDPOINT_DUPLICATE", "duplicate endpoint snapshot", basisId=basis, modelHour=hour)
            endpoints[key] = path
            records.append({"basisId": basis, "modelHour": hour, "source": "recovery", **validate_fields_file(path, cell_count)})
    retained = next((item for item in contract["retainedInputs"] if item["basisId"] == "barrage-open" and item["modelHour"] == -12), None)
    require(retained is not None, "E_ENDPOINT_RETAINED", "retained open minus-12 input is absent from the contract")
    retained_root = repo_root / retained["directory"]
    report = load_json(retained_root / "segment-report.json")
    snapshots = report.get("outputs", {}).get("snapshots", [])
    matches = [item for item in snapshots if item.get("modelHour") == -12]
    require(len(matches) == 1, "E_ENDPOINT_RETAINED", "retained open minus-12 snapshot record is missing or duplicated")
    record = matches[0]
    path = _safe_relative_path(retained_root, record.get("path"), "retainedOpenMinus12.path")
    digest = retained.get("sealedSnapshotMinus12Sha256")
    require(record.get("sha256") == digest, "E_ENDPOINT_RETAINED", "retained open minus-12 report digest mismatch")
    summary = validate_fields_file(path, cell_count, digest)
    key = ("barrage-open", -12)
    require(key not in endpoints, "E_ENDPOINT_DUPLICATE", "retained endpoint duplicates recovery output")
    endpoints[key] = path
    records.append({"basisId": key[0], "modelHour": key[1], "source": "retained_sealed_original_holdout", **summary})
    expected = {(basis, hour) for basis in EXPECTED_BASES for hour in EXPECTED_HOURS}
    require(set(endpoints) == expected, "E_ENDPOINT_SET", "endpoint snapshot basis/hour set mismatch", expected=sorted([list(item) for item in expected]), actual=sorted([list(item) for item in endpoints]))
    records.sort(key=lambda item: (item["basisId"], item["modelHour"]))
    return endpoints, records


def validate_heldout_reference(repo_root: Path, contract: Mapping[str, Any]) -> tuple[dict[int, Path], dict[str, Any]]:
    stopped_analysis = load_json(repo_root / contract["stoppedAnalysis"]["path"])
    reference = stopped_analysis.get("heldOutReference")
    require(isinstance(reference, dict), "E_REFERENCE_RECORD", "held-out reference record is missing")
    reference_root = _safe_relative_path(repo_root, reference.get("root"), "heldOutReference.root")
    manifest_summary, manifest_files = validate_manifest(
        reference_root,
        expected_schema="onga-stage20-reference-s02-evidence-v1",
        expected_sha256=reference.get("evidenceManifestSha256"),
        strict_inventory=False,
    )
    require(manifest_summary["fileCount"] == reference.get("evidenceFileCount"), "E_REFERENCE_MANIFEST_COUNT", "held-out reference manifest file count mismatch")
    snapshots = reference.get("snapshots")
    require(isinstance(snapshots, list) and [item.get("modelHour") for item in snapshots] == list(EXPECTED_HOURS), "E_REFERENCE_HOURS", "held-out reference hours mismatch")
    result: dict[int, Path] = {}
    records = []
    cell_count = int(contract["mesh"]["cellCount"])
    for index, item in enumerate(snapshots):
        hour = _integer(item.get("modelHour"), f"heldOutReference.snapshots[{index}].modelHour")
        path = _safe_relative_path(repo_root, item.get("path"), f"heldOutReference.snapshots[{index}].path")
        require(path.resolve().is_relative_to(reference_root.resolve()), "E_REFERENCE_PATH", "held-out snapshot is outside the reference root", modelHour=hour)
        digest = _hex_digest(item.get("sha256"), f"heldOutReference.snapshots[{index}].sha256")
        relative = path.relative_to(reference_root).as_posix()
        require(relative in manifest_files and manifest_files[relative]["sha256"] == digest, "E_REFERENCE_MANIFEST", "held-out snapshot is not pinned by its evidence manifest", modelHour=hour)
        summary = validate_fields_file(path, cell_count, digest)
        result[hour] = path
        records.append({"modelHour": hour, **summary})
    return result, {**manifest_summary, "root": str(reference_root), "snapshots": records}


def nearest_rank(values: np.ndarray, fraction: float) -> float:
    require(values.ndim == 1 and values.size > 0, "E_PERCENTILE_EMPTY", "nearest-rank percentile requires at least one value")
    require(np.isfinite(values).all(), "E_METRIC_NONFINITE", "percentile input contains non-finite values")
    require(0 < fraction <= 1, "E_PERCENTILE_FRACTION", "nearest-rank fraction must be in (0, 1]")
    ordered = np.sort(values)
    index = min(ordered.size - 1, max(0, math.ceil(fraction * ordered.size) - 1))
    return float(ordered[index])


def compare_fields(
    predicted: Mapping[str, np.ndarray],
    truth: Mapping[str, np.ndarray],
    cell_ids: np.ndarray,
    direction_threshold: float,
) -> dict[str, Any]:
    depth_error = predicted["waterDepthM"][cell_ids] - truth["waterDepthM"][cell_ids]
    pu = predicted["velocityUms"][cell_ids]
    pv = predicted["velocityVms"][cell_ids]
    tu = truth["velocityUms"][cell_ids]
    tv = truth["velocityVms"][cell_ids]
    du = pu - tu
    dv = pv - tv
    vector_error = np.hypot(du, dv)
    predicted_speed = np.hypot(pu, pv)
    truth_speed = np.hypot(tu, tv)
    speed_error = np.abs(predicted_speed - truth_speed)
    active = (predicted_speed >= direction_threshold) & (truth_speed >= direction_threshold)
    active_count = int(np.sum(active))
    require(active_count > 0, "E_DIRECTION_EMPTY", "no cells qualify for direction-error evaluation", directionActiveThresholdMPS=direction_threshold)
    cosine = (pu[active] * tu[active] + pv[active] * tv[active]) / (predicted_speed[active] * truth_speed[active])
    direction_error = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
    metrics = {
        "depthRmseM": float(np.sqrt(np.mean(np.square(depth_error)))),
        "maximumAbsoluteDepthErrorM": float(np.max(np.abs(depth_error))),
        "velocityVectorRmseMPS": float(np.sqrt(np.mean(np.square(du) + np.square(dv)))),
        "speedMaeMPS": float(np.mean(speed_error)),
        "directionActiveThresholdMPS": float(direction_threshold),
        "directionComparedCellCount": active_count,
        "p95DirectionErrorDeg": nearest_rank(direction_error, 0.95),
    }
    require(all(math.isfinite(float(value)) for key, value in metrics.items() if key != "directionComparedCellCount"), "E_METRIC_NONFINITE", "computed holdout metric is non-finite")
    return metrics


def evaluate_holdout(
    endpoints: Mapping[tuple[str, int], Path],
    references: Mapping[int, Path],
    masks: Mapping[str, np.ndarray],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    cell_count = int(contract["mesh"]["cellCount"])
    acceptance = contract["postRunHoldoutAcceptance"]
    thresholds = {
        "velocityVectorRmseMPS": float(acceptance["maximumVelocityVectorRmseMPS"]),
        "speedMaeMPS": float(acceptance["maximumSpeedMaeMPS"]),
        "p95DirectionErrorDeg": float(acceptance["maximumP95DirectionErrorDeg"]),
        "depthRmseM": float(acceptance["maximumDepthRmseM"]),
        "maximumAbsoluteDepthErrorM": float(acceptance["maximumAbsoluteDepthErrorM"]),
    }
    rows: list[dict[str, Any]] = []
    for hour in EXPECTED_HOURS:
        closed = load_fields(endpoints[("barrage-closed", hour)], cell_count)
        opened = load_fields(endpoints[("barrage-open", hour)], cell_count)
        truth = load_fields(references[hour], cell_count)
        predicted = {key: 0.5 * closed[key] + 0.5 * opened[key] for key in FIELD_KEYS}
        for region_id in EXPECTED_REGION_IDS:
            try:
                metrics = compare_fields(predicted, truth, masks[region_id], float(acceptance["directionActiveThresholdMPS"]))
            except NotEvaluableError as error:
                error.details.update({"modelHour": hour, "regionId": region_id})
                raise
            checks = {key: metrics[key] <= limit for key, limit in thresholds.items()}
            rows.append({"modelHour": hour, "regionId": region_id, "cellCount": int(masks[region_id].size), **metrics, "thresholdChecks": checks, "passed": all(checks.values())})
    require(len(rows) == 20, "E_METRIC_COUNT", "holdout comparison count mismatch", actual=len(rows), expected=20)
    failed = [row for row in rows if not row["passed"]]
    worst: dict[str, Any] = {}
    for metric in thresholds:
        row = max(rows, key=lambda item: (float(item[metric]), -EXPECTED_HOURS.index(item["modelHour"]), -EXPECTED_REGION_IDS.index(item["regionId"])))
        worst[metric] = {"value": row[metric], "modelHour": row["modelHour"], "regionId": row["regionId"], "threshold": thresholds[metric], "passed": row[metric] <= thresholds[metric]}
    worst_map_row = max(rows, key=lambda item: float(item["velocityVectorRmseMPS"]))
    return {
        "evaluable": True,
        "acceptanceResult": "passed" if not failed else "failed",
        "expectedComparisonCount": 20,
        "evaluatedComparisonCount": len(rows),
        "passedComparisonCount": len(rows) - len(failed),
        "failedComparisonCount": len(failed),
        "thresholds": thresholds,
        "metricDefinitions": {
            "interpolation": "componentwise_0.5_closed_plus_0.5_open_float64",
            "cellWeighting": "uniform_per_mask_cell_including_dry_cells",
            "velocityVectorRmseMPS": "sqrt(mean((predictedU-directU)^2+(predictedV-directV)^2))",
            "speedMaeMPS": "mean(abs(hypot(predictedU,predictedV)-hypot(directU,directV)))",
            "directionEligibility": "both_predicted_and_direct_speed_at_or_above_directionActiveThresholdMPS",
            "p95DirectionErrorDeg": "nearest_rank_ceil_0.95N_minus_1",
            "depthThresholdMeaning": acceptance["depthThresholdMeaning"],
        },
        "perHourRegion": rows,
        "worstByMetric": worst,
        "worstMapSelection": {"metric": "velocityVectorRmseMPS", "modelHour": worst_map_row["modelHour"], "regionId": worst_map_row["regionId"], "value": worst_map_row["velocityVectorRmseMPS"], "convention": "maximum_across_five_hours_and_four_regions"},
    }


def write_worst_hour_fields(
    output_dir: Path,
    model_hour: int,
    endpoints: Mapping[tuple[str, int], Path],
    reference_path: Path,
    expected_cells: int,
) -> list[dict[str, Any]]:
    """Write map-ready fields only after all evidence has been validated."""

    closed = load_fields(endpoints[("barrage-closed", model_hour)], expected_cells)
    opened = load_fields(endpoints[("barrage-open", model_hour)], expected_cells)
    direct = load_fields(reference_path, expected_cells)
    interpolated = {key: 0.5 * closed[key] + 0.5 * opened[key] for key in FIELD_KEYS}
    error = {
        "waterDepthM": direct["waterDepthM"],
        "velocityUms": interpolated["velocityUms"] - direct["velocityUms"],
        "velocityVms": interpolated["velocityVms"] - direct["velocityVms"],
    }
    depth_error = interpolated["waterDepthM"] - direct["waterDepthM"]
    hour_name = f"m{abs(model_hour):02d}h" if model_hour < 0 else f"p{model_hour:02d}h"
    root = output_dir / f"hour-{hour_name}"
    root.mkdir(parents=True, exist_ok=True)
    direct_path = root / "direct-fields.npz"
    interpolated_path = root / "interpolated-fields.npz"
    error_path = root / "velocity-error-fields.npz"
    depth_error_path = root / "depth-error-fields.npz"
    shutil.copyfile(reference_path, direct_path)
    np.savez_compressed(interpolated_path, **interpolated)
    np.savez_compressed(error_path, **error)
    np.savez_compressed(depth_error_path, waterDepthErrorM=depth_error)
    records = []
    for kind, path in (("direct", direct_path), ("interpolated", interpolated_path), ("velocity_error", error_path), ("depth_error", depth_error_path)):
        records.append({"kind": kind, "modelHour": model_hour, "path": str(path), "byteLength": path.stat().st_size, "sha256": sha256_file(path)})
    return records
