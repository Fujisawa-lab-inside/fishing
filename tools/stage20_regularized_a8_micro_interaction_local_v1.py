#!/usr/bin/env python3
"""Sparse local A8-by-micro interaction diagnostic on the regularized mesh.

The two A8 targets use a 30 s linear numerical ramp followed by a 30 s hold.
The three externally requested micro discharges remain uncalibrated.  This
module has no output-writing, remote, forecast, GUI, or release capability.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Iterator

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_micro_adjustment_gate_local_q_sensitivity_v1 as micro
import stage20_regularized_a8_capacity_sweep_v1 as a8_v1
import stage20_regularized_a8_directional_capacity_sweep_v2 as a8_v2
import stage20_regularized_stage4_gate_net_flux_probe_v1 as gate_probe


CONTRACT_PATH = ROOT / "config/stage20_regularized_a8_micro_interaction_local_v1.json"
MICRO_REPORT_PATH = ROOT / "docs/results/stage20-micro-adjustment-gate-local-q-sensitivity-v1/report.json"
SCHEMA = "onga-stage20-regularized-a8-micro-interaction-local-v1-report"
A8_TARGETS = (0.5, 1.0)
MICRO_Q_M3_S = (0.0, 12.0, 24.0)
DURATION_SECONDS = 60.0
RAMP_SECONDS = 30.0
MAXIMUM_DT_SECONDS = 0.05
MAXIMUM_ACCEPTED_STEPS_PER_CASE = 20000
MAXIMUM_WALL_SECONDS_PER_CASE = 300.0
INITIAL_STATE_RAW_SHA256 = "ea38025be6337869479cecbe898fdd49161a092d44d3e18e1baf3302adbdaf1e"


class LocalInteractionError(RuntimeError):
    """Changed identity or failed local interaction invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LocalInteractionError(
            f"[stage20-regularized-a8-micro-interaction-local-v1] {message}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_and_verify_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    _require(contract.get("schema") == "onga-stage20-regularized-a8-micro-interaction-local-v1", "contract schema changed")
    _require(contract.get("status") == "USER_DIRECTED_RESUME_SPARSE_LOCAL_INTERACTION_NOT_PHYSICAL", "contract status changed")
    scope = contract["scope"]
    _require(scope["newA8TargetCapacityGrid"] == list(A8_TARGETS), "A8 grid changed")
    _require(scope["microCommandGridM3S"] == list(MICRO_Q_M3_S), "micro Q grid changed")
    _require(scope["newCaseCount"] == 6, "new case count changed")
    _require(scope["reusedA8ZeroCaseCount"] == 3, "reuse count changed")
    _require(scope["durationSeconds"] == DURATION_SECONDS, "duration changed")
    _require(scope["a8RampSeconds"] == RAMP_SECONDS, "ramp changed")
    _require(scope["a8HoldSeconds"] == DURATION_SECONDS - RAMP_SECONDS, "hold changed")
    _require(scope["forcingStartModelSeconds"] == 0.0, "forcing start changed")
    _require(scope["initialStateRawSha256"] == INITIAL_STATE_RAW_SHA256, "initial state identity changed")
    _require(scope["allNonA8MainGateCapacity"] == 0.0, "non-A8 gate enabled")
    _require(scope["fishwayDischargeM3S"] == 0.0, "fishway enabled")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        _require(path.is_file(), f"bound file absent: {path}")
        _require(_sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    _require(boundary["sixNewLocalCasesPermitted"] is True, "new local cases disabled")
    _require(boundary["reuseThreeA8ZeroCasesWithoutRerun"] is True, "reuse disabled")
    for key, value in boundary.items():
        if key not in {"sixNewLocalCasesPermitted", "reuseThreeA8ZeroCasesWithoutRerun"}:
            _require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def reused_a8_zero_cases(contract: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    verified = read_and_verify_contract() if contract is None else contract
    binding = next(row for row in verified["bindings"] if row["role"] == "micro_q_prior_report")
    _require(_sha256(MICRO_REPORT_PATH) == binding["sha256"], "micro report SHA changed")
    source = json.loads(MICRO_REPORT_PATH.read_text())
    by_q = {float(row["requestedDischargeM3S"]): row for row in source["cases"]}
    rows = []
    for requested_q in MICRO_Q_M3_S:
        source_row = by_q[requested_q]
        rows.append({
            "targetA8Capacity": 0.0,
            "requestedMicroDischargeM3S": requested_q,
            "simulatedSeconds": source_row["simulatedSeconds"],
            "acceptedSteps": source_row["acceptedSteps"],
            "wallSeconds": source_row["wallSeconds"],
            "cumulativeA8SignedNetVolumeM3": 0.0,
            "cumulativeA8LocalAdverseVolumeM3": 0.0,
            "cumulativeEffectiveMicroTransferVolumeM3": source_row["cumulativeEffectiveTransferVolumeM3"],
            "averageEffectiveMicroDischargeM3S": source_row["cumulativeEffectiveTransferVolumeM3"] / source_row["simulatedSeconds"],
            "minimumMicroHeadDifferenceM": source_row["minimumHeadDifferenceM"],
            "minimumMicroAdverseHeadFactor": source_row["minimumAdverseHeadFactor"],
            "maximumCfl": source_row["maximumCfl"],
            "maximumRelativeMassBalanceError": source_row["maximumRelativeMassBalanceError"],
            "negativeDepthCount": source_row["negativeDepthCount"],
            "nonFiniteValueCount": source_row["nonFiniteValueCount"],
            "effectiveFinalCapacityByGateId1To8": [0.0] * 8,
            "a8TargetHeldAtEnd": True,
            "a8InterlockEvents": [],
            "finalStateRawSha256": source_row["finalStateRawSha256"],
            "reusedWithoutRecalculation": True,
        })
    return rows


def requested_a8_capacity(model_seconds: float, target_capacity: float) -> np.ndarray:
    time_value = float(model_seconds)
    target = float(target_capacity)
    _require(math.isfinite(time_value) and time_value >= 0.0, "model time invalid")
    _require(target in A8_TARGETS, "A8 target outside approved grid")
    result = np.empty(8, dtype=np.float64)
    a8_v1.gate_net_probe.prescribed.mapping.set_capacity_at_time(
        result,
        np.zeros(8, dtype=np.float64),
        np.asarray([7], dtype=np.int64),
        target,
        min(time_value, RAMP_SECONDS),
        RAMP_SECONDS,
    )
    _require(bool(np.all(result[:7] == 0.0)), "non-A8 gate opened")
    _require(0.0 <= result[7] <= target, "A8 escaped target")
    return result


@contextmanager
def _interaction_schedule(target_capacity: float) -> Iterator[None]:
    original_request = gate_probe.prescribed.requested_capacity
    original_observe = gate_probe.observation.observe_per_gate
    gate_probe.prescribed.requested_capacity = (
        lambda model_seconds: requested_a8_capacity(model_seconds, target_capacity)
    )
    gate_probe.observation.observe_per_gate = a8_v2.outward.observe_per_gate_outward
    try:
        yield
    finally:
        gate_probe.prescribed.requested_capacity = original_request
        gate_probe.observation.observe_per_gate = original_observe


def _load_context() -> tuple[dict[str, Any], dict[str, Any]]:
    context = gate_probe.prescribed.load_runtime_context()
    common = micro.regularized.load_numerical_context()
    _require(context["bed"].tobytes() == common["bed"].tobytes(), "bed differs across runtimes")
    _require(context["manning"].tobytes() == common["manning"].tobytes(), "Manning field differs across runtimes")
    _require(
        context["geometry"]["areas"].tobytes() == common["geometry"]["areas"].tobytes(),
        "cell areas differ across runtimes",
    )
    _require(
        context["geometry"]["left"].tobytes() == common["geometry"]["left"].tobytes()
        and context["geometry"]["right"].tobytes() == common["geometry"]["right"].tobytes(),
        "mesh connectivity differs across runtimes",
    )
    common_state = np.ascontiguousarray(common["state"], dtype=np.float64)
    _require(hashlib.sha256(common_state.tobytes()).hexdigest() == INITIAL_STATE_RAW_SHA256, "common initial state SHA changed")
    context["state"] = common_state.copy()
    forcing = gate_probe.prescribed.matched.base.read_json(gate_probe.prescribed.FORCING_PATH)
    gate_probe.prescribed.matched.base.validate_forcing(forcing)
    return context, forcing


def run_one_step_grid() -> dict[str, Any]:
    contract = read_and_verify_contract()
    context, forcing = _load_context()
    supports = micro._load_supports(contract)
    rows = []
    for target in A8_TARGETS:
        for requested_q in MICRO_Q_M3_S:
            latched = np.zeros(8, dtype=bool)
            with _interaction_schedule(target):
                hydro, guard = gate_probe.advance_one_step(
                    context["state"].copy(), context, forcing, RAMP_SECONDS,
                    MAXIMUM_DT_SECONDS, latched,
                )
            state, diagnostics, volume_residual = micro._apply_micro_source(
                hydro.next_state, context, supports, hydro.accepted_dt_s, requested_q
            )
            if requested_q == 0.0:
                _require(state.tobytes() == hydro.next_state.tobytes(), "Q=0 source not bit exact")
            a8_row = next(row for row in guard["effectivePerGate"] if row["gateId"] == 8)
            _require(
                not a8_row["active"] or a8_row["totalSignedOutwardDischargeM3S"] >= -gate_probe.NET_REVERSE_TOLERANCE_M3_S,
                "active A8 retained reverse net flow",
            )
            rows.append({
                "targetA8Capacity": target,
                "requestedMicroDischargeM3S": requested_q,
                "acceptedDtSeconds": float(hydro.accepted_dt_s),
                "effectiveA8Capacity": float(guard["effectiveCapacity"][7]),
                "a8NetSignedOutwardDischargeM3S": float(a8_row["totalSignedOutwardDischargeM3S"]),
                "effectiveMicroDischargeM3S": float(diagnostics["effectiveOutwardDischargeM3S"]),
                "microHeadDifferenceM": float(diagnostics["headDifferenceM"]),
                "microAdverseHeadFactor": float(diagnostics["adverseHeadFactor"]),
                "sourceMassResidualM3S": float(diagnostics["massResidualM3S"]),
                "discreteSourceVolumeResidualM3": volume_residual,
                "negativeDepthCount": int(np.count_nonzero(state[:, 0] < 0.0)),
                "nonFiniteValueCount": int(state.size - np.count_nonzero(np.isfinite(state))),
                "qZeroStateBitExact": requested_q != 0.0 or state.tobytes() == hydro.next_state.tobytes(),
            })
    _require(len(rows) == 6, "one-step case count changed")
    _require(all(row["negativeDepthCount"] == 0 and row["nonFiniteValueCount"] == 0 for row in rows), "one-step state unsafe")
    return {
        "schema": "onga-stage20-regularized-a8-micro-interaction-one-step-v1-report",
        "status": "PASS_LOCAL_SIX_CASE_ONE_STEP_INTERACTION_NOT_PHYSICAL",
        "cases": rows,
        "allCasesSafe": True,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
        "physicalValidation": False,
    }


def _run_duration_case(
    target: float,
    requested_q: float,
    contract: dict[str, Any],
) -> dict[str, Any]:
    context, forcing = _load_context()
    supports = micro._load_supports(contract)
    state = context["state"].copy()
    geometry = context["geometry"]
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    latched = np.zeros(8, dtype=bool)
    model_seconds = 0.0
    accepted_steps = 0
    cumulative_a8_net = 0.0
    cumulative_a8_adverse = 0.0
    cumulative_micro = 0.0
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_source_mass_residual = 0.0
    maximum_source_volume_residual = 0.0
    minimum_micro_head = math.inf
    minimum_micro_factor = 1.0
    events: list[dict[str, Any]] = []
    final_effective = np.zeros(8, dtype=np.float64)
    wall_started = time.monotonic()
    with _interaction_schedule(target):
        while model_seconds < DURATION_SECONDS - 1e-12:
            _require(time.monotonic() - wall_started <= MAXIMUM_WALL_SECONDS_PER_CASE, "case wall limit exceeded")
            _require(accepted_steps < MAXIMUM_ACCEPTED_STEPS_PER_CASE, "case step limit exceeded")
            before = latched.copy()
            hydro, guard = gate_probe.advance_one_step(
                state, context, forcing, model_seconds,
                min(MAXIMUM_DT_SECONDS, DURATION_SECONDS - model_seconds), latched,
            )
            dt = float(hydro.accepted_dt_s)
            state, diagnostics, source_volume_residual = micro._apply_micro_source(
                hydro.next_state, context, supports, dt, requested_q
            )
            if requested_q == 0.0:
                _require(state.tobytes() == hydro.next_state.tobytes(), "Q=0 duration source not bit exact")
            a8_row = next(row for row in guard["effectivePerGate"] if row["gateId"] == 8)
            _require(
                not a8_row["active"] or a8_row["totalSignedOutwardDischargeM3S"] >= -gate_probe.NET_REVERSE_TOLERANCE_M3_S,
                "active A8 retained reverse net flow",
            )
            if a8_row["active"]:
                cumulative_a8_net += dt * float(a8_row["totalSignedOutwardDischargeM3S"])
                cumulative_a8_adverse += dt * float(a8_row["localAdverseDischargeRateM3S"])
            newly_latched = np.flatnonzero(latched & ~before) + 1
            if len(newly_latched):
                events.append({
                    "modelSeconds": model_seconds,
                    "gateIds": newly_latched.tolist(),
                    "netReverseTripGateIds": guard["newNetReverseTripGateIds"],
                    "wetnessTripGateIds": guard["newWetnessTripGateIds"],
                })
            final_effective = guard["effectiveCapacity"].copy()
            model_seconds += dt
            accepted_steps += 1
            expected_volume -= dt * hydro.boundary_outflow_m3_s
            actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
            maximum_mass_error = max(
                maximum_mass_error,
                abs(actual_volume - expected_volume) / max(abs(initial_volume), 1.0),
            )
            cumulative_micro += dt * float(diagnostics["effectiveOutwardDischargeM3S"])
            maximum_cfl = max(maximum_cfl, float(hydro.maximum_cfl))
            maximum_source_mass_residual = max(maximum_source_mass_residual, abs(float(diagnostics["massResidualM3S"])))
            maximum_source_volume_residual = max(maximum_source_volume_residual, abs(source_volume_residual))
            minimum_micro_head = min(minimum_micro_head, float(diagnostics["headDifferenceM"]))
            minimum_micro_factor = min(minimum_micro_factor, float(diagnostics["adverseHeadFactor"]))
            _require(np.isfinite(state).all(), "state became nonfinite")
            _require(np.all(state[:, 0] >= 0.0), "depth became negative")
    _require(math.isclose(model_seconds, DURATION_SECONDS, abs_tol=1e-9), "duration mismatch")
    _require(maximum_cfl <= 0.120000000001, "CFL acceptance failed")
    _require(maximum_mass_error <= 1e-10, "mass acceptance failed")
    _require(maximum_source_mass_residual <= 1e-12, "source mass residual failed")
    return {
        "targetA8Capacity": target,
        "requestedMicroDischargeM3S": requested_q,
        "simulatedSeconds": model_seconds,
        "acceptedSteps": accepted_steps,
        "wallSeconds": time.monotonic() - wall_started,
        "cumulativeA8SignedNetVolumeM3": cumulative_a8_net,
        "cumulativeA8LocalAdverseVolumeM3": cumulative_a8_adverse,
        "cumulativeEffectiveMicroTransferVolumeM3": cumulative_micro,
        "averageEffectiveMicroDischargeM3S": cumulative_micro / model_seconds,
        "minimumMicroHeadDifferenceM": minimum_micro_head,
        "minimumMicroAdverseHeadFactor": minimum_micro_factor,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "maximumSourceMassResidualM3S": maximum_source_mass_residual,
        "maximumDiscreteSourceVolumeResidualM3": maximum_source_volume_residual,
        "negativeDepthCount": int(np.count_nonzero(state[:, 0] < 0.0)),
        "nonFiniteValueCount": int(state.size - np.count_nonzero(np.isfinite(state))),
        "effectiveFinalCapacityByGateId1To8": final_effective.tolist(),
        "a8TargetHeldAtEnd": bool(not latched[7] and math.isclose(final_effective[7], target, abs_tol=1e-12)),
        "a8InterlockEvents": events,
        "finalStateRawSha256": hashlib.sha256(np.ascontiguousarray(state).tobytes()).hexdigest(),
        "reusedWithoutRecalculation": False,
    }


def run_duration_grid() -> dict[str, Any]:
    one_step = run_one_step_grid()
    _require(one_step["allCasesSafe"], "one-step gate failed")
    contract = read_and_verify_contract()
    reused = reused_a8_zero_cases(contract)
    new_cases = [
        _run_duration_case(target, requested_q, contract)
        for target in A8_TARGETS
        for requested_q in MICRO_Q_M3_S
    ]
    all_cases = reused + new_cases
    _require(len(all_cases) == 9 and len(new_cases) == 6, "interaction matrix size changed")
    all_safe = all(
        row["negativeDepthCount"] == 0
        and row["nonFiniteValueCount"] == 0
        and row["maximumCfl"] <= 0.120000000001
        and row["maximumRelativeMassBalanceError"] <= 1e-10
        for row in all_cases
    )
    _require(all_safe, "interaction matrix unsafe")
    comparison = {}
    for requested_q in MICRO_Q_M3_S:
        rows = [row for row in all_cases if row["requestedMicroDischargeM3S"] == requested_q]
        rows.sort(key=lambda row: row["targetA8Capacity"])
        comparison[str(int(requested_q))] = [
            {
                "targetA8Capacity": row["targetA8Capacity"],
                "averageEffectiveMicroDischargeM3S": row["averageEffectiveMicroDischargeM3S"],
                "cumulativeA8SignedNetVolumeM3": row["cumulativeA8SignedNetVolumeM3"],
                "a8TargetHeldAtEnd": row["a8TargetHeldAtEnd"],
            }
            for row in rows
        ]
    return {
        "schema": SCHEMA,
        "status": "PASS_LOCAL_SPARSE_A8_MICRO_INTERACTION_NUMERICALLY_SAFE_NOT_PHYSICAL",
        "classification": "LOCAL_UNCALIBRATED_INTERACTION_SCREEN_NOT_GATE_RATING_NOT_OPERATION_NOT_FORECAST",
        "a8Schedule": {"rampSeconds": RAMP_SECONDS, "holdSeconds": DURATION_SECONDS - RAMP_SECONDS},
        "commonInitialStateRawSha256": INITIAL_STATE_RAW_SHA256,
        "discardedPrecanonicalInitialStateMismatchRunCount": 1,
        "operatorSplit": "direction_guarded_hydrodynamic_step_then_conservative_micro_source_over_accepted_dt",
        "reusedCaseCount": len(reused),
        "newlyRunCaseCount": len(new_cases),
        "cases": all_cases,
        "comparisonByRequestedMicroQ": comparison,
        "allCasesNumericallySafe": all_safe,
        "allNewA8TargetsHeldAtEnd": all(row["a8TargetHeldAtEnd"] for row in new_cases),
        "anyA8Interlock": any(row["a8InterlockEvents"] for row in new_cases),
        "physicalA8ScheduleApproved": False,
        "physicalMicroDischargeLawApproved": False,
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
