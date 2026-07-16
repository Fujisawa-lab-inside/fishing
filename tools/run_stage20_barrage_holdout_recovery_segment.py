#!/usr/bin/env python3
"""Fail-closed runner for the one-time segmented barrage holdout recovery."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from run_stage20_hybrid_physical_pilot import PilotStop, atomic_json, load_json, save_checkpoint, sha256


EXPECTED_REPOSITORY = "Fujisawa-lab-inside/fishing"
EXPECTED_ACTOR = "RyusukeFujisawa"
EXPECTED_REF = "refs/heads/codex/stage19-public-inference-inputs"
EXPECTED_WORKFLOW = "Stage 20 one-time barrage holdout recovery"
CONTRACT_PATH = Path("config/stage20_barrage_holdout_recovery_contract_v1.json")
AUTHORIZATION_PATH = Path("config/stage20_barrage_holdout_recovery_authorization_v1.json")
GATE_PATH = Path("config/stage20_barrage_holdout_recovery_gate_v1.json")
ACTIVATION_PATH = Path("config/stage20_barrage_holdout_recovery_activation_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PilotStop(message)


def parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_mesh(repo_root: Path, contract: dict):
    import numpy as np

    manifest_path = repo_root / contract["mesh"]["manifest"]
    manifest = load_json(manifest_path)
    payload_path = manifest_path.parent / manifest["binary"]["url"]
    require(sha256(payload_path) == contract["mesh"]["sha256"], "mesh binary digest mismatch")
    payload = payload_path.read_bytes()
    arrays = {}
    for name, descriptor in manifest["arrays"].items():
        dtype = np.dtype("<i4") if descriptor["dtype"] == "int32" else np.dtype("u1")
        arrays[name] = np.frombuffer(
            payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])
    return manifest, arrays


def validate_manifest_files(directory: Path, manifest_path: Path, expected_job_id: str, expected_sha256: str | None = None) -> dict:
    require(manifest_path.is_file(), "input evidence manifest missing")
    if expected_sha256 is not None:
        require(sha256(manifest_path) == expected_sha256, "input evidence manifest digest mismatch")
    manifest = load_json(manifest_path)
    require(
        manifest["schema"]
        in {
            "onga-stage20-barrage-holdout-segment-evidence-v1",
            "onga-stage20-barrage-holdout-recovery-segment-evidence-v1",
        },
        "input evidence schema mismatch",
    )
    require(manifest["status"] == "sealed_complete_not_physical_validation", "input evidence is not sealed complete")
    require(manifest["jobId"] == expected_job_id, "input evidence job mismatch")
    listed = set()
    for item in manifest["files"]:
        relative = item["path"]
        require(relative not in listed, "duplicate input evidence path")
        listed.add(relative)
        path = directory / relative
        require(path.is_file(), f"input evidence file missing: {relative}")
        require(path.stat().st_size == item["byteLength"], f"input evidence length mismatch: {relative}")
        require(sha256(path) == item["sha256"], f"input evidence digest mismatch: {relative}")
    require("restart-final.npz" in listed and "segment-report.json" in listed, "input evidence lacks restart or report")
    return manifest


def validate_region_masks(repo_root: Path, contract: dict) -> None:
    masks = contract["regionalMasks"]
    manifest_path = repo_root / masks["manifest"]
    binary_path = repo_root / masks["binary"]
    require(sha256(manifest_path) == masks["manifestSha256"], "regional mask manifest digest mismatch")
    require(sha256(binary_path) == masks["binarySha256"], "regional mask binary digest mismatch")
    manifest = load_json(manifest_path)
    require(manifest["status"] == "digest_locked_before_recovery_execution", "regional masks are not locked")
    require(manifest["binary"]["sha256"] == masks["binarySha256"], "regional mask payload identity mismatch")
    payload = binary_path.read_bytes()
    require(len(manifest["views"]) == 4, "four regional masks required")
    for view in manifest["views"]:
        start = int(view["byteOffset"])
        end = start + int(view["byteLength"])
        require(0 <= start < end <= len(payload), "regional mask range invalid")
        require(sha256_bytes(payload[start:end]) == view["sha256"], f"regional mask digest mismatch: {view['id']}")


def sha256_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def validate_contract(repo_root: Path) -> dict:
    contract = load_json(repo_root / CONTRACT_PATH)
    require(contract["schema"] == "onga-stage20-barrage-holdout-recovery-contract-v1", "contract schema mismatch")
    require(contract["status"] == "sealed_inactive_execution_requires_separate_visual_authorization", "contract status mismatch")
    require(contract["executionAuthorized"] is False, "contract may not self-authorize")
    for item in ("sourceContract", "stoppedResult", "stoppedAnalysis"):
        require(contract[item]["sha256"] == sha256(repo_root / contract[item]["path"]), f"{item} digest mismatch")
    source_contract = load_json(repo_root / contract["sourceContract"]["path"])
    require(contract["basisScenarios"] == source_contract["basisScenarios"], "basis physics changed from original holdout")
    require(contract["inputs"] == source_contract["inputs"], "boundary inputs changed from original holdout")
    require(contract["mesh"]["sha256"] == "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659", "mesh identity mismatch")
    require(contract["mesh"]["cellCount"] == 50199, "mesh cell count mismatch")
    require(contract["kernel"]["sha256"] == sha256(repo_root / contract["kernel"]["path"]), "kernel digest mismatch")
    require(contract["runner"]["sha256"] == sha256(repo_root / contract["runner"]["path"]), "runner digest mismatch")
    require(contract["runner"]["workflowSha256"] == sha256(repo_root / contract["runner"]["workflowPath"]), "workflow digest mismatch")
    require(contract["inputs"]["tideCandidateSha256"] == sha256(repo_root / contract["inputs"]["tideCandidate"]), "tide input digest mismatch")
    require(contract["inputs"]["waterMaskSha256"] == sha256(repo_root / contract["inputs"]["waterMask"]), "water mask digest mismatch")
    validate_region_masks(repo_root, contract)
    for source in contract["retainedInputs"]:
        directory = repo_root / source["directory"]
        restart_path = directory / "restart-final.npz"
        manifest_path = directory / "evidence-manifest.json"
        report_path = directory / "segment-report.json"
        require(sha256(restart_path) == source["restartSha256"], "retained restart digest mismatch")
        require(sha256(report_path) == source["reportSha256"], "retained report digest mismatch")
        validate_manifest_files(directory, manifest_path, source["jobId"], source["evidenceManifestSha256"])
    jobs = contract["jobs"]
    expected = [
        ("barrage-closed-m16-m14", "barrage-closed", -16, -14, 7200, []),
        ("barrage-closed-m14-m12", "barrage-closed", -14, -12, 7200, [-12]),
        ("barrage-closed-m12-m10", "barrage-closed", -12, -10, 7200, [-11, -10]),
        ("barrage-closed-m10-m08", "barrage-closed", -10, -8, 7200, [-9, -8]),
        ("barrage-open-m12-m08", "barrage-open", -12, -8, 14400, [-11, -10, -9, -8]),
    ]
    actual = [(job["id"], job["basisId"], job["modelHourStart"], job["modelHourEnd"], job["targetPhysicalSeconds"], job["snapshotModelHours"]) for job in jobs]
    require(actual == expected, "recovery job scope changed")
    require(len({job["id"] for job in jobs}) == 5, "five unique recovery jobs required")
    require(all(job["maximumNumericalWallSeconds"] == 18000 for job in jobs), "wall stop changed")
    require(contract["acceptance"]["minimumSimulatedSecondsMustReachJobTarget"] is True, "simulated-time acceptance changed")
    require(contract["acceptance"]["maximumCfl"] == 0.95, "CFL acceptance changed")
    require(contract["acceptance"]["maximumRelativeMassBalanceError"] == 1e-8, "mass acceptance changed")
    require(contract["postRunHoldoutAcceptance"]["maximumDepthRmseM"] == 0.1, "depth RMSE threshold changed")
    require(contract["postRunHoldoutAcceptance"]["maximumAbsoluteDepthErrorM"] == 0.25, "depth maximum threshold changed")
    require(contract["safeguards"]["automaticRetryAllowed"] is False, "automatic retry enabled")
    require(contract["safeguards"]["paidResourceAllowed"] is False, "paid resource enabled")
    require(contract["safeguards"]["mainMergeAllowed"] is False, "main merge enabled")
    require(contract["control"]["authorizationPresent"] is False, "authorization must be absent")
    require(contract["control"]["gatePresent"] is False, "gate must be absent")
    require(contract["control"]["activationPresent"] is False, "activation must be absent")
    return contract


def validate_control(repo_root: Path) -> tuple[dict, dict]:
    contract = validate_contract(repo_root)
    for path in (AUTHORIZATION_PATH, GATE_PATH, ACTIVATION_PATH):
        require((repo_root / path).is_file(), f"control file is absent: {path}")
    authorization = load_json(repo_root / AUTHORIZATION_PATH)
    gate = load_json(repo_root / GATE_PATH)
    activation = load_json(repo_root / ACTIVATION_PATH)
    require(authorization["schema"] == "onga-stage20-barrage-holdout-recovery-authorization-v1", "authorization schema mismatch")
    require(authorization["authorized"] is True and authorization["oneTime"] is True, "authorization inactive")
    require(authorization["jobIds"] == [job["id"] for job in contract["jobs"]], "authorized job scope mismatch")
    now = dt.datetime.now(dt.timezone.utc)
    issued = parse_utc(authorization["issuedAtUtc"])
    not_after = parse_utc(authorization["notAfterUtc"])
    require(issued <= now <= not_after, "authorization outside valid window")
    require(0 < (not_after - issued).total_seconds() <= 86400, "authorization window exceeds 24 hours")
    require(authorization["executionContract"]["sha256"] == sha256(repo_root / CONTRACT_PATH), "authorized contract mismatch")
    require(authorization["decisionImage"]["sha256"] == sha256(repo_root / authorization["decisionImage"]["path"]), "decision image mismatch")
    require(authorization["automaticRetryAllowed"] is False and authorization["additionalRunAllowed"] is False, "retry safeguard mismatch")
    require(gate["schema"] == "onga-stage20-barrage-holdout-recovery-gate-v1" and gate["state"] == "active_one_time", "gate inactive")
    require(gate["authorizationId"] == authorization["authorizationId"], "gate authorization mismatch")
    require(gate["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "gate digest mismatch")
    require(activation["schema"] == "onga-stage20-barrage-holdout-recovery-activation-v1" and activation["state"] == "activate_exactly_once", "activation mismatch")
    require(activation["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "activation authorization mismatch")
    require(activation["gateSha256"] == sha256(repo_root / GATE_PATH), "activation gate mismatch")
    require(activation["preparedCommit"] == authorization["reviewedCodeCommit"], "prepared commit mismatch")
    require(os.environ.get("GITHUB_REPOSITORY") == EXPECTED_REPOSITORY, "repository identity mismatch")
    require(os.environ.get("GITHUB_ACTOR") == EXPECTED_ACTOR, "actor identity mismatch")
    require(os.environ.get("GITHUB_REF") == EXPECTED_REF, "ref identity mismatch")
    require(os.environ.get("GITHUB_WORKFLOW") == EXPECTED_WORKFLOW, "workflow identity mismatch")
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "workflow event mismatch")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "workflow rerun forbidden")
    require(os.environ.get("STAGE20_REVIEWED_COMMIT") == authorization["reviewedCodeCommit"], "reviewed base mismatch")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    reviewed = authorization["reviewedCodeCommit"]
    require(subprocess.run(["git", "merge-base", "--is-ancestor", reviewed, current], cwd=repo_root).returncode == 0, "reviewed commit not ancestor")
    changed = set(subprocess.check_output(["git", "diff", "--name-only", f"{reviewed}..{current}"], cwd=repo_root, text=True).splitlines())
    require(changed == {str(AUTHORIZATION_PATH), str(GATE_PATH), str(ACTIVATION_PATH)}, "activation commit contains unreviewed files")
    return contract, authorization


def save_fields(path: Path, state) -> None:
    import numpy as np

    depth = state[:, 0]
    u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    save_checkpoint(path, waterDepthM=depth, velocityUms=u, velocityVms=v)


def seal_evidence(output_dir: Path, authorization_id: str, job_id: str) -> None:
    files = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file() and item.name != "evidence-manifest.json"):
        files.append({"path": str(path.relative_to(output_dir)), "byteLength": path.stat().st_size, "sha256": sha256(path)})
    atomic_json(
        output_dir / "evidence-manifest.json",
        {
            "schema": "onga-stage20-barrage-holdout-recovery-segment-evidence-v1",
            "status": "sealed_complete_not_physical_validation",
            "authorizationId": authorization_id,
            "jobId": job_id,
            "files": files,
            "physicalValidationClaimAllowed": False,
        },
    )


def validate_input_chain(
    job: dict,
    input_restart: Path,
    input_report: Path,
    input_manifest: Path,
    current_authorization_id: str | None = None,
) -> tuple[str, str]:
    import numpy as np

    expected_job_id = job["input"]["jobId"]
    directory = input_restart.parent
    require(input_report.parent == directory and input_manifest.parent == directory, "input evidence files must share one directory")
    expected_manifest_sha = job["input"].get("evidenceManifestSha256")
    manifest = validate_manifest_files(directory, input_manifest, expected_job_id, expected_manifest_sha)
    report = load_json(input_report)
    require(
        report["schema"]
        in {
            "onga-stage20-barrage-holdout-segment-report-v1",
            "onga-stage20-barrage-holdout-recovery-segment-report-v1",
        },
        "input report schema mismatch",
    )
    require(report["status"] == "passed_numerical_checks_not_physical_validation", "input report status mismatch")
    require(report["run"]["jobId"] == expected_job_id, "input report job mismatch")
    require(report["run"]["basisId"] == job["basisId"], "input report basis mismatch")
    require(report["run"]["modelHourEnd"] == job["modelHourStart"], "input report model-hour chain mismatch")
    require(report["authorizationId"] == manifest["authorizationId"], "input report and evidence authorization mismatch")
    if job["input"]["kind"] == "recovery_predecessor":
        require(current_authorization_id is not None, "current recovery authorization is required")
        require(report["authorizationId"] == current_authorization_id, "cross-authorization recovery restart forbidden")
    restart_sha = sha256(input_restart)
    require(report["outputs"]["restart"] == "restart-final.npz", "input report restart path mismatch")
    require(report["outputs"]["restartSha256"] == restart_sha, "input restart does not match input report")
    restart = np.load(input_restart, allow_pickle=False)
    require(int(restart["step"]) == int(report["run"]["endStep"]), "input restart step does not match input report")
    expected_restart_sha = job["input"].get("restartSha256")
    if expected_restart_sha is not None:
        require(restart_sha == expected_restart_sha, "retained input restart digest mismatch")
    return restart_sha, sha256(input_manifest)


def execute(
    repo_root: Path,
    output_dir: Path,
    contract: dict,
    authorization: dict,
    job: dict,
    input_restart: Path,
    input_report: Path,
    input_manifest: Path,
) -> dict:
    import numpy as np

    sys.path.insert(0, str(repo_root / "tools"))
    from stage19_solver_inputs import build_case_fields, classify_branch_ownership, load_water_mask, mesh_geometry
    from stage20_shallow_water_kernel_v3 import advance_one_step, build_solver_geometry

    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoints = output_dir / "checkpoints"
    snapshots = output_dir / "snapshots"
    checkpoints.mkdir()
    snapshots.mkdir()
    input_restart_sha, input_manifest_sha = validate_input_chain(
        job,
        input_restart,
        input_report,
        input_manifest,
        authorization["authorizationId"],
    )
    mesh_manifest, package = load_mesh(repo_root, contract)
    _, mask = load_water_mask(repo_root / contract["inputs"]["waterMask"])
    field_geometry = mesh_geometry(package)
    owner = classify_branch_ownership(package, field_geometry)
    scenario = contract["basisScenarios"][job["basisId"]]
    fields = build_case_fields(scenario, package, mask, geometry=field_geometry, owner=owner)
    solver_geometry = build_solver_geometry(package)
    tide_candidate = load_json(repo_root / contract["inputs"]["tideCandidate"])
    areas = solver_geometry["areas"]
    tide_clock_start = float(job["modelHourStart"]) * 3600.0
    restart = np.load(input_restart, allow_pickle=False)
    state = restart["state"].astype(np.float64, copy=True)
    expected_volume = float(restart["expected_volume_m3"])
    start_step = int(restart["step"])
    require(state.shape == (mesh_manifest["counts"]["cells"], 3), "restart shape mismatch")
    require(np.isfinite(state).all() and np.all(state[:, 0] >= 0), "restart state invalid")
    start_volume = float(np.sum(state[:, 0] * areas))
    restart_mass_error = abs(start_volume - expected_volume) / max(abs(start_volume), 1.0)
    require(restart_mass_error <= contract["acceptance"]["maximumRelativeMassBalanceError"], "restart mass mismatch")
    elapsed = 0.0
    step = start_step
    maximum_cfl = 0.0
    maximum_mass_error = restart_mass_error
    maximum_speed = 0.0
    target = float(job["targetPhysicalSeconds"])
    checkpoint_interval = float(contract["runPolicy"]["checkpointIntervalPhysicalSeconds"])
    next_checkpoint = checkpoint_interval
    snapshot_offsets = {float((hour - job["modelHourStart"]) * 3600): hour for hour in job["snapshotModelHours"]}
    pending_snapshots = sorted(snapshot_offsets)
    checkpoint_records = []
    snapshot_records = []
    wall_start = time.monotonic()
    while elapsed < target:
        state, time_step, diagnostic = advance_one_step(state, tide_clock_start + elapsed, fields, solver_geometry, package, tide_candidate)
        elapsed += time_step
        step += 1
        expected_volume -= time_step * diagnostic["boundaryOutflowM3S"]
        actual_volume = float(np.sum(state[:, 0] * areas))
        mass_error = abs(actual_volume - expected_volume) / max(abs(start_volume), 1.0)
        maximum_cfl = max(maximum_cfl, float(diagnostic["maxCfl"]))
        maximum_mass_error = max(maximum_mass_error, mass_error)
        depth = state[:, 0]
        velocity = np.hypot(state[:, 1], state[:, 2]) / np.maximum(depth, 1e-12)
        maximum_speed = max(maximum_speed, float(velocity.max()))
        wall = time.monotonic() - wall_start
        require(np.isfinite(state).all(), "non-finite state")
        require(np.all(depth >= 0), "negative depth")
        require(maximum_cfl <= contract["acceptance"]["maximumCfl"], "CFL limit exceeded")
        require(maximum_mass_error <= contract["acceptance"]["maximumRelativeMassBalanceError"], "mass balance exceeded")
        require(wall <= job["maximumNumericalWallSeconds"], "numerical wall-time limit exceeded")
        while pending_snapshots and elapsed >= pending_snapshots[0]:
            offset = pending_snapshots.pop(0)
            model_hour = snapshot_offsets[offset]
            name = f"snapshot-{model_hour:+03d}h-fields.npz".replace("+", "p").replace("-", "m")
            path = snapshots / name
            save_fields(path, state)
            snapshot_records.append({"modelHour": model_hour, "path": str(path.relative_to(output_dir)), "sha256": sha256(path)})
        if elapsed >= next_checkpoint or elapsed >= target:
            ordinal = min(round(next_checkpoint / checkpoint_interval), round(target / checkpoint_interval))
            checkpoint_path = checkpoints / f"checkpoint-{ordinal:02d}h.npz"
            save_checkpoint(
                checkpoint_path,
                state=state,
                elapsed_seconds=np.asarray(elapsed),
                step=np.asarray(step),
                expected_volume_m3=np.asarray(expected_volume),
                maximum_cfl=np.asarray(maximum_cfl),
                maximum_mass_error=np.asarray(maximum_mass_error),
            )
            checkpoint_records.append({"path": str(checkpoint_path.relative_to(output_dir)), "sha256": sha256(checkpoint_path), "elapsedSeconds": elapsed, "step": step})
            atomic_json(
                output_dir / "progress.json",
                {
                    "schema": "onga-stage20-barrage-holdout-recovery-progress-v1",
                    "status": "complete" if elapsed >= target else "in_progress",
                    "authorizationId": authorization["authorizationId"],
                    "jobId": job["id"],
                    "simulatedSeconds": elapsed,
                    "wallSeconds": wall,
                    "checkpoints": checkpoint_records,
                    "snapshots": snapshot_records,
                },
            )
            next_checkpoint += checkpoint_interval

    final_restart = output_dir / "restart-final.npz"
    save_checkpoint(
        final_restart,
        state=state,
        elapsed_seconds=np.asarray(elapsed),
        step=np.asarray(step),
        expected_volume_m3=np.asarray(expected_volume),
        maximum_cfl=np.asarray(maximum_cfl),
        maximum_mass_error=np.asarray(maximum_mass_error),
    )
    final_fields = output_dir / "segment-final-fields.npz"
    save_fields(final_fields, state)
    wall = time.monotonic() - wall_start
    report = {
        "schema": "onga-stage20-barrage-holdout-recovery-segment-report-v1",
        "status": "passed_numerical_checks_not_physical_validation",
        "authorizationId": authorization["authorizationId"],
        "platform": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version()},
        "run": {
            "jobId": job["id"],
            "basisId": job["basisId"],
            "modelHourStart": job["modelHourStart"],
            "modelHourEnd": job["modelHourEnd"],
            "simulatedSeconds": elapsed,
            "startStep": start_step,
            "endStep": step,
            "wallSeconds": wall,
        },
        "input": {
            "jobId": job["input"]["jobId"],
            "restartSha256": input_restart_sha,
            "evidenceManifestSha256": input_manifest_sha,
        },
        "diagnostics": {
            "inputRestartRelativeMassError": restart_mass_error,
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
            "negativeDepthCount": int(np.sum(state[:, 0] < 0)),
            "maximumSpeedMPS": maximum_speed,
        },
        "outputs": {
            "restart": "restart-final.npz",
            "restartSha256": sha256(final_restart),
            "fields": "segment-final-fields.npz",
            "fieldsSha256": sha256(final_fields),
            "checkpoints": checkpoint_records,
            "snapshots": snapshot_records,
        },
        "safeguards": {"automaticRetryAllowed": False, "physicalValidationClaimAllowed": False, "publicSimulatorConnected": False},
    }
    atomic_json(output_dir / "segment-report.json", report)
    atomic_json(
        output_dir / "execution-receipt.json",
        {
            "schema": "onga-stage20-barrage-holdout-recovery-segment-receipt-v1",
            "authorizationId": authorization["authorizationId"],
            "authorizationSha256": sha256(repo_root / AUTHORIZATION_PATH),
            "executionContractSha256": sha256(repo_root / CONTRACT_PATH),
            "decisionImageSha256": authorization["decisionImage"]["sha256"],
            "jobId": job["id"],
            "predecessorJobId": job["input"]["jobId"],
            "inputRestartSha256": input_restart_sha,
            "inputEvidenceManifestSha256": input_manifest_sha,
            "githubRunId": os.environ.get("GITHUB_RUN_ID"),
            "githubSha": os.environ.get("GITHUB_SHA"),
            "automaticRetryAllowed": False,
        },
    )
    seal_evidence(output_dir, authorization["authorizationId"], job["id"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--job-id")
    parser.add_argument("--input-restart")
    parser.add_argument("--input-report")
    parser.add_argument("--input-evidence-manifest")
    parser.add_argument("--output-dir")
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        if args.contract_only:
            contract = validate_contract(repo_root)
            print(
                json.dumps(
                    {
                        "status": "passed_inactive_recovery_contract_only",
                        "jobCount": len(contract["jobs"]),
                        "authorizationPresent": (repo_root / AUTHORIZATION_PATH).is_file(),
                        "gatePresent": (repo_root / GATE_PATH).is_file(),
                        "activationPresent": (repo_root / ACTIVATION_PATH).is_file(),
                        "numericalStepCalled": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        contract, authorization = validate_control(repo_root)
        if args.preflight_only:
            print(json.dumps({"status": "passed_active_one_time_recovery_preflight", "authorizationId": authorization["authorizationId"], "jobCount": len(contract["jobs"]), "numericalStepCalled": False}, ensure_ascii=False, indent=2))
            return
        require(args.job_id is not None and args.output_dir is not None, "--job-id and --output-dir are required")
        require(args.input_restart is not None and args.input_report is not None and args.input_evidence_manifest is not None, "complete input evidence is required")
        matches = [job for job in contract["jobs"] if job["id"] == args.job_id]
        require(len(matches) == 1, "job id is outside contract")
        print(
            json.dumps(
                execute(
                    repo_root,
                    Path(args.output_dir),
                    contract,
                    authorization,
                    matches[0],
                    Path(args.input_restart),
                    Path(args.input_report),
                    Path(args.input_evidence_manifest),
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as error:
        if args.output_dir:
            output = Path(args.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            atomic_json(output / "segment-stop.json", {"schema": "onga-stage20-barrage-holdout-recovery-stop-v1", "status": "stopped", "jobId": args.job_id, "error": str(error), "automaticRetryAllowed": False, "physicalValidationClaimAllowed": False})
        raise


if __name__ == "__main__":
    main()
