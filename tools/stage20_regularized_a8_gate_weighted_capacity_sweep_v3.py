#!/usr/bin/env python3
"""Reuse safe A8 25-75% cases and rerun only 100% with gate-weighted head."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_regularized_a8_directional_capacity_sweep_v2 as v2


SCHEMA = "onga-stage20-regularized-a8-gate-weighted-capacity-sweep-v3"
V2_REPORT = ROOT / "docs/results/stage20-regularized-a8-directional-capacity-sweep-v2/report.json"
V2_REPORT_SHA256 = "275cf660c064cbd11a39542f26b0d1b917202a0667f8922c1bfa34d556fd19bf"
OUTPUT = ROOT / "docs/results/stage20-regularized-a8-gate-weighted-capacity-sweep-v3"
REPORT = OUTPUT / "report.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage20-regularized-a8-gate-weighted-capacity-sweep-v3] {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reusable_cases() -> list[dict[str, Any]]:
    require(sha256(V2_REPORT) == V2_REPORT_SHA256, "v2 report SHA changed")
    source = json.loads(V2_REPORT.read_text())
    rows = source["cases"][:3]
    require([row["targetA8Capacity"] for row in rows] == [0.25, 0.5, 0.75], "v2 reusable cases changed")
    require(all(row["targetHeldThroughRequestedHold"] for row in rows), "v2 reusable case did not hold")
    require(all(not row["interlockEvents"] for row in rows), "v2 reusable case contains an interlock")
    return [{**row, "reusedFromV2ExactArtifact": True} for row in rows]


def build_report(full_capacity_case: dict[str, Any]) -> dict[str, Any]:
    require(full_capacity_case["targetA8Capacity"] == 1.0, "full-capacity case missing")
    cases = reusable_cases() + [{**full_capacity_case, "reusedFromV2ExactArtifact": False}]
    return {
        "schema": SCHEMA,
        "status": "PASS_LOCAL_A8_GATE_WEIGHTED_SWEEP_NOT_PHYSICAL_LOW_FLOW_SCENARIO",
        "classification": "LOCAL_A8_GATE_WEIGHTED_HEAD_AND_GATE_NET_SENSITIVITY_MICRO_ADJUSTMENT_GATE_OMITTED_NOT_SALINITY_VALIDATION_NOT_FORECAST",
        "headTrustBasis": "LENGTH_WEIGHTED_GATE_MEAN",
        "fluxTrustBasis": "GATE_INTEGRATED_NET_SIGNED_OUTWARD_DISCHARGE",
        "sourceV2Report": str(V2_REPORT.relative_to(ROOT)),
        "sourceV2ReportSha256": V2_REPORT_SHA256,
        "reusedTargetCapacities": [0.25, 0.5, 0.75],
        "rerunTargetCapacities": [1.0],
        "cases": cases,
        "allCasesNumericallySafe": all(
            row["negativeDepthCount"] == 0
            and row["nonFiniteValueCount"] == 0
            and row["fishwayDischargeM3S"] == 0.0
            for row in cases
        ),
        "allCasesHeldThroughRequestedHold": all(
            row["targetHeldThroughRequestedHold"] for row in cases
        ),
        "localHeadReversalAloneBlocksOutwardMotion": False,
        "gateNetInterlockEvaluatedBeforeEveryStep": True,
        "localAdverseFaceFluxClipped": False,
        "microAdjustmentGateHydraulicRepresentationIncluded": False,
        "regulatingMainGateRolePhysicalAdopted": False,
        "salinityTransportEvaluated": False,
        "meshAdopted": False,
        "yodaLaunchPermitted": False,
        "forecastAuthorized": False,
        "guiAuthorized": False,
        "releaseAuthorized": False,
    }


def run() -> dict[str, Any]:
    return build_report(v2.run_case(1.0))


def main() -> None:
    report = run()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
