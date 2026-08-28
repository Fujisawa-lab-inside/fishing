#!/usr/bin/env python3
"""SHA-bound per-gate observations for the regularized multizone mesh."""

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
import stage20_barrage_per_gate_predictive_r1c_adapter_v2 as identity
import stage20_depth_weighted_boundary_kernel_candidate_v2 as kernel


CONTRACT = ROOT / "config/stage20_regularized_multizone_gate_observation_v1.json"
OUTPUT = ROOT / "docs/results/stage20-regularized-multizone-gate-observation-v1"
REPORT = OUTPUT / "report.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"[stage20-regularized-multizone-gate-observation-v1] {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_bound_context() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract["schema"] == "onga-stage20-regularized-multizone-gate-observation-v1-contract", "contract schema changed")
    require(contract["status"] == "LOCAL_SHA_BOUND_OBSERVATION_READY_RUNTIME_MOTION_BLOCKED", "contract status broadened")
    mesh_path = ROOT / contract["mesh"]["path"]
    fields_path = ROOT / contract["fields"]["path"]
    state_path = ROOT / contract["comparisonState"]["path"]
    require(sha256(mesh_path) == contract["mesh"]["sha256"], "mesh SHA mismatch")
    require(sha256(fields_path) == contract["fields"]["sha256"], "fields SHA mismatch")
    require(sha256(state_path) == contract["comparisonState"]["sha256"], "state SHA mismatch")
    geometry = kernel.build_review_geometry(kernel.mesh_arrays(mesh_path))
    with np.load(fields_path, allow_pickle=False) as archive:
        depth = np.asarray(archive["continuous_depth_m"], dtype=np.float64).copy()
        bed = np.asarray(archive["continuous_bed_elevation_m"], dtype=np.float64).copy()
        upstream_mask = np.asarray(archive["upstream_component_mask"], dtype=np.uint8).copy()
        gate_faces = np.asarray(archive["gate_face_id"], dtype=np.int64).copy()
        upstream = np.asarray(archive["barrage_upstream_cell_id"], dtype=np.int64).copy()
        donor = np.asarray(archive["p2_donor_overlap_area_m2"], dtype=np.float64).copy()
        receiver = np.asarray(archive["p2_receiver_overlap_area_m2"], dtype=np.float64).copy()
    markers = np.asarray(geometry["internalMarkers"], dtype=np.int32)
    structure = np.flatnonzero(
        (markers == kernel.FIXED_MARKER)
        | ((markers >= kernel.GATE_MARKER_BASE + 1) & (markers <= kernel.GATE_MARKER_BASE + 8))
    ).astype(np.int64)
    gate_ids = (markers[gate_faces] - kernel.GATE_MARKER_BASE).astype(np.int64)
    left = np.asarray(geometry["left"], dtype=np.int64)[gate_faces]
    right = np.asarray(geometry["right"], dtype=np.int64)[gate_faces]
    downstream = np.where(upstream == left, right, left).astype(np.int64)
    arrays = {
        "structureFaceId": structure,
        "structureMarker": markers[structure],
        "mainGateFaceId": gate_faces,
        "mainGateIdBySelectedFace": gate_ids,
        "mainGateUpstreamCellId": upstream,
        "mainGateDownstreamCellId": downstream,
        "mainGateLeftCellId": left,
        "mainGateRightCellId": right,
        "mainGateBaseFaceLengthM": np.asarray(geometry["internalLengths"], dtype=np.float64)[gate_faces],
        "mainGateInternalNormalXY": np.asarray(geometry["internalNormals"], dtype=np.float64)[gate_faces],
        "upstreamComponentMask": upstream_mask,
        "p2DonorOverlapAreaM2": donor,
        "p2ReceiverOverlapAreaM2": receiver,
    }
    actual = {name: identity.array_sha256(values) for name, values in arrays.items()}
    require(actual == contract["arraySha256"], "bound array identity changed")
    semantics = contract["semantics"]
    counts = [int(np.sum(gate_ids == gate)) for gate in range(1, 9)]
    require(counts == semantics["faceCountByGateId1To8"], "per-gate face count changed")
    require(len(structure) == semantics["structureFaceCount"], "structure count changed")
    require(int(np.sum(markers[structure] == kernel.FIXED_MARKER)) == semantics["fixedFaceCount"], "fixed count changed")
    up_bool = upstream_mask.astype(bool)
    require(np.all(up_bool[upstream]) and np.all(~up_bool[downstream]), "upstream orientation changed")
    require(not np.any((donor > 0.0) & (receiver > 0.0)), "P2 donor and receiver overlap")
    return {
        "contract": contract,
        "geometry": geometry,
        "depth": depth,
        "bed": bed,
        "gateFaces": gate_faces,
        "gateIds": gate_ids,
        "upstream": upstream,
        "downstream": downstream,
        "statePath": state_path,
    }


