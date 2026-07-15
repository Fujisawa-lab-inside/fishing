#!/usr/bin/env python3
"""Validate the execution-disabled Stage 20 segmented plan without a solver run."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path


PLAN_PATH = Path("config/stage20_36h_segmented_precompute_plan_v1.json")
APPROVAL_PATH = Path("config/stage20_kernel_v3_segmented_plan_approval_v1.json")
REFERENCE_INPUTS = {
    "tideAmplitudeMultiplier": 1.0,
    "tidePhaseShiftMinutes": 0.0,
    "ongaDischargeM3S": 35.0,
    "nishiDischargeM3S": 2.0,
    "magariDischargeM3S": 1.0,
    "barrageOpeningFraction": 0.5,
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def fixture_checkpoint(job: dict, predecessor_digest: str | None) -> bytes:
    return canonical({
        "schema": "onga-stage20-segment-checkpoint-fixture-v1",
        "jobId": job["id"],
        "basisId": job["basisId"],
        "modelHourEnd": job["modelHourEnd"],
        "predecessorDigest": predecessor_digest,
        "physicalSolverExecuted": False,
    })


def verify_predecessor(job: dict, jobs_by_id: dict[str, dict], root: Path) -> str | None:
    predecessor_id = job["dependsOn"]
    if predecessor_id is None:
        return None
    predecessor = jobs_by_id[predecessor_id]
    checkpoint = root / predecessor["outputCheckpoint"]
    manifest = checkpoint.with_name("fixture-digest.json")
    if not checkpoint.is_file() or not manifest.is_file():
        raise RuntimeError("missing predecessor checkpoint; stopped before numerical step")
    evidence = load(manifest)
    digest = sha256(checkpoint)
    if digest != evidence["sha256"]:
        raise RuntimeError("predecessor digest mismatch; stopped before numerical step")
    return digest


def write_fixture(job: dict, jobs_by_id: dict[str, dict], root: Path) -> None:
    predecessor_digest = verify_predecessor(job, jobs_by_id, root)
    checkpoint = root / job["outputCheckpoint"]
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    payload = fixture_checkpoint(job, predecessor_digest)
    checkpoint.write_bytes(payload)
    checkpoint.with_name("fixture-digest.json").write_text(
        json.dumps({"sha256": sha256_bytes(payload), "physicalSolverExecuted": False}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    plan = load(PLAN_PATH)
    approval = load(APPROVAL_PATH)
    require(plan["schema"] == "onga-stage20-36h-segmented-precompute-plan-v1", "plan schema mismatch")
    require(plan["approval"]["sha256"] == sha256(APPROVAL_PATH), "approval digest mismatch")
    require(approval["status"] == "approved_for_detailed_planning_only", "approval scope mismatch")
    require("any_physical_segment" in approval["doesNotAuthorize"], "physical-run prohibition missing")
    require(plan["basisCount"] == len(plan["bases"]) == 11, "basis count mismatch")
    require(plan["segmentContract"]["segmentsPerBasis"] == 6, "segments per basis mismatch")
    require(plan["segmentContract"]["totalSegments"] == len(plan["jobs"]) == 66, "total segment count mismatch")
    require(plan["target"]["warmupHours"] == 12, "warmup duration mismatch")
    require(plan["target"]["requestedWindow"]["snapshotCount"] == 37, "snapshot target mismatch")

    bases_by_id = {basis["id"]: basis for basis in plan["bases"]}
    require(len(bases_by_id) == 11, "basis identifiers are not unique")
    require(bases_by_id["reference"]["inputs"] == REFERENCE_INPUTS, "reference inputs mismatch")
    for basis in plan["bases"]:
        if basis["id"] == "reference":
            continue
        changed = [key for key, value in basis["inputs"].items() if value != REFERENCE_INPUTS[key]]
        require(changed == [basis["dimension"]], f"basis does not vary exactly one dimension: {basis['id']}")

    jobs_by_id = {job["id"]: job for job in plan["jobs"]}
    require(len(jobs_by_id) == 66, "job identifiers are not unique")
    boundaries = plan["segmentContract"]["segmentBoundariesModelHours"]
    all_snapshot_hours: list[int] = []
    for basis_id in bases_by_id:
        basis_jobs = sorted((job for job in plan["jobs"] if job["basisId"] == basis_id), key=lambda item: item["segmentIndex"])
        require(len(basis_jobs) == 6, f"basis chain length mismatch: {basis_id}")
        basis_hours: list[int] = []
        for index, job in enumerate(basis_jobs):
            require(job["segmentIndex"] == index + 1, f"segment index mismatch: {job['id']}")
            require((job["modelHourStart"], job["modelHourEnd"]) == (boundaries[index], boundaries[index + 1]), f"segment bounds mismatch: {job['id']}")
            require(job["physicalSeconds"] == 28800, f"segment physical duration mismatch: {job['id']}")
            expected_predecessor = None if index == 0 else basis_jobs[index - 1]["id"]
            require(job["dependsOn"] == expected_predecessor, f"dependency mismatch: {job['id']}")
            basis_hours.extend(job["snapshotHours"])
        require(basis_hours == list(range(-12, 25)), f"snapshot coverage mismatch: {basis_id}")
        require(len(basis_hours) == len(set(basis_hours)), f"duplicate snapshot hour: {basis_id}")
        all_snapshot_hours.extend(basis_hours)
    require(len(all_snapshot_hours) == 11 * 37, "aggregate snapshot count mismatch")

    projected = plan["segmentContract"]["projectedWallSecondsPerEightHourSegment"]
    maximum = plan["segmentContract"]["maximumWallSecondsPerSegment"]
    require(projected < maximum, "projected segment exceeds wall cap")
    require(abs((maximum - projected) - plan["segmentContract"]["projectedWallMarginSeconds"]) < 1e-9, "wall margin mismatch")
    require(plan["resourceProjection"]["githubDefaultJobTimeoutMinutes"] == 360, "GitHub timeout reference mismatch")
    require(plan["resourceProjection"]["plannedJobTimeoutMinutes"] == 330, "planned timeout mismatch")

    execution = plan["execution"]
    require(all(execution[key] is False for key in (
        "physicalRunnerConnected",
        "workflowPresent",
        "authorizationPresent",
        "gatePresent",
        "physicalSegmentAuthorized",
        "campaignAuthorized",
        "automaticRetryAllowed",
        "paidResourceProvisioningAuthorized",
        "publicSimulatorConnected",
        "mainMergeAuthorized",
    )), "execution safeguard mismatch")
    require(plan["canary"]["currentlyAuthorized"] is False, "canary unexpectedly authorized")
    require(plan["failurePolicy"]["automaticRetryAllowed"] is False, "automatic retry enabled")
    require(plan["failurePolicy"]["automaticResumeAllowed"] is False, "automatic resume enabled")

    missing_rejected = False
    corruption_rejected = False
    with tempfile.TemporaryDirectory(prefix="stage20-segment-plan-fixture-") as temporary:
        fixture_root = Path(temporary)
        first = jobs_by_id["reference-s01"]
        second = jobs_by_id["reference-s02"]
        try:
            write_fixture(second, jobs_by_id, fixture_root)
        except RuntimeError as error:
            missing_rejected = "stopped before numerical step" in str(error)
        write_fixture(first, jobs_by_id, fixture_root)
        first_checkpoint = fixture_root / first["outputCheckpoint"]
        first_checkpoint.write_bytes(first_checkpoint.read_bytes() + b"corrupt")
        try:
            write_fixture(second, jobs_by_id, fixture_root)
        except RuntimeError as error:
            corruption_rejected = "stopped before numerical step" in str(error)
    require(missing_rejected, "missing predecessor was accepted")
    require(corruption_rejected, "corrupt predecessor was accepted")

    print(json.dumps({
        "schema": "onga-stage20-36h-segmented-precompute-plan-validation-v1",
        "status": "passed_fixture_only_execution_disabled",
        "basisCount": len(bases_by_id),
        "segmentsPerBasis": 6,
        "totalSegments": len(jobs_by_id),
        "warmupHours": plan["target"]["warmupHours"],
        "snapshotCountPerBasis": 37,
        "missingPredecessorRejectedBeforeNumericalStep": missing_rejected,
        "corruptPredecessorRejectedBeforeNumericalStep": corruption_rejected,
        "physicalSolverExecuted": False,
        "physicalSegmentAuthorized": False,
        "campaignAuthorized": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
