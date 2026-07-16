#!/usr/bin/env python3
"""Validate the inactive Stage 20 cross-condition holdout plan."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def digest(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    path = "config/stage20_cross_condition_holdout_plan_candidate_v1.json"
    plan = load(path)
    approval = load(plan["planningApproval"])
    comparison = load(plan["sources"]["browserComparison"])

    require(digest(plan["planningApproval"]) == plan["planningApprovalSha256"], "approval digest mismatch")
    require(approval["approvedChoice"] == "A", "browser comparison adoption not approved")
    require(approval["adopted"]["retainEveryDisplayedHourlySnapshot"] is True, "hourly policy not adopted")
    require(approval["adopted"]["allowMissingHourLinearFallback"] is False, "missing-hour fallback enabled")
    for path_key, hash_key in (
        ("browserComparison", "browserComparisonSha256"),
        ("segmentedBasisPlan", "segmentedBasisPlanSha256"),
        ("referenceS02Result", "referenceS02ResultSha256AtPlanning"),
    ):
        require(digest(plan["sources"][path_key]) == plan["sources"][hash_key], f"source digest mismatch: {path_key}")

    policy = plan["adoptedBrowserPolicy"]
    require(policy["displayIntervalHours"] == 1, "display interval changed")
    require(policy["retainEveryDisplayedHourlySnapshot"] is True, "hourly snapshots must be retained")
    require(policy["allowMissingHourLinearFallback"] is False, "missing-hour interpolation must be forbidden")
    require(policy["crossConditionInterpolationValidated"] is False, "cross-condition path is not validated")

    test = plan["recommendedFirstTest"]
    require(test["id"] == "barrage-opening-midpoint-holdout-v1", "unexpected first test")
    require([item["barrageOpeningFraction"] for item in test["fitBases"]] == [0.0, 1.0], "fit endpoints changed")
    require(math.isclose(sum(item["interpolationWeight"] for item in test["fitBases"]), 1.0), "weights do not sum to one")
    target = test["heldOutDirectReference"]
    require(target["barrageOpeningFraction"] == 0.5, "held-out point is not midpoint")
    require(target["wasUsedToFitInterpolation"] is False, "held-out target may not fit interpolation")
    require(target["s01RunId"] == 29415527789 and target["s02RunId"] == 29434250546, "reference run changed")
    require(test["comparisonHours"] == [-12, -11, -10, -9, -8], "comparison hours changed")
    require(len(test["comparisonViews"]) == 4, "four comparison views required")

    thresholds = plan["candidateAcceptance"]
    source_thresholds = comparison["thresholds"]
    require(thresholds["maximumVelocityVectorRmseMPS"] == source_thresholds["maximumLeaveOneOutVelocityVectorRmseMPS"], "vector threshold changed")
    require(thresholds["maximumSpeedMaeMPS"] == source_thresholds["maximumLeaveOneOutSpeedMaeMPS"], "speed threshold changed")
    require(thresholds["maximumP95DirectionErrorDeg"] == source_thresholds["maximumLeaveOneOutP95DirectionErrorDeg"], "direction threshold changed")
    require(thresholds["allHoursAndRegionsMustPass"] is True, "partial pass is forbidden")
    require(thresholds["partialPassMayNotBePublished"] is True, "partial publication must remain forbidden")

    execution = plan["stagedExecutionCandidate"]
    require(execution["basisTrajectoryCount"] == 2, "two endpoint trajectories required")
    require(execution["segmentsPerBasis"] == 4 and execution["totalJobs"] == 8, "unexpected staged job count")
    require(execution["segmentBoundariesModelHours"] == [-24, -20, -16, -12, -8], "segment boundaries changed")
    require(execution["retainedSnapshotHours"] == [-12, -11, -10, -9, -8], "snapshot hours changed")
    require(execution["automaticRetryAllowed"] is False, "automatic retry enabled")
    require(execution["crossBasisRestartAllowed"] is False, "cross-basis restart enabled")
    require(execution["executionContractExists"] is False, "execution contract unexpectedly exists")
    require(execution["workflowExists"] is False, "workflow unexpectedly exists")
    require(execution["executionAuthorized"] is False, "execution unexpectedly authorized")

    resources = plan["resourceProjection"]
    require(math.isclose(resources["projectedRunnerHoursForTwoBases"], 2 * resources["referenceS01PlusS02MeasuredRunnerHours"]), "two-basis projection mismatch")
    alternative = plan["fullFiveDimensionAlternative"]
    require(alternative["totalJobsThroughModelHourMinus8"] == 40, "full alternative job count changed")
    require(math.isclose(alternative["projectedRunnerHours"], 5 * resources["projectedRunnerHoursForTwoBases"]), "full alternative projection mismatch")

    decision = plan["nextDecision"]
    require(decision["recommendedChoice"] == "A", "unexpected recommended choice")
    require(digest(decision["decisionImage"]) == decision["decisionImageSha256"], "decision image mismatch")
    require(digest(decision["renderer"]) == decision["rendererSha256"], "renderer mismatch")
    safeguards = plan["safeguards"]
    require(safeguards["additionalPhysicalRunPerformed"] is False, "additional physical run recorded")
    require(safeguards["physicalRunAuthorized"] is False, "physical run authorized")
    require(safeguards["publicSimulatorConnected"] is False, "public simulator connected")
    require(safeguards["mainMergeAuthorized"] is False, "main merge authorized")
    require(safeguards["physicalValidationClaimAllowed"] is False, "physical validation claim enabled")

    print(json.dumps({
        "status": "passed",
        "plan": path,
        "recommendedScope": "barrage_first_eight_job_inactive_contract",
        "physicalRunAuthorized": False,
        "mainMergeAuthorized": False
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
