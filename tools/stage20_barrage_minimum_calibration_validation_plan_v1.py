#!/usr/bin/env python3
"""Static fail-closed audit of the minimum barrage calibration plan."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "config/stage20_barrage_minimum_calibration_validation_plan_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-minimum-calibration-validation-plan-v1/static-validation.json"


class MinimumCalibrationPlanError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MinimumCalibrationPlanError(f"[stage20-barrage-minimum-calibration-plan-v1] {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_plan() -> dict[str, Any]:
    plan = json.loads(PLAN.read_text())
    require(plan.get("schema") == "onga-stage20-barrage-minimum-calibration-validation-plan-v1", "schema changed")
    require(plan.get("status") == "PREPARE_ONLY_OBSERVATION_DEPENDENT_NO_PARAMETER_FIT_NO_SOLVER_RUN", "status changed")
    for binding in plan["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound evidence absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound evidence changed: {path}")
    candidate_ids = [candidate["id"] for candidate in plan["modelCandidates"]]
    require(candidate_ids == ["M0_zero_release_or_closed_gate_baseline", "M1_observed_monotone_rating_by_gate_configuration", "M2_geometry_and_regime_aware_gate_law"], "candidate order changed")
    require(any("one_way_wall_clamp" in value for value in plan["forbiddenCandidates"]), "one-way clamp prohibition missing")
    design = plan["eventDesign"]
    expected_total = len(design["operatingStates"]) * len(design["splitRoles"]) * design["minimumIndependentEventsPerStatePerSplit"]
    require(design["minimumTotalIndependentEvents"] == expected_total == 18, "event minimum inconsistent")
    require(design["wholeEventSplit"] and design["splitFrozenBeforeParameterSearch"] and design["postResultReassignmentForbidden"], "split leakage protection weakened")
    release_fit = plan["acceptanceMetrics"]["releaseFit"]
    require(release_fit["numericThresholds"] is None, "unsupported numeric threshold invented")
    require("instrument uncertainty" in release_fit["thresholdRule"], "measurement-based threshold rule missing")
    require(plan["acceptanceMetrics"]["directionalSafety"]["adverseHeadReverseDischargeCount"] == 0, "reverse flow accepted")
    require(plan["acceptanceMetrics"]["saltSafety"]["hydrodynamicOutwardNetFlowAloneIsInsufficient"], "salt safety weakened")
    stages = plan["stagedExecution"]
    require([stage["stage"] for stage in stages] == ["P0_observation_pack", "P1_offline_law_comparison", "P2_one_step_conservative_connection", "P3_bounded_duration_canary", "P4_independent_validation"], "stage order changed")
    require(stages[0]["solverSeconds"] == 0 and stages[1]["solverSeconds"] == 0, "pre-solver stages execute solver")
    require(stages[3]["automaticRetry"] is False and stages[4]["parameterRefitPermitted"] is False, "retry or validation refit enabled")
    boundary = plan["decisionBoundary"]
    require(boundary["planAndStaticValidationPermitted"] is True, "static plan disabled")
    for key, value in boundary.items():
        if key != "planAndStaticValidationPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return {
        "schema": "onga-stage20-barrage-minimum-calibration-validation-plan-v1-static-validation",
        "status": "PASS_PREPARE_ONLY_PLAN_NO_OBSERVATIONS_NO_FIT_NO_SOLVER",
        "candidateCount": len(candidate_ids),
        "minimumIndependentEventCount": expected_total,
        "stageCount": len(stages),
        "numericFitThresholdInvented": False,
        "solverRunCount": 0,
        "yodaConnectionCount": 0,
        "parameterFitCount": 0,
        "physicalValidation": False,
        "releaseAuthorized": False,
    }


def main() -> None:
    result = validate_plan()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
