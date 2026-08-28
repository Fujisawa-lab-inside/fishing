#!/usr/bin/env python3
"""Local-only micro-adjustment-gate Q sensitivity on the regularized mesh.

The requested discharge grid is explicitly uncalibrated and user-approved
only for numerical sensitivity.  Every accepted hydrodynamic step is followed
by one conservative source application over that exact accepted time step.
No physical gate law, mesh change, A8 command, fishway flow, YODA connection,
or output writing is implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

import stage20_micro_adjustment_gate_transfer_primitive_v1 as transfer
import stage20_regularized_multizone_900s_runner_v1 as regularized


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/stage20_micro_adjustment_gate_local_q_sensitivity_v1.json"
FORCING_PATH = ROOT / "config/stage20_continuous_all_closed_forcing_manifest_20260828_v1.json"
Q_GRID_M3_S = (0.0, 6.0, 12.0, 18.0, 24.0)
DURATION_SECONDS = 60.0
MAXIMUM_KERNEL_DT_SECONDS = 0.05
MAXIMUM_ACCEPTED_STEPS_PER_CASE = 20000
MAXIMUM_WALL_SECONDS_PER_CASE = 300.0


class LocalQSensitivityError(RuntimeError):
    """Changed identity or failed local numerical invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LocalQSensitivityError(
            f"[stage20-micro-adjustment-gate-local-q-sensitivity-v1] {message}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_and_verify_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    _require(
        contract.get("schema")
        == "onga-stage20-micro-adjustment-gate-local-q-sensitivity-v1",
        "contract schema changed",
    )
    _require(
        contract.get("status")
        == "USER_APPROVED_LOCAL_UNCALIBRATED_Q_SENSITIVITY_NOT_PHYSICAL",
        "contract status changed",
    )
    scope = contract["scope"]
    _require(scope["requestedDischargeGridM3S"] == list(Q_GRID_M3_S), "Q grid changed")
    _require(scope["durationSeconds"] == DURATION_SECONDS, "duration changed")
    _require(scope["mainGateCapacityByGateId1To8"] == [0.0] * 8, "main gate opened")
    _require(scope["fishwayDischargeM3S"] == 0.0, "fishway enabled")
    _require(scope["forcingStartModelSeconds"] == 0.0, "forcing start changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        _require(path.is_file(), f"bound file absent: {path}")
        _require(_sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    _require(boundary["localOneStepAndShortDurationPermitted"] is True, "local scope disabled")
    for key, value in boundary.items():
        if key != "localOneStepAndShortDurationPermitted":
            _require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def _safety() -> transfer.TransferSafety:
    primitive_contract = json.loads(
        (ROOT / "config/stage20_micro_adjustment_gate_transfer_primitive_v1.json").read_text()
    )
    values = primitive_contract["safetyParameters"]
    return transfer.TransferSafety(
        reserve_depth_m=float(values["reserveDepthM"]),
        maximum_available_volume_fraction_per_step=float(
            values["maximumAvailableVolumeFractionPerStep"]
        ),
        adverse_head_shutdown_m=float(values["adverseHeadShutdownM"]),
    )


def _load_supports(contract: dict[str, Any]) -> dict[str, np.ndarray]:
    fields = next(row for row in contract["bindings"] if row["role"] == "candidate_fields")
    with np.load(ROOT / fields["path"], allow_pickle=False) as archive:
        upstream_mask = np.asarray(archive["upstream_component_mask"], dtype=np.bool_)
        donor_overlap = np.asarray(archive["p2_donor_overlap_area_m2"], dtype=np.float64)
        receiver_overlap = np.asarray(
            archive["p2_receiver_overlap_area_m2"], dtype=np.float64
        )
    _require(upstream_mask.shape == donor_overlap.shape == receiver_overlap.shape, "support shape mismatch")
    _require(np.any(upstream_mask), "upstream component is empty")
    _require(
        np.isfinite(donor_overlap).all()
        and np.isfinite(receiver_overlap).all()
        and np.all(donor_overlap >= 0.0)
        and np.all(receiver_overlap >= 0.0),
        "invalid P2 support",
    )
    donor_total = float(np.sum(donor_overlap))
    receiver_total = float(np.sum(receiver_overlap))
    _require(donor_total > 0.0 and receiver_total > 0.0, "empty P2 support")
    donor_weights = donor_overlap / donor_total
    receiver_weights = receiver_overlap / receiver_total
    _require(np.all(donor_weights[~upstream_mask] == 0.0), "donor leaves upstream component")
    _require(np.all(receiver_weights[upstream_mask] == 0.0), "receiver enters upstream component")
    return {
        "upstreamMask": upstream_mask,
        "donorHeadWeights": donor_weights,
        "receiverHeadWeights": receiver_weights,
        "receiverWeights": receiver_weights,
    }


def _head_difference_m(
    state: np.ndarray,
    bed: np.ndarray,
    supports: dict[str, np.ndarray],
) -> float:
    water_surface = state[:, 0] + bed
    upstream = float(np.sum(water_surface * supports["donorHeadWeights"]))
    downstream = float(np.sum(water_surface * supports["receiverHeadWeights"]))
    value = upstream - downstream
    _require(math.isfinite(value), "nonfinite head difference")
    return value


def _forcing_values(
    forcing: dict[str, Any], geometry: dict[str, Any], model_seconds: float
) -> tuple[float, np.ndarray]:
    timeline = forcing["timeline"]["modelSeconds"]
    discharge = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        value = regularized.base._interpolate(
            forcing["series"]["riverDischargeM3S"][boundary_id],
            timeline,
            model_seconds,
        )
        discharge[tag] = -value / float(geometry["boundaryTagLengthSums"][tag])
    tide = regularized.base._interpolate(
        forcing["series"]["relativeTideM"], timeline, model_seconds
    )
    return float(tide), discharge


def _hydrodynamic_step(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
    model_seconds: float,
    maximum_dt: float,
) -> Any:
    geometry = context["geometry"]
    regularized.base.require_structure_closed(
        context["kernel"], geometry["internalMarkers"], context["multipliers"]
    )
    tide, discharge = _forcing_values(forcing, geometry, model_seconds)
    step = context["kernel"].advance_h2_step_depth_weighted_boundary_with_trace_v1(
        state,
        context["bed"],
        context["manning"],
        geometry["areas"],
        geometry["inverseAreas"],
        geometry["left"],
        geometry["right"],
        geometry["internalLengths"],
        geometry["internalNormals"],
        context["multipliers"],
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
    _require(step.effective_fishway_discharge_m3_s == 0.0, "fishway flow became nonzero")
    _require(step.fishway_source_residual_m3_s == 0.0, "fishway residual became nonzero")
    return step


def _apply_micro_source(
    hydro_state: np.ndarray,
    context: dict[str, Any],
    supports: dict[str, np.ndarray],
    accepted_dt_s: float,
    requested_q_m3_s: float,
) -> tuple[np.ndarray, dict[str, Any], float]:
    head = _head_difference_m(hydro_state, context["bed"], supports)
    result = transfer.apply_authorized_outward_transfer(
        state_h_hu_hv=hydro_state,
        cell_areas_m2=context["geometry"]["areas"],
        upstream_donor_mask=supports["upstreamMask"],
        downstream_receiver_weights=supports["receiverWeights"],
        time_step_s=accepted_dt_s,
        requested_outward_discharge_m3_s=requested_q_m3_s,
        head_difference_m=head,
        safety=_safety(),
    )
    areas = context["geometry"]["areas"]
    state = hydro_state.copy()
    state[:, 0] = result["postSourceDepthM"]
    state[:, 1] += accepted_dt_s * result["horizontalMomentumRateXByCell"] / areas
    state[:, 2] += accepted_dt_s * result["horizontalMomentumRateYByCell"] / areas
    source_volume_residual = float(
        np.sum((state[:, 0] - hydro_state[:, 0]) * areas)
    )
    _require(abs(source_volume_residual) <= 1e-9, "discrete source volume residual exceeded")
    _require(np.isfinite(state).all(), "source result contains nonfinite values")
    _require(np.all(state[:, 0] >= 0.0), "source result contains negative depth")
    return state, result["diagnostics"], source_volume_residual


def run_one_step_grid() -> dict[str, Any]:
    contract = read_and_verify_contract()
    context = regularized.load_numerical_context()
    forcing = regularized.base.read_json(FORCING_PATH)
    regularized.base.validate_forcing(forcing)
    supports = _load_supports(contract)
    hydro = _hydrodynamic_step(
        context["state"], context, forcing, 0.0, MAXIMUM_KERNEL_DT_SECONDS
    )
    cases = []
    for requested_q in Q_GRID_M3_S:
        state, diagnostics, volume_residual = _apply_micro_source(
            hydro.next_state,
            context,
            supports,
            hydro.accepted_dt_s,
            requested_q,
        )
        if requested_q == 0.0:
            _require(state.tobytes() == hydro.next_state.tobytes(), "Q=0 is not bit exact")
        cases.append(
            {
                "requestedDischargeM3S": requested_q,
                "effectiveDischargeM3S": diagnostics["effectiveOutwardDischargeM3S"],
                "headDifferenceM": diagnostics["headDifferenceM"],
                "adverseHeadFactor": diagnostics["adverseHeadFactor"],
                "massResidualM3S": diagnostics["massResidualM3S"],
                "discreteSourceVolumeResidualM3": volume_residual,
                "minimumDepthM": float(np.min(state[:, 0])),
                "negativeDepthCount": int(np.count_nonzero(state[:, 0] < 0.0)),
                "nonFiniteValueCount": int(np.size(state) - np.count_nonzero(np.isfinite(state))),
                "limitation": diagnostics["limitation"],
                "qZeroStateBitExact": requested_q != 0.0 or state.tobytes() == hydro.next_state.tobytes(),
            }
        )
    effective = [row["effectiveDischargeM3S"] for row in cases]
    _require(all(a <= b + 1e-12 for a, b in zip(effective, effective[1:])), "effective Q is not monotonic")
    return {
        "schema": "onga-stage20-micro-adjustment-gate-local-q-one-step-v1-report",
        "status": "PASS_LOCAL_UNCALIBRATED_Q_GRID_ONE_STEP_NOT_PHYSICAL",
        "cellCount": int(len(context["state"])),
        "acceptedDtSeconds": float(hydro.accepted_dt_s),
        "maximumCfl": float(hydro.maximum_cfl),
        "cases": cases,
        "allCasesSafe": True,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
        "physicalValidation": False,
    }


def run_duration_grid(duration_seconds: float = DURATION_SECONDS) -> dict[str, Any]:
    _require(duration_seconds == DURATION_SECONDS, "duration authority changed")
    one_step = run_one_step_grid()
    _require(one_step["allCasesSafe"], "one-step gate failed")
    contract = read_and_verify_contract()
    context = regularized.load_numerical_context()
    forcing = regularized.base.read_json(FORCING_PATH)
    regularized.base.validate_forcing(forcing)
    supports = _load_supports(contract)
    geometry = context["geometry"]
    initial_state = context["state"]
    initial_volume = float(np.sum(initial_state[:, 0] * geometry["areas"]))
    cases = []
    for requested_q in Q_GRID_M3_S:
        state = initial_state.copy()
        model_seconds = 0.0
        accepted_steps = 0
        expected_volume = initial_volume
        cumulative_effective_volume = 0.0
        maximum_cfl = 0.0
        maximum_relative_mass_error = 0.0
        maximum_source_mass_residual = 0.0
        maximum_source_volume_residual = 0.0
        minimum_head = math.inf
        maximum_head = -math.inf
        minimum_adverse_factor = 1.0
        limitation_counts: dict[str, int] = {}
        wall_started = time.monotonic()
        while model_seconds < duration_seconds - 1e-12:
            _require(
                time.monotonic() - wall_started <= MAXIMUM_WALL_SECONDS_PER_CASE,
                "case wall-time limit exceeded",
            )
            _require(
                accepted_steps < MAXIMUM_ACCEPTED_STEPS_PER_CASE,
                "case accepted-step limit exceeded",
            )
            maximum_dt = min(MAXIMUM_KERNEL_DT_SECONDS, duration_seconds - model_seconds)
            hydro = _hydrodynamic_step(state, context, forcing, model_seconds, maximum_dt)
            state, diagnostics, source_volume_residual = _apply_micro_source(
                hydro.next_state,
                context,
                supports,
                hydro.accepted_dt_s,
                requested_q,
            )
            if requested_q == 0.0:
                _require(
                    state.tobytes() == hydro.next_state.tobytes(),
                    "Q=0 duration source is not a no-op",
                )
            model_seconds += hydro.accepted_dt_s
            accepted_steps += 1
            expected_volume -= hydro.accepted_dt_s * hydro.boundary_outflow_m3_s
            cumulative_effective_volume += (
                hydro.accepted_dt_s * diagnostics["effectiveOutwardDischargeM3S"]
            )
            actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
            relative_mass_error = abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0)
            maximum_relative_mass_error = max(maximum_relative_mass_error, relative_mass_error)
            maximum_cfl = max(maximum_cfl, float(hydro.maximum_cfl))
            maximum_source_mass_residual = max(
                maximum_source_mass_residual, abs(diagnostics["massResidualM3S"])
            )
            maximum_source_volume_residual = max(
                maximum_source_volume_residual, abs(source_volume_residual)
            )
            minimum_head = min(minimum_head, diagnostics["headDifferenceM"])
            maximum_head = max(maximum_head, diagnostics["headDifferenceM"])
            minimum_adverse_factor = min(
                minimum_adverse_factor, diagnostics["adverseHeadFactor"]
            )
            label = diagnostics["limitation"]
            limitation_counts[label] = limitation_counts.get(label, 0) + 1
        _require(math.isclose(model_seconds, duration_seconds, abs_tol=1e-9), "duration mismatch")
        _require(maximum_cfl <= 0.120000000001, "CFL acceptance failed")
        _require(maximum_relative_mass_error <= 1e-10, "mass acceptance failed")
        _require(maximum_source_mass_residual <= 1e-12, "source mass guard failed")
        _require(np.isfinite(state).all(), "final state contains nonfinite values")
        _require(np.all(state[:, 0] >= 0.0), "final state contains negative depth")
        cases.append(
            {
                "requestedDischargeM3S": requested_q,
                "simulatedSeconds": model_seconds,
                "acceptedSteps": accepted_steps,
                "wallSeconds": time.monotonic() - wall_started,
                "cumulativeEffectiveTransferVolumeM3": cumulative_effective_volume,
                "maximumCfl": maximum_cfl,
                "maximumRelativeMassBalanceError": maximum_relative_mass_error,
                "maximumSourceMassResidualM3S": maximum_source_mass_residual,
                "maximumDiscreteSourceVolumeResidualM3": maximum_source_volume_residual,
                "minimumHeadDifferenceM": minimum_head,
                "maximumHeadDifferenceM": maximum_head,
                "minimumAdverseHeadFactor": minimum_adverse_factor,
                "minimumDepthM": float(np.min(state[:, 0])),
                "maximumDepthM": float(np.max(state[:, 0])),
                "negativeDepthCount": int(np.count_nonzero(state[:, 0] < 0.0)),
                "nonFiniteValueCount": int(np.size(state) - np.count_nonzero(np.isfinite(state))),
                "limitationCounts": limitation_counts,
                "finalStateRawSha256": hashlib.sha256(
                    np.ascontiguousarray(state).tobytes()
                ).hexdigest(),
            }
        )
    cumulative = [row["cumulativeEffectiveTransferVolumeM3"] for row in cases]
    _require(all(a <= b + 1e-9 for a, b in zip(cumulative, cumulative[1:])), "cumulative transfer is not monotonic")
    return {
        "schema": "onga-stage20-micro-adjustment-gate-local-q-sensitivity-v1-report",
        "status": "PASS_LOCAL_60S_UNCALIBRATED_Q_SENSITIVITY_NOT_PHYSICAL",
        "classification": "LOCAL_NUMERICAL_COUPLING_ONLY_NOT_GATE_RATING_NOT_FORECAST",
        "operatorSplit": "hydrodynamic_step_then_conservative_micro_source_over_accepted_dt",
        "initialState": "regularized_multizone_candidate_at_forcing_model_second_0",
        "mainGateCapacityByGateId1To8": [0.0] * 8,
        "fishwayDischargeM3S": 0.0,
        "requestedDischargeGridM3S": list(Q_GRID_M3_S),
        "oneStepGate": one_step,
        "cases": cases,
        "allCasesNumericallySafe": True,
        "physicalDischargeLawImplemented": False,
        "a8CombinedScenarioEvaluated": False,
        "meshChanged": False,
        "outputCreationCountByRunner": 0,
        "yodaConnectionCount": 0,
        "physicalValidation": False,
        "forecastAuthorized": False,
        "guiAuthorized": False,
        "releaseAuthorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--one-step-grid", action="store_true")
    parser.add_argument("--duration-grid", action="store_true")
    arguments = parser.parse_args()
    _require(arguments.one_step_grid != arguments.duration_grid, "choose exactly one mode")
    report = run_one_step_grid() if arguments.one_step_grid else run_duration_grid()
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
