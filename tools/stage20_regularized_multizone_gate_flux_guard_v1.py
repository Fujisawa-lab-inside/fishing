#!/usr/bin/env python3
"""Candidate-mesh outward-flux and adverse-head fail-closed probes."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import run_stage20_barrage_C1_local_transition_600s_v1 as mapping
import stage20_barrage_fractional_motion_r1c_adapter_v1 as fractional
import stage20_barrage_operational_control_r1c_adapter_v1 as flux_adapter
import stage20_regularized_multizone_gate_observation_v1 as observation


OUTPUT = ROOT / "docs/results/stage20-regularized-multizone-gate-flux-guard-v1"
REPORT = OUTPUT / "report.json"
STAGE4 = np.asarray([0, 0, 1, 1, 1, 1, 0, 0], dtype=np.float64)
RAMP_FRACTIONS = (0.0, 0.1, 0.25, 0.5, 1.0)
REVERSE_TOLERANCE_M3_S = 1.0e-10


def flux_for_capacity(
    state: np.ndarray,
    context: dict[str, Any],
    capacity: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any], dict[str, Any]]:
    workspace = mapping.build_mapping_workspace(context["geometry"])
    mapping.update_mapping_workspace(workspace, capacity)
    flux = flux_adapter.signed_outward_gate_discharge_m3_s(
        state,
        context["bed"],
        context["geometry"],
        context["gateFaces"],
        context["upstream"],
        workspace["effectiveLengths"],
        workspace["multipliers"],
    )
    validation = fractional.validate_fractional_active_flux(
        flux,
        workspace["gateIndexBySelectedFace"],
        capacity,
        tolerance_m3_s=REVERSE_TOLERANCE_M3_S,
    )
    return flux, validation, workspace


def adverse_fixture(context: dict[str, Any]) -> np.ndarray:
    state = np.column_stack(
        (context["depth"].copy(), np.zeros((28746, 2), dtype=np.float64))
    )
    selected = np.isin(context["gateIds"], [3, 4, 5, 6])
    downstream = np.unique(context["downstream"][selected])
    state[downstream, 0] += 0.03
    return state


def build_report() -> dict[str, Any]:
    context = observation.load_bound_context()
    final = np.load(context["statePath"], allow_pickle=False)
    ramp_rows = []
    totals = []
    for fraction in RAMP_FRACTIONS:
        capacity = STAGE4 * fraction
        flux, validation, workspace = flux_for_capacity(final, context, capacity)
        active = capacity[workspace["gateIndexBySelectedFace"]] > 0.0
        total = float(np.sum(flux[active])) if np.any(active) else 0.0
        totals.append(total)
        ramp_rows.append({
            "stage4CapacityFraction": fraction,
            "activeFaceCount": int(np.sum(active)),
            "minimumSignedOutwardFaceDischargeM3S": (
                float(np.min(flux[active])) if np.any(active) else None
            ),
            "totalSignedOutwardDischargeM3S": total,
            "reverseFlowGuard": validation,
        })
    monotonic = bool(np.all(np.diff(totals) >= -1.0e-12))

    adverse_state = adverse_fixture(context)
    capacity = STAGE4 * 0.25
    workspace = mapping.build_mapping_workspace(context["geometry"])
    mapping.update_mapping_workspace(workspace, capacity)
    adverse_flux = flux_adapter.signed_outward_gate_discharge_m3_s(
        adverse_state, context["bed"], context["geometry"], context["gateFaces"],
        context["upstream"], workspace["effectiveLengths"], workspace["multipliers"],
    )
    active = capacity[workspace["gateIndexBySelectedFace"]] > 0.0
    rejected = False
    rejection_message = None
    try:
        fractional.validate_fractional_active_flux(
            adverse_flux,
            workspace["gateIndexBySelectedFace"],
            capacity,
            tolerance_m3_s=REVERSE_TOLERANCE_M3_S,
        )
    except ValueError as error:
        rejected = True
        rejection_message = str(error)
    zero_flux, zero_validation, _ = flux_for_capacity(
        adverse_state, context, np.zeros(8, dtype=np.float64)
    )
    return {
        "schema": "onga-stage20-regularized-multizone-gate-flux-guard-v1",
        "version": 1,
        "status": "PASS_LOCAL_STAGE4_OUTWARD_RAMP_AND_ADVERSE_HEAD_REJECTION_RUNTIME_NOT_CONNECTED",
        "classification": "LOCAL_NUMERICAL_FLUX_PROBE_NOT_OPERATIONAL_OR_PHYSICAL_CALIBRATION",
        "stage4OutwardRamp": {
            "capacityFractions": list(RAMP_FRACTIONS),
            "rows": ramp_rows,
            "totalOutwardDischargeMonotonic": monotonic,
            "allActiveFaceFluxOutward": all(
                row["minimumSignedOutwardFaceDischargeM3S"] is None
                or row["minimumSignedOutwardFaceDischargeM3S"] >= -REVERSE_TOLERANCE_M3_S
                for row in ramp_rows
            ),
        },
        "adverseHeadProbe": {
            "fixtureDownstreamHeadIncreaseM": 0.03,
            "stage4CapacityFraction": 0.25,
            "activeFaceCount": int(np.sum(active)),
            "adverseFaceCount": int(np.sum(adverse_flux[active] < -REVERSE_TOLERANCE_M3_S)),
            "minimumSignedOutwardFaceDischargeM3S": float(np.min(adverse_flux[active])),
            "totalSignedOutwardDischargeM3S": float(np.sum(adverse_flux[active])),
            "rejectedWithoutClipping": rejected,
            "rejectionMessage": rejection_message,
            "allClosedAfterInterlockActiveFaceCount": zero_validation["activeFaceCount"],
            "allClosedMaximumAbsoluteFluxM3S": float(np.max(np.abs(zero_flux))),
        },
        "decision": {
            "localFluxMechanicsPass": monotonic and rejected and float(np.max(np.abs(zero_flux))) == 0.0,
            "runtimeConnected": False,
            "YodaDynamicGateCanaryAuthorized": False,
            "meshOperationallyAdopted": False,
            "next": "connect the SHA-bound orientation and predictive fractional controller under a separate single-use runtime activation",
        },
    }


def main() -> None:
    report = build_report()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
