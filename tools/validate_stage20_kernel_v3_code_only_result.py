#!/usr/bin/env python3
"""Validate the retained Stage 20 kernel v3 code-only Linux result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    result_record = load(Path("config/stage20_kernel_v3_code_only_result_v1.json"))
    approval = load(Path("config/stage20_kernel_v3_code_only_approval_v1.json"))
    retained_path = Path(result_record["execution"]["retainedResult"])
    retained = load(retained_path)

    require(approval["status"] == "consumed_code_only_linux_x86_benchmark_completed", "approval not consumed")
    require(approval["oneTimeLinuxX86Benchmark"] is True, "one-time scope missing")
    require(approval["executionResult"]["githubRunId"] == 29410611389, "run id mismatch")
    require(result_record["execution"]["conclusion"] == "success", "workflow did not succeed")
    require(sha256(retained_path) == result_record["execution"]["retainedResultSha256"], "retained result digest mismatch")
    require(retained["platform"]["system"] == "Linux", "result is not Linux")
    require(retained["platform"]["machine"] == "x86_64", "result is not x86_64")
    require(retained["mesh"]["cells"] == 50199, "cell count mismatch")
    require(retained["mesh"]["barrageFaces"] == 68, "barrage count mismatch")
    require(retained["fixture"]["stepsPerRun"] == 300, "step count mismatch")
    require(retained["fixture"]["repetitionsPerKernel"] == 5, "repetition count mismatch")
    require(retained["equivalence"]["passed"] is True, "equivalence failed")
    require(retained["equivalence"]["maximumRelativeStateDifference"] <= 1e-12, "state difference exceeds tolerance")
    require(retained["equivalence"]["simulatedTimeDifferenceSeconds"] <= 1e-12, "simulated time differs")
    require(retained["timing"]["speedTargetPassed"] is True, "speed target failed")
    require(retained["timing"]["kernelV3Speedup"] >= 5.0, "speedup below 5x")
    require(retained["representativeRuns"]["kernelV3"]["nonFiniteValueCount"] == 0, "non-finite state")
    require(retained["representativeRuns"]["kernelV3"]["negativeDepthCount"] == 0, "negative depth")
    require(retained["safeguards"]["physicalPrecomputationExecuted"] is False, "physical precompute executed")
    require(retained["safeguards"]["newPhysicalPilotExecuted"] is False, "physical pilot executed")
    require(result_record["safeguards"]["physicalExecutionAuthorized"] is False, "physical execution authorized")
    require(result_record["safeguards"]["elevenBasisCampaignAuthorized"] is False, "basis campaign authorized")
    require(result_record["safeguards"]["mainMergeAuthorized"] is False, "main merge authorized")
    print("Stage 20 kernel v3 code-only result validation: PASS")


if __name__ == "__main__":
    main()
