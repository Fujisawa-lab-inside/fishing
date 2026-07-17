#!/usr/bin/env python3
"""Validate the Stage 20 barrage recovery post-run checker without a run.

All dynamic evidence used here is synthetic and lives in a temporary
directory.  The only repository evidence read by this validator is the sealed
static input chain checked by ``validate_static_inputs``.
"""

from __future__ import annotations

import ast
import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from stage20_barrage_holdout_postrun import (  # noqa: E402
    EXPECTED_HOURS,
    NotEvaluableError,
    ValidatedSegment,
    compare_fields,
    evaluate_holdout,
    nearest_rank,
    sha256_bytes,
    sha256_file,
    validate_manifest,
    validate_recovery_segment,
    validate_restart_chain,
    validate_run_metadata,
    validate_static_inputs,
)


CONTRACT_PATH = Path("config/stage20_barrage_holdout_recovery_contract_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def expect_not_evaluable(code: str, callback: Callable[[], Any], label: str) -> NotEvaluableError:
    try:
        callback()
    except NotEvaluableError as error:
        require(error.code == code, f"{label}: expected {code}, received {error.code}: {error}")
        return error
    raise RuntimeError(f"{label}: invalid evidence was accepted; expected {code}")


def write_fields(path: Path, *, depth: np.ndarray, u: np.ndarray, v: np.ndarray) -> None:
    np.savez_compressed(
        path,
        waterDepthM=np.asarray(depth, dtype=np.float64),
        velocityUms=np.asarray(u, dtype=np.float64),
        velocityVms=np.asarray(v, dtype=np.float64),
    )


def test_static_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    static = validate_static_inputs(ROOT, CONTRACT_PATH)
    contract = static["contract"]
    require(len(static["contractSha256"]) == 64, "static contract digest is malformed")
    require(contract["mesh"]["cellCount"] == 50199, "static mesh cell count changed")
    require(len(static["regionalMasks"]["views"]) == 4, "static regional-mask inventory changed")
    require(static["authorization"]["automaticRetryAllowed"] is False, "static authorization now permits retry")
    require(static["authorization"]["additionalRunAllowed"] is False, "static authorization now permits another run")
    return static, contract


def test_run_metadata(contract: dict[str, Any]) -> dict[str, Any]:
    job_conclusions = {"preflight": "success", "authorize": "success"}
    job_conclusions.update({job["id"].removeprefix("barrage-").replace("-", "_"): "success" for job in contract["jobs"]})
    metadata = {
        "schema": "onga-stage20-barrage-holdout-recovery-run-metadata-v1",
        "runId": 29511898671,
        "runAttempt": 1,
        "status": "completed",
        "conclusion": "success",
        "headSha": "92fd709ba4b8760c35b203649e5a0bf00904cdc5",
        "url": "https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29511898671",
        "createdAtUtc": "2026-07-16T18:00:00Z",
        "completedAtUtc": "2026-07-16T23:00:00Z",
        "jobConclusions": job_conclusions,
    }
    validated = validate_run_metadata(metadata, contract["jobs"])
    require(validated["runAttempt"] == 1, "first run attempt was not retained")
    rerun = copy.deepcopy(metadata)
    rerun["runAttempt"] = 2
    expect_not_evaluable(
        "E_RUN_ATTEMPT",
        lambda: validate_run_metadata(rerun, contract["jobs"]),
        "rerun rejection",
    )
    return validated


def test_nearest_rank() -> None:
    five = np.asarray([5.0, 1.0, 4.0, 2.0, 3.0], dtype=np.float64)
    twenty = np.arange(1.0, 21.0, dtype=np.float64)[::-1]
    require(nearest_rank(five, 0.5) == 3.0, "nearest-rank median convention changed")
    require(nearest_rank(twenty, 0.95) == 19.0, "nearest-rank p95 convention changed")


def test_compare_fields() -> None:
    truth = {
        "waterDepthM": np.asarray([1.0, 1.2, 1.4, 1.6], dtype=np.float64),
        "velocityUms": np.asarray([0.10, 0.11, 0.12, 0.13], dtype=np.float64),
        "velocityVms": np.asarray([0.02, 0.03, 0.04, 0.05], dtype=np.float64),
    }
    ids = np.arange(4, dtype=np.int64)
    metrics = compare_fields(truth, truth, ids, 0.02)
    require(metrics["depthRmseM"] == 0.0, "identical depth fields produced error")
    require(metrics["velocityVectorRmseMPS"] == 0.0, "identical velocity fields produced error")
    require(metrics["p95DirectionErrorDeg"] <= 1e-5, "identical velocity fields produced material direction error")
    still = {
        "waterDepthM": truth["waterDepthM"],
        "velocityUms": np.zeros(4, dtype=np.float64),
        "velocityVms": np.zeros(4, dtype=np.float64),
    }
    expect_not_evaluable(
        "E_DIRECTION_EMPTY",
        lambda: compare_fields(still, still, ids, 0.02),
        "empty direction population",
    )


def test_holdout_evaluation(root: Path) -> dict[str, Any]:
    cell_count = 4
    contract = {
        "mesh": {"cellCount": cell_count},
        "postRunHoldoutAcceptance": {
            "maximumVelocityVectorRmseMPS": 0.01,
            "maximumSpeedMaeMPS": 0.005,
            "maximumP95DirectionErrorDeg": 5.0,
            "directionActiveThresholdMPS": 0.02,
            "maximumDepthRmseM": 0.1,
            "maximumAbsoluteDepthErrorM": 0.25,
            "depthThresholdMeaning": "synthetic fixture thresholds retain the sealed comparison semantics",
        },
    }
    masks = {
        "estuary": np.asarray([0, 1, 2, 3], dtype=np.int64),
        "barrage": np.asarray([0, 1], dtype=np.int64),
        "confluence": np.asarray([1, 2], dtype=np.int64),
        "fishway": np.asarray([2, 3], dtype=np.int64),
    }
    endpoints: dict[tuple[str, int], Path] = {}
    references: dict[int, Path] = {}
    truth_by_hour: dict[int, dict[str, np.ndarray]] = {}
    for hour_index, hour in enumerate(EXPECTED_HOURS):
        truth = {
            "waterDepthM": np.asarray([1.0, 1.1, 1.2, 1.3], dtype=np.float64) + hour_index * 0.01,
            "velocityUms": np.asarray([0.10, 0.11, 0.12, 0.13], dtype=np.float64) + hour_index * 0.001,
            "velocityVms": np.asarray([0.03, 0.04, 0.05, 0.06], dtype=np.float64),
        }
        truth_by_hour[hour] = truth
        reference_path = root / f"reference-{hour}.npz"
        write_fields(reference_path, depth=truth["waterDepthM"], u=truth["velocityUms"], v=truth["velocityVms"])
        references[hour] = reference_path
        for basis in ("barrage-closed", "barrage-open"):
            endpoint_path = root / f"{basis}-{hour}.npz"
            write_fields(endpoint_path, depth=truth["waterDepthM"], u=truth["velocityUms"], v=truth["velocityVms"])
            endpoints[(basis, hour)] = endpoint_path

    passed = evaluate_holdout(endpoints, references, masks, contract)
    require(passed["acceptanceResult"] == "passed", "exact interpolation fixture did not pass")
    require(passed["evaluatedComparisonCount"] == 20, "not all 20 synthetic comparisons were evaluated")
    require(passed["failedComparisonCount"] == 0, "exact interpolation fixture recorded failures")

    failed_hour = EXPECTED_HOURS[0]
    truth = truth_by_hour[failed_hour]
    write_fields(
        endpoints[("barrage-open", failed_hour)],
        depth=truth["waterDepthM"],
        u=truth["velocityUms"] + 0.04,
        v=truth["velocityVms"],
    )
    failed = evaluate_holdout(endpoints, references, masks, contract)
    require(failed["acceptanceResult"] == "failed", "above-threshold interpolation fixture was accepted")
    require(failed["evaluable"] is True, "threshold failure was incorrectly marked not evaluable")
    require(failed["failedComparisonCount"] > 0, "threshold failure did not identify a failed comparison")
    require(
        any(not row["thresholdChecks"]["velocityVectorRmseMPS"] for row in failed["perHourRegion"]),
        "vector RMSE threshold boundary was not enforced",
    )
    boundary_contract = copy.deepcopy(contract)
    threshold_keys = {
        "maximumVelocityVectorRmseMPS": "velocityVectorRmseMPS",
        "maximumSpeedMaeMPS": "speedMaeMPS",
        "maximumP95DirectionErrorDeg": "p95DirectionErrorDeg",
        "maximumDepthRmseM": "depthRmseM",
        "maximumAbsoluteDepthErrorM": "maximumAbsoluteDepthErrorM",
    }
    for contract_key, metric_key in threshold_keys.items():
        boundary_contract["postRunHoldoutAcceptance"][contract_key] = max(
            row[metric_key] for row in failed["perHourRegion"]
        )
    boundary = evaluate_holdout(endpoints, references, masks, boundary_contract)
    require(boundary["acceptanceResult"] == "passed", "a metric exactly equal to its threshold did not pass")
    vector_limit = boundary_contract["postRunHoldoutAcceptance"]["maximumVelocityVectorRmseMPS"]
    boundary_contract["postRunHoldoutAcceptance"]["maximumVelocityVectorRmseMPS"] = float(
        np.nextafter(vector_limit, -np.inf)
    )
    just_over = evaluate_holdout(endpoints, references, masks, boundary_contract)
    require(just_over["acceptanceResult"] == "failed", "a metric one float above its threshold did not fail")
    return {
        "passedComparisonCount": passed["passedComparisonCount"],
        "thresholdFailureComparisonCount": failed["failedComparisonCount"],
        "exactThresholdAccepted": True,
        "nextFloatThresholdRejected": True,
    }


def write_synthetic_manifest(root: Path, relative: str, payload: bytes) -> None:
    file_path = root / relative
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(payload)
    manifest = {
        "schema": "onga-stage20-synthetic-local-evidence-v1",
        "status": "sealed_complete_not_physical_validation",
        "physicalValidationClaimAllowed": False,
        "files": [{"path": relative, "byteLength": len(payload), "sha256": sha256_bytes(payload)}],
    }
    (root / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_strict_manifest(root: Path) -> None:
    artifact = root / "manifest-fixture"
    artifact.mkdir()
    write_synthetic_manifest(artifact, "nested/payload.bin", b"alpha")
    summary, inventory = validate_manifest(
        artifact,
        expected_schema="onga-stage20-synthetic-local-evidence-v1",
        strict_inventory=True,
    )
    require(summary["exactInventoryMatched"] is True, "strict manifest inventory was not checked")
    require(set(inventory) == {"nested/payload.bin"}, "strict manifest inventory changed")

    extra = artifact / "unexpected.bin"
    extra.write_bytes(b"extra")
    expect_not_evaluable(
        "E_MANIFEST_INVENTORY",
        lambda: validate_manifest(artifact, expected_schema="onga-stage20-synthetic-local-evidence-v1"),
        "extra-file rejection",
    )
    extra.unlink()

    payload_path = artifact / "nested/payload.bin"
    payload_path.write_bytes(b"bravo")
    expect_not_evaluable(
        "E_MANIFEST_FILE_SHA256",
        lambda: validate_manifest(artifact, expected_schema="onga-stage20-synthetic-local-evidence-v1"),
        "digest-tamper rejection",
    )

    unsafe = json.loads((artifact / "evidence-manifest.json").read_text(encoding="utf-8"))
    unsafe["files"][0]["path"] = "../escape.bin"
    (artifact / "evidence-manifest.json").write_text(json.dumps(unsafe, indent=2) + "\n", encoding="utf-8")
    expect_not_evaluable(
        "E_PATH_UNSAFE",
        lambda: validate_manifest(artifact, expected_schema="onga-stage20-synthetic-local-evidence-v1"),
        "unsafe-path rejection",
    )


def write_state(
    path: Path,
    *,
    state: np.ndarray,
    elapsed_seconds: float,
    step: int,
    expected_volume_m3: float,
    maximum_cfl: float,
    maximum_mass_error: float,
) -> None:
    np.savez_compressed(
        path,
        state=np.asarray(state, dtype=np.float64),
        elapsed_seconds=np.asarray(elapsed_seconds, dtype=np.float64),
        step=np.asarray(step, dtype=np.int64),
        expected_volume_m3=np.asarray(expected_volume_m3, dtype=np.float64),
        maximum_cfl=np.asarray(maximum_cfl, dtype=np.float64),
        maximum_mass_error=np.asarray(maximum_mass_error, dtype=np.float64),
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def reseal_recovery_artifact(root: Path, authorization_id: str, job_id: str) -> None:
    manifest_path = root / "evidence-manifest.json"
    files = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file() and candidate != manifest_path):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "byteLength": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    write_json(manifest_path, {
        "schema": "onga-stage20-barrage-holdout-recovery-segment-evidence-v1",
        "status": "sealed_complete_not_physical_validation",
        "authorizationId": authorization_id,
        "jobId": job_id,
        "physicalValidationClaimAllowed": False,
        "files": files,
    })


def test_complete_recovery_segment(root: Path) -> dict[str, Any]:
    artifact = root / "complete-recovery-segment"
    (artifact / "checkpoints").mkdir(parents=True)
    (artifact / "snapshots").mkdir()
    authorization_id = "synthetic-local-authorization"
    authorization_sha = "1" * 64
    contract_sha = "2" * 64
    decision_sha = "3" * 64
    input_restart_sha = "4" * 64
    input_manifest_sha = "5" * 64
    head_sha = "6" * 40
    job = {
        "id": "barrage-closed-synthetic-m13-m12",
        "basisId": "barrage-closed",
        "modelHourStart": -13,
        "modelHourEnd": -12,
        "targetPhysicalSeconds": 3600,
        "input": {
            "kind": "retained_sealed_restart",
            "jobId": "barrage-closed-synthetic-input",
            "restartSha256": input_restart_sha,
            "evidenceManifestSha256": input_manifest_sha,
        },
        "snapshotModelHours": [-12],
        "maximumNumericalWallSeconds": 18000,
    }
    contract = {
        "mesh": {"cellCount": 4},
        "resource": {"requiredPlatform": "Linux x86_64"},
        "acceptance": {
            "maximumCfl": 0.95,
            "maximumRelativeMassBalanceError": 1e-8,
            "checkpointIntervalPhysicalSeconds": 3600,
        },
    }
    authorization = {
        "authorizationId": authorization_id,
        "decisionImage": {"sha256": decision_sha},
    }
    run = {"runId": 29511898671, "headSha": head_sha}

    depth = np.asarray([1.0, 2.0, 0.0, 1.5], dtype=np.float64)
    intended_u = np.asarray([0.10, 0.20, 0.0, 0.30], dtype=np.float64)
    intended_v = np.asarray([0.02, -0.04, 0.0, 0.06], dtype=np.float64)
    state = np.column_stack((depth, depth * intended_u, depth * intended_v)).astype(np.float64)
    fields_u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    fields_v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    elapsed_seconds = 3600.0
    start_step = 100
    end_step = 110
    maximum_cfl = 0.5
    maximum_mass_error = 1e-9
    expected_volume = float(np.sum(depth))

    restart_path = artifact / "restart-final.npz"
    checkpoint_path = artifact / "checkpoints/checkpoint-01.npz"
    for path in (restart_path, checkpoint_path):
        write_state(
            path,
            state=state,
            elapsed_seconds=elapsed_seconds,
            step=end_step,
            expected_volume_m3=expected_volume,
            maximum_cfl=maximum_cfl,
            maximum_mass_error=maximum_mass_error,
        )
    fields_path = artifact / "segment-final-fields.npz"
    snapshot_path = artifact / "snapshots/snapshot-m12h-fields.npz"
    for path in (fields_path, snapshot_path):
        write_fields(path, depth=depth, u=fields_u, v=fields_v)
    checkpoint_record = {
        "path": "checkpoints/checkpoint-01.npz",
        "sha256": sha256_file(checkpoint_path),
        "elapsedSeconds": elapsed_seconds,
        "step": end_step,
    }
    snapshot_record = {
        "modelHour": -12,
        "path": "snapshots/snapshot-m12h-fields.npz",
        "sha256": sha256_file(snapshot_path),
    }
    platform_record = {"system": "Linux", "machine": "x86_64", "python": "3.13.7"}
    report = {
        "schema": "onga-stage20-barrage-holdout-recovery-segment-report-v1",
        "status": "passed_numerical_checks_not_physical_validation",
        "authorizationId": authorization_id,
        "platform": platform_record,
        "run": {
            "jobId": job["id"],
            "basisId": job["basisId"],
            "modelHourStart": job["modelHourStart"],
            "modelHourEnd": job["modelHourEnd"],
            "simulatedSeconds": elapsed_seconds,
            "startStep": start_step,
            "endStep": end_step,
            "wallSeconds": 10.0,
        },
        "input": {
            "jobId": job["input"]["jobId"],
            "restartSha256": input_restart_sha,
            "evidenceManifestSha256": input_manifest_sha,
        },
        "diagnostics": {
            "inputRestartRelativeMassError": 5e-10,
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "nonFiniteValueCount": 0,
            "negativeDepthCount": 0,
            "maximumSpeedMPS": float(np.max(np.hypot(fields_u, fields_v))),
        },
        "outputs": {
            "restart": "restart-final.npz",
            "restartSha256": sha256_file(restart_path),
            "fields": "segment-final-fields.npz",
            "fieldsSha256": sha256_file(fields_path),
            "checkpoints": [checkpoint_record],
            "snapshots": [snapshot_record],
        },
        "safeguards": {
            "automaticRetryAllowed": False,
            "physicalValidationClaimAllowed": False,
            "publicSimulatorConnected": False,
        },
    }
    receipt = {
        "schema": "onga-stage20-barrage-holdout-recovery-segment-receipt-v1",
        "authorizationId": authorization_id,
        "authorizationSha256": authorization_sha,
        "executionContractSha256": contract_sha,
        "decisionImageSha256": decision_sha,
        "jobId": job["id"],
        "predecessorJobId": job["input"]["jobId"],
        "inputRestartSha256": input_restart_sha,
        "inputEvidenceManifestSha256": input_manifest_sha,
        "githubRunId": str(run["runId"]),
        "githubSha": head_sha,
        "automaticRetryAllowed": False,
    }
    progress = {
        "schema": "onga-stage20-barrage-holdout-recovery-progress-v1",
        "status": "complete",
        "authorizationId": authorization_id,
        "jobId": job["id"],
        "simulatedSeconds": elapsed_seconds,
        "wallSeconds": 9.5,
        "checkpoints": [checkpoint_record],
        "snapshots": [snapshot_record],
    }
    write_json(artifact / "segment-report.json", report)
    write_json(artifact / "execution-receipt.json", receipt)
    write_json(artifact / "progress.json", progress)
    reseal_recovery_artifact(artifact, authorization_id, job["id"])

    segment = validate_recovery_segment(
        artifact,
        job,
        contract,
        authorization,
        run,
        authorization_sha256=authorization_sha,
        contract_sha256=contract_sha,
    )
    require(segment.summary["manifest"]["exactInventoryMatched"] is True, "complete segment did not use strict inventory validation")
    require(segment.summary["manifest"]["fileCount"] == 7, "complete segment manifest file count changed")
    require(segment.summary["checkpointCount"] == 1, "complete segment checkpoint count changed")
    require(segment.summary["snapshotHours"] == [-12], "complete segment snapshot hour changed")
    require(segment.summary["finalCheckpointMatchesRestartExactly"] is True, "checkpoint/restart equality was not verified")
    require(segment.summary["finalFieldsMatchRestartExactly"] is True, "restart/fields equality was not verified")
    require(segment.summary["finalSnapshotMatchesFieldsExactly"] is True, "fields/snapshot equality was not verified")
    require(segment.report["platform"] == platform_record, "Linux x86_64 Python 3.13 platform record changed")

    mutated_report = json.loads((artifact / "segment-report.json").read_text(encoding="utf-8"))
    mutated_report["run"]["endStep"] = end_step + 1
    write_json(artifact / "segment-report.json", mutated_report)
    reseal_recovery_artifact(artifact, authorization_id, job["id"])
    expect_not_evaluable(
        "E_FINAL_STATE_METADATA",
        lambda: validate_recovery_segment(
            artifact,
            job,
            contract,
            authorization,
            run,
            authorization_sha256=authorization_sha,
            contract_sha256=contract_sha,
        ),
        "resealed report/restart cross-layer mutation rejection",
    )
    return {
        "manifestFileCount": segment.summary["manifest"]["fileCount"],
        "checkpointCount": segment.summary["checkpointCount"],
        "snapshotHours": segment.summary["snapshotHours"],
        "platform": platform_record,
        "resealedCrossLayerMutationRejected": True,
    }


def test_restart_chain(root: Path) -> None:
    retained_restart = "a" * 64
    retained_manifest = "b" * 64
    predecessor_restart = "c" * 64
    predecessor_manifest = "d" * 64
    first_job = {
        "id": "barrage-closed-fixture-a",
        "basisId": "barrage-closed",
        "modelHourStart": -16,
        "modelHourEnd": -14,
        "input": {
            "kind": "retained_sealed_restart",
            "jobId": "retained-fixture",
            "restartSha256": retained_restart,
            "evidenceManifestSha256": retained_manifest,
        },
    }
    first = ValidatedSegment(
        job=first_job,
        root=root,
        report={
            "input": {"restartSha256": retained_restart, "evidenceManifestSha256": retained_manifest},
            "run": {"startStep": 100, "endStep": 200},
        },
        receipt={"inputRestartSha256": retained_restart, "inputEvidenceManifestSha256": retained_manifest},
        manifest_sha256=predecessor_manifest,
        restart_path=root / "unused-first.npz",
        restart_sha256=predecessor_restart,
        snapshot_paths={},
        summary={},
    )
    second_job = {
        "id": "barrage-closed-fixture-b",
        "basisId": "barrage-closed",
        "modelHourStart": -14,
        "modelHourEnd": -12,
        "input": {"kind": "recovery_predecessor", "jobId": first_job["id"]},
    }
    second = ValidatedSegment(
        job=second_job,
        root=root,
        report={
            "input": {"restartSha256": predecessor_restart, "evidenceManifestSha256": predecessor_manifest},
            "run": {"startStep": 200, "endStep": 300},
        },
        receipt={"inputRestartSha256": predecessor_restart, "inputEvidenceManifestSha256": predecessor_manifest},
        manifest_sha256="e" * 64,
        restart_path=root / "unused-second.npz",
        restart_sha256="f" * 64,
        snapshot_paths={},
        summary={},
    )
    links = validate_restart_chain([first, second])
    require(len(links) == 2 and all(link["passed"] for link in links), "valid synthetic restart chain failed")
    second.report["input"]["restartSha256"] = "0" * 64
    expect_not_evaluable(
        "E_CHAIN_RESTART_SHA256",
        lambda: validate_restart_chain([first, second]),
        "restart-chain tamper rejection",
    )


def dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def test_offline_source_boundary() -> None:
    sources = [
        TOOLS / "stage20_barrage_holdout_postrun.py",
        TOOLS / "analyze_stage20_barrage_holdout_recovery_result.py",
    ]
    forbidden_import_roots = {
        "aiohttp",
        "ftplib",
        "http",
        "httpx",
        "requests",
        "smtplib",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_solver_calls = {
        "advance_one_step",
        "advance_state",
        "integrate_model",
        "run_solver",
        "solve_physical_segment",
    }
    violations: list[str] = []
    for path in sources:
        require(path.is_file(), f"offline checker source missing: {path}")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in forbidden_import_roots:
                        violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".", 1)[0] in forbidden_import_roots:
                    violations.append(f"{path.name}:{node.lineno}: from {module} import")
            elif isinstance(node, ast.Call):
                call = dotted_name(node.func)
                root = call.split(".", 1)[0]
                tail = call.rsplit(".", 1)[-1]
                if root in forbidden_import_roots or tail in forbidden_solver_calls:
                    violations.append(f"{path.name}:{node.lineno}: call {call}")
    require(not violations, "offline/source boundary violated: " + "; ".join(violations))


def main() -> None:
    static, contract = test_static_inputs()
    run = test_run_metadata(contract)
    test_nearest_rank()
    test_compare_fields()
    with tempfile.TemporaryDirectory(prefix="stage20-barrage-postrun-fixture-") as temporary:
        fixture_root = Path(temporary)
        holdout_summary = test_holdout_evaluation(fixture_root)
        test_strict_manifest(fixture_root)
        recovery_segment_summary = test_complete_recovery_segment(fixture_root)
        test_restart_chain(fixture_root)
    test_offline_source_boundary()
    print(json.dumps({
        "schema": "onga-stage20-barrage-holdout-recovery-postrun-validation-v1",
        "status": "passed_fixture_only_offline_validation",
        "staticInputs": {
            "contractSha256": static["contractSha256"],
            "authorizationId": static["authorization"]["authorizationId"],
            "regionalMaskCount": len(static["regionalMasks"]["views"]),
        },
        "runMetadata": {
            "fixtureRunId": run["runId"],
            "firstAttemptAccepted": True,
            "rerunRejected": True,
        },
        "holdout": holdout_summary,
        "completeSyntheticRecoverySegment": recovery_segment_summary,
        "checks": {
            "nearestRankConvention": True,
            "directionEmptyRejected": True,
            "twentyComparisonsEvaluated": True,
            "exactThresholdAccepted": True,
            "nextFloatThresholdRejected": True,
            "thresholdFailureSeparatedFromEvidenceFailure": True,
            "strictManifestInventory": True,
            "manifestExtraFileRejected": True,
            "manifestDigestTamperRejected": True,
            "unsafeManifestPathRejected": True,
            "completeRecoverySegmentValidatedEndToEnd": True,
            "resealedCrossLayerMutationRejected": True,
            "restartChainValidatedAndTamperRejected": True,
            "offlineSourceBoundary": True,
        },
        "safeguards": {
            "fixtureOnly": True,
            "networkAccessAttempted": False,
            "solverInvoked": False,
            "recoveryRunTriggered": False,
            "filesOutsideTemporaryDirectoryModified": False,
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
