#!/usr/bin/env python3
"""Checkpoint/restart control plane for Stage 20 response precomputation.

Only the deterministic fixture executor is connected.  A physical executor is
intentionally absent until a separate numerical-run authorization is recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


STATUS_SCHEMA = "onga-stage20-offline-precompute-checkpoint-v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def load_plan(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    plan = json.loads(raw)
    if plan.get("schema") not in {
        "onga-stage20-offline-response-precompute-plan-v1",
        "onga-stage20-offline-response-precompute-plan-v2",
    }:
        raise RuntimeError("precompute plan schema mismatch")
    if plan.get("execution", {}).get("authorized") is not False:
        raise RuntimeError("implementation plan must not authorize physical execution")
    identifiers = [job["id"] for job in plan["jobs"]]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("precompute job identifiers are not unique")
    return plan, sha256(raw)


def fixture_result(job: dict) -> bytes:
    return canonical_bytes({
        "schema": "onga-stage20-precompute-fixture-output-v1",
        "status": "synthetic_checkpoint_validation_only",
        "job": job,
        "physicalSolverExecuted": False,
    }) + b"\n"


def validate_completed(checkpoint_dir: Path, completed: list[dict]) -> None:
    for item in completed:
        output = checkpoint_dir / item["output"]
        if not output.is_file():
            raise RuntimeError(f"completed output is missing: {item['id']}")
        raw = output.read_bytes()
        if len(raw) != item["byteLength"] or sha256(raw) != item["sha256"]:
            raise RuntimeError(f"completed output digest mismatch: {item['id']}")


def run_plan(
    plan_path: Path,
    checkpoint_dir: Path,
    *,
    fixture: bool,
    stop_after: int | None = None,
) -> dict:
    if not fixture:
        raise RuntimeError("physical executor is not connected; use --fixture only")
    plan, plan_sha = load_plan(plan_path)
    status_path = checkpoint_dir / "checkpoint.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("schema") != STATUS_SCHEMA or status.get("planSha256") != plan_sha:
            raise RuntimeError("checkpoint does not belong to this plan")
    else:
        status = {
            "schema": STATUS_SCHEMA,
            "status": "in_progress",
            "plan": str(plan_path),
            "planSha256": plan_sha,
            "executor": "deterministic_fixture_only",
            "completed": [],
            "physicalSolverExecuted": False,
        }
    validate_completed(checkpoint_dir, status["completed"])
    completed_ids = {item["id"] for item in status["completed"]}
    skipped = 0
    executed = 0
    for job in plan["jobs"]:
        if job["id"] in completed_ids:
            skipped += 1
            continue
        if stop_after is not None and len(status["completed"]) >= stop_after:
            break
        raw = fixture_result(job)
        output_name = f"outputs/{job['id']}.json"
        atomic_write(checkpoint_dir / output_name, raw)
        status["completed"].append({
            "id": job["id"],
            "jobSha256": sha256(canonical_bytes(job)),
            "output": output_name,
            "byteLength": len(raw),
            "sha256": sha256(raw),
        })
        executed += 1
        atomic_write(status_path, json.dumps(status, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    status["status"] = "complete" if len(status["completed"]) == len(plan["jobs"]) else "in_progress"
    status["jobCount"] = len(plan["jobs"])
    status["completedJobCount"] = len(status["completed"])
    status["lastInvocation"] = {"executedJobCount": executed, "skippedCompletedJobCount": skipped}
    atomic_write(status_path, json.dumps(status, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="config/stage20_offline_response_precompute_plan_v2.json")
    parser.add_argument("--checkpoint-dir", required=True)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--stop-after", type=int)
    args = parser.parse_args()
    result = run_plan(
        Path(args.plan),
        Path(args.checkpoint_dir),
        fixture=args.fixture,
        stop_after=args.stop_after,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
