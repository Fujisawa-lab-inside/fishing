#!/usr/bin/env python3
"""Local fixed Stage-4 60 s canary using the copied one-way kernel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_barrage_one_way_kernel_one_step_probe_v1 as one_step
import stage20_stage4_facewise_capacity_backoff_real_context_probe_v1 as reconstruction


CONTRACT_PATH = ROOT / "config/stage20_barrage_one_way_stage4_hold_60s_canary_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-one-way-stage4-hold-60s-canary-v1"
REPORT = OUTPUT / "report.json"


class OneWayStage4HoldCanaryError(RuntimeError):
    """The local fixed Stage-4 canary contract was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OneWayStage4HoldCanaryError(
            f"[stage20-barrage-one-way-stage4-hold-60s-canary-v1] {message}"
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    require(
        contract.get("schema") == "onga-stage20-barrage-one-way-stage4-hold-60s-canary-v1",
        "contract schema changed",
    )
    require(
        contract.get("status")
        == "LOCAL_FIXED_STAGE4_60S_CANARY_READY_NOT_YODA_NOT_PHYSICAL_VALIDATION",
        "contract status changed",
    )
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound file absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["singleLocal60SecondCanaryPermitted"] is True, "local canary disabled")
    for key, value in boundary.items():
        if key != "singleLocal60SecondCanaryPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def run_fixed_stage4_scope(scope: dict[str, Any]) -> dict[str, Any]:
    """Run a caller-verified fixed-capacity local scope."""

    context, forcing, orientation = one_step.runtime()
    start_seconds = float(scope["reconstructionTargetModelSeconds"])
    target_seconds = float(scope["endModelSeconds"])
    capacity = np.asarray(scope["capacityByGateId1To8"], dtype=np.float64)
    maximum_step = float(scope["maximumStepSeconds"])
    maximum_steps = int(scope["maximumAcceptedSteps"])
    mass_limit = float(scope["maximumRelativeMassBalanceError"])

    wall_started = time.monotonic()
    state, reconstruction_steps, model_seconds = reconstruction.reconstruct_pre_trip_state(
        context, forcing, start_seconds
    )
    one_step.stage4.mapping.update_mapping_workspace(context["workspace"], capacity)
    geometry = context["geometry"]
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_mass_error = 0.0
    maximum_cfl = 0.0
    accepted_steps = 0
    blocked_step_count = 0
    blocked_face_observation_count = 0
    maximum_blocked_faces_in_step = 0
    cumulative_blocked_potential_volume = 0.0
    first_blocked_model_seconds: float | None = None
    last_blocked_model_seconds: float | None = None

    while model_seconds < target_seconds - 1.0e-12:
        require(accepted_steps < maximum_steps, "accepted step limit reached")
        tide, discharge = one_step.stage4._forcing_values(
            forcing, geometry, model_seconds
        )
        step = one_step.candidate.advance_h2_step_barrage_one_way_with_trace_v1(
            state, context["bed"], context["manning"], geometry["areas"],
            geometry["inverseAreas"], geometry["left"], geometry["right"],
            context["workspace"]["effectiveLengths"], geometry["internalNormals"],
            context["workspace"]["multipliers"], geometry["boundaryCells"],
            geometry["boundaryLengths"], geometry["boundaryNormals"],
            geometry["boundaryTags"], tide, discharge, context["donor"],
            context["receiver"], 0.0, float(scope["cflTarget"]),
            min(maximum_step, target_seconds - model_seconds), orientation,
        )
        require(
            step.limiter_sample.expected_candidate_count == len(state)
            and step.limiter_sample.evaluated_candidate_count == len(state)
            and step.limiter_sample.coverage_complete,
            "limiter coverage incomplete",
        )
        if step.blocked_reverse_face_count > 0:
            blocked_step_count += 1
            blocked_face_observation_count += step.blocked_reverse_face_count
            maximum_blocked_faces_in_step = max(
                maximum_blocked_faces_in_step, step.blocked_reverse_face_count
            )
            cumulative_blocked_potential_volume += (
                step.blocked_reverse_potential_discharge_m3_s
                * step.accepted_dt_s
            )
            if first_blocked_model_seconds is None:
                first_blocked_model_seconds = model_seconds
            last_blocked_model_seconds = model_seconds
        state = step.next_state
        model_seconds += step.accepted_dt_s
        accepted_steps += 1
        expected_volume -= step.accepted_dt_s * step.boundary_outflow_m3_s
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        maximum_mass_error = max(
            maximum_mass_error,
            abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0),
        )
        maximum_cfl = max(maximum_cfl, step.maximum_cfl)
        require(maximum_mass_error <= mass_limit, "mass balance limit exceeded")
        require(bool(np.isfinite(state).all()), "state became nonfinite")
        require(bool(np.all(state[:, 0] >= 0.0)), "depth became negative")
        require(step.effective_fishway_discharge_m3_s == 0.0, "fishway flow became nonzero")
        require(step.fishway_source_residual_m3_s == 0.0, "fishway residual became nonzero")

    require(abs(model_seconds - target_seconds) <= 1.0e-10, "target time not reached")
    return {
        "schema": "onga-stage20-barrage-one-way-stage4-hold-60s-canary-v1-result",
        "status": "PASS_LOCAL_FIXED_STAGE4_60S_ONE_WAY_NUMERICAL_CANARY_NOT_PHYSICAL_VALIDATION",
        "reconstructionTargetModelSeconds": start_seconds,
        "reconstructionAcceptedSteps": reconstruction_steps,
        "simulatedHoldSeconds": model_seconds - start_seconds,
        "endModelSeconds": model_seconds,
        "acceptedSteps": accepted_steps,
        "wallSeconds": time.monotonic() - wall_started,
        "capacityByGateId1To8": capacity.tolist(),
        "blockedStepCount": blocked_step_count,
        "blockedFaceObservationCount": blocked_face_observation_count,
        "maximumBlockedFacesInStep": maximum_blocked_faces_in_step,
        "cumulativeBlockedPotentialReverseVolumeM3": cumulative_blocked_potential_volume,
        "firstBlockedModelSeconds": first_blocked_model_seconds,
        "lastBlockedModelSeconds": last_blocked_model_seconds,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "minimumDepthM": float(np.min(state[:, 0])),
        "maximumDepthM": float(np.max(state[:, 0])),
        "negativeDepthCount": int(np.count_nonzero(state[:, 0] < 0.0)),
        "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
        "fishwayDischargeM3S": 0.0,
        "limiterExpectedCandidateCount": len(state),
        "limiterEvaluatedCandidateCount": len(state),
        "limiterCoverageCompleteEveryStep": True,
        "full300SecondHoldEvaluated": False,
        "yodaConnectionCount": 0,
        "physicalValidation": False,
        "releaseAuthorized": False,
    }


def run_canary() -> dict[str, Any]:
    return run_fixed_stage4_scope(verified_contract()["scope"])


def main() -> None:
    report = run_canary()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
