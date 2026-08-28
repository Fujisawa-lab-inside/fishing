#!/usr/bin/env python3
"""One-state real-context probe for strict facewise Stage-4 backoff.

The script reconstructs the state immediately before the first recorded
strict-facewise trip, then evaluates every capacity candidate from that same
state and at one common accepted dt.  It is intentionally not a duration
controller and has no remote execution path.
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

import stage20_regularized_stage4_per_gate_interlock_probe_v1 as strict_probe
import stage20_stage4_facewise_capacity_backoff_v1 as backoff


CONTRACT_PATH = ROOT / "config/stage20_stage4_facewise_capacity_backoff_real_context_probe_v1.json"
OUTPUT = ROOT / "docs/results/stage20-stage4-facewise-capacity-backoff-real-context-probe-v1"
REPORT = OUTPUT / "report.json"


class RealContextBackoffProbeError(RuntimeError):
    """The local one-state probe contract was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RealContextBackoffProbeError(
            f"[stage20-stage4-facewise-capacity-backoff-real-context-probe-v1] {message}"
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    require(
        contract.get("schema")
        == "onga-stage20-stage4-facewise-capacity-backoff-real-context-probe-v1",
        "contract schema changed",
    )
    require(
        contract.get("status")
        == "LOCAL_SINGLE_STATE_PROBE_READY_NOT_DURATION_CONTROL_NOT_YODA",
        "contract status changed",
    )
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound file absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    require(
        boundary["singleLocalReconstructionAndCandidateProbePermitted"] is True,
        "single local probe disabled",
    )
    for key, value in boundary.items():
        if key != "singleLocalReconstructionAndCandidateProbePermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def advance_with_capacity(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
    capacity: np.ndarray,
) -> Any:
    workspace = context["workspace"]
    strict_probe.prescribed.mapping.update_mapping_workspace(workspace, capacity)
    tide, discharge = strict_probe.prescribed._forcing_values(
        forcing, context["geometry"], model_seconds
    )
    geometry = context["geometry"]
    step = context["kernel"].advance_h2_step_depth_weighted_boundary_with_trace_v1(
        state,
        context["bed"],
        context["manning"],
        geometry["areas"],
        geometry["inverseAreas"],
        geometry["left"],
        geometry["right"],
        workspace["effectiveLengths"],
        geometry["internalNormals"],
        workspace["multipliers"],
        geometry["boundaryCells"],
        geometry["boundaryLengths"],
        geometry["boundaryNormals"],
        geometry["boundaryTags"],
        tide,
        discharge,
        context["donor"],
        context["receiver"],
        0.0,
        0.12,
        maximum_dt,
    )
    require(step.effective_fishway_discharge_m3_s == 0.0, "fishway flow became nonzero")
    require(step.fishway_source_residual_m3_s == 0.0, "fishway residual became nonzero")
    require(bool(np.isfinite(step.next_state).all()), "trial state became nonfinite")
    require(bool(np.all(step.next_state[:, 0] >= 0.0)), "trial depth became negative")
    return step


def reconstruct_pre_trip_state(
    context: dict[str, Any], forcing: dict[str, Any], target_seconds: float
) -> tuple[np.ndarray, int, float]:
    state = context["state"].copy()
    latched = np.zeros(8, dtype=bool)
    model_seconds = 0.0
    accepted_steps = 0
    while model_seconds < target_seconds - 1.0e-12:
        step, guard = strict_probe.advance_one_step(
            state,
            context,
            forcing,
            model_seconds,
            min(0.05, target_seconds - model_seconds),
            latched,
        )
        require(not bool(np.any(latched)), "a gate tripped before the bound target state")
        require(
            guard["newReverseTripGateIds"] == [],
            "reverse trip occurred before the bound target state",
        )
        state = step.next_state
        model_seconds += step.accepted_dt_s
        accepted_steps += 1
    require(abs(model_seconds - target_seconds) <= 1.0e-10, "target time not reached exactly")
    return state, accepted_steps, model_seconds


def _face_flux(
    state: np.ndarray, context: dict[str, Any], capacity: np.ndarray
) -> np.ndarray:
    workspace = context["workspace"]
    strict_probe.prescribed.mapping.update_mapping_workspace(workspace, capacity)
    return strict_probe.flux_adapter.signed_outward_gate_discharge_m3_s(
        state,
        context["bed"],
        context["geometry"],
        context["gate"]["gateFaces"],
        context["gate"]["upstream"],
        workspace["effectiveLengths"],
        workspace["multipliers"],
    )


