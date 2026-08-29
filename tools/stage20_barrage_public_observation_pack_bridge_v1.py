#!/usr/bin/env python3
"""Explain why public point summaries cannot become a gate-physics pack."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_public_observation_pack_bridge_v1.json"
POINT = ROOT / "docs/results/stage20-barrage-physical-validation-readiness-v1/official-point-observation.json"
HISTORY = ROOT / "docs/results/stage20-barrage-physical-validation-readiness-v1/official-12h-flow-history.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-public-observation-pack-bridge-v1/report.json"


class PublicObservationBridgeError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicObservationBridgeError(f"[stage20-barrage-public-observation-pack-bridge-v1] {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    require(contract.get("schema") == "onga-stage20-barrage-public-observation-pack-bridge-v1", "schema changed")
    require(contract.get("status") == "PREPARED_FAIL_CLOSED_PUBLIC_SUMMARIES_NOT_GATE_PHYSICS_PACK", "status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound evidence absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound evidence changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["readOnlyBridgeAuditPermitted"] is True, "audit disabled")
    for key, value in boundary.items():
        if key != "readOnlyBridgeAuditPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def audit_bridge() -> dict[str, Any]:
    verified_contract()
    point = json.loads(POINT.read_text())
    history = json.loads(HISTORY.read_text())
    point_class = point["classification"]
    history_class = history["classification"]
    reasons = {
        "gateByGateOpeningMissingAtPoint": not point_class["gateByGateOpeningObserved"],
        "actuatorMotionMissingAtPoint": not point_class["actuatorMotionObserved"],
        "gateByGateOpeningMissingInHistory": not history_class["gateByGateOpeningObserved"],
        "upstreamDownstreamLevelHistoryMissing": not history_class["upstreamDownstreamLevelHistoryObserved"],
        "actuatorMotionMissingInHistory": not history_class["actuatorMotionObserved"],
        "commonVerticalDatumUnconfirmed": True,
        "independentValidationEventsMissing": True,
        "saltIntrusionOrAdverseVolumeCriterionMissing": True,
    }
    require(all(reasons.values()), "public summary classification unexpectedly changed")
    return {
        "schema": "onga-stage20-barrage-public-observation-pack-bridge-v1-report",
        "status": "BLOCKED_PUBLIC_SUMMARIES_NOT_GATE_PHYSICS_OBSERVATION_PACK",
        "pointObservedAt": point["observedAt"],
        "historyUpdatedAt": history["updatedAt"],
        "publicPointValueCount": len(point["values"]),
        "publicHistoryRowCount": history["summary"]["rowCount"],
        "publicHistoryDistinctReleaseM3S": history["summary"]["distinctReleaseM3S"],
        "blockingReasons": reasons,
        "observationPackCreated": False,
        "observationRowsEmitted": 0,
        "inventedValueCount": 0,
        "parameterCalibrationPermitted": False,
        "solverRunCount": 0,
        "yodaConnectionCount": 0,
        "physicalValidation": False,
        "promotion": {
            "forecast": False,
            "gui": False,
            "fishingDecision": False,
            "release": False
        },
        "minimumMissingInput": "time-aligned gate 1..8 openings, micro-gate state, upstream/downstream levels, total release, actuator state, datum, and event split",
    }


def main() -> None:
    report = audit_bridge()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "rows": report["observationRowsEmitted"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
