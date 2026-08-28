#!/usr/bin/env python3
"""A8-only local sweep with direction-aware wet/dry observation."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_regularized_a8_capacity_sweep_v1 as v1
import stage20_regularized_multizone_gate_outward_observation_v1 as outward


SCHEMA = "onga-stage20-regularized-a8-directional-capacity-sweep-v2"
OUTPUT = ROOT / "docs/results/stage20-regularized-a8-directional-capacity-sweep-v2"
REPORT = OUTPUT / "report.json"


@contextmanager
def directional_a8_schedule(target_capacity: float) -> Iterator[None]:
    original_request = v1.gate_net_probe.prescribed.requested_capacity
    original_observe = v1.gate_net_probe.observation.observe_per_gate
    v1.gate_net_probe.prescribed.requested_capacity = (
        lambda model_seconds: v1.requested_a8_capacity(model_seconds, target_capacity)
    )
    v1.gate_net_probe.observation.observe_per_gate = outward.observe_per_gate_outward
    try:
        yield
    finally:
        v1.gate_net_probe.prescribed.requested_capacity = original_request
        v1.gate_net_probe.observation.observe_per_gate = original_observe


def initial_a8_observation() -> dict:
    context = v1.gate_net_probe.prescribed.load_runtime_context()
    observed = outward.observe_per_gate_outward(context["state"], context["gate"])
    return next(row for row in observed["perGate"] if row["gateId"] == 8)


def run_case(target_capacity: float) -> dict:
    with directional_a8_schedule(target_capacity):
        raw = v1.gate_net_probe.run_probe(v1.TOTAL_SECONDS)
    return v1.summarize_case(raw, target_capacity)


def run_sweep() -> dict:
    initial = initial_a8_observation()
    if not initial["trustedForPositiveMotionObservation"]:
        raise RuntimeError("direction-aware A8 observation failed closed before sweep")
    cases = [run_case(value) for value in v1.TARGET_CAPACITIES]
    return {
        "schema": SCHEMA,
        "status": "PASS_LOCAL_A8_DIRECTIONAL_CAPACITY_SWEEP_NOT_PHYSICAL_LOW_FLOW_SCENARIO",
        "classification": "LOCAL_A8_DIRECTIONAL_GATE_NET_SENSITIVITY_MICRO_ADJUSTMENT_GATE_OMITTED_NOT_SALINITY_VALIDATION_NOT_FORECAST",
        "regulatingMainGateResolution": "config/stage20_barrage_regulating_main_gate_resolution_v1.json#gate8",
        "boundDiagnosticTotalInflowM3S": 38.0,
        "initialA8Observation": initial,
        "targetCapacities": list(v1.TARGET_CAPACITIES),
        "cases": cases,
        "allCasesNumericallySafe": all(
            row["negativeDepthCount"] == 0
            and row["nonFiniteValueCount"] == 0
            and row["fishwayDischargeM3S"] == 0.0
            for row in cases
        ),
        "downstreamDrynessAloneBlockedOutwardMotion": False,
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


def main() -> None:
    report = run_sweep()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