def compare_candidates_from_state(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
) -> tuple[dict[str, Any], Any]:
    capacities = backoff.candidate_capacities()
    first_pass = [
        advance_with_capacity(state, context, forcing, model_seconds, maximum_dt, capacity)
        for capacity in capacities
    ]
    common_dt = min(float(step.accepted_dt_s) for step in first_pass)
    require(common_dt > 0.0, "common trial dt is not positive")
    trials = [
        advance_with_capacity(state, context, forcing, model_seconds, common_dt, capacity)
        for capacity in capacities
    ]
    require(
        all(abs(float(step.accepted_dt_s) - common_dt) <= 1.0e-15 for step in trials),
        "candidate trials do not share one accepted dt",
    )
    gate_index = context["workspace"]["gateIndexBySelectedFace"]
    evidence = []
    for scale, capacity, step in zip(backoff.CANDIDATE_SCALES, capacities, trials):
        evidence.append(
            {
                "scale": scale,
                "capacityByGateId1To8": capacity.tolist(),
                "signedOutwardFluxM3SBySelectedFace": _face_flux(
                    step.next_state, context, capacity
                ).tolist(),
                "gateIndexBySelectedFace": gate_index.tolist(),
            }
        )
    selection = backoff.select_largest_safe_candidate(evidence)
    selected_index = list(backoff.CANDIDATE_SCALES).index(selection["selectedScale"])
    selected_step = trials[selected_index]
    selected_capacity = capacities[selected_index]
    strict_probe.prescribed.mapping.update_mapping_workspace(
        context["workspace"], selected_capacity
    )
    selection["commonAcceptedDtSeconds"] = common_dt
    selection["trialKernelCallCount"] = len(first_pass) + len(trials)
    selection["acceptedStateSha256"] = hashlib.sha256(
        np.ascontiguousarray(selected_step.next_state, dtype=np.float64).tobytes()
    ).hexdigest()
    return selection, selected_step


def run_probe() -> dict[str, Any]:
    contract = verified_contract()
    backoff.read_and_verify_contract()
    target = float(contract["scope"]["targetModelSeconds"])
    maximum_dt = float(contract["scope"]["maximumTrialDtSeconds"])
    context = strict_probe.prescribed.load_runtime_context()
    forcing = strict_probe.prescribed.matched.base.read_json(
        strict_probe.prescribed.FORCING_PATH
    )
    strict_probe.prescribed.matched.base.validate_forcing(forcing)
    wall_started = time.monotonic()
    state, accepted_steps, reached = reconstruct_pre_trip_state(
        context, forcing, target
    )
    pre_flux = _face_flux(state, context, backoff.stage4_capacity_for_scale(1.0))
    active = np.isin(
        context["workspace"]["gateIndexBySelectedFace"],
        np.asarray(backoff.ACTIVE_GATE_IDS) - 1,
    )
    selection, selected_step = compare_candidates_from_state(
        state, context, forcing, reached, maximum_dt
    )
    return {
        "schema": "onga-stage20-stage4-facewise-capacity-backoff-real-context-probe-v1-result",
        "status": "PASS_LOCAL_SINGLE_PRETRIP_STATE_BACKOFF_PROBE_NOT_DURATION_CONTROL",
        "targetModelSeconds": target,
        "reconstructionAcceptedSteps": accepted_steps,
        "reconstructionWallSeconds": time.monotonic() - wall_started,
        "fullCapacityPreStepMinimumSignedOutwardFluxM3S": float(np.min(pre_flux[active])),
        "fullCapacityPreStepAdverseFaceCount": int(
            np.count_nonzero(pre_flux[active] < -backoff.REVERSE_TOLERANCE_M3_S)
        ),
        "selection": selection,
        "selectedStepMaximumCfl": float(selected_step.maximum_cfl),
        "selectedStepNegativeDepthCount": int(np.count_nonzero(selected_step.next_state[:, 0] < 0.0)),
        "selectedStepNonFiniteValueCount": int(
            selected_step.next_state.size - np.isfinite(selected_step.next_state).sum()
        ),
        "fishwayDischargeM3S": float(selected_step.effective_fishway_discharge_m3_s),
        "durationControlEvaluated": False,
        "physicalValidation": False,
        "yodaConnectionCount": 0,
        "releaseAuthorized": False,
    }


def main() -> None:
    report = run_probe()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
