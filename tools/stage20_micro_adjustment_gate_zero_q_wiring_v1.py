#!/usr/bin/env python3
"""Zero-discharge wiring proof for the micro-adjustment-gate primitive.

The adapter is intentionally incapable of requesting nonzero flow.  It loads
the SHA-bound regularized context, applies the transfer primitive at Q=0, and
proves that one numerical step remains bit-identical to the existing runner.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

import stage20_micro_adjustment_gate_transfer_primitive_v1 as transfer
import stage20_regularized_multizone_900s_runner_v1 as regularized


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/stage20_micro_adjustment_gate_zero_q_wiring_v1.json"


class ZeroQWiringError(RuntimeError):
    """Changed identity or failed no-op invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ZeroQWiringError(
            f"[stage20-micro-adjustment-gate-zero-q-wiring-v1] {message}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_and_verify_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    _require(
        contract.get("schema")
        == "onga-stage20-micro-adjustment-gate-zero-q-wiring-v1",
        "contract schema changed",
    )
    _require(
        contract.get("status")
        == "PASS_LOCAL_ZERO_Q_BIT_EXACT_WIRING_NOT_NONZERO_CONNECTION",
        "contract status changed",
    )
    for binding in contract.get("bindings", []):
        path = ROOT / binding["path"]
        _require(path.is_file(), f"bound file absent: {path}")
        _require(_sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    _require(boundary["zeroQOneStepWiringPermitted"] is True, "zero-Q proof disabled")
    for key, value in boundary.items():
        if key != "zeroQOneStepWiringPermitted":
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


def run_zero_q_one_step_equivalence() -> dict[str, Any]:
    """Prove real-context Q=0 wiring is a bit-exact numerical no-op."""

    contract = read_and_verify_contract()
    context = regularized.load_numerical_context()
    fields_binding = next(
        row for row in contract["bindings"] if row["role"] == "candidate_fields"
    )
    with np.load(ROOT / fields_binding["path"], allow_pickle=False) as archive:
        upstream_mask = np.asarray(
            archive["upstream_component_mask"], dtype=np.bool_
        )
        raw_receiver = np.asarray(
            archive["p2_receiver_overlap_area_m2"], dtype=np.float64
        )
    _require(np.any(upstream_mask), "upstream donor support is empty")
    _require(np.all(raw_receiver >= 0.0), "receiver overlap is negative")
    receiver_total = float(np.sum(raw_receiver))
    _require(receiver_total > 0.0, "downstream receiver support is empty")
    receiver_weights = raw_receiver / receiver_total
    _require(
        not np.any(receiver_weights[upstream_mask] > 0.0),
        "upstream and downstream supports overlap",
    )

    state_before = context["state"].copy()
    wired = transfer.apply_authorized_outward_transfer(
        state_h_hu_hv=state_before,
        cell_areas_m2=context["geometry"]["areas"],
        upstream_donor_mask=upstream_mask,
        downstream_receiver_weights=receiver_weights,
        time_step_s=0.01,
        requested_outward_discharge_m3_s=0.0,
        head_difference_m=0.0,
        safety=_safety(),
    )
    _require(
        wired["diagnostics"]["effectiveOutwardDischargeM3S"] == 0.0,
        "zero-Q primitive produced nonzero flow",
    )
    _require(
        np.count_nonzero(wired["massRateM3SByCell"]) == 0
        and np.count_nonzero(wired["horizontalMomentumRateXByCell"]) == 0
        and np.count_nonzero(wired["horizontalMomentumRateYByCell"]) == 0,
        "zero-Q primitive produced a source",
    )
    _require(
        wired["postSourceDepthM"].tobytes() == state_before[:, 0].tobytes(),
        "zero-Q primitive changed depth",
    )

    arguments = list(regularized.one_step_arguments(context))
    kernel = context["kernel"]
    baseline = kernel.advance_h2_step_depth_weighted_boundary(*arguments)
    wired_state = state_before.copy()
    areas = context["geometry"]["areas"]
    wired_state[:, 0] = wired["postSourceDepthM"]
    wired_state[:, 1] += (
        0.01 * wired["horizontalMomentumRateXByCell"] / areas
    )
    wired_state[:, 2] += (
        0.01 * wired["horizontalMomentumRateYByCell"] / areas
    )
    _require(wired_state.tobytes() == state_before.tobytes(), "wired input changed")
    arguments[0] = wired_state
    after_wiring = kernel.advance_h2_step_depth_weighted_boundary(*arguments)
    _require(
        baseline[0].tobytes() == after_wiring[0].tobytes(),
        "one-step state is not bit identical",
    )
    _require(baseline[1:] == after_wiring[1:], "one-step scalars changed")

    return {
        "schema": "onga-stage20-micro-adjustment-gate-zero-q-wiring-v1-report",
        "status": "PASS_LOCAL_ZERO_Q_REAL_CONTEXT_ONE_STEP_BIT_EXACT",
        "cellCount": int(len(state_before)),
        "donorCellCount": int(np.count_nonzero(upstream_mask)),
        "receiverCellCount": int(np.count_nonzero(receiver_weights)),
        "requestedDischargeM3S": 0.0,
        "effectiveDischargeM3S": 0.0,
        "sourceNonzeroCount": 0,
        "inputStateBitExact": True,
        "oneStepStateBitExact": True,
        "oneStepScalarsBitExact": True,
        "acceptedDtSeconds": float(after_wiring[1]),
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
        "nonzeroDischargeConnectionPermitted": False,
        "physicalValidation": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_zero_q_one_step_equivalence(), ensure_ascii=False))
