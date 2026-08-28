#!/usr/bin/env python3
"""Local stage-4 probe using gate-integrated net flux as the close interlock."""

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

import stage20_barrage_operational_control_r1c_adapter_v1 as flux_adapter
import stage20_regularized_multizone_gate_observation_v1 as observation
import stage20_regularized_stage4_ramp_hold_600s_runner_v1 as prescribed


NET_REVERSE_TOLERANCE_M3_S = 1.0e-10
OUTPUT = ROOT / "docs/results/stage20-regularized-stage4-gate-net-flux-probe-v1"
REPORT = OUTPUT / "report.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(
            f"[stage20-regularized-stage4-gate-net-flux-probe-v1] {message}"
        )


def per_gate_flux_diagnostics(
    signed_flux: np.ndarray,
    gate_index_by_face: np.ndarray,
    effective_capacity: np.ndarray,
) -> list[dict[str, Any]]:
    values = np.asarray(signed_flux, dtype=np.float64)
    gate_index = np.asarray(gate_index_by_face, dtype=np.int64)
    capacity = np.asarray(effective_capacity, dtype=np.float64)
    require(values.shape == gate_index.shape, "flux/index shape mismatch")
    require(capacity.shape == (8,), "capacity shape mismatch")
    require(np.isfinite(values).all(), "gate flux is nonfinite")
    rows = []
    for index in range(8):
        selected = gate_index == index
        active = bool(capacity[index] > 0.0)
        selected_values = values[selected]
        negative_rate = float(np.sum(-selected_values[selected_values < 0.0]))
        positive_rate = float(np.sum(selected_values[selected_values > 0.0]))
        total = float(np.sum(selected_values)) if active else 0.0
        rows.append({
            "gateId": index + 1,
            "active": active,
            "faceCount": int(np.sum(selected)),
            "adverseFaceCount": int(np.sum(selected_values < -prescribed.REVERSE_TOLERANCE_M3_S)) if active else 0,
            "minimumSignedOutwardDischargeM3S": float(np.min(selected_values)) if active else None,
            "totalSignedOutwardDischargeM3S": total,
            "localAdverseDischargeRateM3S": negative_rate if active else 0.0,
            "positiveDischargeRateM3S": positive_rate if active else 0.0,
            "localAdverseToPositiveRateRatio": (
                negative_rate / positive_rate if active and positive_rate > 0.0 else 0.0
            ),
        })
    return rows


def prepare_gate_step(
    state: np.ndarray,
    context: dict[str, Any],
    model_seconds: float,
    latched_closed: np.ndarray,
) -> dict[str, Any]:
    """Latch a gate only for near-dry input or gate-integrated net reverse flow."""

    latched = np.asarray(latched_closed, dtype=bool)
    require(latched.shape == (8,), "latched state must contain eight gates")
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
    diagnostics = per_gate_flux_diagnostics(
        signed_flux, workspace["gateIndexBySelectedFace"], effective
    )
    net_trip_indices = np.asarray(
        [
            row["gateId"] - 1
            for row in diagnostics
            if row["active"]
            and row["totalSignedOutwardDischargeM3S"] < -NET_REVERSE_TOLERANCE_M3_S
        ],
        dtype=np.int64,
    )
    if len(net_trip_indices):
        latched[net_trip_indices] = True
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
        final_rows = per_gate_flux_diagnostics(
            signed_flux, workspace["gateIndexBySelectedFace"], effective
        )
    else:
        final_rows = diagnostics
    require(
        all(
            not row["active"]
            or row["totalSignedOutwardDischargeM3S"] >= -NET_REVERSE_TOLERANCE_M3_S
            for row in final_rows
        ),
        "net reverse gate remained active",
    )
    return {
        "requestedCapacity": requested,
        "effectiveCapacity": effective,
        "latchedClosedByGateId1To8": latched.copy(),
        "newWetnessTripGateIds": (np.flatnonzero(wetness_trip) + 1).tolist(),
        "newNetReverseTripGateIds": (net_trip_indices + 1).tolist(),
        "preInterlockPerGate": diagnostics,
        "effectivePerGate": final_rows,
    }


