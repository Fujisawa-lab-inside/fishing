#!/usr/bin/env python3
"""Local 60 s preventive facewise Stage-4 hold canary.

The controller starts from the reconstructed 300 s state.  A numerical trial
is accepted only when every active selected face is outward both before and
after the exact trial step.  Capacity decreases immediately; increases are
delayed and limited to one grid level.
"""

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

import stage20_stage4_facewise_capacity_backoff_v1 as backoff
import stage20_stage4_facewise_capacity_backoff_real_context_probe_v1 as trial_adapter


CONTRACT_PATH = ROOT / "config/stage20_stage4_facewise_hysteresis_hold_canary_v1.json"
OUTPUT = ROOT / "docs/results/stage20-stage4-facewise-hysteresis-hold-canary-v1"
REPORT = OUTPUT / "report.json"


class HysteresisHoldCanaryError(RuntimeError):
    """The preventive hold-canary contract was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HysteresisHoldCanaryError(
            f"[stage20-stage4-facewise-hysteresis-hold-canary-v1] {message}"
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    require(
        contract.get("schema") == "onga-stage20-stage4-facewise-hysteresis-hold-canary-v1",
        "contract schema changed",
    )
    require(
        contract.get("status")
        == "LOCAL_PREVENTIVE_PRE_AND_POST_FACEWISE_CANARY_READY_NOT_YODA",
        "contract status changed",
    )
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound file absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound file changed: {path}")
    scope = contract["scope"]
    require(scope["activeGateIds"] == list(backoff.ACTIVE_GATE_IDS), "active gates changed")
    require(
        scope["jointCapacityScaleDescending"] == list(backoff.CANDIDATE_SCALES),
        "capacity grid changed",
    )
    require(scope["acceptedStateMustMatchSelectedCandidate"] is True, "state identity weakened")
    require(scope["fluxClippingPermitted"] is False, "flux clipping enabled")
    boundary = contract["decisionBoundary"]
    require(boundary["singleLocal60SecondHoldCanaryPermitted"] is True, "local canary disabled")
    for key, value in boundary.items():
        if key != "singleLocal60SecondHoldCanaryPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def face_diagnostic(
    state: np.ndarray, context: dict[str, Any], capacity: np.ndarray
) -> dict[str, Any]:
    flux = trial_adapter._face_flux(state, context, capacity)
    gate_index = np.asarray(
        context["workspace"]["gateIndexBySelectedFace"], dtype=np.int64
    )
    active = capacity[gate_index] > 0.0
    adverse = active & (flux < -backoff.REVERSE_TOLERANCE_M3_S)
    leakage = ~active & (np.abs(flux) > backoff.REVERSE_TOLERANCE_M3_S)
    return {
        "activeFaceCount": int(np.count_nonzero(active)),
        "adverseActiveFaceCount": int(np.count_nonzero(adverse)),
        "inactiveLeakageFaceCount": int(np.count_nonzero(leakage)),
        "minimumActiveSignedOutwardFluxM3S": (
            None if not np.any(active) else float(np.min(flux[active]))
        ),
        "safe": bool(not np.any(adverse) and not np.any(leakage)),
    }


def trial_candidate(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
    scale: float,
) -> dict[str, Any]:
    capacity = backoff.stage4_capacity_for_scale(scale)
    pre = face_diagnostic(state, context, capacity)
    step = trial_adapter.advance_with_capacity(
        state, context, forcing, model_seconds, maximum_dt, capacity
    )
    post = face_diagnostic(step.next_state, context, capacity)
    return {
        "scale": scale,
        "capacity": capacity,
        "step": step,
        "pre": pre,
        "post": post,
        "safe": bool(pre["safe"] and post["safe"]),
    }


def lower_scales(current_scale: float) -> tuple[float, ...]:
    index = backoff.CANDIDATE_SCALES.index(float(current_scale))
    return backoff.CANDIDATE_SCALES[index + 1 :]


def next_higher_scale(current_scale: float) -> float | None:
    index = backoff.CANDIDATE_SCALES.index(float(current_scale))
    return None if index == 0 else backoff.CANDIDATE_SCALES[index - 1]


def choose_safe_trial(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
    current_scale: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempted: list[dict[str, Any]] = []
    first = trial_candidate(
        state, context, forcing, model_seconds, maximum_dt, current_scale
    )
    attempted.append(first)
    if first["safe"]:
        return first, attempted
    common_dt = float(first["step"].accepted_dt_s)
    for scale in lower_scales(current_scale):
        candidate = trial_candidate(
            state, context, forcing, model_seconds, common_dt, scale
        )
        require(
            abs(float(candidate["step"].accepted_dt_s) - common_dt) <= 1.0e-15,
            "decrease candidates do not share accepted dt",
        )
        attempted.append(candidate)
        if candidate["safe"]:
            return candidate, attempted
    raise HysteresisHoldCanaryError("all-closed candidate unexpectedly unsafe")


def diagnostic_row(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "scale": candidate["scale"],
        "acceptedDtSeconds": float(candidate["step"].accepted_dt_s),
        "pre": candidate["pre"],
        "post": candidate["post"],
        "safe": candidate["safe"],
    }


def run_canary() -> dict[str, Any]:
    contract = verified_contract()
    backoff.read_and_verify_contract()
    scope = contract["scope"]
    start_seconds = float(scope["reconstructionTargetModelSeconds"])
    duration_seconds = float(scope["localCanaryDurationSeconds"])
    end_seconds = start_seconds + duration_seconds
    maximum_step = float(scope["maximumStepSeconds"])
    positive_margin = float(scope["positiveIncreaseMarginM3S"])
    increase_dwell = float(scope["increaseDwellSeconds"])

    context = trial_adapter.strict_probe.prescribed.load_runtime_context()
    forcing = trial_adapter.strict_probe.prescribed.matched.base.read_json(
        trial_adapter.strict_probe.prescribed.FORCING_PATH
    )
    trial_adapter.strict_probe.prescribed.matched.base.validate_forcing(forcing)
    wall_started = time.monotonic()
    state, reconstruction_steps, model_seconds = trial_adapter.reconstruct_pre_trip_state(
        context, forcing, start_seconds
    )
    geometry = context["geometry"]
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_mass_error = 0.0
    maximum_cfl = 0.0
    accepted_steps = 0
    trial_kernel_calls = 0
    rejected_trial_count = 0
    current_scale = 1.0
    positive_margin_seconds = 0.0
    transitions: list[dict[str, Any]] = []
    upward_probes: list[dict[str, Any]] = []
    minimum_accepted_pre_flux = float("inf")
    minimum_accepted_post_flux = float("inf")

    while model_seconds < end_seconds - 1.0e-12:
        selected, attempts = choose_safe_trial(
            state,
            context,
            forcing,
            model_seconds,
            min(maximum_step, end_seconds - model_seconds),
            current_scale,
        )
        trial_kernel_calls += len(attempts)
        rejected_trial_count += sum(not row["safe"] for row in attempts)
        if selected["scale"] < current_scale:
            transitions.append(
                {
                    "modelSeconds": model_seconds,
                    "kind": "IMMEDIATE_DECREASE",
                    "fromScale": current_scale,
                    "toScale": selected["scale"],
                    "attempts": [diagnostic_row(row) for row in attempts],
                }
            )
            current_scale = float(selected["scale"])
            positive_margin_seconds = 0.0

        accepted_dt = float(selected["step"].accepted_dt_s)
        selected_minimum = selected["post"]["minimumActiveSignedOutwardFluxM3S"]
        if current_scale == 0.0:
            positive_margin_seconds += accepted_dt
        elif selected_minimum is not None and selected_minimum >= positive_margin:
            positive_margin_seconds += accepted_dt
        else:
            positive_margin_seconds = 0.0

        higher = next_higher_scale(current_scale)
        if higher is not None and positive_margin_seconds >= increase_dwell:
            higher_trial = trial_candidate(
                state, context, forcing, model_seconds, accepted_dt, higher
            )
            trial_kernel_calls += 1
            require(
                abs(float(higher_trial["step"].accepted_dt_s) - accepted_dt) <= 1.0e-15,
                "higher candidate does not share accepted dt",
            )
            higher_minimum = higher_trial["post"]["minimumActiveSignedOutwardFluxM3S"]
            higher_margin_safe = bool(
                higher_trial["safe"]
                and higher_minimum is not None
                and higher_minimum >= positive_margin
            )
            upward_probes.append(
                {
                    "modelSeconds": model_seconds,
                    "fromScale": current_scale,
                    "toScale": higher,
                    "accepted": higher_margin_safe,
                    "diagnostic": diagnostic_row(higher_trial),
                }
            )
            if higher_margin_safe:
                transitions.append(
                    {
                        "modelSeconds": model_seconds,
                        "kind": "DELAYED_INCREASE",
                        "fromScale": current_scale,
                        "toScale": higher,
                    }
                )
                selected = higher_trial
                current_scale = higher
            positive_margin_seconds = 0.0

        require(selected["pre"]["safe"], "accepted pre-step face set is unsafe")
        require(selected["post"]["safe"], "accepted post-step face set is unsafe")
        pre_min = selected["pre"]["minimumActiveSignedOutwardFluxM3S"]
        post_min = selected["post"]["minimumActiveSignedOutwardFluxM3S"]
        if pre_min is not None:
            minimum_accepted_pre_flux = min(minimum_accepted_pre_flux, pre_min)
        if post_min is not None:
            minimum_accepted_post_flux = min(minimum_accepted_post_flux, post_min)

        step = selected["step"]
        state = step.next_state
        model_seconds += float(step.accepted_dt_s)
        accepted_steps += 1
        expected_volume -= float(step.accepted_dt_s) * float(step.boundary_outflow_m3_s)
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        maximum_mass_error = max(
            maximum_mass_error,
            abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0),
        )
        maximum_cfl = max(maximum_cfl, float(step.maximum_cfl))
        require(bool(np.isfinite(state).all()), "accepted state became nonfinite")
        require(bool(np.all(state[:, 0] >= 0.0)), "accepted depth became negative")
        require(step.effective_fishway_discharge_m3_s == 0.0, "fishway flow became nonzero")
        require(step.fishway_source_residual_m3_s == 0.0, "fishway residual became nonzero")

    transition_directions = [
        1 if float(row["toScale"]) > float(row["fromScale"]) else -1
        for row in transitions
        if float(row["toScale"]) != float(row["fromScale"])
    ]
    oscillation_detected = any(
        current != previous
        for previous, current in zip(
            transition_directions, transition_directions[1:]
        )
    )
    hold_utility_passed = current_scale > 0.0
    return {
        "schema": "onga-stage20-stage4-facewise-hysteresis-hold-canary-v1-result",
        "status": (
            "PASS_LOCAL_60S_FACEWISE_SAFETY_AND_NONZERO_HOLD_NOT_FULL_HOLD"
            if hold_utility_passed
            else "PASS_NUMERICAL_FACEWISE_SAFETY_FAIL_NONZERO_HOLD_ALL_CLOSED"
        ),
        "reconstructionTargetModelSeconds": start_seconds,
        "reconstructionAcceptedSteps": reconstruction_steps,
        "canaryDurationSeconds": model_seconds - start_seconds,
        "canaryAcceptedSteps": accepted_steps,
        "wallSeconds": time.monotonic() - wall_started,
        "trialKernelCallCount": trial_kernel_calls,
        "rejectedTrialCount": rejected_trial_count,
        "finalScale": current_scale,
        "nonzeroHoldUtilityPassed": hold_utility_passed,
        "scaleTransitionCount": len(transitions),
        "scaleTransitions": transitions,
        "upwardProbeCount": len(upward_probes),
        "upwardProbes": upward_probes,
        "minimumAcceptedPreStepSignedOutwardFluxM3S": minimum_accepted_pre_flux,
        "minimumAcceptedPostStepSignedOutwardFluxM3S": minimum_accepted_post_flux,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "negativeDepthCount": int(np.count_nonzero(state[:, 0] < 0.0)),
        "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
        "fishwayDischargeM3S": 0.0,
        "oscillationDetected": oscillation_detected,
        "full300SecondHoldEvaluated": False,
        "physicalValidation": False,
        "yodaConnectionCount": 0,
        "releaseAuthorized": False,
    }


def main() -> None:
    report = run_canary()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
