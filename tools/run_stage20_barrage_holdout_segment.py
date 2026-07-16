#!/usr/bin/env python3
"""Fail-closed segment runner for the inactive barrage holdout contract."""

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
EXPECTED_WORKFLOW = "Stage 20 one-time barrage holdout"
CONTRACT_PATH = Path("config/stage20_barrage_holdout_contract_v1.json")
AUTHORIZATION_PATH = Path("config/stage20_barrage_holdout_authorization_v1.json")
GATE_PATH = Path("config/stage20_barrage_holdout_gate_v1.json")
ACTIVATION_PATH = Path("config/stage20_barrage_holdout_activation_v1.json")


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


def validate_contract(repo_root: Path) -> dict:
    contract = load_json(repo_root / CONTRACT_PATH)
    require(contract["schema"] == "onga-stage20-barrage-holdout-contract-v1", "contract schema mismatch")
    require(contract["status"] == "sealed_inactive_execution_requires_separate_visual_authorization", "contract status mismatch")
    require(contract["executionAuthorized"] is False, "contract may not self-authorize")
    for item in ("scopeApproval", "holdoutPlan", "basisPlan"):
        require(contract[item]["sha256"] == sha256(repo_root / contract[item]["path"]), f"{item} digest mismatch")
    require(contract["mesh"]["sha256"] == "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659", "mesh identity mismatch")
    require(contract["mesh"]["cellCount"] == 50199, "mesh cell count mismatch")
    require(contract["kernel"]["sha256"] == sha256(repo_root / contract["kernel"]["path"]), "kernel digest mismatch")
    require(contract["runner"]["sha256"] == sha256(repo_root / contract["runner"]["path"]), "runner digest mismatch")
    require(contract["runner"]["workflowSha256"] == sha256(repo_root / contract["runner"]["workflowPath"]), "workflow digest mismatch")
    require(contract["inputs"]["tideCandidateSha256"] == sha256(repo_root / contract["inputs"]["tideCandidate"]), "tide input digest mismatch")
    require(contract["inputs"]["waterMaskSha256"] == sha256(repo_root / contract["inputs"]["waterMask"]), "water mask digest mismatch")
    require(contract["basisScenarios"]["barrage-closed"]["barrage"]["scenario"] == "fully_closed", "closed basis changed")
    require(contract["basisScenarios"]["barrage-open"]["barrage"]["scenario"] == "uniform_100_percent", "open basis changed")
    require(contract["heldOutReference"]["openingFraction"] == 0.5, "held-out midpoint changed")
    require(contract["heldOutReference"]["usedToFitInterpolation"] is False, "held-out reference may not fit interpolation")
    require(contract["control"]["authorizationPresent"] is False, "authorization must be absent")
    require(contract["control"]["gatePresent"] is False, "gate must be absent")
    require(contract["control"]["activationPresent"] is False, "activation must be absent")
    jobs = contract["jobs"]
    require(len(jobs) == 8 and len({job["id"] for job in jobs}) == 8, "exactly eight unique jobs required")
    for basis in ("barrage-closed", "barrage-open"):
        basis_jobs = [job for job in jobs if job["basisId"] == basis]
        require(len(basis_jobs) == 4, f"four jobs required for {basis}")
        require([job["modelHourStart"] for job in basis_jobs] == [-24, -20, -16, -12], f"start hours changed for {basis}")
        require([job["modelHourEnd"] for job in basis_jobs] == [-20, -16, -12, -8], f"end hours changed for {basis}")
        require([job["snapshotModelHours"] for job in basis_jobs] == [[], [], [-12], [-11, -10, -9, -8]], f"snapshot hours changed for {basis}")
    require(all(job["targetPhysicalSeconds"] == 14400 for job in jobs), "segment duration changed")
    require(all(job["maximumNumericalWallSeconds"] == 18000 for job in jobs), "wall stop changed")
    require(contract["acceptance"]["maximumCfl"] == 0.95, "CFL acceptance changed")
    require(contract["acceptance"]["maximumRelativeMassBalanceError"] == 1e-8, "mass acceptance changed")
    require(contract["safeguards"]["automaticRetryAllowed"] is False, "automatic retry enabled")
    require(contract["safeguards"]["crossBasisRestartAllowed"] is False, "cross-basis restart enabled")
    return contract


