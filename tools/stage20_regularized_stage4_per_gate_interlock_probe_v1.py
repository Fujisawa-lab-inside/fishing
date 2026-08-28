#!/usr/bin/env python3
"""Local-only per-gate latched reverse-flow interlock probe for stage 4."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_barrage_fractional_motion_r1c_adapter_v1 as fractional
import stage20_barrage_operational_control_r1c_adapter_v1 as flux_adapter
import stage20_regularized_multizone_gate_observation_v1 as observation
import stage20_regularized_stage4_ramp_hold_600s_runner_v1 as prescribed


STATUS = "LOCAL_CONTROL_PROBE_NOT_YODA_AUTHORITY_NOT_PHYSICAL_VALIDATION"
OUTPUT = ROOT / "docs/results/stage20-regularized-stage4-per-gate-interlock-probe-v1"
REPORT = OUTPUT / "report.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(
            f"[stage20-regularized-stage4-per-gate-interlock-probe-v1] {message}"
        )


def prepare_interlocked_gate_step(
    state: np.ndarray,
    context: dict[str, Any],
    model_seconds: float,
    latched_closed: np.ndarray,
) -> dict[str, Any]:
    """Close an entire affected gate before advancing; never clip face flux."""

    latched = np.asarray(latched_closed, dtype=bool)
    require(latched.shape == (8,), "latched gate state must contain eight gates")
    requested = prescribed.requested_capacity(model_seconds)
    observed = observation.observe_per_gate(state, context["gate"])
    trusted = np.asarray(
        observed["trustedForPositiveMotionByGateId1To8"], dtype=bool
    )
    wetness_trip = (requested > 0.0) & ~trusted
    latched |= wetness_trip

    workspace = context["workspace"]
    effective = requested.copy()
    effective[latched] = 0.0
    prescribed.mapping.update_mapping_workspace(workspace, effective)
    signed_flux = flux_adapter.signed_outward_gate_discharge_m3_s(
        state,
        context["bed"],
        context["geometry"],
        context["gate"]["gateFaces"],
        context["gate"]["upstream"],
        workspace["effectiveLengths"],
        workspace["multipliers"],
    )
    selected_gate_index = workspace["gateIndexBySelectedFace"]
    active = effective[selected_gate_index] > 0.0
    adverse = active & (signed_flux < -prescribed.REVERSE_TOLERANCE_M3_S)
    pre_trip_minimum = float(np.min(signed_flux[adverse])) if np.any(adverse) else None
    reverse_trip_gate_indices = np.unique(selected_gate_index[adverse])
    pre_trip_rows = []
    for gate_index in reverse_trip_gate_indices:
        selected = selected_gate_index == gate_index
        selected_active = selected & active
        pre_trip_rows.append({
            "gateId": int(gate_index + 1),
            "activeFaceCount": int(np.sum(selected_active)),
            "adverseFaceCount": int(np.sum(selected_active & adverse)),
            "minimumSignedOutwardDischargeM3S": float(np.min(signed_flux[selected_active])),
            "totalSignedOutwardDischargeM3S": float(np.sum(signed_flux[selected_active])),
        })
    if len(reverse_trip_gate_indices):
        latched[reverse_trip_gate_indices] = True
        effective = requested.copy()
        effective[latched] = 0.0
        prescribed.mapping.update_mapping_workspace(workspace, effective)
        signed_flux = flux_adapter.signed_outward_gate_discharge_m3_s(
            state,
            context["bed"],
            context["geometry"],
            context["gate"]["gateFaces"],
            context["gate"]["upstream"],
            workspace["effectiveLengths"],
            workspace["multipliers"],
        )
    validation = fractional.validate_fractional_active_flux(
        signed_flux,
        selected_gate_index,
        effective,
        tolerance_m3_s=prescribed.REVERSE_TOLERANCE_M3_S,
    )
    return {
        "requestedCapacity": requested,
        "effectiveCapacity": effective,
        "latchedClosedByGateId1To8": latched.copy(),
        "newWetnessTripGateIds": (np.flatnonzero(wetness_trip) + 1).tolist(),
        "newReverseTripGateIds": (reverse_trip_gate_indices + 1).tolist(),
        "preTripMinimumSignedOutwardDischargeM3S": pre_trip_minimum,
        "preTripGateDiagnostics": pre_trip_rows,
        "validation": validation,
    }


def advance_one_step(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
    latched_closed: np.ndarray,
) -> tuple[Any, dict[str, Any]]:
    guard = prepare_interlocked_gate_step(
        state, context, model_seconds, latched_closed
    )
    tide, discharge = prescribed._forcing_values(
        forcing, context["geometry"], model_seconds
    )
    geometry = context["geometry"]
    workspace = context["workspace"]
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
    return step, guard


def run_probe(target_seconds: float = prescribed.TOTAL_SECONDS) -> dict[str, Any]:
    require(0.0 < target_seconds <= prescribed.TOTAL_SECONDS, "target time invalid")
    context = prescribed.load_runtime_context()
    forcing = prescribed.matched.base.read_json(prescribed.FORCING_PATH)
    prescribed.matched.base.validate_forcing(forcing)
    state = context["state"].copy()
    geometry = context["geometry"]
    latched = np.zeros(8, dtype=bool)
    events: list[dict[str, Any]] = []
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_mass_error = 0.0
    maximum_cfl = 0.0
    model_seconds = 0.0
    accepted_steps = 0
    wall_started = time.monotonic()
    final_effective = np.zeros(8, dtype=np.float64)

    while model_seconds < target_seconds - 1.0e-12:
        before = latched.copy()
        step, guard = advance_one_step(
            state,
            context,
            forcing,
            model_seconds,
            min(0.05, target_seconds - model_seconds),
            latched,
        )
        newly_latched = np.flatnonzero(latched & ~before) + 1
        if len(newly_latched):
            events.append({
                "modelSeconds": model_seconds,
                "gateIds": newly_latched.tolist(),
                "reverseTripGateIds": guard["newReverseTripGateIds"],
                "wetnessTripGateIds": guard["newWetnessTripGateIds"],
                "preTripGateDiagnostics": guard["preTripGateDiagnostics"],
            })
        final_effective = guard["effectiveCapacity"].copy()
        state = step.next_state
        model_seconds += step.accepted_dt_s
        accepted_steps += 1
        expected_volume -= step.accepted_dt_s * step.boundary_outflow_m3_s
        maximum_cfl = max(maximum_cfl, step.maximum_cfl)
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        maximum_mass_error = max(
            maximum_mass_error,
            abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0),
        )
        require(np.isfinite(state).all(), "state became nonfinite")
        require(np.all(state[:, 0] >= 0.0), "depth became negative")

    return {
        "schema": "onga-stage20-regularized-stage4-per-gate-interlock-probe-v1",
        "status": "PASS_LOCAL_PER_GATE_LATCHED_INTERLOCK_NUMERICAL_PROBE",
        "classification": STATUS,
        "simulatedSeconds": model_seconds,
        "acceptedSteps": accepted_steps,
        "wallSeconds": time.monotonic() - wall_started,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "requestedFinalCapacityByGateId1To8": prescribed.requested_capacity(target_seconds).tolist(),
        "effectiveFinalCapacityByGateId1To8": final_effective.tolist(),
        "latchedClosedGateIds": (np.flatnonzero(latched) + 1).tolist(),
        "interlockEvents": events,
        "negativeDepthCount": int(np.sum(state[:, 0] < 0.0)),
        "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
        "fishwayDischargeM3S": 0.0,
        "meshAdopted": False,
        "physicalValidation": False,
    }


def main() -> None:
    report = run_probe()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
