#!/usr/bin/env python3
"""Fail-closed one-time Stage 20 physical-time pilot runner."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path


SOURCE_STATEMENT = "GitHub提供Linux runnerで1条件×10分を一回だけ実行"
EXPECTED_REPOSITORY = "Fujisawa-lab-inside/fishing"
EXPECTED_ACTOR = "RyusukeFujisawa"
EXPECTED_REF = "refs/heads/codex/stage19-public-inference-inputs"
EXPECTED_WORKFLOW = "Stage 20 one-time hybrid physical pilot"
CONTRACT_PATH = Path("config/stage20_hybrid_physical_pilot_contract_v1.json")
AUTHORIZATION_PATH = Path("config/stage20_hybrid_physical_pilot_authorization_v1.json")
GATE_PATH = Path("config/stage20_hybrid_physical_pilot_gate_v1.json")


class PilotStop(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PilotStop(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_control(repo_root: Path, *, local: bool = False) -> tuple[dict, dict, dict]:
    contract = load_json(repo_root / CONTRACT_PATH)
    authorization = load_json(repo_root / AUTHORIZATION_PATH)
    gate = load_json(repo_root / GATE_PATH)
    require(contract["schema"] == "onga-stage20-hybrid-physical-pilot-contract-v1", "contract schema mismatch")
    require(contract["status"] == "sealed_execution_requires_authorization", "contract status mismatch")
    require(contract["executionAuthorized"] is False, "contract may not self-authorize")
    require(contract["sourceStatement"] == SOURCE_STATEMENT, "contract source statement mismatch")
    require(authorization["schema"] == "onga-stage20-hybrid-physical-pilot-authorization-v1", "authorization schema mismatch")
    require(authorization["authorized"] is True and authorization["oneTime"] is True, "authorization is inactive")
    require(authorization["sourceStatement"] == SOURCE_STATEMENT, "authorization statement mismatch")
    now = dt.datetime.now(dt.timezone.utc)
    issued = parse_utc(authorization["issuedAtUtc"])
    not_after = parse_utc(authorization["notAfterUtc"])
    require(issued <= now <= not_after, "authorization is outside its valid time window")
    require(0 < (not_after - issued).total_seconds() <= 86400, "authorization window exceeds 24 hours")
    require(authorization["executionContract"]["path"] == str(CONTRACT_PATH), "authorization contract path mismatch")
    require(authorization["executionContract"]["sha256"] == sha256(repo_root / CONTRACT_PATH), "authorization contract digest mismatch")
    require(authorization["decisionImage"]["sha256"] == sha256(repo_root / authorization["decisionImage"]["path"]), "decision image digest mismatch")
    require(gate["schema"] == "onga-stage20-hybrid-physical-pilot-gate-v1", "gate schema mismatch")
    require(gate["state"] == "active_one_time", "gate is not active")
    require(gate["authorizationId"] == authorization["authorizationId"], "gate authorization ID mismatch")
    require(gate["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "gate authorization digest mismatch")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False, "retry safeguard changed")
    run = contract["run"]
    require(run["caseCount"] == 1 and run["targetPhysicalSeconds"] == 600, "pilot run scope mismatch")
    require(run["checkpointIntervalPhysicalSeconds"] == 60, "checkpoint interval mismatch")
    require(run["maximumWallSeconds"] == 5400, "wall limit mismatch")
    require(contract["mesh"]["sha256"] == "717a076b901c29763b3b565250e68e15ad72fe2b87306ebd41f35b9dd37f4347", "mesh identity mismatch")
    if not local:
        require(os.environ.get("GITHUB_REPOSITORY") == EXPECTED_REPOSITORY, "repository identity mismatch")
        require(os.environ.get("GITHUB_ACTOR") == EXPECTED_ACTOR, "actor identity mismatch")
        require(os.environ.get("GITHUB_REF") == EXPECTED_REF, "ref identity mismatch")
        require(os.environ.get("GITHUB_WORKFLOW") == EXPECTED_WORKFLOW, "workflow identity mismatch")
        require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "rerun attempt is forbidden")
        current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
        reviewed = authorization["reviewedCodeCommit"]
        require(subprocess.run(["git", "merge-base", "--is-ancestor", reviewed, current], cwd=repo_root).returncode == 0, "reviewed code is not an ancestor")
        changed = subprocess.check_output(["git", "diff", "--name-only", f"{reviewed}..{current}"], cwd=repo_root, text=True).splitlines()
        require(set(changed) <= {str(AUTHORIZATION_PATH), str(GATE_PATH)}, "unreviewed code changed after authorization")
    return contract, authorization, gate


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def save_checkpoint(path: Path, **arrays) -> None:
    import numpy as np

    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(temporary, path)


def load_mesh(repo_root: Path):
    import math
    import numpy as np

    manifest_path = repo_root / "public/data/onga/stage20/mesh-v1.json"
    manifest = load_json(manifest_path)
    payload_path = manifest_path.parent / manifest["binary"]["url"]
    require(sha256(payload_path) == manifest["binary"]["sha256"], "browser mesh payload digest mismatch")
    payload = payload_path.read_bytes()
    arrays = {}
    for name, descriptor in manifest["arrays"].items():
        dtype = np.int32 if descriptor["dtype"] == "int32" else np.uint8
        arrays[name] = np.frombuffer(
            payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])
    return manifest, arrays


def execute(repo_root: Path, output_dir: Path, contract: dict, authorization: dict) -> dict:
    import numpy as np

    sys.path.insert(0, str(repo_root / "tools"))
    from stage19_shallow_water_kernel_v1 import advance_one_step, build_solver_geometry
    from stage19_solver_inputs import (
        build_case_fields,
        classify_branch_ownership,
        load_water_mask,
        mesh_geometry,
        tide_anomaly_m,
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoints = output_dir / "checkpoints"
    checkpoints.mkdir()
    mesh_manifest, package = load_mesh(repo_root)
    _, mask = load_water_mask(repo_root / "data/onga_unified_water_manifest_r3.json")
    field_geometry = mesh_geometry(package)
    owner = classify_branch_ownership(package, field_geometry)
    scenario = contract["scenario"]
    fields = build_case_fields(scenario, package, mask, geometry=field_geometry, owner=owner)
    solver_geometry = build_solver_geometry(package)
    tide_candidate = load_json(repo_root / "config/stage19_m_boundary_tide_candidate_v1.json")
    tide_clock_start = float(contract["run"]["tideCurveStartHour"]) * 3600.0
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
    progress_path = output_dir / "pilot-progress.json"
    checkpoint_records = []
    while elapsed < target:
        state, time_step, diagnostic = advance_one_step(
            state,
            tide_clock_start + elapsed,
            fields,
            solver_geometry,
            package,
            tide_candidate,
        )
        elapsed += time_step
        step += 1
        expected_volume -= time_step * diagnostic["boundaryOutflowM3S"]
        actual_volume = float(np.sum(state[:, 0] * areas))
        mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
        maximum_cfl = max(maximum_cfl, float(diagnostic["maxCfl"]))
        maximum_mass_error = max(maximum_mass_error, mass_error)
        velocity = np.hypot(state[:, 1], state[:, 2]) / np.maximum(state[:, 0], 1e-12)
        maximum_speed = max(maximum_speed, float(velocity.max()))
        wall = time.monotonic() - wall_start
        require(np.isfinite(state).all(), "non-finite state")
        require(np.all(state[:, 0] >= 0), "negative depth")
        require(maximum_cfl <= contract["acceptance"]["maximumCfl"], "CFL limit exceeded")
        require(maximum_mass_error <= contract["acceptance"]["maximumRelativeMassBalanceError"], "mass-balance limit exceeded")
        require(wall <= contract["run"]["maximumWallSeconds"], "wall-time limit exceeded")
        if elapsed >= next_checkpoint or elapsed >= target:
            checkpoint_name = f"checkpoint-{min(int(next_checkpoint), 600):04d}s.npz"
            checkpoint_path = checkpoints / checkpoint_name
            save_checkpoint(
                checkpoint_path,
                state=state,
                elapsed_seconds=np.asarray(elapsed),
                step=np.asarray(step),
                expected_volume_m3=np.asarray(expected_volume),
                maximum_cfl=np.asarray(maximum_cfl),
                maximum_mass_error=np.asarray(maximum_mass_error),
            )
            checkpoint_records.append({
                "path": f"checkpoints/{checkpoint_name}",
                "sha256": sha256(checkpoint_path),
                "elapsedSeconds": elapsed,
                "step": step,
            })
            progress = {
                "schema": "onga-stage20-hybrid-physical-pilot-progress-v1",
                "status": "complete" if elapsed >= target else "in_progress",
                "authorizationId": authorization["authorizationId"],
                "targetPhysicalSeconds": target,
                "simulatedSeconds": elapsed,
                "stepsCompleted": step,
                "wallSeconds": wall,
                "maximumCfl": maximum_cfl,
                "maximumRelativeMassBalanceError": maximum_mass_error,
                "checkpoints": checkpoint_records,
            }
            atomic_json(progress_path, progress)
            next_checkpoint += float(contract["run"]["checkpointIntervalPhysicalSeconds"])

    depth = state[:, 0]
    u = np.divide(state[:, 1], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    v = np.divide(state[:, 2], depth, out=np.zeros_like(depth), where=depth > 1e-12)
    fields_path = output_dir / "pilot-final-fields.npz"
    save_checkpoint(fields_path, waterDepthM=depth, velocityUms=u, velocityVms=v)
    wall = time.monotonic() - wall_start
    report = {
        "schema": "onga-stage20-hybrid-physical-pilot-report-v1",
        "status": "passed_numerical_checks_not_physical_validation",
        "authorizationId": authorization["authorizationId"],
        "sourceStatement": SOURCE_STATEMENT,
        "platform": {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version()},
        "mesh": {"sha256": mesh_manifest["binary"]["sha256"], "cellCount": mesh_manifest["counts"]["cells"]},
        "run": {"targetPhysicalSeconds": target, "simulatedSeconds": elapsed, "stepsCompleted": step, "wallSeconds": wall},
        "diagnostics": {
            "maximumCfl": maximum_cfl,
            "maximumRelativeMassBalanceError": maximum_mass_error,
            "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
            "negativeDepthCount": int(np.sum(depth < 0)),
            "minimumDepthM": float(depth.min()),
            "maximumDepthM": float(depth.max()),
            "maximumSpeedMPS": maximum_speed,
        },
        "outputs": {"fields": "pilot-final-fields.npz", "fieldsSha256": sha256(fields_path), "checkpoints": checkpoint_records},
        "safeguards": {"inferredInputsOnly": True, "physicalValidationClaimAllowed": False, "publicSimulatorConnected": False},
    }
    atomic_json(output_dir / "pilot-report.json", report)
    atomic_json(output_dir / "execution-receipt.json", {
        "schema": "onga-stage20-hybrid-physical-pilot-receipt-v1",
        "authorizationId": authorization["authorizationId"],
        "authorizationSha256": sha256(repo_root / AUTHORIZATION_PATH),
        "executionContractSha256": sha256(repo_root / CONTRACT_PATH),
        "decisionImageSha256": authorization["decisionImage"]["sha256"],
        "githubRunId": os.environ.get("GITHUB_RUN_ID"),
        "githubSha": os.environ.get("GITHUB_SHA"),
        "automaticRetryAllowed": False,
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        contract, authorization, _ = validate_control(repo_root, local=args.local)
        if args.preflight_only:
            print(json.dumps({"status": "passed", "scope": "one_case_600_physical_seconds_one_time", "numericalStepCalled": False}, ensure_ascii=False))
            return
        require(args.output_dir is not None, "--output-dir is required")
        result = execute(repo_root, Path(args.output_dir), contract, authorization)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        if args.output_dir:
            output = Path(args.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            atomic_json(output / "pilot-stop.json", {
                "schema": "onga-stage20-hybrid-physical-pilot-stop-v1",
                "status": "stopped",
                "error": str(error),
                "physicalValidationClaimAllowed": False,
            })
        raise


if __name__ == "__main__":
    main()
