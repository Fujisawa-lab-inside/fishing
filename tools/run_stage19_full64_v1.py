#!/usr/bin/env python3
"""One-time Stage 19 full64 runner bound to the approved integration contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from stage19_shallow_water_kernel_v1 import build_solver_geometry, run_case
from stage19_solver_inputs import (
    build_case_fields,
    classify_branch_ownership,
    load_water_mask,
    mesh_geometry,
)


SOURCE_STATEMENT = (
    "承認済み相対潮位M境界v1とStage19入力統合v1上で、この判断資料に示された64条件×500ステップを、"
    "承認後24時間以内に一回限り、完全な数値証拠と5枚の地図を作成するため実行してよい。"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-full64] {message}")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json_atomic(path: str | Path, value: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def save_npz_atomic(path: str | Path, **arrays: np.ndarray) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(temporary, destination)


def parse_utc(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return parsed


def validate_authorization(
    authorization: dict,
    gate: dict,
    contract: dict,
    integration: dict,
    *,
    repo_root: Path,
) -> None:
    require(authorization["schema"] == "onga-stage19-full64-run-authorization-v1", "authorization schema")
    require(authorization["authorized"] is True and authorization["oneTime"] is True, "authorization inactive")
    require(authorization["sourceStatement"] == SOURCE_STATEMENT, "authorization statement mismatch")
    issued = parse_utc(authorization["issuedAtUtc"])
    not_after = parse_utc(authorization["notAfterUtc"])
    now = datetime.now(timezone.utc)
    require(issued <= now <= not_after, "authorization is not currently valid")
    require(0 < (not_after - issued).total_seconds() <= 86400, "authorization window exceeds 24 hours")
    require(authorization["executionContract"]["sha256"] == sha256(repo_root / authorization["executionContract"]["path"]),
            "authorization contract digest mismatch")
    require(authorization["executionContract"]["sha256"] == sha256(repo_root / "config/stage19_full64_execution_contract_v1.json"),
            "unexpected execution contract")
    require(authorization["solverIntegration"]["sha256"] == sha256(repo_root / authorization["solverIntegration"]["path"]),
            "authorization integration digest mismatch")
    require(authorization["decisionVisual"]["sha256"] == sha256(repo_root / authorization["decisionVisual"]["path"]),
            "authorization visual digest mismatch")
    require(contract["executionAuthorized"] is False and contract["authorization"] is None,
            "immutable contract must remain inactive")
    require(contract["solverIntegration"]["sha256"] == sha256(repo_root / "config/stage19_solver_integration_contract_v1.json"),
            "contract integration binding mismatch")
    require(integration["safeguards"]["full64ExecutionAuthorized"] is False,
            "integration contract must not self-authorize")
    require(gate["schema"] == "onga-stage19-full64-execution-gate-v1", "gate schema")
    require(gate["state"] == "active_one_time", "gate is not active")
    require(gate["authorizationId"] == authorization["authorizationId"], "gate authorization ID mismatch")
    require(gate["authorizationSha256"] == sha256(repo_root / "config/stage19_full64_run_authorization_v1.json"),
            "gate authorization digest mismatch")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False,
            "gate retry safeguard changed")
    for group in ("approvedInputs", "implementation"):
        for item in integration[group].values():
            if isinstance(item, dict) and "path" in item and "sha256" in item:
                require(sha256(repo_root / item["path"]) == item["sha256"], f"integration digest mismatch: {item['path']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh")
    parser.add_argument("--ensemble", default="config/stage19_provisional_ensemble_cases_v1.json")
    parser.add_argument("--candidate", default="config/stage19_m_boundary_tide_candidate_v1.json")
    parser.add_argument("--authorization", default="config/stage19_full64_run_authorization_v1.json")
    parser.add_argument("--gate", default="config/stage19_full64_execution_gate_v1.json")
    parser.add_argument("--contract", default="config/stage19_full64_execution_contract_v1.json")
    parser.add_argument("--integration", default="config/stage19_solver_integration_contract_v1.json")
    parser.add_argument("--manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--fields-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--progress-output", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    for output in (args.fields_output, args.report_output, args.progress_output):
        require(not Path(output).exists(), f"output already exists: {output}")

    contract = load_json(args.contract)
    integration = load_json(args.integration)
    authorization = load_json(args.authorization)
    gate = load_json(args.gate)
    validate_authorization(authorization, gate, contract, integration, repo_root=repo_root)
    require(sha256(args.mesh) == contract["mesh"]["sha256"], "canonical mesh digest mismatch")
    require(sha256(args.ensemble) == integration["approvedInputs"]["ensemble"]["sha256"], "ensemble digest mismatch")
    require(sha256(args.candidate) == integration["approvedInputs"]["tideCandidate"]["sha256"], "tide digest mismatch")

    ensemble = load_json(args.ensemble)
    candidate = load_json(args.candidate)
    require(ensemble["count"] == 64 and len(ensemble["cases"]) == 64, "exactly 64 cases required")
    mesh_file = np.load(args.mesh, allow_pickle=False)
    package = {key: mesh_file[key] for key in mesh_file.files}
    solver_geometry = build_solver_geometry(package)
    input_geometry = mesh_geometry(package)
    require(len(solver_geometry["areas"]) == 50129, "canonical cell count mismatch")
    _, water_mask = load_water_mask(args.manifest)
    owner = classify_branch_ownership(package, input_geometry)
    shore_cache: dict = {}

    depth_fields: list[np.ndarray] = []
    velocity_u_fields: list[np.ndarray] = []
    velocity_v_fields: list[np.ndarray] = []
    diagnostics: list[dict] = []
    started = time.perf_counter()
    attempted: list[str] = []
    progress = {
        "schema": "onga-stage19-full64-progress-v1",
        "status": "running",
        "authorizationId": authorization["authorizationId"],
        "requestedCaseCount": 64,
        "completedCaseCount": 0,
        "failedCaseCount": 0,
        "numericalCasesStarted": 0,
        "lastCompletedCaseId": None,
    }
    write_json_atomic(args.progress_output, progress)

    try:
        for case in ensemble["cases"]:
            case_id = case["caseId"]
            attempted.append(case_id)
            progress["numericalCasesStarted"] += 1
            fields = build_case_fields(
                case,
                package,
                water_mask,
                geometry=input_geometry,
                owner=owner,
                shore_cache=shore_cache,
            )
            result = run_case(
                case,
                fields,
                solver_geometry,
                package,
                candidate,
                steps=500,
                include_fields=True,
            )
            depth_fields.append(result.pop("waterDepthM"))
            velocity_u_fields.append(result.pop("velocityUms"))
            velocity_v_fields.append(result.pop("velocityVms"))
            diagnostics.append({"caseId": case_id, **result})
            progress["completedCaseCount"] += 1
            progress["lastCompletedCaseId"] = case_id
            progress["elapsedSeconds"] = time.perf_counter() - started
            write_json_atomic(args.progress_output, progress)
    except Exception as error:
        progress["status"] = "stopped"
        progress["failedCaseCount"] = 1
        progress["failure"] = {"caseId": attempted[-1] if attempted else None, "message": str(error)}
        progress["elapsedSeconds"] = time.perf_counter() - started
        write_json_atomic(args.progress_output, progress)
        raise

    depth = np.stack(depth_fields).astype(np.float64, copy=False)
    velocity_u = np.stack(velocity_u_fields).astype(np.float64, copy=False)
    velocity_v = np.stack(velocity_v_fields).astype(np.float64, copy=False)
    save_npz_atomic(
        args.fields_output,
        schema=np.array("onga-stage19-full64-fields-v1"),
        case_ids=np.asarray([case["caseId"] for case in ensemble["cases"]]),
        water_depth_m=depth,
        velocity_u_ms=velocity_u,
        velocity_v_ms=velocity_v,
        comparison_basis=np.array(contract["run"]["comparisonBasis"]),
        mesh_sha256=np.array(sha256(args.mesh)),
        ensemble_sha256=np.array(sha256(args.ensemble)),
        authorization_sha256=np.array(sha256(args.authorization)),
    )
    wall_seconds = time.perf_counter() - started
    peak_rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0
    report = {
        "schema": "onga-stage19-full64-run-report-v1",
        "status": "passed",
        "classification": "provisional_numerical_stability_and_spatial_output_evidence_only",
        "authorizationId": authorization["authorizationId"],
        "requestedCaseCount": 64,
        "completedCaseCount": 64,
        "failedCaseCount": 0,
        "stepsPerCase": 500,
        "attemptedCaseIds": attempted,
        "comparisonBasis": contract["run"]["comparisonBasis"],
        "nanCount": int(depth.size + velocity_u.size + velocity_v.size - np.isfinite(depth).sum() - np.isfinite(velocity_u).sum() - np.isfinite(velocity_v).sum()),
        "negativeDepthCount": int(np.sum(depth < 0)),
        "maxCfl": max(item["maxCfl"] for item in diagnostics),
        "maxAbsoluteMassBalanceError": max(item["maxAbsoluteMassBalanceError"] for item in diagnostics),
        "minimumDepthM": float(np.min(depth)),
        "minimumSimulatedTimeSeconds": min(item["simulatedTimeSeconds"] for item in diagnostics),
        "maximumSimulatedTimeSeconds": max(item["simulatedTimeSeconds"] for item in diagnostics),
        "wallSeconds": wall_seconds,
        "peakResidentMemoryMiB": peak_rss,
        "caseDiagnostics": diagnostics,
        "inputDigests": {
            "meshSha256": sha256(args.mesh),
            "ensembleSha256": sha256(args.ensemble),
            "candidateSha256": sha256(args.candidate),
            "authorizationSha256": sha256(args.authorization),
            "contractSha256": sha256(args.contract),
            "integrationSha256": sha256(args.integration),
        },
        "fieldArtifact": {
            "path": str(args.fields_output),
            "sha256": sha256(args.fields_output),
            "shape": {"caseCount": 64, "cellCount": 50129},
            "dtype": "float64",
        },
        "interpretationLimits": integration["interpretationLimits"],
        "safeguards": {
            "automaticRetryAllowed": False,
            "additionalRunAuthorized": False,
            "physicalValidationClaimAllowed": False,
            "publicSimulatorConnectionAllowed": False,
            "mainMergeAllowed": False,
        },
    }
    acceptance = contract["acceptance"]
    require(report["nanCount"] <= acceptance["nanCountMax"], "NaN acceptance failed")
    require(report["negativeDepthCount"] <= acceptance["negativeDepthCountMax"], "negative depth acceptance failed")
    require(report["maxCfl"] <= acceptance["maxCflMax"], "CFL acceptance failed")
    require(report["maxAbsoluteMassBalanceError"] <= acceptance["maxAbsoluteMassBalanceErrorMax"], "mass acceptance failed")
    require(report["wallSeconds"] <= acceptance["maxWallSeconds"], "wall time acceptance failed")
    require(report["peakResidentMemoryMiB"] <= acceptance["maxResidentMemoryMiB"], "memory acceptance failed")
    write_json_atomic(args.report_output, report)
    progress["status"] = "passed"
    progress["elapsedSeconds"] = wall_seconds
    progress["reportSha256"] = sha256(args.report_output)
    progress["fieldsSha256"] = sha256(args.fields_output)
    write_json_atomic(args.progress_output, progress)
    print(json.dumps({"status": "passed", "completedCaseCount": 64, "wallSeconds": wall_seconds}))


if __name__ == "__main__":
    main()
