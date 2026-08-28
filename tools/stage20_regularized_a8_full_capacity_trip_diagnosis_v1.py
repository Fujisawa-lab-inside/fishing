#!/usr/bin/env python3
"""Stop at and record the first direction-aware A8 full-capacity trip."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import time
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_regularized_a8_capacity_sweep_v1 as v1
import stage20_regularized_multizone_gate_outward_observation_v1 as outward


SCHEMA = "onga-stage20-regularized-a8-full-capacity-trip-diagnosis-v1"
OUTPUT = ROOT / "docs/results/stage20-regularized-a8-full-capacity-trip-diagnosis-v1"
REPORT = OUTPUT / "report.json"


class A8TripDetected(RuntimeError):
    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload["a8Observation"]["failClosedReason"])
        self.payload = payload


@contextmanager
def stop_at_first_trip() -> Iterator[dict[str, Any]]:
    tracker: dict[str, Any] = {
        "modelSeconds": 0.0,
        "observationCallCount": 0,
    }
    original_request = v1.gate_net_probe.prescribed.requested_capacity
    original_observe = v1.gate_net_probe.observation.observe_per_gate

    def requested(model_seconds: float):
        tracker["modelSeconds"] = float(model_seconds)
        return v1.requested_a8_capacity(model_seconds, 1.0)

    def observed(state, context):
        tracker["observationCallCount"] += 1
        result = outward.observe_per_gate_outward(state, context)
        gate8 = result["perGate"][7]
        if not gate8["trustedForPositiveMotionObservation"]:
            raise A8TripDetected(
                {
                    "modelSeconds": tracker["modelSeconds"],
                    "requestedA8Capacity": float(requested(tracker["modelSeconds"])[7]),
                    "a8Observation": gate8,
                    "observationCallCount": tracker["observationCallCount"],
                }
            )
        return result

    v1.gate_net_probe.prescribed.requested_capacity = requested
    v1.gate_net_probe.observation.observe_per_gate = observed
    try:
        yield tracker
    finally:
        v1.gate_net_probe.prescribed.requested_capacity = original_request
        v1.gate_net_probe.observation.observe_per_gate = original_observe


def diagnose() -> dict[str, Any]:
    started = time.monotonic()
    with stop_at_first_trip() as tracker:
        try:
            v1.gate_net_probe.run_probe(v1.TOTAL_SECONDS)
        except A8TripDetected as error:
            trip = error.payload
        else:
            raise RuntimeError("expected A8 full-capacity trip was not detected")
    return {
        "schema": SCHEMA,
        "status": "PASS_LOCAL_A8_FULL_CAPACITY_TRIP_CAUSE_CAPTURED_NO_RETRY",
        "classification": "LOCAL_DIRECTIONAL_OBSERVATION_DIAGNOSIS_NOT_PHYSICAL_OPERATION_NOT_FORECAST",
        "sourceSweep": "docs/results/stage20-regularized-a8-directional-capacity-sweep-v2/report.json",
        "targetA8Capacity": 1.0,
        "trip": trip,
        "acceptedStepsBeforeTrip": int(tracker["observationCallCount"] - 1),
        "wallSeconds": time.monotonic() - started,
        "numericalAdvanceAtOrAfterTrip": 0,
        "retryCount": 0,
        "microAdjustmentGateHydraulicRepresentationIncluded": False,
        "physicalValidation": False,
        "yodaLaunchPermitted": False,
        "releaseAuthorized": False,
    }


def main() -> None:
    report = diagnose()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
