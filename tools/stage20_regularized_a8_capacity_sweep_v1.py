#!/usr/bin/env python3
"""Local A8-only capacity sweep for the 38 m3/s diagnostic forcing.

A8 is a composite visual resolution of the regulating main gate.  The
separate micro-adjustment gate is not represented.  This sweep therefore
tests numerical gate-net behavior only and cannot be promoted to a physical
low-flow operation scenario.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterator

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_regularized_stage4_gate_net_flux_probe_v1 as gate_net_probe


SCHEMA = "onga-stage20-regularized-a8-capacity-sweep-v1"
RAMP_SECONDS = 300.0
TOTAL_SECONDS = 600.0
TARGET_CAPACITIES = (0.25, 0.5, 0.75, 1.0)
OUTPUT = ROOT / "docs/results/stage20-regularized-a8-capacity-sweep-v1"
REPORT = OUTPUT / "report.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[stage20-regularized-a8-capacity-sweep-v1] {message}")


def requested_a8_capacity(model_seconds: float, target_capacity: float) -> np.ndarray:
    time_value = float(model_seconds)
    target = float(target_capacity)
    require(math.isfinite(time_value) and time_value >= 0.0, "model time is invalid")
    require(math.isfinite(target) and 0.0 < target <= 1.0, "target capacity is outside (0, 1]")
    result = np.empty(8, dtype=np.float64)
    gate_net_probe.prescribed.mapping.set_capacity_at_time(
        result,
        np.zeros(8, dtype=np.float64),
        np.asarray([7], dtype=np.int64),
        target,
        min(time_value, RAMP_SECONDS),
        RAMP_SECONDS,
    )
    require(bool(np.all(result[:7] == 0.0)), "a non-A8 gate opened")
    require(0.0 <= result[7] <= target, "A8 capacity escaped its target")
    return result


@contextmanager
def _a8_schedule(target_capacity: float) -> Iterator[None]:
    original = gate_net_probe.prescribed.requested_capacity
    gate_net_probe.prescribed.requested_capacity = (
        lambda model_seconds: requested_a8_capacity(model_seconds, target_capacity)
    )
    try:
        yield
    finally:
        gate_net_probe.prescribed.requested_capacity = original


def summarize_case(raw: dict[str, Any], target_capacity: float) -> dict[str, Any]:
    requested = requested_a8_capacity(TOTAL_SECONDS, target_capacity)
    effective = np.asarray(raw["effectiveFinalCapacityByGateId1To8"], dtype=np.float64)
    held = bool(np.array_equal(effective, requested))
    a8_accounting = next(row for row in raw["gateFluxAccounting"] if row["gateId"] == 8)
    return {
        "targetA8Capacity": float(target_capacity),
        "status": "PASS_LOCAL_A8_TARGET_HELD" if held else "PASS_LOCAL_A8_GATE_NET_INTERLOCK_CLOSED",
        "simulatedSeconds": raw["simulatedSeconds"],
        "acceptedSteps": raw["acceptedSteps"],
        "wallSeconds": raw["wallSeconds"],
        "maximumCfl": raw["maximumCfl"],
        "maximumRelativeMassBalanceError": raw["maximumRelativeMassBalanceError"],
        "effectiveFinalCapacityByGateId1To8": effective.tolist(),
        "targetHeldThroughRequestedHold": held,
        "interlockEvents": raw["interlockEvents"],
        "a8FluxAccounting": a8_accounting,
        "negativeDepthCount": raw["negativeDepthCount"],
        "nonFiniteValueCount": raw["nonFiniteValueCount"],
        "fishwayDischargeM3S": raw["fishwayDischargeM3S"],
    }


def run_case(target_capacity: float) -> dict[str, Any]:
    with _a8_schedule(target_capacity):
        raw = gate_net_probe.run_probe(TOTAL_SECONDS)
    return summarize_case(raw, target_capacity)


def initial_a8_observation() -> dict[str, Any]:
    context = gate_net_probe.prescribed.load_runtime_context()
    observed = gate_net_probe.observation.observe_per_gate(
        context["state"], context["gate"]
    )
    row = next(item for item in observed["perGate"] if item["gateId"] == 8)
    return {
        **row,
        "minimumTrustedSelectedFaceDepthM": observed[
            "minimumTrustedSelectedFaceDepthM"
        ],
    }


def run_sweep() -> dict[str, Any]:
    initial = initial_a8_observation()
    if not initial["trustedForPositiveMotionObservation"]:
        return {
            "schema": SCHEMA,
            "status": "BLOCKED_LOCAL_A8_NEAR_DRY_GEOMETRY_NO_SWEEP",
            "classification": "LOCAL_A8_PREFLIGHT_BLOCKED_NO_NUMERICAL_ADVANCE_NOT_PHYSICAL_LOW_FLOW_SCENARIO",
            "regulatingMainGateResolution": "config/stage20_barrage_regulating_main_gate_resolution_v1.json#gate8",
            "boundDiagnosticTotalInflowM3S": 38.0,
            "targetCapacities": list(TARGET_CAPACITIES),
            "a8InitialObservation": initial,
            "cases": [],
            "numericalAdvanceCount": 0,
            "sweepRunCount": 0,
            "microAdjustmentGateHydraulicRepresentationIncluded": False,
            "regulatingMainGateRolePhysicalAdopted": False,
            "salinityTransportEvaluated": False,
            "meshAdopted": False,
            "yodaLaunchPermitted": False,
            "forecastAuthorized": False,
            "guiAuthorized": False,
            "releaseAuthorized": False,
        }
    cases = [run_case(value) for value in TARGET_CAPACITIES]
    return {
        "schema": SCHEMA,
        "status": "PASS_LOCAL_A8_CAPACITY_SWEEP_NOT_PHYSICAL_LOW_FLOW_SCENARIO",
        "classification": "LOCAL_A8_GATE_NET_SENSITIVITY_MICRO_ADJUSTMENT_GATE_OMITTED_NOT_SALINITY_VALIDATION_NOT_FORECAST",
        "regulatingMainGateResolution": "config/stage20_barrage_regulating_main_gate_resolution_v1.json#gate8",
        "boundDiagnosticTotalInflowM3S": 38.0,
        "targetCapacities": list(TARGET_CAPACITIES),
        "cases": cases,
        "a8InitialObservation": initial,
        "numericalAdvanceCount": None,
        "sweepRunCount": len(cases),
        "allCasesNumericallySafe": all(
            row["negativeDepthCount"] == 0
            and row["nonFiniteValueCount"] == 0
            and row["fishwayDischargeM3S"] == 0.0
            for row in cases
        ),
        "microAdjustmentGateHydraulicRepresentationIncluded": False,
        "regulatingMainGateRolePhysicalAdopted": False,
        "salinityTransportEvaluated": False,
        "meshAdopted": False,
        "yodaLaunchPermitted": False,
        "forecastAuthorized": False,
        "guiAuthorized": False,
        "releaseAuthorized": False,
    }


def main() -> None:
    report = run_sweep()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
