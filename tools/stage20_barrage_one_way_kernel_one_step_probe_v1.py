#!/usr/bin/env python3
"""Real-context one-step evidence for the copied one-way barrage kernel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_barrage_one_way_depth_weighted_kernel_candidate_v1 as candidate
import stage20_depth_weighted_boundary_kernel_candidate_v2 as legacy
import stage20_regularized_stage4_ramp_hold_600s_runner_v1 as stage4


CONTRACT_PATH = ROOT / "config/stage20_barrage_one_way_kernel_one_step_probe_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-one-way-kernel-one-step-probe-v1"
REPORT = OUTPUT / "report.json"


class OneWayKernelProbeError(RuntimeError):
    """The one-step probe contract was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OneWayKernelProbeError(
            f"[stage20-barrage-one-way-kernel-one-step-probe-v1] {message}"
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    require(
        contract.get("schema") == "onga-stage20-barrage-one-way-kernel-one-step-probe-v1",
        "contract schema changed",
    )
    require(
        contract.get("status") == "LOCAL_REAL_CONTEXT_ONE_STEP_READY_NOT_DURATION_NOT_YODA",
        "contract status changed",
    )
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound file absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["singleLocalRealContextProbePermitted"] is True, "local probe disabled")
    for key, value in boundary.items():
        if key != "singleLocalRealContextProbePermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def runtime() -> tuple[dict[str, Any], dict[str, Any], np.ndarray]:
    context = stage4.load_runtime_context()
    forcing = stage4.matched.base.read_json(stage4.FORCING_PATH)
    stage4.matched.base.validate_forcing(forcing)
    geometry = context["geometry"]
    orientation = np.full(len(geometry["left"]), -1, dtype=np.int64)
    orientation[context["gate"]["gateFaces"]] = context["gate"]["upstream"]
    require(int(np.count_nonzero(orientation >= 0)) == len(context["gate"]["gateFaces"]), "orientation coverage changed")
    return context, forcing, orientation


def arguments(
    state: np.ndarray,
    context: dict[str, Any],
    forcing: dict[str, Any],
) -> tuple[Any, ...]:
    capacity = stage4.requested_capacity(150.0)
    stage4.mapping.update_mapping_workspace(context["workspace"], capacity)
    tide, discharge = stage4._forcing_values(forcing, context["geometry"], 150.0)
    geometry = context["geometry"]
    return (
        state, context["bed"], context["manning"], geometry["areas"],
        geometry["inverseAreas"], geometry["left"], geometry["right"],
        context["workspace"]["effectiveLengths"], geometry["internalNormals"],
        context["workspace"]["multipliers"], geometry["boundaryCells"],
        geometry["boundaryLengths"], geometry["boundaryNormals"],
        geometry["boundaryTags"], tide, discharge, context["donor"],
        context["receiver"], 0.0, 0.12, 0.05,
    )


def run_probe() -> dict[str, Any]:
    contract = verified_contract()
    context, forcing, orientation = runtime()
    outward_args = arguments(context["state"], context, forcing)
    old = legacy.advance_h2_step_depth_weighted_boundary_with_trace_v1(*outward_args)
    outward = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
        *outward_args, orientation
    )
    state_bit_exact = outward.next_state.tobytes() == old.next_state.tobytes()
    scalars_exact = tuple(outward[1:6]) == tuple(old[1:6])
    limiter_exact = outward.limiter_sample == old.limiter_sample
    require(state_bit_exact and scalars_exact and limiter_exact, "outward case differs from legacy")
    require(outward.blocked_reverse_face_count == 0, "outward case blocked a face")

    adverse_state = context["state"].copy()
    selected = np.isin(context["gate"]["gateIds"], contract["scope"].get("activeGateIds", [3, 4, 5, 6]))
    downstream = np.unique(context["gate"]["downstream"][selected])
    adverse_state[downstream, 0] += 0.30
    adverse_args = arguments(adverse_state, context, forcing)
    adverse = candidate.advance_h2_step_barrage_one_way_with_trace_v1(
        *adverse_args, orientation
    )
    geometry = context["geometry"]
    initial_volume = float(np.sum(adverse_state[:, 0] * geometry["areas"]))
    final_volume = float(np.sum(adverse.next_state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume - adverse.accepted_dt_s * adverse.boundary_outflow_m3_s
    relative_mass_error = abs(final_volume - expected_volume) / max(abs(initial_volume), 1.0)
    require(adverse.blocked_reverse_face_count > 0, "adverse case did not block a face")
    require(relative_mass_error <= 1.0e-12, "adverse case mass balance failed")
    require(bool(np.isfinite(adverse.next_state).all()), "adverse state became nonfinite")
    require(bool(np.all(adverse.next_state[:, 0] >= 0.0)), "adverse depth became negative")
    require(adverse.effective_fishway_discharge_m3_s == 0.0, "fishway flow became nonzero")
    require(adverse.fishway_source_residual_m3_s == 0.0, "fishway residual became nonzero")
    require(
        adverse.limiter_sample.expected_candidate_count == len(adverse_state)
        and adverse.limiter_sample.evaluated_candidate_count == len(adverse_state)
        and adverse.limiter_sample.coverage_complete,
        "adverse limiter coverage incomplete",
    )
    return {
        "schema": "onga-stage20-barrage-one-way-kernel-one-step-probe-v1-result",
        "status": "PASS_LOCAL_REAL_CONTEXT_ONE_STEP_NOT_DURATION_NOT_PHYSICAL_VALIDATION",
        "cellCount": len(context["state"]),
        "orientedBarrageFaceCount": int(np.count_nonzero(orientation >= 0)),
        "outwardCase": {
            "stateBitExactToLegacy": state_bit_exact,
            "scalarsBitExactToLegacy": scalars_exact,
            "limiterBitExactToLegacy": limiter_exact,
            "blockedReverseFaceCount": outward.blocked_reverse_face_count,
            "acceptedDtSeconds": outward.accepted_dt_s,
        },
        "adverseCase": {
            "blockedReverseFaceCount": adverse.blocked_reverse_face_count,
            "blockedReversePotentialDischargeM3S": adverse.blocked_reverse_potential_discharge_m3_s,
            "maximumCfl": adverse.maximum_cfl,
            "relativeMassBalanceError": relative_mass_error,
            "negativeDepthCount": int(np.count_nonzero(adverse.next_state[:, 0] < 0.0)),
            "nonFiniteValueCount": int(adverse.next_state.size - np.isfinite(adverse.next_state).sum()),
            "fishwayDischargeM3S": adverse.effective_fishway_discharge_m3_s,
            "fishwayResidualM3S": adverse.fishway_source_residual_m3_s,
            "limiterExpectedCandidateCount": adverse.limiter_sample.expected_candidate_count,
            "limiterEvaluatedCandidateCount": adverse.limiter_sample.evaluated_candidate_count,
            "limiterCoverageComplete": adverse.limiter_sample.coverage_complete,
        },
        "durationRunPerformed": False,
        "yodaConnectionCount": 0,
        "legacyKernelModified": False,
        "physicalValidation": False,
        "releaseAuthorized": False,
    }


def main() -> None:
    report = run_probe()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
