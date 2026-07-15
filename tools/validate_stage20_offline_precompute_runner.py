#!/usr/bin/env python3
"""Validate Stage 20 precompute checkpoint/restart without a physical run."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stage20_offline_precompute_runner import run_plan


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    plan_path = Path("config/stage20_offline_response_precompute_plan_v1.json")
    with tempfile.TemporaryDirectory(prefix="stage20-precompute-checkpoint-") as temporary:
        checkpoint = Path(temporary)
        first = run_plan(plan_path, checkpoint, fixture=True, stop_after=3)
        require(first["status"] == "in_progress", "first invocation unexpectedly completed")
        require(first["completedJobCount"] == 3, "first checkpoint count mismatch")
        first_hashes = {item["id"]: item["sha256"] for item in first["completed"]}
        resumed = run_plan(plan_path, checkpoint, fixture=True)
        require(resumed["status"] == "complete", "resumed invocation did not complete")
        require(resumed["completedJobCount"] == resumed["jobCount"] == 11, "resumed checkpoint count mismatch")
        require(resumed["lastInvocation"]["skippedCompletedJobCount"] == 3, "restart did not skip completed jobs")
        require(all(
            next(item for item in resumed["completed"] if item["id"] == identifier)["sha256"] == digest
            for identifier, digest in first_hashes.items()
        ), "restart changed a completed output")
        no_op = run_plan(plan_path, checkpoint, fixture=True)
        require(no_op["lastInvocation"]["executedJobCount"] == 0, "complete restart executed a job")
        corrupt = checkpoint / resumed["completed"][0]["output"]
        corrupt.write_text("corrupt\n", encoding="utf-8")
        corruption_rejected = False
        try:
            run_plan(plan_path, checkpoint, fixture=True)
        except RuntimeError as error:
            corruption_rejected = "digest mismatch" in str(error)
        require(corruption_rejected, "corrupt completed output was accepted")
        print(json.dumps({
            "schema": "onga-stage20-offline-precompute-runner-validation-v1",
            "status": "passed",
            "jobCount": resumed["jobCount"],
            "firstCheckpointCompleted": first["completedJobCount"],
            "restartSkipped": resumed["lastInvocation"]["skippedCompletedJobCount"],
            "completeRestartExecuted": no_op["lastInvocation"]["executedJobCount"],
            "corruptionRejected": corruption_rejected,
            "safeguards": {
                "fixtureOnly": True,
                "physicalSolverExecuted": False,
                "paidResourceProvisioned": False,
            },
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
