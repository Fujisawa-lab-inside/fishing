#!/usr/bin/env python3
"""Pure jointly-scaled Stage-4 capacity backoff planner.

Each candidate must be evaluated by the caller on its own tentative post-step
state.  This module selects evidence; it never runs the kernel, clips flux,
writes output, or connects to a remote host.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/stage20_stage4_facewise_capacity_backoff_v1.json"
ACTIVE_GATE_IDS = (3, 4, 5, 6)
CANDIDATE_SCALES = (1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0)
REVERSE_TOLERANCE_M3_S = 1.0e-10


class FacewiseCapacityBackoffError(RuntimeError):
    """Invalid candidate evidence or no safe fail-closed result."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FacewiseCapacityBackoffError(
            f"[stage20-stage4-facewise-capacity-backoff-v1] {message}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_and_verify_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text())
    _require(contract.get("schema") == "onga-stage20-stage4-facewise-capacity-backoff-v1", "contract schema changed")
    _require(contract.get("status") == "LOCAL_PURE_BACKOFF_PLANNER_READY_NOT_SOLVER_CONNECTED", "contract status changed")
    scope = contract["scope"]
    _require(scope["activeGateIds"] == list(ACTIVE_GATE_IDS), "active gate set changed")
    _require(scope["candidateScaleDescending"] == list(CANDIDATE_SCALES), "candidate scales changed")
    _require(scope["reverseFluxToleranceM3S"] == REVERSE_TOLERANCE_M3_S, "reverse tolerance changed")
    _require(scope["evaluationState"] == "tentative post-step state produced with the exact candidate capacity", "evaluation state weakened")
    _require(scope["fluxClippingPermitted"] is False, "flux clipping enabled")
    _require(scope["acceptedStateMustMatchSelectedCandidate"] is True, "state/candidate identity weakened")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        _require(path.is_file(), f"bound file absent: {path}")
        _require(_sha256(path) == binding["sha256"], f"bound file changed: {path}")
    boundary = contract["decisionBoundary"]
    _require(boundary["purePlannerAndSyntheticTestsPermitted"] is True, "pure planner disabled")
    for key, value in boundary.items():
        if key != "purePlannerAndSyntheticTestsPermitted":
            _require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def stage4_capacity_for_scale(scale: float) -> np.ndarray:
    value = float(scale)
    _require(value in CANDIDATE_SCALES, "scale outside fixed grid")
    capacity = np.zeros(8, dtype=np.float64)
    capacity[np.asarray(ACTIVE_GATE_IDS, dtype=np.int64) - 1] = value
    return capacity


def candidate_capacities() -> list[np.ndarray]:
    return [stage4_capacity_for_scale(scale) for scale in CANDIDATE_SCALES]


def _evaluate_candidate(evidence: dict[str, Any]) -> dict[str, Any]:
    scale = float(evidence["scale"])
    capacity = np.asarray(evidence["capacityByGateId1To8"], dtype=np.float64)
    flux = np.asarray(evidence["signedOutwardFluxM3SBySelectedFace"], dtype=np.float64)
    gate_index = np.asarray(evidence["gateIndexBySelectedFace"], dtype=np.int64)
    _require(capacity.shape == (8,), "capacity shape changed")
    _require(flux.ndim == gate_index.ndim == 1 and flux.shape == gate_index.shape, "flux/index shape changed")
    _require(bool(np.isfinite(capacity).all() and np.isfinite(flux).all()), "nonfinite candidate evidence")
    _require(np.array_equal(capacity, stage4_capacity_for_scale(scale)), "capacity does not match scale")
    _require(bool(np.all((gate_index >= 0) & (gate_index < 8))), "gate index outside 0..7")
    active = capacity[gate_index] > 0.0
    adverse = active & (flux < -REVERSE_TOLERANCE_M3_S)
    leakage = ~active & (np.abs(flux) > REVERSE_TOLERANCE_M3_S)
    return {
        "scale": scale,
        "capacityByGateId1To8": capacity.tolist(),
        "activeFaceCount": int(np.count_nonzero(active)),
        "adverseActiveFaceCount": int(np.count_nonzero(adverse)),
        "inactiveLeakageFaceCount": int(np.count_nonzero(leakage)),
        "minimumActiveSignedOutwardFluxM3S": (
            None if not np.any(active) else float(np.min(flux[active]))
        ),
        "maximumInactiveAbsoluteFluxM3S": (
            0.0 if np.all(active) else float(np.max(np.abs(flux[~active])))
        ),
        "safe": bool(not np.any(adverse) and not np.any(leakage)),
    }


def select_largest_safe_candidate(
    candidate_evidence_descending: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Select the first fully facewise-safe exact post-step candidate."""

    read_and_verify_contract()
    evidence = list(candidate_evidence_descending)
    _require(len(evidence) == len(CANDIDATE_SCALES), "candidate evidence count changed")
    _require([float(row["scale"]) for row in evidence] == list(CANDIDATE_SCALES), "candidate order changed")
    evaluated = [_evaluate_candidate(row) for row in evidence]
    safe_rows = [row for row in evaluated if row["safe"]]
    _require(bool(safe_rows), "no safe candidate including all-closed")
    selected = safe_rows[0]
    return {
        "schema": "onga-stage20-stage4-facewise-capacity-backoff-v1-selection",
        "status": "PASS_PURE_LARGEST_FACEWISE_SAFE_CANDIDATE_SELECTED",
        "selectedScale": selected["scale"],
        "selectedCapacityByGateId1To8": selected["capacityByGateId1To8"],
        "evaluatedCandidateCountThroughSelection": evaluated.index(selected) + 1,
        "candidateDiagnostics": evaluated,
        "acceptedStateMustComeFromSelectedCandidateTrial": True,
        "fluxClipped": False,
        "reverseFlowPermitted": False,
        "kernelCallCount": 0,
        "outputCreationCount": 0,
        "yodaConnectionCount": 0,
        "physicalValidation": False,
    }


if __name__ == "__main__":
    print(json.dumps({
        "schema": "onga-stage20-stage4-facewise-capacity-backoff-v1-preflight",
        "status": "PASS_LOCAL_PURE_PLANNER_NOT_SOLVER_CONNECTED",
        "candidateCapacityByScale": [row.tolist() for row in candidate_capacities()],
        "contract": read_and_verify_contract()["status"],
    }, ensure_ascii=False))