def advance_one_step(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
    latched_closed: np.ndarray,
) -> tuple[Any, dict[str, Any]]:
    guard = prepare_gate_step(state, context, model_seconds, latched_closed)
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
    cumulative_adverse_volume = np.zeros(8, dtype=np.float64)
    cumulative_net_volume = np.zeros(8, dtype=np.float64)
    maximum_adverse_rate = np.zeros(8, dtype=np.float64)
    maximum_adverse_ratio = np.zeros(8, dtype=np.float64)
    minimum_net_rate = np.full(8, math.inf, dtype=np.float64)
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
        dt = float(step.accepted_dt_s)
        for row in guard["effectivePerGate"]:
            index = row["gateId"] - 1
            if row["active"]:
                adverse_rate = float(row["localAdverseDischargeRateM3S"])
                net_rate = float(row["totalSignedOutwardDischargeM3S"])
                cumulative_adverse_volume[index] += adverse_rate * dt
                cumulative_net_volume[index] += net_rate * dt
                maximum_adverse_rate[index] = max(maximum_adverse_rate[index], adverse_rate)
                maximum_adverse_ratio[index] = max(
                    maximum_adverse_ratio[index],
                    float(row["localAdverseToPositiveRateRatio"]),
                )
                minimum_net_rate[index] = min(minimum_net_rate[index], net_rate)
        newly_latched = np.flatnonzero(latched & ~before) + 1
        if len(newly_latched):
            events.append({
                "modelSeconds": model_seconds,
                "gateIds": newly_latched.tolist(),
                "netReverseTripGateIds": guard["newNetReverseTripGateIds"],
                "wetnessTripGateIds": guard["newWetnessTripGateIds"],
            })
        final_effective = guard["effectiveCapacity"].copy()
        state = step.next_state
        model_seconds += dt
        accepted_steps += 1
        expected_volume -= dt * step.boundary_outflow_m3_s
        maximum_cfl = max(maximum_cfl, step.maximum_cfl)
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        maximum_mass_error = max(
            maximum_mass_error,
            abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0),
        )
        require(np.isfinite(state).all(), "state became nonfinite")
        require(np.all(state[:, 0] >= 0.0), "depth became negative")

    gate_rows = []
    for index in range(8):
        gate_rows.append({
            "gateId": index + 1,
            "cumulativeLocalAdverseVolumeM3": float(cumulative_adverse_volume[index]),
            "cumulativeSignedNetVolumeM3": float(cumulative_net_volume[index]),
            "maximumLocalAdverseDischargeRateM3S": float(maximum_adverse_rate[index]),
            "maximumLocalAdverseToPositiveRateRatio": float(maximum_adverse_ratio[index]),
            "minimumGateNetSignedOutwardDischargeM3S": (
                None if math.isinf(minimum_net_rate[index]) else float(minimum_net_rate[index])
            ),
        })
    stage4_held = bool(np.array_equal(final_effective, prescribed.STAGE4))
    return {
        "schema": "onga-stage20-regularized-stage4-gate-net-flux-probe-v1",
        "status": (
            "PASS_LOCAL_GATE_NET_OUTWARD_STAGE4_HELD"
            if stage4_held
            else "PASS_LOCAL_GATE_NET_INTERLOCK_STAGE4_HOLD_NOT_ACHIEVED"
        ),
        "classification": "LOCAL_GATE_NET_FLOW_CONTROL_PROBE_NOT_SALINITY_VALIDATION_NOT_PHYSICAL_FORECAST",
        "simulatedSeconds": model_seconds,
        "acceptedSteps": accepted_steps,
        "wallSeconds": time.monotonic() - wall_started,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "requestedFinalCapacityByGateId1To8": prescribed.requested_capacity(target_seconds).tolist(),
        "effectiveFinalCapacityByGateId1To8": final_effective.tolist(),
        "latchedClosedGateIds": (np.flatnonzero(latched) + 1).tolist(),
        "interlockEvents": events,
        "gateFluxAccounting": gate_rows,
        "allAcceptedActiveGateNetFluxOutward": True,
        "stage4HeldThroughRequestedHold": stage4_held,
        "requestedHoldUnachievableUnderCurrentForcing": not stage4_held,
        "netReverseToleranceM3S": NET_REVERSE_TOLERANCE_M3_S,
        "localFaceReverseIsRecordedNotClipped": True,
        "localAdverseVolumeIsHydrodynamicFaceExchangeNotSaltTransport": True,
        "salinityTransportEvaluated": False,
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
