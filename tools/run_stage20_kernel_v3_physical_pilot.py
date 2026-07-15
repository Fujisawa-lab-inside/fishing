#!/usr/bin/env python3
"""Fail-closed one-time Stage 20 mesh-v2/kernel-v3 physical pilot runner."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import run_stage20_physical_pilot_v2 as base
from run_stage20_hybrid_physical_pilot import PilotStop, atomic_json, load_json, sha256


EXPECTED_REPOSITORY = "Fujisawa-lab-inside/fishing"
EXPECTED_ACTOR = "RyusukeFujisawa"
EXPECTED_REF = "refs/heads/codex/stage19-public-inference-inputs"
EXPECTED_WORKFLOW = "Stage 20 one-time kernel v3 physical pilot"
CONTRACT_PATH = Path("config/stage20_kernel_v3_physical_pilot_contract_v1.json")
AUTHORIZATION_PATH = Path("config/stage20_kernel_v3_physical_pilot_authorization_v1.json")
GATE_PATH = Path("config/stage20_kernel_v3_physical_pilot_gate_v1.json")
ACTIVATION_PATH = Path("config/stage20_kernel_v3_physical_pilot_activation_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PilotStop(message)


def parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_contract(repo_root: Path) -> dict:
    contract = load_json(repo_root / CONTRACT_PATH)
    require(contract["schema"] == "onga-stage20-kernel-v3-physical-pilot-contract-v1", "contract schema mismatch")
    require(contract["status"] == "sealed_execution_requires_explicit_one_time_authorization", "contract status mismatch")
    require(contract["executionAuthorized"] is False, "contract may not self-authorize")
    require(contract["mesh"]["manifest"] == "public/data/onga/stage20/mesh-v2.json", "mesh path mismatch")
    require(contract["mesh"]["sha256"] == "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659", "mesh digest mismatch")
    require(contract["mesh"]["cellCount"] == 50199 and contract["mesh"]["barrageFaces"] == 68, "mesh identity mismatch")
    require(contract["kernel"]["path"] == "tools/stage20_shallow_water_kernel_v3.py", "kernel path mismatch")
    require(contract["kernel"]["sha256"] == sha256(repo_root / contract["kernel"]["path"]), "kernel digest mismatch")
    require(contract["kernel"]["codeOnlyResultSha256"] == sha256(repo_root / contract["kernel"]["codeOnlyResult"]), "code-only result digest mismatch")
    require(contract["runner"]["path"] == "tools/run_stage20_kernel_v3_physical_pilot.py", "runner path mismatch")
    require(contract["runner"]["sha256"] == sha256(repo_root / contract["runner"]["path"]), "runner digest mismatch")
    require(contract["runner"]["workflowPath"] == ".github/workflows/stage20-kernel-v3-physical-pilot.yml", "workflow path mismatch")
    require(contract["runner"]["workflowSha256"] == sha256(repo_root / contract["runner"]["workflowPath"]), "workflow digest mismatch")
    for item in contract["postprocessing"]:
        require(item["sha256"] == sha256(repo_root / item["path"]), f"postprocessing digest mismatch: {item['path']}")
    run = contract["run"]
    require(run["caseCount"] == 1 and run["targetPhysicalSeconds"] == 600, "run scope mismatch")
    require(run["checkpointIntervalPhysicalSeconds"] == 60, "checkpoint interval mismatch")
    require(run["maximumWallSeconds"] == 1200, "wall limit mismatch")
    require(run["oneTime"] is True and run["automaticRetryAllowed"] is False, "one-time safeguard mismatch")
    return contract


def validate_control(repo_root: Path) -> tuple[dict, dict, dict, dict]:
    contract = validate_contract(repo_root)
    for path in (AUTHORIZATION_PATH, GATE_PATH, ACTIVATION_PATH):
        require((repo_root / path).is_file(), f"control file is absent: {path}")
    authorization = load_json(repo_root / AUTHORIZATION_PATH)
    gate = load_json(repo_root / GATE_PATH)
    activation = load_json(repo_root / ACTIVATION_PATH)
    require(authorization["schema"] == "onga-stage20-kernel-v3-physical-pilot-authorization-v1", "authorization schema mismatch")
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
    require(gate["schema"] == "onga-stage20-kernel-v3-physical-pilot-gate-v1", "gate schema mismatch")
    require(gate["state"] == "active_one_time", "gate is not active")
    require(gate["authorizationId"] == authorization["authorizationId"], "gate authorization ID mismatch")
    require(gate["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "gate authorization digest mismatch")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False, "gate retry safeguard mismatch")
    require(activation["schema"] == "onga-stage20-kernel-v3-physical-pilot-activation-v1", "activation schema mismatch")
    require(activation["state"] == "activate_exactly_once", "activation state mismatch")
    require(activation["authorizationId"] == authorization["authorizationId"], "activation authorization mismatch")
    require(activation["authorizationSha256"] == sha256(repo_root / AUTHORIZATION_PATH), "activation authorization digest mismatch")
    require(activation["gateSha256"] == sha256(repo_root / GATE_PATH), "activation gate digest mismatch")
    require(activation["preparedCommit"] == authorization["reviewedCodeCommit"], "activation prepared commit mismatch")
    require(os.environ.get("GITHUB_REPOSITORY") == EXPECTED_REPOSITORY, "repository identity mismatch")
    require(os.environ.get("GITHUB_ACTOR") == EXPECTED_ACTOR, "actor identity mismatch")
    require(os.environ.get("GITHUB_REF") == EXPECTED_REF, "ref identity mismatch")
    require(os.environ.get("GITHUB_WORKFLOW") == EXPECTED_WORKFLOW, "workflow identity mismatch")
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "workflow event mismatch")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "rerun attempt is forbidden")
    require(os.environ.get("STAGE20_REVIEWED_COMMIT") == authorization["reviewedCodeCommit"], "push base is not the reviewed commit")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    reviewed = authorization["reviewedCodeCommit"]
    require(subprocess.run(["git", "merge-base", "--is-ancestor", reviewed, current], cwd=repo_root).returncode == 0, "reviewed code is not an ancestor")
    changed = subprocess.check_output(["git", "diff", "--name-only", f"{reviewed}..{current}"], cwd=repo_root, text=True).splitlines()
    allowed = {str(AUTHORIZATION_PATH), str(GATE_PATH), str(ACTIVATION_PATH)}
    require(set(changed) == allowed, "activation commit contains unreviewed or missing control files")
    return contract, authorization, gate, activation


def execute(repo_root: Path, output_dir: Path, contract: dict, authorization: dict) -> dict:
    sys.path.insert(0, str(repo_root / "tools"))
    import stage20_shallow_water_kernel_v3 as kernel_v3

    previous_module = sys.modules.get("stage20_shallow_water_kernel_v2")
    previous_paths = (base.CONTRACT_PATH, base.AUTHORIZATION_PATH, base.GATE_PATH)
    sys.modules["stage20_shallow_water_kernel_v2"] = kernel_v3
    base.CONTRACT_PATH = CONTRACT_PATH
    base.AUTHORIZATION_PATH = AUTHORIZATION_PATH
    base.GATE_PATH = GATE_PATH
    try:
        report = base.execute(repo_root, output_dir, contract, authorization)
    finally:
        base.CONTRACT_PATH, base.AUTHORIZATION_PATH, base.GATE_PATH = previous_paths
        if previous_module is None:
            sys.modules.pop("stage20_shallow_water_kernel_v2", None)
        else:
            sys.modules["stage20_shallow_water_kernel_v2"] = previous_module

    schema_updates = {
        "pilot-progress.json": "onga-stage20-kernel-v3-physical-pilot-progress-v1",
        "pilot-report.json": "onga-stage20-kernel-v3-physical-pilot-report-v1",
        "execution-receipt.json": "onga-stage20-kernel-v3-physical-pilot-receipt-v1",
    }
    for name, schema in schema_updates.items():
        path = output_dir / name
        payload = load_json(path)
        payload["schema"] = schema
        atomic_json(path, payload)
    report = load_json(output_dir / "pilot-report.json")
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
                "targetPhysicalSeconds": contract["run"]["targetPhysicalSeconds"],
                "numericalStepCalled": False,
                "authorizationPresent": (repo_root / AUTHORIZATION_PATH).is_file(),
                "gatePresent": (repo_root / GATE_PATH).is_file(),
                "activationPresent": (repo_root / ACTIVATION_PATH).is_file(),
            }, ensure_ascii=False, indent=2))
            return
        contract, authorization, _, _ = validate_control(repo_root)
        if args.preflight_only:
            print(json.dumps({
                "status": "passed_active_one_time_preflight",
                "authorizationId": authorization["authorizationId"],
                "targetPhysicalSeconds": contract["run"]["targetPhysicalSeconds"],
                "maximumWallSeconds": contract["run"]["maximumWallSeconds"],
                "numericalStepCalled": False,
            }, ensure_ascii=False, indent=2))
            return
        require(args.output_dir is not None, "--output-dir is required")
        result = execute(repo_root, Path(args.output_dir), contract, authorization)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        if args.output_dir:
            output = Path(args.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            atomic_json(output / "pilot-stop.json", {
                "schema": "onga-stage20-kernel-v3-physical-pilot-stop-v1",
                "status": "stopped",
                "error": str(error),
                "physicalValidationClaimAllowed": False,
            })
        raise


if __name__ == "__main__":
    main()
