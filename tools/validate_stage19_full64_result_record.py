#!/usr/bin/env python3
"""Validate the local Stage 19 result record against sealed run evidence."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/results/stage19-full64-run-29323240389"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage19-result] {message}")


def close(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-15)


def main() -> None:
    record = load(ROOT / "config/stage19_full64_result_record_v1.json")
    report = load(RESULTS / "full64-report.json")
    progress = load(RESULTS / "full64-progress.json")
    preflight = load(RESULTS / "canonical-zero-case-preflight.json")
    maps = load(RESULTS / "full64-map-manifest.json")
    evidence = load(RESULTS / "full64-evidence-manifest.json")
    gate = load(ROOT / "config/stage19_full64_execution_gate_v1.json")
    require(record["status"] == report["status"] == progress["status"] == maps["status"] == "passed", "status")
    require(preflight["status"] == "passed" and preflight["mesh"]["canonical"] is True, "canonical preflight")
    require(preflight["approvedInputDimensionsReached"] == 16, "input dimensions")
    require(preflight["safeguards"]["numericalTimeStepFunctionCalled"] is False, "preflight called a step")
    numerical = record["numericalResult"]
    for key in ("requestedCaseCount", "completedCaseCount", "failedCaseCount", "stepsPerCase",
                "nanCount", "negativeDepthCount"):
        require(numerical[key] == report[key], f"numeric mismatch: {key}")
    for key in ("maxCfl", "maxAbsoluteMassBalanceError", "minimumDepthM",
                "minimumSimulatedTimeSeconds", "maximumSimulatedTimeSeconds", "wallSeconds",
                "peakResidentMemoryMiB"):
        require(close(numerical[key], report[key]), f"metric mismatch: {key}")
    require(numerical["reportSha256"] == sha256(RESULTS / "full64-report.json"), "report digest")
    require(numerical["fieldArtifactSha256"] == report["fieldArtifact"]["sha256"], "field digest")
    require(record["sealedEvidence"]["manifestSha256"] == sha256(RESULTS / "full64-evidence-manifest.json"), "evidence digest")
    require(evidence["status"] == "sealed" and len(evidence["files"]) == 14, "evidence seal")
    require(maps["mapCount"] == 5 and maps["representedCellCount"] == 50129 and maps["coverageFraction"] == 1.0,
            "map completeness")
    local_map_dir = ROOT / "docs/visuals/stage19-full64-results"
    digest_by_name = {item["filename"]: item["sha256"] for item in maps["maps"]}
    for filename, expected in digest_by_name.items():
        require(sha256(local_map_dir / filename) == expected, f"map digest: {filename}")
    require(sha256(ROOT / "docs/visuals/stage19-full64-result-judgment.png")
            == record["mapPackage"]["judgmentImageSha256"], "judgment digest")
    require(gate["state"] == "consumed" and gate["consumedBy"]["workflowRunId"] == 29323240389, "gate not consumed")
    require(gate["automaticRetryAllowed"] is False and gate["additionalRunAllowed"] is False, "rerun safeguard")
    require(record["interpretationLimits"]["physicalValidationClaimAllowed"] is False, "physical claim enabled")
    print(json.dumps({
        "schema": "onga-stage19-full64-result-record-validation-v1",
        "status": "passed",
        "completedCaseCount": 64,
        "mapCount": 5,
        "representedCellCount": 50129,
        "evidenceManifestSha256": record["sealedEvidence"]["manifestSha256"],
        "authorizationConsumed": True,
        "additionalRunAuthorized": False,
    }, indent=2))


if __name__ == "__main__":
    main()