def observe_per_gate(state: np.ndarray, context: dict[str, Any]) -> dict[str, Any]:
    values = np.asarray(state, dtype=np.float64)
    require(values.shape == (28746, 3), "state shape changed")
    require(np.isfinite(values).all() and np.all(values[:, 0] >= 0.0), "invalid state")
    eta = values[:, 0] + context["bed"]
    upstream = context["upstream"]
    downstream = context["downstream"]
    differences = eta[upstream] - eta[downstream]
    lengths = context["geometry"]["internalLengths"][context["gateFaces"]]
    threshold = float(context["contract"]["semantics"]["minimumTrustedSelectedFaceDepthM"])
    rows = []
    available = []
    for gate in range(1, 9):
        selected = context["gateIds"] == gate
        weights = lengths[selected] / float(np.sum(lengths[selected]))
        upstream_depth = values[upstream[selected], 0]
        downstream_depth = values[downstream[selected], 0]
        minimum_depth = float(min(np.min(upstream_depth), np.min(downstream_depth)))
        trusted = minimum_depth > threshold
        available.append(trusted)
        rows.append({
            "gateId": gate,
            "faceCount": int(np.sum(selected)),
            "weightedMeanHeadDifferenceM": float(np.sum(weights * differences[selected])),
            "minimumLocalHeadDifferenceM": float(np.min(differences[selected])),
            "maximumLocalHeadDifferenceM": float(np.max(differences[selected])),
            "minimumSelectedFaceSideDepthM": minimum_depth,
            "trustedForPositiveMotionObservation": trusted,
            "failClosedReason": None if trusted else "DRY_OR_NEAR_DRY_SELECTED_FACE_SIDE",
        })
    return {
        "minimumTrustedSelectedFaceDepthM": threshold,
        "perGate": rows,
        "trustedForPositiveMotionByGateId1To8": available,
        "trustedGateIds": [index + 1 for index, value in enumerate(available) if value],
        "failClosedGateIds": [index + 1 for index, value in enumerate(available) if not value],
        "globalAllGateShutdownRequired": False,
    }


def fail_closed_requested_capacity(requested: np.ndarray, observation: dict[str, Any]) -> np.ndarray:
    values = np.asarray(requested, dtype=np.float64)
    require(values.shape == (8,) and np.isfinite(values).all(), "requested capacity invalid")
    require(np.all((values >= 0.0) & (values <= 1.0)), "requested capacity outside 0..1")
    trusted = np.asarray(observation["trustedForPositiveMotionByGateId1To8"], dtype=bool)
    result = values.copy()
    result[~trusted] = 0.0
    return result


def build_report() -> dict[str, Any]:
    context = load_bound_context()
    initial = np.column_stack((context["depth"], np.zeros((28746, 2), dtype=np.float64)))
    final = np.load(context["statePath"], allow_pickle=False)
    initial_observation = observe_per_gate(initial, context)
    final_observation = observe_per_gate(final, context)
    stage4 = np.asarray([0, 0, 1, 1, 1, 1, 0, 0], dtype=np.float64)
    effective = fail_closed_requested_capacity(stage4, final_observation)
    stage4_ready = bool(np.array_equal(effective, stage4))
    return {
        "schema": "onga-stage20-regularized-multizone-gate-observation-v1",
        "version": 1,
        "status": "PASS_SHA_BOUND_OBSERVATION_STAGE4_WET_GATE8_NEAR_DRY_RUNTIME_MOTION_BLOCKED",
        "classification": context["contract"]["classification"],
        "contractSha256": sha256(CONTRACT),
        "initialObservation": initial_observation,
        "allClosed900sObservation": final_observation,
        "stage4DiagnosticRequest": {
            "requestedCapacityByGateId1To8": stage4.tolist(),
            "nearDryFilteredCapacityByGateId1To8": effective.tolist(),
            "allRequestedGatesHaveTrustedHeadObservation": stage4_ready,
        },
        "decision": {
            "observationBindingPass": True,
            "stage4RequestedGateObservationReady": stage4_ready,
            "allEightGateObservationReady": len(final_observation["failClosedGateIds"]) == 0,
            "runtimeMotionAuthorized": False,
            "forecastEvidenceAvailable": False,
            "meshOperationallyAdopted": False,
            "next": "freeze an external runtime orientation activation and bounded stage4 outward/adverse-head canaries; keep gate 8 fail closed while near-dry",
        },
    }


def main() -> None:
    report = build_report()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
