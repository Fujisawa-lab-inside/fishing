#!/usr/bin/env python3
"""Audit the stopped Stage 20 barrage holdout without running the solver."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np


RUN_ID = 29464186133
CONTRACT_PATH = Path("config/stage20_barrage_holdout_contract_v1.json")
AUTHORIZATION_PATH = Path("config/stage20_barrage_holdout_authorization_v1.json")
REFERENCE_ROOT = Path("docs/results/stage20-reference-s02-29434250546")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def gh_json(arguments: list[str]) -> dict:
    return json.loads(subprocess.check_output(["gh", *arguments], text=True))


def validate_state_file(path: Path, expected_cells: int) -> dict:
    with np.load(path, allow_pickle=False) as payload:
        require("state" in payload.files, f"state missing: {path}")
        state = payload["state"]
        require(state.shape == (expected_cells, 3), f"state shape mismatch: {path}")
        non_finite = int(state.size - np.isfinite(state).sum())
        negative_depth = int(np.sum(state[:, 0] < 0))
        require(non_finite == 0, f"non-finite state: {path}")
        require(negative_depth == 0, f"negative depth: {path}")
        result = {
            "path": str(path),
            "sha256": sha256(path),
            "shape": list(state.shape),
            "nonFiniteValueCount": non_finite,
            "negativeDepthCount": negative_depth,
        }
        for key in ("elapsed_seconds", "step", "expected_volume_m3", "maximum_cfl", "maximum_mass_error"):
            if key in payload.files:
                value = payload[key].item()
                result[key] = int(value) if key == "step" else float(value)
        return result


def validate_fields_file(path: Path, expected_cells: int) -> dict:
    expected = ("waterDepthM", "velocityUms", "velocityVms")
    with np.load(path, allow_pickle=False) as payload:
        require(set(payload.files) == set(expected), f"field keys mismatch: {path}")
        arrays = [payload[name] for name in expected]
        require(all(array.shape == (expected_cells,) for array in arrays), f"field shape mismatch: {path}")
        non_finite = sum(int(array.size - np.isfinite(array).sum()) for array in arrays)
        negative_depth = int(np.sum(arrays[0] < 0))
        require(non_finite == 0, f"non-finite fields: {path}")
        require(negative_depth == 0, f"negative depth fields: {path}")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "shapePerComponent": [expected_cells],
        "nonFiniteValueCount": non_finite,
        "negativeDepthCount": negative_depth,
    }


def arrays_equal(first: Path, second: Path, keys: tuple[str, ...]) -> bool:
    with np.load(first, allow_pickle=False) as a, np.load(second, allow_pickle=False) as b:
        return all(np.array_equal(a[key], b[key]) for key in keys)


def fields_match_restart(fields_path: Path, restart_path: Path) -> bool:
    with np.load(restart_path, allow_pickle=False) as restart, np.load(fields_path, allow_pickle=False) as fields:
        state = restart["state"]
        depth = state[:, 0]
        u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
        return (
            np.array_equal(fields["waterDepthM"], depth)
            and np.array_equal(fields["velocityUms"], u)
            and np.array_equal(fields["velocityVms"], v)
        )


def validate_manifest(root: Path, job_root: Path, authorization_id: str, job_id: str) -> dict:
    manifest_path = job_root / "evidence-manifest.json"
    manifest = load_json(manifest_path)
    require(manifest["schema"] == "onga-stage20-barrage-holdout-segment-evidence-v1", "manifest schema mismatch")
    require(manifest["status"] == "sealed_complete_not_physical_validation", "manifest status mismatch")
    require(manifest["authorizationId"] == authorization_id, "manifest authorization mismatch")
    require(manifest["jobId"] == job_id, "manifest job mismatch")
    require(manifest["physicalValidationClaimAllowed"] is False, "physical claim enabled")
    expected_files = sorted(
        str(path.relative_to(job_root))
        for path in job_root.rglob("*")
        if path.is_file() and path.name != "evidence-manifest.json"
    )
    recorded_files = sorted(item["path"] for item in manifest["files"])
    require(recorded_files == expected_files, f"manifest inventory mismatch: {job_id}")
    for item in manifest["files"]:
        path = job_root / item["path"]
        require(path.stat().st_size == item["byteLength"], f"manifest length mismatch: {path}")
        require(sha256(path) == item["sha256"], f"manifest digest mismatch: {path}")
    return {
        "path": str(manifest_path.relative_to(root)),
        "sha256": sha256(manifest_path),
        "fileCount": len(manifest["files"]),
        "allFileLengthsAndDigestsVerified": True,
    }


def validate_complete_job(
    root: Path,
    result_root: Path,
    job: dict,
    authorization: dict,
    contract: dict,
) -> dict:
    job_id = job["id"]
    job_root = result_root / f"{job_id}-{RUN_ID}"
    report_path = job_root / "segment-report.json"
    receipt_path = job_root / "execution-receipt.json"
    report = load_json(report_path)
    receipt = load_json(receipt_path)
    manifest = validate_manifest(root, job_root, authorization["authorizationId"], job_id)
    require(report["schema"] == "onga-stage20-barrage-holdout-segment-report-v1", "report schema mismatch")
    require(report["status"] == "passed_numerical_checks_not_physical_validation", "report status mismatch")
    require(report["run"]["jobId"] == job_id and report["run"]["basisId"] == job["basisId"], "report identity mismatch")
    require(report["run"]["modelHourStart"] == job["modelHourStart"], "report start hour mismatch")
    require(report["run"]["modelHourEnd"] == job["modelHourEnd"], "report end hour mismatch")
    require(report["run"]["simulatedSeconds"] >= job["targetPhysicalSeconds"], "segment target not reached")
    require(report["run"]["wallSeconds"] <= job["maximumNumericalWallSeconds"], "segment wall limit exceeded")
    diagnostics = report["diagnostics"]
    require(diagnostics["maximumCfl"] <= contract["acceptance"]["maximumCfl"], "CFL threshold exceeded")
    require(
        diagnostics["maximumRelativeMassBalanceError"] <= contract["acceptance"]["maximumRelativeMassBalanceError"],
        "mass threshold exceeded",
    )
    require(
        diagnostics["inputRestartRelativeMassError"] <= contract["acceptance"]["maximumRelativeMassBalanceError"],
        "restart mass threshold exceeded",
    )
    require(diagnostics["nonFiniteValueCount"] == 0, "report non-finite count")
    require(diagnostics["negativeDepthCount"] == 0, "report negative depth count")
    require(len(report["outputs"]["checkpoints"]) == 4, "checkpoint count mismatch")
    require(len(report["outputs"]["snapshots"]) == len(job["snapshotModelHours"]), "snapshot count mismatch")
    require(receipt["schema"] == "onga-stage20-barrage-holdout-segment-receipt-v1", "receipt schema mismatch")
    require(receipt["authorizationId"] == authorization["authorizationId"], "receipt authorization mismatch")
    require(receipt["authorizationSha256"] == sha256(root / AUTHORIZATION_PATH), "receipt authorization digest mismatch")
    require(receipt["executionContractSha256"] == sha256(root / CONTRACT_PATH), "receipt contract digest mismatch")
    require(receipt["decisionImageSha256"] == authorization["decisionImage"]["sha256"], "receipt image digest mismatch")
    require(receipt["jobId"] == job_id and receipt["predecessorJobId"] == job["predecessorJobId"], "receipt job mismatch")
    require(receipt["githubRunId"] == str(RUN_ID), "receipt run id mismatch")
    require(receipt["githubSha"] == "3b2cba242b2da1205121d9dbf2e231f0b081b49a", "receipt commit mismatch")
    require(receipt["automaticRetryAllowed"] is False, "receipt retry enabled")
    checkpoints = []
    for item in report["outputs"]["checkpoints"]:
        path = job_root / item["path"]
        require(sha256(path) == item["sha256"], f"reported checkpoint digest mismatch: {path}")
        checkpoints.append(validate_state_file(path, contract["mesh"]["cellCount"]))
    restart_path = job_root / report["outputs"]["restart"]
    fields_path = job_root / report["outputs"]["fields"]
    require(sha256(restart_path) == report["outputs"]["restartSha256"], "restart digest mismatch")
    require(sha256(fields_path) == report["outputs"]["fieldsSha256"], "fields digest mismatch")
    restart = validate_state_file(restart_path, contract["mesh"]["cellCount"])
    fields = validate_fields_file(fields_path, contract["mesh"]["cellCount"])
    final_checkpoint_path = job_root / report["outputs"]["checkpoints"][-1]["path"]
    final_checkpoint_matches_restart = arrays_equal(
        final_checkpoint_path,
        restart_path,
        ("state", "elapsed_seconds", "step", "expected_volume_m3", "maximum_cfl", "maximum_mass_error"),
    )
    require(final_checkpoint_matches_restart, "final checkpoint does not match restart")
    final_fields_match_restart = fields_match_restart(fields_path, restart_path)
    require(final_fields_match_restart, "final fields do not match restart")
    snapshots = []
    for item in report["outputs"]["snapshots"]:
        path = job_root / item["path"]
        require(sha256(path) == item["sha256"], f"reported snapshot digest mismatch: {path}")
        snapshots.append({"modelHour": item["modelHour"], **validate_fields_file(path, contract["mesh"]["cellCount"])})
    final_snapshot_matches_fields = None
    if snapshots and snapshots[-1]["modelHour"] == job["modelHourEnd"]:
        final_snapshot_path = job_root / report["outputs"]["snapshots"][-1]["path"]
        final_snapshot_matches_fields = arrays_equal(
            final_snapshot_path,
            fields_path,
            ("waterDepthM", "velocityUms", "velocityVms"),
        )
        require(final_snapshot_matches_fields, "final snapshot does not match fields")
    return {
        "jobId": job_id,
        "basisId": job["basisId"],
        "modelHourStart": job["modelHourStart"],
        "modelHourEnd": job["modelHourEnd"],
        "startStep": report["run"]["startStep"],
        "endStep": report["run"]["endStep"],
        "simulatedSeconds": report["run"]["simulatedSeconds"],
        "wallSeconds": report["run"]["wallSeconds"],
        "diagnostics": diagnostics,
        "checkpointCount": len(checkpoints),
        "snapshotHours": [item["modelHour"] for item in snapshots],
        "restartSha256": restart["sha256"],
        "fieldsSha256": fields["sha256"],
        "manifest": manifest,
        "finalCheckpointMatchesRestartExactly": final_checkpoint_matches_restart,
        "finalFieldsMatchRestartExactly": final_fields_match_restart,
        "finalSnapshotMatchesFieldsExactly": final_snapshot_matches_fields,
    }


def validate_reference(root: Path) -> dict:
    reference_root = root / REFERENCE_ROOT
    manifest_path = reference_root / "evidence-manifest.json"
    manifest = load_json(manifest_path)
    for item in manifest["files"]:
        path = reference_root / item["path"]
        require(path.stat().st_size == item["byteLength"], f"reference length mismatch: {path}")
        require(sha256(path) == item["sha256"], f"reference digest mismatch: {path}")
    snapshot_hours = [-12, -11, -10, -9, -8]
    snapshots = []
    for hour in snapshot_hours:
        name = f"snapshotmm{abs(hour):02d}hmfields.npz"
        path = reference_root / "snapshots" / name
        snapshots.append({"modelHour": hour, "path": str(path.relative_to(root)), "sha256": sha256(path)})
    return {
        "root": str(REFERENCE_ROOT),
        "evidenceManifestSha256": sha256(manifest_path),
        "evidenceFileCount": len(manifest["files"]),
        "allEvidenceDigestsVerified": True,
        "snapshots": snapshots,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--result-root", default=f"docs/results/stage20-barrage-holdout-{RUN_ID}")
    parser.add_argument("--output", default="config/stage20_barrage_holdout_analysis_v1.json")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    result_root = root / args.result_root
    contract = load_json(root / CONTRACT_PATH)
    authorization = load_json(root / AUTHORIZATION_PATH)
    run = gh_json([
        "run", "view", str(RUN_ID), "--json",
        "status,conclusion,createdAt,startedAt,updatedAt,url,headSha,event,jobs",
    ])
    run_api = gh_json(["api", f"repos/Fujisawa-lab-inside/fishing/actions/runs/{RUN_ID}"])
    artifact_api = gh_json(["api", f"repos/Fujisawa-lab-inside/fishing/actions/runs/{RUN_ID}/artifacts"])
    failed_log = subprocess.check_output(["gh", "run", "view", str(RUN_ID), "--log-failed"], text=True)
    require(run["status"] == "completed" and run["conclusion"] == "failure", "unexpected run result")
    require(run["headSha"] == "3b2cba242b2da1205121d9dbf2e231f0b081b49a", "execution commit mismatch")
    require(run_api["run_attempt"] == 1, "run attempt mismatch")
    external_timeout_confirmed = "Process completed with exit code 124" in failed_log and "timeout --signal=TERM" in failed_log
    require(external_timeout_confirmed, "external timeout was not confirmed")
    jobs_by_name = {item["name"]: item for item in run["jobs"]}
    expected_conclusions = {
        "preflight": "success",
        "authorize": "success",
        "closed_s01": "success",
        "open_s01": "success",
        "closed_s02": "success",
        "open_s02": "success",
        "closed_s03": "failure",
        "open_s03": "success",
        "closed_s04": "skipped",
        "open_s04": "skipped",
    }
    require({name: jobs_by_name[name]["conclusion"] for name in expected_conclusions} == expected_conclusions, "job conclusions changed")
    artifact_by_name = {item["name"]: item for item in artifact_api["artifacts"]}
    completed = []
    partial = None
    absent = []
    for job in contract["jobs"]:
        job_root = result_root / f"{job['id']}-{RUN_ID}"
        if (job_root / "segment-report.json").is_file():
            completed.append(validate_complete_job(root, result_root, job, authorization, contract))
        elif job_root.is_dir():
            require(job["id"] == "barrage-closed-s03", "unexpected partial artifact")
            progress_path = job_root / "progress.json"
            progress = load_json(progress_path)
            require(progress["schema"] == "onga-stage20-barrage-holdout-progress-v1", "partial progress schema mismatch")
            require(progress["status"] == "in_progress" and progress["jobId"] == job["id"], "partial progress mismatch")
            require(len(progress["checkpoints"]) == 3 and len(progress["snapshots"]) == 0, "partial inventory mismatch")
            checkpoints = []
            for item in progress["checkpoints"]:
                path = job_root / item["path"]
                require(sha256(path) == item["sha256"], "partial checkpoint digest mismatch")
                checkpoints.append(validate_state_file(path, contract["mesh"]["cellCount"]))
            last = checkpoints[-1]
            require(last["elapsed_seconds"] == progress["simulatedSeconds"], "partial elapsed mismatch")
            require(last["step"] == progress["checkpoints"][-1]["step"], "partial step mismatch")
            require(last["maximum_cfl"] <= contract["acceptance"]["maximumCfl"], "partial CFL threshold exceeded")
            require(last["maximum_mass_error"] <= contract["acceptance"]["maximumRelativeMassBalanceError"], "partial mass threshold exceeded")
            partial = {
                "jobId": job["id"],
                "basisId": job["basisId"],
                "status": "externally_terminated_at_five_wall_hours",
                "exitCode": 124,
                "externalTimeoutConfirmedFromGitHubLog": external_timeout_confirmed,
                "lastRetainedSimulatedSeconds": progress["simulatedSeconds"],
                "targetSimulatedSeconds": job["targetPhysicalSeconds"],
                "lastRetainedCompletionFraction": progress["simulatedSeconds"] / job["targetPhysicalSeconds"],
                "lastRetainedWallSeconds": progress["wallSeconds"],
                "lastRetainedStep": last["step"],
                "checkpointCount": len(checkpoints),
                "maximumCflAtLastCheckpoint": last["maximum_cfl"],
                "maximumRelativeMassBalanceErrorAtLastCheckpoint": last["maximum_mass_error"],
                "nonFiniteValueCountAtRetainedCheckpoints": 0,
                "negativeDepthCountAtRetainedCheckpoints": 0,
                "progressPath": str(progress_path.relative_to(root)),
                "progressSha256": sha256(progress_path),
                "sealedEvidenceManifestPresent": False,
                "finalRestartPresent": False,
                "requiredMinus12SnapshotPresent": False,
            }
        else:
            absent.append(job["id"])
    completed_by_id = {item["jobId"]: item for item in completed}
    require(set(completed_by_id) == {
        "barrage-closed-s01", "barrage-closed-s02", "barrage-open-s01", "barrage-open-s02", "barrage-open-s03"
    }, "completed job set mismatch")
    require(partial is not None, "partial stopped artifact missing")
    require(absent == ["barrage-closed-s04", "barrage-open-s04"], "absent job set mismatch")
    chain_checks = []
    for basis, ids in {
        "barrage-closed": ["barrage-closed-s01", "barrage-closed-s02"],
        "barrage-open": ["barrage-open-s01", "barrage-open-s02", "barrage-open-s03"],
    }.items():
        for previous_id, current_id in zip(ids, ids[1:]):
            passed = completed_by_id[previous_id]["endStep"] == completed_by_id[current_id]["startStep"]
            require(passed, f"step chain mismatch: {previous_id} -> {current_id}")
            chain_checks.append({"basisId": basis, "previousJobId": previous_id, "currentJobId": current_id, "stepChainVerified": passed})
    partial_step_follows_predecessor = partial["lastRetainedStep"] > completed_by_id["barrage-closed-s02"]["endStep"]
    require(partial_step_follows_predecessor, "partial step did not advance predecessor")
    max_cfl = max(item["diagnostics"]["maximumCfl"] for item in completed)
    max_mass = max(item["diagnostics"]["maximumRelativeMassBalanceError"] for item in completed)
    max_restart_mass = max(item["diagnostics"]["inputRestartRelativeMassError"] for item in completed)
    successful_snapshot_hours = [hour for item in completed for hour in item["snapshotHours"]]
    expected_snapshot_count = 10
    available_snapshot_count = len(successful_snapshot_hours)
    reference = validate_reference(root)
    complete_artifact_names = [f"{item['jobId']}-{RUN_ID}" for item in completed]
    partial_artifact_name = f"{partial['jobId']}-{RUN_ID}"
    require(all(name in artifact_by_name for name in complete_artifact_names + [partial_artifact_name]), "GitHub artifact missing")
    analysis = {
        "schema": "onga-stage20-barrage-holdout-analysis-v1",
        "status": "stopped_external_timeout_incomplete_holdout_not_evaluable",
        "recordedDate": "2026-07-16",
        "github": {
            "runId": RUN_ID,
            "runAttempt": run_api["run_attempt"],
            "runUrl": run["url"],
            "executionCommit": run["headSha"],
            "status": run["status"],
            "conclusion": run["conclusion"],
            "createdAtUtc": run["createdAt"],
            "completedAtUtc": run["updatedAt"],
            "jobConclusions": expected_conclusions,
        },
        "authorization": {
            "id": authorization["authorizationId"],
            "contractSha256": sha256(root / CONTRACT_PATH),
            "authorizationSha256": sha256(root / AUTHORIZATION_PATH),
            "consumed": True,
            "automaticRetryAllowed": False,
            "additionalRunAllowed": False,
        },
        "artifactInventory": {
            "expectedJobCount": 8,
            "successfulCompleteJobCount": len(completed),
            "partialStoppedJobCount": 1,
            "skippedJobCount": len(absent),
            "downloadedArtifactCount": len(artifact_api["artifacts"]),
            "completeArtifacts": [
                {
                    "name": name,
                    "artifactId": artifact_by_name[name]["id"],
                    "sizeBytes": artifact_by_name[name]["size_in_bytes"],
                    "expiresAtUtc": artifact_by_name[name]["expires_at"],
                }
                for name in complete_artifact_names
            ],
            "partialArtifact": {
                "name": partial_artifact_name,
                "artifactId": artifact_by_name[partial_artifact_name]["id"],
                "sizeBytes": artifact_by_name[partial_artifact_name]["size_in_bytes"],
                "expiresAtUtc": artifact_by_name[partial_artifact_name]["expires_at"],
            },
            "absentSkippedArtifacts": [f"{job_id}-{RUN_ID}" for job_id in absent],
            "retainedPath": str(result_root.relative_to(root)),
        },
        "completedSegments": completed,
        "stoppedSegment": partial,
        "chainEvidence": {
            "completedStepChains": chain_checks,
            "partialStepAdvancedFromClosedS02": partial_step_follows_predecessor,
            "cryptographicInputRestartDigestRecordedBySuccessor": False,
            "limitation": "workflow source identity, predecessor ids, downloaded artifact names, and step continuity verify the chain operationally; successor receipts do not record the input restart SHA-256",
        },
        "numericalSummary": {
            "completedSegmentsPassedContractChecks": True,
            "maximumCflAcrossCompletedSegments": max_cfl,
            "maximumRelativeMassBalanceErrorAcrossCompletedSegments": max_mass,
            "maximumInputRestartRelativeMassErrorAcrossCompletedSegments": max_restart_mass,
            "nonFiniteValueCountAcrossCompletedSegments": 0,
            "negativeDepthCountAcrossCompletedSegments": 0,
            "partialRetainedCheckpointsPassedAvailableChecks": True,
            "externalTimeoutWasNotANumericalThresholdFailure": True,
        },
        "snapshotInventory": {
            "expectedCount": expected_snapshot_count,
            "availableSealedCount": available_snapshot_count,
            "available": [{"basisId": "barrage-open", "modelHour": -12}],
            "missingCount": expected_snapshot_count - available_snapshot_count,
            "missing": [
                {"basisId": "barrage-closed", "modelHour": hour} for hour in [-12, -11, -10, -9, -8]
            ] + [
                {"basisId": "barrage-open", "modelHour": hour} for hour in [-11, -10, -9, -8]
            ],
        },
        "heldOutReference": reference,
        "postRunHoldout": {
            "evaluable": False,
            "reason": "both endpoint bases are required at all five hours; only the open basis at minus 12 hours is sealed",
            "interpolatedFieldsCreated": False,
            "metricComparisonPerformed": False,
            "directInterpolatedErrorMapsCreated": False,
            "acceptanceResult": "not_evaluable_not_failed",
        },
        "resourceDiagnosis": {
            "closedS01WallSeconds": completed_by_id["barrage-closed-s01"]["wallSeconds"],
            "openS01WallSeconds": completed_by_id["barrage-open-s01"]["wallSeconds"],
            "closedS02WallSeconds": completed_by_id["barrage-closed-s02"]["wallSeconds"],
            "openS02WallSeconds": completed_by_id["barrage-open-s02"]["wallSeconds"],
            "openS03WallSeconds": completed_by_id["barrage-open-s03"]["wallSeconds"],
            "closedS02MarginToNumericalLimitSeconds": 18000 - completed_by_id["barrage-closed-s02"]["wallSeconds"],
            "closedS03LastRetainedThreePhysicalHoursWallSeconds": partial["lastRetainedWallSeconds"],
            "closedS03LinearFourHourProjectionWallSeconds": partial["lastRetainedWallSeconds"] * 4 / 3,
            "closedS03LinearProjectionExcessOverLimitSeconds": partial["lastRetainedWallSeconds"] * 4 / 3 - 18000,
            "interpretation": "fully closed barrage requires materially more solver steps and exceeded the fixed five-hour external wall limit before the minus 12 hour snapshot",
        },
        "contractGapsObserved": {
            "regionalMasksDigestLockedBeforeExecution": False,
            "regionalViewDefinitionsExistedBeforeExecution": True,
            "waterDepthAcceptanceThresholdDefined": False,
            "impact": "even a complete run would require these limitations to be disclosed in any strict four-region acceptance claim",
        },
        "safeguards": {
            "retryPerformed": False,
            "additionalPhysicalRunPerformed": False,
            "referenceS03RunPerformed": False,
            "publicSimulatorConnected": False,
            "mainMerged": False,
            "physicalValidationClaimAllowed": False,
            "dailyForecastClaimAllowed": False,
        },
    }
    write_json(root / args.output, analysis)
    write_json(result_root / "run-metadata.json", run)
    write_json(result_root / "artifact-inventory.json", artifact_api)
    write_json(result_root / "analysis.json", analysis)
    print(json.dumps(analysis, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