def validate_control(repo_root: Path) -> tuple[dict, dict]:
    contract = validate_contract(repo_root)
    for path in (AUTHORIZATION_PATH, GATE_PATH, ACTIVATION_PATH):
        require((repo_root / path).is_file(), f"control file is absent: {path}")
    authorization = load_json(repo_root / AUTHORIZATION_PATH)
    gate = load_json(repo_root / GATE_PATH)
    activation = load_json(repo_root / ACTIVATION_PATH)
    require(authorization["schema"] == "onga-stage20-barrage-holdout-authorization-v1", "authorization schema mismatch")
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
    require(gate["schema"] == "onga-stage20-barrage-holdout-gate-v1" and gate["state"] == "active_one_time", "gate inactive")
    require(gate["authorizationId"] == authorization["authorizationId"], "gate authorization mismatch")
    require(gate["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "gate digest mismatch")
    require(activation["schema"] == "onga-stage20-barrage-holdout-activation-v1" and activation["state"] == "activate_exactly_once", "activation mismatch")
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
    atomic_json(output_dir / "evidence-manifest.json", {
        "schema": "onga-stage20-barrage-holdout-segment-evidence-v1",
        "status": "sealed_complete_not_physical_validation",
        "authorizationId": authorization_id,
        "jobId": job_id,
        "files": files,
        "physicalValidationClaimAllowed": False,
    })


def execute(repo_root: Path, output_dir: Path, contract: dict, authorization: dict, job: dict, input_restart: Path | None) -> dict:
    import numpy as np

    sys.path.insert(0, str(repo_root / "tools"))
    from stage19_solver_inputs import build_case_fields, classify_branch_ownership, load_water_mask, mesh_geometry, tide_anomaly_m
    from stage20_shallow_water_kernel_v3 import advance_one_step, build_solver_geometry

    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoints = output_dir / "checkpoints"
    snapshots = output_dir / "snapshots"
    checkpoints.mkdir()
    snapshots.mkdir()
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
    if job["predecessorJobId"] is None:
        require(input_restart is None, "first segment may not receive restart")
        start_eta = tide_anomaly_m(tide_clock_start, fields["tide"], tide_candidate)
        state = np.zeros((mesh_manifest["counts"]["cells"], 3), dtype=np.float64)
        state[:, 0] = np.maximum(start_eta - fields["bedElevationM"], 0.05)
        expected_volume = float(np.sum(state[:, 0] * areas))
        start_step = 0
    else:
        require(input_restart is not None and input_restart.is_file(), "required predecessor restart missing")
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
    next_checkpoint = float(contract["runPolicy"]["checkpointIntervalPhysicalSeconds"])
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
            checkpoint_path = checkpoints / f"checkpoint-{min(round(next_checkpoint / 3600), 4):02d}h.npz"
            save_checkpoint(checkpoint_path, state=state, elapsed_seconds=np.asarray(elapsed), step=np.asarray(step), expected_volume_m3=np.asarray(expected_volume), maximum_cfl=np.asarray(maximum_cfl), maximum_mass_error=np.asarray(maximum_mass_error))
            checkpoint_records.append({"path": str(checkpoint_path.relative_to(output_dir)), "sha256": sha256(checkpoint_path), "elapsedSeconds": elapsed, "step": step})
            atomic_json(output_dir / "progress.json", {"schema": "onga-stage20-barrage-holdout-progress-v1", "status": "complete" if elapsed >= target else "in_progress", "authorizationId": authorization["authorizationId"], "jobId": job["id"], "simulatedSeconds": elapsed, "wallSeconds": wall, "checkpoints": checkpoint_records, "snapshots": snapshot_records})
            next_checkpoint += float(contract["runPolicy"]["checkpointIntervalPhysicalSeconds"])

    final_restart = output_dir / "restart-final.npz"
    save_checkpoint(final_restart, state=state, elapsed_seconds=np.asarray(elapsed), step=np.asarray(step), expected_volume_m3=np.asarray(expected_volume), maximum_cfl=np.asarray(maximum_cfl), maximum_mass_error=np.asarray(maximum_mass_error))
    final_fields = output_dir / "segment-final-fields.npz"
    save_fields(final_fields, state)
    wall = time.monotonic() - wall_start
    report = {
        "schema": "onga-stage20-barrage-holdout-segment-report-v1",
        "status": "passed_numerical_checks_not_physical_validation",
        "authorizationId": authorization["authorizationId"],
        "platform": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version()},
        "run": {"jobId": job["id"], "basisId": job["basisId"], "modelHourStart": job["modelHourStart"], "modelHourEnd": job["modelHourEnd"], "simulatedSeconds": elapsed, "startStep": start_step, "endStep": step, "wallSeconds": wall},
        "diagnostics": {"inputRestartRelativeMassError": restart_mass_error, "maximumCfl": maximum_cfl, "maximumRelativeMassBalanceError": maximum_mass_error, "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()), "negativeDepthCount": int(np.sum(state[:, 0] < 0)), "maximumSpeedMPS": maximum_speed},
        "outputs": {"restart": "restart-final.npz", "restartSha256": sha256(final_restart), "fields": "segment-final-fields.npz", "fieldsSha256": sha256(final_fields), "checkpoints": checkpoint_records, "snapshots": snapshot_records},
        "safeguards": {"automaticRetryAllowed": False, "physicalValidationClaimAllowed": False, "publicSimulatorConnected": False},
    }
    atomic_json(output_dir / "segment-report.json", report)
    atomic_json(output_dir / "execution-receipt.json", {"schema": "onga-stage20-barrage-holdout-segment-receipt-v1", "authorizationId": authorization["authorizationId"], "authorizationSha256": sha256(repo_root / AUTHORIZATION_PATH), "executionContractSha256": sha256(repo_root / CONTRACT_PATH), "decisionImageSha256": authorization["decisionImage"]["sha256"], "jobId": job["id"], "predecessorJobId": job["predecessorJobId"], "githubRunId": os.environ.get("GITHUB_RUN_ID"), "githubSha": os.environ.get("GITHUB_SHA"), "automaticRetryAllowed": False})
    seal_evidence(output_dir, authorization["authorizationId"], job["id"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--job-id")
    parser.add_argument("--input-restart")
    parser.add_argument("--output-dir")
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        if args.contract_only:
            contract = validate_contract(repo_root)
            print(json.dumps({"status": "passed_inactive_contract_only", "jobCount": len(contract["jobs"]), "authorizationPresent": (repo_root / AUTHORIZATION_PATH).is_file(), "gatePresent": (repo_root / GATE_PATH).is_file(), "activationPresent": (repo_root / ACTIVATION_PATH).is_file(), "numericalStepCalled": False}, ensure_ascii=False, indent=2))
            return
        contract, authorization = validate_control(repo_root)
        if args.preflight_only:
            print(json.dumps({"status": "passed_active_one_time_preflight", "authorizationId": authorization["authorizationId"], "jobCount": len(contract["jobs"]), "numericalStepCalled": False}, ensure_ascii=False, indent=2))
            return
        require(args.job_id is not None and args.output_dir is not None, "--job-id and --output-dir are required")
        matches = [job for job in contract["jobs"] if job["id"] == args.job_id]
        require(len(matches) == 1, "job id is outside contract")
        restart = Path(args.input_restart) if args.input_restart else None
        print(json.dumps(execute(repo_root, Path(args.output_dir), contract, authorization, matches[0], restart), ensure_ascii=False, indent=2))
    except Exception as error:
        if args.output_dir:
            output = Path(args.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            atomic_json(output / "segment-stop.json", {"schema": "onga-stage20-barrage-holdout-stop-v1", "status": "stopped", "jobId": args.job_id, "error": str(error), "automaticRetryAllowed": False, "physicalValidationClaimAllowed": False})
        raise


if __name__ == "__main__":
    main()
