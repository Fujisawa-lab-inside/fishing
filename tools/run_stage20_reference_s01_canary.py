#!/usr/bin/env python3
"""Fail-closed one-time runner for the reference-s01 eight-hour warmup canary."""

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
EXPECTED_WORKFLOW = "Stage 20 one-time reference s01 warmup canary"
CONTRACT_PATH = Path("config/stage20_reference_s01_canary_contract_v1.json")
AUTHORIZATION_PATH = Path("config/stage20_reference_s01_canary_authorization_v1.json")
GATE_PATH = Path("config/stage20_reference_s01_canary_gate_v1.json")
ACTIVATION_PATH = Path("config/stage20_reference_s01_canary_activation_v1.json")


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
    require(contract["schema"] == "onga-stage20-reference-s01-canary-contract-v1", "contract schema mismatch")
    require(contract["status"] == "sealed_execution_requires_separate_visual_authorization", "contract status mismatch")
    require(contract["executionAuthorized"] is False, "contract may not self-authorize")
    require(contract["plan"]["sha256"] == sha256(repo_root / contract["plan"]["path"]), "plan digest mismatch")
    require(contract["mesh"]["sha256"] == "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659", "mesh identity mismatch")
    require(contract["mesh"]["cellCount"] == 50199, "mesh cell count mismatch")
    require(contract["kernel"]["path"] == "tools/stage20_shallow_water_kernel_v3.py", "kernel path mismatch")
    require(contract["kernel"]["sha256"] == sha256(repo_root / contract["kernel"]["path"]), "kernel digest mismatch")
    require(contract["runner"]["path"] == "tools/run_stage20_reference_s01_canary.py", "runner path mismatch")
    require(contract["runner"]["sha256"] == sha256(repo_root / contract["runner"]["path"]), "runner digest mismatch")
    require(contract["runner"]["workflowSha256"] == sha256(repo_root / contract["runner"]["workflowPath"]), "workflow digest mismatch")
    run = contract["run"]
    require(run["jobId"] == "reference-s01", "job identity mismatch")
    require(run["modelHourStart"] == -24 and run["modelHourEnd"] == -16, "model-hour scope mismatch")
    require(run["tideCurveHourAtModelHourZero"] == 0.0, "tide clock anchor mismatch")
    require(run["targetPhysicalSeconds"] == 28800, "physical-time scope mismatch")
    require(run["checkpointIntervalPhysicalSeconds"] == 3600, "checkpoint interval mismatch")
    require(run["maximumNumericalWallSeconds"] == 18000, "wall-time limit mismatch")
    require(run["oneTime"] is True and run["automaticRetryAllowed"] is False, "one-time safeguard mismatch")
    require(contract["acceptance"]["checkpointCount"] == 8, "checkpoint acceptance mismatch")
    require(contract["safeguards"]["remainingSegmentsAllowed"] is False, "remaining segments enabled")
    return contract


