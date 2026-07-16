#!/usr/bin/env python3
"""Validate the stopped Stage 20 barrage holdout result package."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    result = load_json("config/stage20_barrage_holdout_result_v1.json")
    analysis = load_json("config/stage20_barrage_holdout_analysis_v1.json")
    gate = load_json("config/stage20_barrage_holdout_gate_v1.json")
    require(result["schema"] == "onga-stage20-barrage-holdout-result-v1", "result schema mismatch")
    require(result["status"] == "stopped_external_timeout_incomplete_holdout_not_evaluable", "result status mismatch")
    require(analysis["schema"] == "onga-stage20-barrage-holdout-analysis-v1", "analysis schema mismatch")
    require(analysis["status"] == result["status"], "analysis status mismatch")
    require(result["github"]["runId"] == 29464186133, "run id mismatch")
    require(result["github"]["runAttempt"] == 1, "run attempt mismatch")
    require(result["github"]["conclusion"] == "failure", "run conclusion mismatch")
    require(result["execution"]["successfulJobCount"] == 5, "successful job count mismatch")
    require(result["execution"]["failedJobCount"] == 1, "failed job count mismatch")
    require(result["execution"]["skippedJobCount"] == 2, "skipped job count mismatch")
    require(result["execution"]["failedJobId"] == "barrage-closed-s03", "failed job mismatch")
    require(result["execution"]["failureCause"] == "external_five_wall_hour_timeout_exit_124", "failure cause mismatch")
    require(result["execution"]["closedS03FinalRestartPresent"] is False, "partial restart unexpectedly present")
    require(result["snapshotEvidence"]["expectedCount"] == 10, "snapshot expectation mismatch")
    require(result["snapshotEvidence"]["availableSealedCount"] == 1, "available snapshot count mismatch")
    require(result["snapshotEvidence"]["missingCount"] == 9, "missing snapshot count mismatch")
    require(result["holdoutComparison"]["evaluable"] is False, "incomplete holdout marked evaluable")
    require(result["holdoutComparison"]["acceptanceResult"] == "not_evaluable_not_failed", "holdout conclusion mismatch")
    require(result["holdoutComparison"]["metricComparisonPerformed"] is False, "metric comparison incorrectly claimed")
    require(result["holdoutComparison"]["directInterpolatedErrorMapsCreated"] is False, "comparison maps incorrectly claimed")
    require(analysis["artifactInventory"]["successfulCompleteJobCount"] == 5, "analysis job count mismatch")
    require(analysis["artifactInventory"]["partialStoppedJobCount"] == 1, "analysis partial count mismatch")
    require(analysis["artifactInventory"]["skippedJobCount"] == 2, "analysis skipped count mismatch")
    require(analysis["stoppedSegment"]["exitCode"] == 124, "analysis timeout exit mismatch")
    require(analysis["stoppedSegment"]["externalTimeoutConfirmedFromGitHubLog"] is True, "timeout log not confirmed")
    require(analysis["stoppedSegment"]["checkpointCount"] == 3, "partial checkpoint count mismatch")
    require(analysis["numericalSummary"]["completedSegmentsPassedContractChecks"] is True, "completed checks failed")
    require(analysis["numericalSummary"]["partialRetainedCheckpointsPassedAvailableChecks"] is True, "partial checks failed")
    require(analysis["numericalSummary"]["nonFiniteValueCountAcrossCompletedSegments"] == 0, "non-finite count changed")
    require(analysis["numericalSummary"]["negativeDepthCountAcrossCompletedSegments"] == 0, "negative depth count changed")
    require(analysis["postRunHoldout"]["evaluable"] is False, "analysis holdout marked evaluable")
    require(analysis["contractGapsObserved"]["regionalMasksDigestLockedBeforeExecution"] is False, "mask gap hidden")
    require(analysis["contractGapsObserved"]["waterDepthAcceptanceThresholdDefined"] is False, "depth threshold gap hidden")
    for key, expected in result["safeguards"].items():
        require(expected is False, f"result safeguard changed: {key}")
    for key, expected in analysis["safeguards"].items():
        require(expected is False, f"analysis safeguard changed: {key}")
    analysis_path = ROOT / result["numericalEvidence"]["analysis"]
    analyzer_path = ROOT / result["numericalEvidence"]["analyzer"]
    image_path = ROOT / result["decision"]["decisionImage"]
    renderer_path = ROOT / result["decision"]["renderer"]
    require(sha256(analysis_path) == result["numericalEvidence"]["analysisSha256"], "analysis digest mismatch")
    require(sha256(analyzer_path) == result["numericalEvidence"]["analyzerSha256"], "analyzer digest mismatch")
    require(sha256(image_path) == result["decision"]["decisionImageSha256"], "decision image digest mismatch")
    require(sha256(renderer_path) == result["decision"]["rendererSha256"], "renderer digest mismatch")
    require(
        sha256(ROOT / result["validation"]["validator"]) == result["validation"]["validatorSha256"],
        "validator digest mismatch",
    )
    require(
        sha256(ROOT / result["documentation"]["resultDocument"]) == result["documentation"]["resultDocumentSha256"],
        "result document digest mismatch",
    )
    require(
        sha256(ROOT / result["artifact"]["runMetadata"]) == result["artifact"]["runMetadataSha256"],
        "run metadata digest mismatch",
    )
    require(
        sha256(ROOT / result["artifact"]["artifactInventory"]) == result["artifact"]["artifactInventorySha256"],
        "artifact inventory digest mismatch",
    )
    require(
        (ROOT / "docs/results/stage20-barrage-holdout-29464186133/analysis.json").read_bytes() == analysis_path.read_bytes(),
        "retained analysis copy mismatch",
    )
    require(gate["state"] == "consumed", "gate is not consumed")
    require(gate["consumedBy"]["githubRunId"] == 29464186133, "gate run mismatch")
    require(gate["consumedBy"]["result"] == "failure_external_timeout_incomplete_holdout", "gate result mismatch")
    require(gate["consumedBy"]["resultRecord"] == "config/stage20_barrage_holdout_result_v1.json", "gate result record mismatch")
    with Image.open(image_path) as image:
        require(image.size == (1600, 2520), "decision image dimensions changed")
    with tempfile.TemporaryDirectory() as temporary:
        rerendered = Path(temporary) / "decision.jpg"
        subprocess.run(
            [
                sys.executable,
                str(renderer_path),
                "--repo-root",
                str(ROOT),
                "--output",
                str(rerendered),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        require(sha256(rerendered) == sha256(image_path), "decision image is not reproducible")
    require((ROOT / "docs/WORK_HANDOFF.md").is_file(), "handoff missing")
    print(json.dumps({
        "status": "passed_stopped_holdout_result_validation",
        "runId": 29464186133,
        "completeJobs": 5,
        "partialJobs": 1,
        "skippedJobs": 2,
        "availableSnapshots": 1,
        "expectedSnapshots": 10,
        "holdoutEvaluable": False,
        "decisionImageSha256": sha256(image_path),
        "retryPerformed": False,
        "additionalPhysicalRunPerformed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
