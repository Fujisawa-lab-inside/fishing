#!/usr/bin/env python3
"""Direction-aware per-gate observation for outward barrage release.

An outward release requires a trusted wet upstream cell and a positive local
free-surface head difference.  A dry downstream cell is recorded but is not,
by itself, an adverse-flow condition.  Gate-net flux is still checked by the
separate interlock before a numerical step is accepted.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


VERSION = "stage20-regularized-multizone-gate-outward-observation-v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{VERSION}] {message}")


def observe_per_gate_outward(
    state: np.ndarray,
    context: dict[str, Any],
    *,
    minimum_outward_head_margin_m: float = 0.0,
) -> dict[str, Any]:
    values = np.asarray(state, dtype=np.float64)
    require(values.ndim == 2 and values.shape[1] == 3, "state shape changed")
    require(bool(np.isfinite(values).all()), "state contains non-finite values")
    require(bool(np.all(values[:, 0] >= 0.0)), "state contains negative depth")
    margin = float(minimum_outward_head_margin_m)
    require(math.isfinite(margin) and margin >= 0.0, "head margin is invalid")
    bed = np.asarray(context["bed"], dtype=np.float64)
    upstream = np.asarray(context["upstream"], dtype=np.int64)
    downstream = np.asarray(context["downstream"], dtype=np.int64)
    gate_ids = np.asarray(context["gateIds"], dtype=np.int64)
    faces = np.asarray(context["gateFaces"], dtype=np.int64)
    lengths = np.asarray(context["geometry"]["internalLengths"], dtype=np.float64)[faces]
    threshold = float(context["contract"]["semantics"]["minimumTrustedSelectedFaceDepthM"])
    eta = values[:, 0] + bed
    head_difference = eta[upstream] - eta[downstream]

    rows: list[dict[str, Any]] = []
    trusted_by_gate: list[bool] = []
    for gate_id in range(1, 9):
        selected = gate_ids == gate_id
        require(bool(np.any(selected)), f"gate {gate_id} has no selected faces")
        weight = lengths[selected] / float(np.sum(lengths[selected]))
        upstream_depth = values[upstream[selected], 0]
        downstream_depth = values[downstream[selected], 0]
        local_head = head_difference[selected]
        weighted_head = float(np.sum(weight * local_head))
        upstream_wet = bool(np.min(upstream_depth) > threshold)
        outward_head = bool(weighted_head > margin)
        trusted = upstream_wet and outward_head
        if not upstream_wet:
            reason = "DRY_OR_NEAR_DRY_UPSTREAM_SELECTED_FACE_SIDE"
        elif not outward_head:
            reason = "ADVERSE_OR_INSUFFICIENT_LOCAL_HEAD"
        else:
            reason = None
        trusted_by_gate.append(trusted)
        rows.append(
            {
                "gateId": gate_id,
                "faceCount": int(np.sum(selected)),
                "weightedMeanHeadDifferenceM": weighted_head,
                "minimumLocalHeadDifferenceM": float(np.min(local_head)),
                "maximumLocalHeadDifferenceM": float(np.max(local_head)),
                "adverseOrInsufficientLocalHeadFaceCount": int(np.sum(local_head <= margin)),
                "minimumUpstreamSelectedFaceDepthM": float(np.min(upstream_depth)),
                "minimumDownstreamSelectedFaceDepthM": float(np.min(downstream_depth)),
                "downstreamDryOrNearDryFaceCount": int(np.sum(downstream_depth <= threshold)),
                "minimumSelectedFaceSideDepthM": float(
                    min(np.min(upstream_depth), np.min(downstream_depth))
                ),
                "trustedForPositiveMotionObservation": trusted,
                "failClosedReason": reason,
            }
        )
    return {
        "version": VERSION,
        "minimumTrustedSelectedFaceDepthM": threshold,
        "minimumOutwardHeadMarginM": margin,
        "perGate": rows,
        "trustedForPositiveMotionByGateId1To8": trusted_by_gate,
        "trustedGateIds": [index + 1 for index, value in enumerate(trusted_by_gate) if value],
        "failClosedGateIds": [index + 1 for index, value in enumerate(trusted_by_gate) if not value],
        "globalAllGateShutdownRequired": False,
        "downstreamDrynessAloneBlocksOutwardMotion": False,
        "localHeadReversalAloneBlocksOutwardMotion": False,
        "headTrustBasis": "LENGTH_WEIGHTED_GATE_MEAN",
        "gateNetFluxCheckStillRequired": True,
    }
