#!/usr/bin/env python3
"""Fail-closed evidence gate for the actual barrage one-way physics."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_physical_validation_readiness_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-physical-validation-readiness-v1/assessment.json"
HISTORY = ROOT / "docs/results/stage20-barrage-physical-validation-readiness-v1/official-12h-flow-history.json"


class PhysicalValidationReadinessError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PhysicalValidationReadinessError(
            f"[stage20-barrage-physical-validation-readiness-v1] {message}"
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    require(
        contract.get("schema") == "onga-stage20-barrage-physical-validation-readiness-v1",
        "contract schema changed",
    )
    require(
        contract.get("status") == "LOCAL_EVIDENCE_GATE_READY_PHYSICAL_VALIDATION_BLOCKED",
        "contract status changed",
    )
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound evidence absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound evidence changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["staticReadinessAssessmentPermitted"] is True, "assessment disabled")
    for key, value in boundary.items():
        if key != "staticReadinessAssessmentPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def _seconds_between(later: str, earlier: str) -> float:
    left = datetime.fromisoformat(later)
    right = datetime.fromisoformat(earlier)
    require(left.utcoffset() is not None and right.utcoffset() is not None, "timestamps need timezone")
    return (left - right).total_seconds()


def assess(contract: dict[str, Any]) -> dict[str, Any]:
    observation = contract["officialPointObservation"]
    values = observation["values"]
    numbers = [float(value) for value in values.values()]
    require(all(math.isfinite(value) for value in numbers), "observation contains nonfinite values")
    age_seconds = _seconds_between(contract["assessmentAt"], observation["observedAt"])
    freshness_pass = 0.0 <= age_seconds <= contract["requiredEvidence"]["maximumPointObservationAgeSeconds"]
    head_m = float(values["barrageUpstreamLevelM"] - values["barrageDownstreamLevelM"])

    available = contract["availableEvidence"]
    required = contract["requiredEvidence"]
    history = json.loads(HISTORY.read_text())
    require(history.get("schema") == "onga-official-barrage-flow-history-v1", "history schema changed")
    require(history["summary"]["rowCount"] == 12, "history row count changed")
    require(history["classification"]["gateByGateOpeningObserved"] is False, "history gate classification changed")
    checks = {
        "officialPointObservationFresh": freshness_pass,
        "official12hPointFlowHistoryPresent": available["official12hPointFlowHistoryPresent"],
        "timeAlignedLevelReleaseAndGateHistoryPresent": available["timeAlignedLevelReleaseAndGateHistoryPresent"],
        "distinctOperatingStatesSufficient": (
            available["distinctOperatingStates"] >= required["minimumDistinctOperatingStates"]
        ),
        "gateByGateOpeningAndTimestampPresent": available["gateByGateOpeningAndTimestampPresent"],
        "commonVerticalDatumConfirmed": available["commonVerticalDatumConfirmed"],
        "actuatorClosureTimingPresent": available["actuatorClosureTimingPresent"],
        "dischargeLawAndCoefficientProvenancePresent": available["dischargeLawAndCoefficientProvenancePresent"],
        "momentumReactionLawPresent": available["momentumReactionLawPresent"],
        "independentValidationPeriodPresent": available["independentValidationPeriodPresent"],
        "saltIntrusionOrConservativeAdverseVolumeCriterionPresent": available["saltIntrusionOrConservativeAdverseVolumeCriterionPresent"],
    }

    numerical = json.loads(
        (ROOT / "docs/results/stage20-barrage-one-way-stage4-hold-300s-canary-v1/report.json").read_text()
    )
    blocked_fraction = numerical["blockedStepCount"] / numerical["acceptedSteps"]
    blocked_rate = numerical["cumulativeBlockedPotentialReverseVolumeM3"] / numerical["simulatedHoldSeconds"]
    ready = all(checks.values())
    return {
        "schema": "onga-stage20-barrage-physical-validation-readiness-v1-assessment",
        "status": (
            "PASS_PHYSICAL_VALIDATION_EVIDENCE_READY_NOT_MODEL_PROMOTION"
            if ready
            else "BLOCKED_INSUFFICIENT_GATE_PHYSICS_EVIDENCE_NO_MORE_NUMERICAL_EXPANSION"
        ),
        "assessmentAt": contract["assessmentAt"],
        "officialObservation": {
            "observedAt": observation["observedAt"],
            "ageSecondsAtAssessment": age_seconds,
            "upstreamMinusDownstreamHeadM": head_m,
            "barrageReleaseM3S": values["barrageReleaseM3S"],
            "interpretation": (
                "A positive outward head with zero reported release cannot identify a head-only law "
                "without time-aligned gate state, datum, and actuator evidence."
            ),
        },
        "official12hFlowHistory": {
            "updatedAt": history["updatedAt"],
            "rowCount": history["summary"]["rowCount"],
            "distinctReleaseM3S": history["summary"]["distinctReleaseM3S"],
            "releaseTransitionCount": history["summary"]["releaseTransitionCount"],
            "interpretation": (
                "The public history proves that reported release changed, but it lacks time-aligned "
                "upstream/downstream levels and gate openings, so the transition cannot identify a gate law."
            ),
        },
        "numericalModelDependence": {
            "oneWayBranchBlockedStepFraction": blocked_fraction,
            "blockedPotentialReverseVolumeM3": numerical["cumulativeBlockedPotentialReverseVolumeM3"],
            "blockedPotentialReverseVolumeRateM3S": blocked_rate,
            "oneWayAssumptionNegligible": False,
        },
        "checks": checks,
        "passedCheckCount": sum(checks.values()),
        "requiredCheckCount": len(checks),
        "physicalValidationEvidenceReady": ready,
        "headOnlyDischargeLawIdentifiable": False,
        "additionalNumericalExpansionRecommended": False,
        "nextEvidence": [
            "time-aligned upstream/downstream levels, total release, and gate-by-gate openings",
            "at least closed, open-outward, and near-zero/adverse-head operating states",
            "common vertical datum and gate sill/effective opening geometry",
            "actuator closure timing plus discharge and momentum-law provenance",
            "independent validation period and salt-intrusion or adverse-volume criterion",
        ],
        "promotion": {
            "kernelPhysicalAdoption": False,
            "forecast": False,
            "gui": False,
            "fishingDecision": False,
            "release": False,
        },
    }


def main() -> None:
    result = assess(verified_contract())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "passed": result["passedCheckCount"], "required": result["requiredCheckCount"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
