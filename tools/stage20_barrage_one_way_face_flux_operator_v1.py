#!/usr/bin/env python3
"""Pure conservative branch resolver for one oriented barrage face.

This module does not calculate a Riemann flux and does not connect to the
solver.  It selects between already-computed open-interface and reflected-wall
terms using a SHA-bound upstream orientation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/stage20_barrage_one_way_face_flux_operator_v1.json"
MASS_CONSERVATION_TOLERANCE = 1.0e-12


class OneWayFaceFluxError(RuntimeError):
    """The pure one-way face contract was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OneWayFaceFluxError(
            f"[stage20-barrage-one-way-face-flux-operator-v1] {message}"
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    require(
        contract.get("schema") == "onga-stage20-barrage-one-way-face-flux-operator-v1",
        "contract schema changed",
    )
    require(
        contract.get("status") == "LOCAL_PURE_FACE_OPERATOR_READY_NOT_KERNEL_CONNECTED",
        "contract status changed",
    )
    require(
        contract["orientation"]["reverseBranchThresholdM3PerMS"] == 0.0,
        "reverse threshold weakened",
    )
    invariants = contract["invariants"]
    require(invariants["reverseMassTransferPermitted"] is False, "reverse transfer enabled")
    require(invariants["postHocStateRepairPermitted"] is False, "state repair enabled")
    require(invariants["negativeDepthClippingPermitted"] is False, "depth clipping enabled")
    require(invariants["wallMassTermsMustBeZero"] is True, "wall mass invariant weakened")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound file absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["pureOperatorAndSyntheticTestsPermitted"] is True, "pure tests disabled")
    for key, value in boundary.items():
        if key != "pureOperatorAndSyntheticTestsPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def _term(value: object, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    require(result.shape == (3,), f"{name} must contain h, hu, hv")
    require(bool(np.isfinite(result).all()), f"{name} contains nonfinite values")
    return result


def resolve_one_way_face_terms(
    *,
    open_left_term: object,
    open_right_term: object,
    wall_left_term: object,
    wall_right_term: object,
    opening_multiplier: float,
    upstream_is_left: bool,
) -> dict[str, Any]:
    """Return conservative mass terms and explicit structure momentum reaction."""

    verified_contract()
    open_left = _term(open_left_term, "open left term")
    open_right = _term(open_right_term, "open right term")
    wall_left = _term(wall_left_term, "wall left term")
    wall_right = _term(wall_right_term, "wall right term")
    multiplier = float(opening_multiplier)
    require(np.isfinite(multiplier) and 0.0 <= multiplier <= 1.0, "opening outside 0..1")
    require(
        abs(float(open_left[0] + open_right[0])) <= MASS_CONSERVATION_TOLERANCE,
        "open-interface mass terms are not equal and opposite",
    )
    require(
        abs(float(wall_left[0])) <= MASS_CONSERVATION_TOLERANCE
        and abs(float(wall_right[0])) <= MASS_CONSERVATION_TOLERANCE,
        "reflected wall carries mass",
    )

    raw_outward_mass_term = float(open_left[0] if upstream_is_left else open_right[0])
    if multiplier == 0.0:
        branch = "WALL_CLOSED"
        left = wall_left.copy()
        right = wall_right.copy()
    elif raw_outward_mass_term < 0.0:
        branch = "WALL_BLOCKED_REVERSE"
        left = wall_left.copy()
        right = wall_right.copy()
    else:
        branch = "OPEN_OUTWARD_BLEND"
        wall_fraction = 1.0 - multiplier
        left = multiplier * open_left + wall_fraction * wall_left
        right = multiplier * open_right + wall_fraction * wall_right

    mass_residual = float(left[0] + right[0])
    require(
        abs(mass_residual) <= MASS_CONSERVATION_TOLERANCE,
        "resolved mass terms are not conservative",
    )
    resolved_outward_mass_term = float(left[0] if upstream_is_left else right[0])
    require(
        resolved_outward_mass_term >= -MASS_CONSERVATION_TOLERANCE,
        "resolved face transfers mass toward upstream",
    )
    momentum_reaction = left[1:] + right[1:]
    return {
        "schema": "onga-stage20-barrage-one-way-face-flux-operator-v1-result",
        "status": "PASS_PURE_FACE_BRANCH_RESOLVED_NOT_KERNEL_CONNECTED",
        "branch": branch,
        "openingMultiplier": multiplier,
        "upstreamIsLeft": bool(upstream_is_left),
        "rawOutwardMassTerm": raw_outward_mass_term,
        "resolvedOutwardMassTerm": resolved_outward_mass_term,
        "leftTerm": left.tolist(),
        "rightTerm": right.tolist(),
        "massResidual": mass_residual,
        "structureMomentumReactionXY": momentum_reaction.tolist(),
        "reverseMassTransferPermitted": False,
        "kernelConnectionPerformed": False,
        "physicalValidation": False,
    }


if __name__ == "__main__":
    print(json.dumps({
        "schema": "onga-stage20-barrage-one-way-face-flux-operator-v1-preflight",
        "status": "PASS_LOCAL_PURE_OPERATOR_NOT_KERNEL_CONNECTED",
        "contract": verified_contract()["status"],
    }, ensure_ascii=False))
