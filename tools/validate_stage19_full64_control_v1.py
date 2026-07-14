#!/usr/bin/env python3
"""Fail-closed control-plane validation for the one-time Stage 19 run."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SOURCE_STATEMENT = (
    "承認済み相対潮位M境界v1とStage19入力統合v1上で、この判断資料に示された64条件×500ステップを、"
    "承認後24時間以内に一回限り、完全な数値証拠と5枚の地図を作成するため実行してよい。"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-control] {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    auth_path = root / "config/stage19_full64_run_authorization_v1.json"
    gate_path = root / "config/stage19_full64_execution_gate_v1.json"
    auth, gate = load(auth_path), load(gate_path)
    require(auth["schema"] == "onga-stage19-full64-run-authorization-v1", "authorization schema")
    require(auth["authorized"] is True and auth["oneTime"] is True, "authorization inactive")
    require(auth["sourceStatement"] == SOURCE_STATEMENT, "source statement mismatch")
    issued = datetime.strptime(auth["issuedAtUtc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    not_after = datetime.strptime(auth["notAfterUtc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    require(issued <= now <= not_after, "authorization is outside its validity window")
    require(0 < (not_after - issued).total_seconds() <= 86400, "authorization window exceeds 24h")
    for key in ("executionContract", "solverIntegration", "decisionVisual"):
        item = auth[key]
        require(sha256(root / item["path"]) == item["sha256"], f"digest mismatch: {key}")
    for item in auth["executionCode"]:
        require(sha256(root / item["path"]) == item["sha256"], f"execution code changed: {item['path']}")
    require(gate == {
        "schema": "onga-stage19-full64-execution-gate-v1",
        "state": "active_one_time",
        "authorizationId": auth["authorizationId"],
        "authorizationSha256": sha256(auth_path),
        "automaticRetryAllowed": False,
        "additionalRunAllowed": False,
        "mainMergeAllowed": False,
    }, "gate content mismatch")
    reviewed = auth["reviewedCodeCommit"]
    require(len(reviewed) == 40, "reviewed commit must be full SHA")
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{reviewed}..HEAD"], cwd=root, text=True
    ).splitlines()
    require(set(changed) == {
        "config/stage19_full64_run_authorization_v1.json",
        "config/stage19_full64_execution_gate_v1.json",
    }, f"post-review changes exceed activation files: {changed}")
    require(auth["safeguards"] == {
        "automaticRetryAllowed": False,
        "additionalRunAllowed": False,
        "failedCasesMayBeImputed": False,
        "physicalValidationClaimAllowed": False,
        "publicSimulatorConnectionAllowed": False,
        "mainMergeAllowed": False,
    }, "authorization safeguards changed")
    print(json.dumps({
        "schema": "onga-stage19-full64-control-validation-v1",
        "status": "active_one_time",
        "authorizationId": auth["authorizationId"],
        "reviewedCodeCommit": reviewed,
        "notAfterUtc": auth["notAfterUtc"],
        "postReviewChangeCount": len(changed),
    }, indent=2))


if __name__ == "__main__":
    main()
