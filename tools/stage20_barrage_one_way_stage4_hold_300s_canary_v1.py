#!/usr/bin/env python3
"""Local full 300 s Stage-4 hold under the one-way face assumption."""

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

import stage20_barrage_one_way_stage4_hold_60s_canary_v1 as bounded


CONTRACT_PATH = ROOT / "config/stage20_barrage_one_way_stage4_hold_300s_canary_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-one-way-stage4-hold-300s-canary-v1"
REPORT = OUTPUT / "report.json"


class OneWayStage4Hold300sCanaryError(RuntimeError):
    """The full local hold contract was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OneWayStage4Hold300sCanaryError(
            f"[stage20-barrage-one-way-stage4-hold-300s-canary-v1] {message}"
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    require(
        contract.get("schema") == "onga-stage20-barrage-one-way-stage4-hold-300s-canary-v1",
        "contract schema changed",
    )
    require(
        contract.get("status")
        == "LOCAL_FIXED_STAGE4_300S_DIAGNOSTIC_READY_NOT_YODA_NOT_PHYSICAL_VALIDATION",
        "contract status changed",
    )
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound file absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["singleLocal300SecondCanaryPermitted"] is True, "local canary disabled")
    for key, value in boundary.items():
        if key != "singleLocal300SecondCanaryPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def run_canary() -> dict[str, Any]:
    report = bounded.run_fixed_stage4_scope(verified_contract()["scope"])
    report["schema"] = "onga-stage20-barrage-one-way-stage4-hold-300s-canary-v1-result"
    report["status"] = (
        "PASS_LOCAL_FIXED_STAGE4_300S_ONE_WAY_NUMERICAL_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION"
    )
    report["full300SecondHoldEvaluated"] = True
    return report


def main() -> None:
    report = run_canary()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