def validate_control(repo_root: Path) -> tuple[dict, dict, dict, dict]:
    contract = validate_contract(repo_root)
    for path in (AUTHORIZATION_PATH, GATE_PATH, ACTIVATION_PATH):
        require((repo_root / path).is_file(), f"control file is absent: {path}")
    authorization = load_json(repo_root / AUTHORIZATION_PATH)
    gate = load_json(repo_root / GATE_PATH)
    activation = load_json(repo_root / ACTIVATION_PATH)
    require(authorization["schema"] == "onga-stage20-reference-s01-canary-authorization-v1", "authorization schema mismatch")
    require(authorization["authorized"] is True and authorization["oneTime"] is True, "authorization is inactive")
    require(authorization["automaticRetryAllowed"] is False and authorization["additionalRunAllowed"] is False, "authorization retry safeguard mismatch")
    now = dt.datetime.now(dt.timezone.utc)
    issued = parse_utc(authorization["issuedAtUtc"])
    not_after = parse_utc(authorization["notAfterUtc"])
    require(issued <= now <= not_after, "authorization is outside its valid time window")
    require(0 < (not_after - issued).total_seconds() <= 86400, "authorization window exceeds 24 hours")
    require(authorization["executionContract"]["path"] == str(CONTRACT_PATH), "authorization contract path mismatch")
    require(authorization["executionContract"]["sha256"] == sha256(repo_root / CONTRACT_PATH), "authorization contract digest mismatch")
    require(authorization["decisionImage"]["sha256"] == sha256(repo_root / authorization["decisionImage"]["path"]), "decision image digest mismatch")
    require(gate["schema"] == "onga-stage20-reference-s01-canary-gate-v1" and gate["state"] == "active_one_time", "gate is not active")
    require(gate["authorizationId"] == authorization["authorizationId"], "gate authorization mismatch")
    require(gate["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "gate authorization digest mismatch")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False, "gate retry safeguard mismatch")
    require(activation["schema"] == "onga-stage20-reference-s01-canary-activation-v1" and activation["state"] == "activate_exactly_once", "activation mismatch")
    require(activation["authorizationId"] == authorization["authorizationId"], "activation authorization mismatch")
    require(activation["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "activation authorization digest mismatch")
    require(activation["gateSha256"] == sha256(repo_root / GATE_PATH), "activation gate digest mismatch")
    require(activation["preparedCommit"] == authorization["reviewedCodeCommit"], "prepared commit mismatch")
    require(os.environ.get("GITHUB_REPOSITORY") == EXPECTED_REPOSITORY, "repository identity mismatch")
    require(os.environ.get("GITHUB_ACTOR") == EXPECTED_ACTOR, "actor identity mismatch")
    require(os.environ.get("GITHUB_REF") == EXPECTED_REF, "ref identity mismatch")
    require(os.environ.get("GITHUB_WORKFLOW") == EXPECTED_WORKFLOW, "workflow identity mismatch")
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "workflow event mismatch")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "rerun attempt is forbidden")
    require(os.environ.get("STAGE20_REVIEWED_COMMIT") == authorization["reviewedCodeCommit"], "push base is not reviewed commit")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    reviewed = authorization["reviewedCodeCommit"]
    require(subprocess.run(["git", "merge-base", "--is-ancestor", reviewed, current], cwd=repo_root).returncode == 0, "reviewed code is not an ancestor")
    changed = subprocess.check_output(["git", "diff", "--name-only", f"{reviewed}..{current}"], cwd=repo_root, text=True).splitlines()
    require(set(changed) == {str(AUTHORIZATION_PATH), str(GATE_PATH), str(ACTIVATION_PATH)}, "activation commit contains unreviewed files")
    return contract, authorization, gate, activation


def seal_evidence(output_dir: Path, authorization_id: str) -> None:
    files = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file() and item.name != "evidence-manifest.json"):
        files.append({
            "path": str(path.relative_to(output_dir)),
            "byteLength": path.stat().st_size,
            "sha256": sha256(path),
        })
    atomic_json(output_dir / "evidence-manifest.json", {
        "schema": "onga-stage20-reference-s01-canary-evidence-v1",
        "status": "sealed_complete_not_physical_validation",
        "authorizationId": authorization_id,
        "files": files,
        "physicalValidationClaimAllowed": False,
    })


def execute(repo_root: Path, output_dir: Path, contract: dict, authorization: dict) -> dict:
    import numpy as np

    sys.path.insert(0, str(repo_root / "tools"))
    from stage19_solver_inputs import build_case_fields, classify_branch_ownership, load_water_mask, mesh_geometry, tide_anomaly_m
    from stage20_shallow_water_kernel_v3 import advance_one_step, build_solver_geometry

    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoints = output_dir / "checkpoints"
    checkpoints.mkdir()
    mesh_manifest, package = load_mesh(repo_root, contract)
    _, mask = load_water_mask(repo_root / "data/onga_unified_water_manifest_r3.json")
    field_geometry = mesh_geometry(package)
    owner = classify_branch_ownership(package, field_geometry)
    fields = build_case_fields(contract["scenario"], package, mask, geometry=field_geometry, owner=owner)
    solver_geometry = build_solver_geometry(package)
    tide_candidate = load_json(repo_root / "config/stage19_m_boundary_tide_candidate_v1.json")
    tide_clock_start = (
        float(contract["run"]["modelHourStart"])
        + float(contract["run"]["tideCurveHourAtModelHourZero"])
    ) * 3600.0
    start_eta = tide_anomaly_m(tide_clock_start, fields["tide"], tide_candidate)
    state = np.zeros((mesh_manifest["counts"]["cells"], 3), dtype=np.float64)
    state[:, 0] = np.maximum(start_eta - fields["bedElevationM"], 0.05)
    areas = solver_geometry["areas"]
    initial_volume = float(np.sum(state[:, 0] * areas))
    expected_volume = initial_volume
    elapsed = 0.0
    step = 0
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_speed = 0.0
    next_checkpoint = float(contract["run"]["checkpointIntervalPhysicalSeconds"])
    target = float(contract["run"]["targetPhysicalSeconds"])
    wall_start = time.monotonic()
    checkpoint_records = []
    while elapsed < target:
        state, time_step, diagnostic = advance_one_step(
            state, tide_clock_start + elapsed, fields, solver_geometry, package, tide_candidate
        )
        elapsed += time_step
        step += 1
        expected_volume -= time_step * diagnostic["boundaryOutflowM3S"]
        actual_volume = float(np.sum(state[:, 0] * areas))
        mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
        maximum_cfl = max(maximum_cfl, float(diagnostic["maxCfl"]))
        maximum_mass_error = max(maximum_mass_error, mass_error)
        depth = state[:, 0]
        velocity = np.hypot(state[:, 1], state[:, 2]) / np.maximum(depth, 1e-12)
        maximum_speed = max(maximum_speed, float(velocity.max()))
        wall = time.monotonic() - wall_start
        require(np.isfinite(state).all(), "non-finite state")
        require(np.all(depth >= 0), "negative depth")
        require(maximum_cfl <= contract["acceptance"]["maximumCfl"], "CFL limit exceeded")
        require(maximum_mass_error <= contract["acceptance"]["maximumRelativeMassBalanceError"], "mass-balance limit exceeded")
        require(wall <= contract["run"]["maximumNumericalWallSeconds"], "numerical wall-time limit exceeded")
        if elapsed >= next_checkpoint or elapsed >= target:
            checkpoint_path = checkpoints / f"checkpoint-{min(round(next_checkpoint / 3600), 8):02d}h.npz"
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
            atomic_json(output_dir / "progress.json", {
                "schema": "onga-stage20-reference-s01-canary-progress-v1",
                "status": "complete" if elapsed >= target else "in_progress",
                "authorizationId": authorization["authorizationId"],
                "simulatedSeconds": elapsed,
                "stepsCompleted": step,
                "wallSeconds": wall,
                "checkpoints": checkpoint_records,
            })
            next_checkpoint += float(contract["run"]["checkpointIntervalPhysicalSeconds"])

    final_checkpoint = output_dir / "restart-final.npz"
    save_checkpoint(
        final_checkpoint,
        state=state,
        elapsed_seconds=np.asarray(elapsed),
        step=np.asarray(step),
        expected_volume_m3=np.asarray(expected_volume),
        maximum_cfl=np.asarray(maximum_cfl),
        maximum_mass_error=np.asarray(maximum_mass_error),
    )
    depth = state[:, 0]
    u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    final_fields = output_dir / "segment-final-fields.npz"
    save_checkpoint(final_fields, waterDepthM=depth, velocityUms=u, velocityVms=v)
    wall = time.monotonic() - wall_start
    report = {
        "schema": "onga-stage20-reference-s01-canary-report-v1",
        "status": "passed_numerical_checks_not_physical_validation",
        "authorizationId": authorization["authorizationId"],
        "platform": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version()},
        "run": {"jobId": "reference-s01", "modelHourStart": -24, "modelHourEnd": -16, "targetPhysicalSeconds": target, "simulatedSeconds": elapsed, "stepsCompleted": step, "wallSeconds": wall},
        "diagnostics": {"maximumCfl": maximum_cfl, "maximumRelativeMassBalanceError": maximum_mass_error, "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()), "negativeDepthCount": int(np.sum(depth < 0)), "maximumSpeedMPS": maximum_speed},
        "outputs": {"restart": "restart-final.npz", "restartSha256": sha256(final_checkpoint), "fields": "segment-final-fields.npz", "fieldsSha256": sha256(final_fields), "checkpoints": checkpoint_records},
        "safeguards": {"remainingSegmentsAuthorized": False, "physicalValidationClaimAllowed": False, "publicSimulatorConnected": False},
    }
    atomic_json(output_dir / "segment-report.json", report)
    atomic_json(output_dir / "execution-receipt.json", {
        "schema": "onga-stage20-reference-s01-canary-receipt-v1",
        "authorizationId": authorization["authorizationId"],
        "authorizationSha256": sha256(repo_root / AUTHORIZATION_PATH),
        "executionContractSha256": sha256(repo_root / CONTRACT_PATH),
        "decisionImageSha256": authorization["decisionImage"]["sha256"],
        "githubRunId": os.environ.get("GITHUB_RUN_ID"),
        "githubSha": os.environ.get("GITHUB_SHA"),
        "automaticRetryAllowed": False,
    })
    seal_evidence(output_dir, authorization["authorizationId"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir")
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        if args.contract_only:
            contract = validate_contract(repo_root)
            print(json.dumps({
                "status": "passed_inactive_contract_only",
                "jobId": contract["run"]["jobId"],
                "targetPhysicalSeconds": contract["run"]["targetPhysicalSeconds"],
                "maximumNumericalWallSeconds": contract["run"]["maximumNumericalWallSeconds"],
                "numericalStepCalled": False,
                "authorizationPresent": (repo_root / AUTHORIZATION_PATH).is_file(),
                "gatePresent": (repo_root / GATE_PATH).is_file(),
                "activationPresent": (repo_root / ACTIVATION_PATH).is_file(),
            }, ensure_ascii=False, indent=2))
            return
        contract, authorization, _, _ = validate_control(repo_root)
        if args.preflight_only:
            print(json.dumps({"status": "passed_active_one_time_preflight", "authorizationId": authorization["authorizationId"], "numericalStepCalled": False}, ensure_ascii=False, indent=2))
            return
        require(args.output_dir is not None, "--output-dir is required")
        print(json.dumps(execute(repo_root, Path(args.output_dir), contract, authorization), ensure_ascii=False, indent=2))
    except Exception as error:
        if args.output_dir:
            output = Path(args.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            atomic_json(output / "segment-stop.json", {
                "schema": "onga-stage20-reference-s01-canary-stop-v1",
                "status": "stopped",
                "error": str(error),
                "remainingSegmentsAuthorized": False,
                "physicalValidationClaimAllowed": False,
            })
        raise


if __name__ == "__main__":
    main()
