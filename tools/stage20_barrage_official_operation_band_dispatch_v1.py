#!/usr/bin/env python3
"""Published flow-band classifier with no gate-state inference."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_official_operation_band_dispatch_v1.json"
READINESS = ROOT / "config/stage20_barrage_physical_validation_readiness_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-official-operation-band-dispatch-v1/report.json"


class OperationBandDispatchError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OperationBandDispatchError(f"[stage20-barrage-operation-band-dispatch-v1] {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    require(contract.get("schema") == "onga-stage20-barrage-official-operation-band-dispatch-v1", "schema changed")
    require(contract.get("status") == "LOCAL_PUBLISHED_BAND_CLASSIFIER_READY_NOT_GATE_STATE_INFERENCE", "status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound evidence absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound evidence changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["localBandClassificationPermitted"] is True, "classification disabled")
    for key, value in boundary.items():
        if key != "localBandClassificationPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def classify_inflow(inflow_m3s: float, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    document = contract or verified_contract()
    value = float(inflow_m3s)
    require(math.isfinite(value) and value >= 0.0, "inflow must be finite and nonnegative")
    selected = None
    if value < document["belowPublishedMinimum"]["maximumExclusiveM3S"]:
        selected = document["belowPublishedMinimum"]
    else:
        for band in document["bands"]:
            maximum = band["maximumExclusiveM3S"]
            if value >= band["minimumInclusiveM3S"] and (maximum is None or value < maximum):
                selected = band
                break
    require(selected is not None, "no operation band matched")
    return {
        "schema": "onga-stage20-barrage-official-operation-band-dispatch-v1-result",
        "status": "PASS_PUBLISHED_CONTROL_BAND_CLASSIFIED_NO_GATE_STATE_INFERENCE",
        "observedInflowM3S": value,
        "controlClass": selected["controlClass"],
        "mainGateImplication": selected.get("mainGateImplication", "NO_GATE_STATE_INFERRED"),
        "gateByGateOpening": None,
        "predictedReleaseM3S": None,
        "hydraulicLaw": None,
        "physicalValidation": False,
        "forecast": False,
    }


def current_report() -> dict[str, Any]:
    readiness = json.loads(READINESS.read_text())
    observation = readiness["officialPointObservation"]
    result = classify_inflow(observation["values"]["barrageInflowM3S"])
    result.update(
        {
            "observationTimestamp": observation["observedAt"],
            "reportedReleaseM3S": observation["values"]["barrageReleaseM3S"],
            "upstreamLevelM": observation["values"]["barrageUpstreamLevelM"],
            "downstreamLevelM": observation["values"]["barrageDownstreamLevelM"],
            "interpretation": (
                "The current observation lies in the published micro-adjustment-gate control band. "
                "It must not be displayed or simulated as an A3-A6 Stage-4 opening. Actual gate state remains unknown."
            ),
        }
    )
    return result


def main() -> None:
    report = current_report()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "controlClass": report["controlClass"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
