#!/usr/bin/env python3
"""SHA-bound R1C observations for the per-gate barrage controller v2.

This adapter is intentionally not connected to a solver runner.  It verifies a
frozen main-gate face inventory against the full classified barrage structure,
then exposes per-gate live heads and signed outward flux diagnostics.  Fishway,
fine-adjustment, pier, outer-structure, and unresolved faces are never folded
into the eight main gates.

The safety head for each gate is the minimum local face difference.  Length-
weighted means are retained for diagnosis but cannot hide one adverse face.
The SHA contract binds the full role inventory plus selected face ids, gate
ids, upstream orientation, incident cells, and base face lengths.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

import numpy as np

import stage20_barrage_fractional_motion_r1c_adapter_v1 as legacy
import stage20_barrage_interface_v2 as interface
import stage20_barrage_per_gate_predictive_control_v2 as control


ADAPTER_VERSION = "stage20-barrage-per-gate-predictive-r1c-adapter-v2"
BINDING_SCHEMA = "onga-stage20-r1c-main-gate-face-orientation-binding-v2"
OBSERVATION_SCHEMA = "onga-stage20-r1c-per-gate-head-observation-v2"
CONTROLLER_BRIDGE_SCHEMA = "onga-stage20-r1c-per-gate-controller-input-v2"
CONTROLLER_STEP_SCHEMA = "onga-stage20-r1c-per-gate-controller-step-v2"
FORECAST_EVIDENCE_SCHEMA = "onga-stage20-r1c-per-gate-forecast-evidence-v2"
FLUX_SCHEMA = "onga-stage20-r1c-per-gate-signed-outward-flux-v2"
OFFLINE_INTEGRATION_STATUS = (
    "OFFLINE_READ_ONLY_OBSERVATION_ADAPTER_NOT_CONNECTED_TO_SOLVER"
)
FISHWAY_INTEGRATION_STATUS = (
    "FISHWAY_EXCLUDED_FROM_MAIN_GATE_CONTROL_AND_NOT_HYDRAULICALLY_CONNECTED"
)
BINDING_CLASSIFICATION = (
    "SELF_HASHED_BINDING_CANDIDATE_NOT_EXTERNAL_RUNTIME_AUTHORITY"
)
EXTERNAL_RUNTIME_AUTHORITY_STATUS = (
    "BLOCKED_NO_IMMUTABLE_PREFLIGHT_ACTIVATION_ROOT"
)
MAIN_GATE_IDS = tuple(range(1, 9))
MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M = 1.0e-4
MAXIMUM_REVERSE_FLUX_TOLERANCE_M3_S = 1.0e-10
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HASHED_ARRAY_LABELS = (
    "structureFaceId",
    "structureFaceRole",
    "structureMainGateId",
    "mainGateFaceId",
    "mainGateIdBySelectedFace",
    "mainGateUpstreamCellId",
    "mainGateLeftCellId",
    "mainGateRightCellId",
    "mainGateBaseFaceLengthM",
    "mainGateInternalNormalXY",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[{ADAPTER_VERSION}] {message}")


def _finite(value: object, label: str) -> float:
    require(not isinstance(value, (bool, np.bool_)), f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"[{ADAPTER_VERSION}] {label} must be numeric") from error
    require(math.isfinite(number), f"{label} must be finite")
    return number


def _integer_vector(value: object, label: str) -> np.ndarray:
    array = np.asarray(value)
    require(array.ndim == 1, f"{label} must be a vector")
    require(array.dtype != np.bool_, f"{label} must contain integer ids")
    require(np.issubdtype(array.dtype, np.integer), f"{label} must contain integer ids")
    return array.astype(np.int64, copy=True)


def _float_vector(value: object, label: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"[{ADAPTER_VERSION}] {label} must be numeric") from error
    require(array.ndim == 1, f"{label} must be a vector")
    require(bool(np.isfinite(array).all()), f"{label} contains non-finite values")
    return array.copy()


def _capacity_vector(value: object) -> np.ndarray:
    result = _float_vector(value, "main-gate opening")
    require(result.shape == (8,), "main-gate opening must contain eight gates")
    require(bool(np.all((result >= 0.0) & (result <= 1.0))), "opening left 0..1")
    return result


def _finite_gate_vector(value: object, label: str) -> np.ndarray:
    if np.isscalar(value) and not isinstance(value, (str, bytes)):
        return np.full(8, _finite(value, label), dtype=np.float64)
    result = _float_vector(value, label)
    require(result.shape == (8,), f"{label} must contain eight gates")
    return result


def _explicit_finite_gate_vector(value: object, label: str) -> np.ndarray:
    require(
        not np.isscalar(value) and not isinstance(value, (str, bytes)),
        f"{label} must be an explicit eight-gate vector",
    )
    result = _float_vector(value, label)
    require(result.shape == (8,), f"{label} must contain eight gates")
    return result


def _require_sha256(value: object, label: str) -> str:
    require(
        isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None,
        f"{label} must be a lowercase SHA-256",
    )
    require(value != "0" * 64, f"{label} cannot be the all-zero placeholder SHA")
    return value


def _json_sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def array_sha256(value: np.ndarray) -> str:
    """Use the existing Stage 20 dtype/shape/bytes array identity."""

    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(b"\0")
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def gate_ids_from_zero_based_indices(gate_index_by_selected_face: object) -> np.ndarray:
    """Convert the existing C1 workspace 0..7 indices into exact gate ids 1..8."""

    index = _integer_vector(gate_index_by_selected_face, "selected gate index")
    require(bool(np.all((index >= 0) & (index < 8))), "selected gate index left 0..7")
    return index + 1


def _geometry_arrays(geometry: Mapping[str, object]) -> dict[str, np.ndarray]:
    require(isinstance(geometry, Mapping), "R1C geometry is required")
    required = ("left", "right", "internalLengths", "internalNormals")
    require(all(key in geometry for key in required), "R1C geometry keys are incomplete")
    left = _integer_vector(geometry["left"], "geometry left cell")
    right = _integer_vector(geometry["right"], "geometry right cell")
    lengths = _float_vector(geometry["internalLengths"], "geometry internal length")
    try:
        normals = np.asarray(geometry["internalNormals"], dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"[{ADAPTER_VERSION}] geometry internal normals must be numeric"
        ) from error
    require(
        len(left) == len(right) == len(lengths) and len(left) > 0,
        "geometry face arrays must be nonempty and equal length",
    )
    require(bool(np.all(left >= 0) and np.all(right >= 0)), "geometry cell id is negative")
    require(bool(np.all(left != right)), "geometry face has identical left/right cell")
    require(bool(np.all(lengths > 0.0)), "geometry internal lengths must be positive")
    require(
        normals.shape == (len(left), 2) and bool(np.isfinite(normals).all()),
        "geometry internal normals must be finite face-by-XY vectors",
    )
    normal_magnitude = np.linalg.norm(normals, axis=1)
    require(
        bool(np.all(np.abs(normal_magnitude - 1.0) <= 1.0e-9)),
        "geometry internal normals must be unit vectors",
    )
    return {
        "left": left,
        "right": right,
        "lengths": lengths,
        "normals": normals.copy(),
    }


def _derive_main_gate_identity(
    *,
    geometry: Mapping[str, object],
    structure_face_ids: object,
    structure_face_roles: object,
    structure_main_gate_ids: object,
    main_gate_face_ids: object,
    main_gate_id_by_selected_face: object,
    main_gate_upstream_cell_id: object,
) -> dict[str, Any]:
    geo = _geometry_arrays(geometry)
    structure_faces = _integer_vector(structure_face_ids, "structure face id")
    roles = _integer_vector(structure_face_roles, "structure face role")
    structure_gates = _integer_vector(
        structure_main_gate_ids, "structure main-gate id"
    )
    require(
        len(structure_faces) == len(roles) == len(structure_gates)
        and len(structure_faces) > 0,
        "classified structure arrays must be nonempty and equal length",
    )
    require(
        bool(np.all((structure_faces >= 0) & (structure_faces < len(geo["left"])))),
        "structure face id is outside the R1C geometry",
    )
    require(
        len(np.unique(structure_faces)) == len(structure_faces),
        "duplicate structure face id",
    )
    require(
        set(int(value) for value in np.unique(roles)).issubset(interface.ROLE_NAMES),
        "unknown structure face role",
    )
    main_mask = roles == interface.ROLE_MAIN_GATE
    require(bool(np.any(main_mask)), "main-gate structure faces are missing")
    require(
        bool(np.all(structure_gates[~main_mask] == 0)),
        "non-main structure face carries a main-gate id",
    )
    require(
        bool(np.all((structure_gates[main_mask] >= 1) & (structure_gates[main_mask] <= 8))),
        "main-gate structure face id left 1..8",
    )
    require(
        set(int(value) for value in np.unique(structure_gates[main_mask]))
        == set(MAIN_GATE_IDS),
        "main-gate structure inventory must cover exactly gates 1..8",
    )

    selected_faces = _integer_vector(main_gate_face_ids, "selected main-gate face id")
    selected_gates = _integer_vector(
        main_gate_id_by_selected_face, "gate id by selected face"
    )
    upstream = _integer_vector(
        main_gate_upstream_cell_id, "main-gate upstream cell id"
    )
    require(
        len(selected_faces) == len(selected_gates) == len(upstream)
        and len(selected_faces) > 0,
        "selected main-gate arrays must be nonempty and equal length",
    )
    require(
        len(np.unique(selected_faces)) == len(selected_faces),
        "duplicate selected main-gate face id",
    )
    authoritative_main_faces = structure_faces[main_mask]
    require(
        set(int(value) for value in selected_faces)
        == set(int(value) for value in authoritative_main_faces),
        "selected faces must equal the classified main-gate face set",
    )
    structure_position = {
        int(face): index for index, face in enumerate(structure_faces)
    }
    selected_structure_positions = np.asarray(
        [structure_position[int(face)] for face in selected_faces], dtype=np.int64
    )
    require(
        bool(np.all(roles[selected_structure_positions] == interface.ROLE_MAIN_GATE)),
        "selected face includes a non-main role such as fishway or fixed structure",
    )
    authoritative_gate_ids = structure_gates[selected_structure_positions]
    require(
        bool(np.array_equal(selected_gates, authoritative_gate_ids)),
        "selected face-to-gate assignment disagrees with classified structure",
    )
    require(
        set(int(value) for value in np.unique(selected_gates)) == set(MAIN_GATE_IDS),
        "selected main-gate faces must cover gates 1..8",
    )

    left = geo["left"][selected_faces]
    right = geo["right"][selected_faces]
    upstream_is_left = upstream == left
    upstream_is_right = upstream == right
    require(
        bool(np.all(upstream_is_left ^ upstream_is_right)),
        "each selected face must have exactly one incident SHA-bound upstream cell",
    )
    downstream = np.where(upstream_is_left, right, left).astype(np.int64)
    require(bool(np.all(upstream != downstream)), "upstream/downstream orientation overlaps")
    lengths = geo["lengths"][selected_faces]
    normals = geo["normals"][selected_faces]
    counts = np.asarray(
        [int(np.sum(selected_gates == gate_id)) for gate_id in MAIN_GATE_IDS],
        dtype=np.int64,
    )
    require(bool(np.all(counts > 0)), "one or more main gates have no selected faces")
    arrays = {
        "structureFaceId": structure_faces,
        "structureFaceRole": roles,
        "structureMainGateId": structure_gates,
        "mainGateFaceId": selected_faces,
        "mainGateIdBySelectedFace": selected_gates,
        "mainGateUpstreamCellId": upstream,
        "mainGateLeftCellId": left,
        "mainGateRightCellId": right,
        "mainGateBaseFaceLengthM": lengths,
        "mainGateInternalNormalXY": normals,
    }
    return {
        "arrays": arrays,
        "downstream": downstream,
        "faceCountByGateId1To8": counts,
        "excludedNonMainStructureFaceCount": int(np.sum(~main_mask)),
        "excludedFishwayFaceCount": int(
            np.sum(roles == interface.ROLE_FISHWAY_GATE)
        ),
        "excludedFineAdjustmentFaceCount": int(
            np.sum(roles == interface.ROLE_FINE_ADJUSTMENT_GATE)
        ),
    }


def _array_hash_inventory(identity: Mapping[str, object]) -> dict[str, str]:
    arrays = identity["arrays"]
    require(isinstance(arrays, Mapping), "identity array inventory is missing")
    return {
        label: array_sha256(np.asarray(arrays[label]))
        for label in HASHED_ARRAY_LABELS
    }


def _binding_identity_sha256(
    array_hashes: Mapping[str, str],
    expected_count: int,
    expected_count_by_gate: Sequence[int],
) -> str:
    payload = {
        "schema": BINDING_SCHEMA,
        "classification": BINDING_CLASSIFICATION,
        "arraySha256": dict(array_hashes),
        "expectedMainGateFaceCount": int(expected_count),
        "expectedFaceCountByGateId1To8": [
            int(value) for value in expected_count_by_gate
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_sha_bound_main_gate_face_contract(
    *,
    geometry: Mapping[str, object],
    structure_face_ids: object,
    structure_face_roles: object,
    structure_main_gate_ids: object,
    main_gate_face_ids: object,
    main_gate_id_by_selected_face: object,
    main_gate_upstream_cell_id: object,
) -> dict[str, object]:
    """Prepare a self-hashed candidate, never a runtime authority.

    Building and verifying a contract from the same live arrays is not an
    authority check.  This helper exists for package preparation and fixtures.
    """

    identity = _derive_main_gate_identity(
        geometry=geometry,
        structure_face_ids=structure_face_ids,
        structure_face_roles=structure_face_roles,
        structure_main_gate_ids=structure_main_gate_ids,
        main_gate_face_ids=main_gate_face_ids,
        main_gate_id_by_selected_face=main_gate_id_by_selected_face,
        main_gate_upstream_cell_id=main_gate_upstream_cell_id,
    )
    hashes = _array_hash_inventory(identity)
    count = len(identity["arrays"]["mainGateFaceId"])
    counts = np.asarray(identity["faceCountByGateId1To8"], dtype=np.int64)
    return {
        "schema": BINDING_SCHEMA,
        "classification": BINDING_CLASSIFICATION,
        "expectedMainGateFaceCount": int(count),
        "expectedFaceCountByGateId1To8": counts.tolist(),
        "arraySha256": hashes,
        "bindingIdentitySha256": _binding_identity_sha256(hashes, count, counts),
    }


def _validate_binding_contract(contract: Mapping[str, object]) -> dict[str, object]:
    require(isinstance(contract, Mapping), "SHA-bound face contract is required")
    required = {
        "schema",
        "classification",
        "expectedMainGateFaceCount",
        "expectedFaceCountByGateId1To8",
        "arraySha256",
        "bindingIdentitySha256",
    }
    require(set(contract) == required, "SHA-bound face contract keys are invalid")
    require(contract["schema"] == BINDING_SCHEMA, "face contract schema mismatch")
    require(
        contract["classification"] == BINDING_CLASSIFICATION,
        "face contract classification mismatch",
    )
    expected_count = contract["expectedMainGateFaceCount"]
    require(
        type(expected_count) is int and expected_count > 0,
        "expected main-gate face count must be a positive integer",
    )
    counts = _integer_vector(
        contract["expectedFaceCountByGateId1To8"], "expected face count by gate"
    )
    require(counts.shape == (8,), "expected face count must contain eight gates")
    require(bool(np.all(counts > 0)), "expected face count contains a missing gate")
    require(int(np.sum(counts)) == expected_count, "expected face counts do not sum")
    hashes = contract["arraySha256"]
    require(isinstance(hashes, Mapping), "array SHA inventory is required")
    require(set(hashes) == set(HASHED_ARRAY_LABELS), "array SHA inventory keys changed")
    normalized_hashes: dict[str, str] = {}
    for label in HASHED_ARRAY_LABELS:
        value = hashes[label]
        require(
            isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None,
            f"{label} SHA-256 is invalid",
        )
        normalized_hashes[label] = value
    binding_sha = contract["bindingIdentitySha256"]
    require(
        isinstance(binding_sha, str)
        and SHA256_PATTERN.fullmatch(binding_sha) is not None,
        "binding identity SHA-256 is invalid",
    )
    expected_binding_sha = _binding_identity_sha256(
        normalized_hashes, expected_count, counts
    )
    require(binding_sha == expected_binding_sha, "binding identity SHA-256 mismatch")
    return {
        "expectedMainGateFaceCount": expected_count,
        "expectedFaceCountByGateId1To8": counts,
        "arraySha256": normalized_hashes,
        "bindingIdentitySha256": binding_sha,
    }


def inspect_candidate_main_gate_faces(
    *,
    geometry: Mapping[str, object],
    structure_face_ids: object,
    structure_face_roles: object,
    structure_main_gate_ids: object,
    main_gate_face_ids: object,
    main_gate_id_by_selected_face: object,
    main_gate_upstream_cell_id: object,
    binding_contract: Mapping[str, object],
) -> dict[str, object]:
    """Check candidate consistency without granting runtime authority."""

    expected = _validate_binding_contract(binding_contract)
    identity = _derive_main_gate_identity(
        geometry=geometry,
        structure_face_ids=structure_face_ids,
        structure_face_roles=structure_face_roles,
        structure_main_gate_ids=structure_main_gate_ids,
        main_gate_face_ids=main_gate_face_ids,
        main_gate_id_by_selected_face=main_gate_id_by_selected_face,
        main_gate_upstream_cell_id=main_gate_upstream_cell_id,
    )
    hashes = _array_hash_inventory(identity)
    require(hashes == expected["arraySha256"], "current main-gate arrays do not match bound SHAs")
    faces = np.asarray(identity["arrays"]["mainGateFaceId"], dtype=np.int64)
    counts = np.asarray(identity["faceCountByGateId1To8"], dtype=np.int64)
    require(
        len(faces) == expected["expectedMainGateFaceCount"],
        "current main-gate face count changed",
    )
    require(
        bool(np.array_equal(counts, expected["expectedFaceCountByGateId1To8"])),
        "current per-gate face counts changed",
    )
    arrays = identity["arrays"]
    return {
        "version": ADAPTER_VERSION,
        "schema": BINDING_SCHEMA,
        "classification": BINDING_CLASSIFICATION,
        "bindingIdentitySha256": expected["bindingIdentitySha256"],
        "arraySha256": hashes,
        "mainGateFaceId": np.asarray(arrays["mainGateFaceId"], dtype=np.int64),
        "mainGateIdBySelectedFace": np.asarray(
            arrays["mainGateIdBySelectedFace"], dtype=np.int64
        ),
        "mainGateUpstreamCellId": np.asarray(
            arrays["mainGateUpstreamCellId"], dtype=np.int64
        ),
        "mainGateDownstreamCellId": np.asarray(identity["downstream"], dtype=np.int64),
        "mainGateLeftCellId": np.asarray(arrays["mainGateLeftCellId"], dtype=np.int64),
        "mainGateRightCellId": np.asarray(arrays["mainGateRightCellId"], dtype=np.int64),
        "mainGateBaseFaceLengthM": np.asarray(
            arrays["mainGateBaseFaceLengthM"], dtype=np.float64
        ),
        "mainGateInternalNormalXY": np.asarray(
            arrays["mainGateInternalNormalXY"], dtype=np.float64
        ),
        "faceCountByGateId1To8": counts,
        "excludedNonMainStructureFaceCount": identity[
            "excludedNonMainStructureFaceCount"
        ],
        "excludedFishwayFaceCount": identity["excludedFishwayFaceCount"],
        "excludedFineAdjustmentFaceCount": identity[
            "excludedFineAdjustmentFaceCount"
        ],
        "mainGateOnly": True,
        "fishwayExcluded": True,
        "fishwayHydraulicConnectionPerformed": False,
        "fishwayIntegrationStatus": FISHWAY_INTEGRATION_STATUS,
        "solverConnectionPerformed": False,
        "solverIntegrationStatus": OFFLINE_INTEGRATION_STATUS,
        "candidateUpstreamOrientationInternallyConsistent": True,
        "bindingAuthorityVerified": False,
        "externalRuntimeAuthorityStatus": EXTERNAL_RUNTIME_AUTHORITY_STATUS,
    }


def verify_sha_bound_main_gate_faces(
    **_: object,
) -> dict[str, object]:
    """Reject runtime verification until an immutable activation root exists.

    A contract built from the same live arrays can authorize either upstream
    orientation and is therefore not an authority.  A future successor adapter
    must receive an independently issued, immutable preflight activation
    capability; this v2 module deliberately cannot mint or accept one.
    """

    raise ValueError(
        f"[{ADAPTER_VERSION}] binding authority unavailable: "
        f"{EXTERNAL_RUNTIME_AUTHORITY_STATUS}; self-issued live-array contracts "
        "cannot authorize runtime orientation"
    )


def _validated_binding(binding: Mapping[str, object]) -> dict[str, np.ndarray | str]:
    require(isinstance(binding, Mapping), "verified face binding is required")
    require(binding.get("version") == ADAPTER_VERSION, "verified binding version mismatch")
    require(binding.get("schema") == BINDING_SCHEMA, "verified binding schema mismatch")
    require(
        binding.get("classification") == BINDING_CLASSIFICATION,
        "verified binding classification mismatch",
    )
    require(binding.get("mainGateOnly") is True, "verified binding is not main-gate-only")
    require(binding.get("fishwayExcluded") is True, "verified binding did not exclude fishway")
    require(
        binding.get("fishwayHydraulicConnectionPerformed") is False
        and binding.get("fishwayIntegrationStatus") == FISHWAY_INTEGRATION_STATUS,
        "verified binding does not retain fishway-unconnected status",
    )
    require(
        binding.get("solverConnectionPerformed") is False
        and binding.get("solverIntegrationStatus") == OFFLINE_INTEGRATION_STATUS,
        "verified binding does not retain offline solver status",
    )
    require(
        binding.get("candidateUpstreamOrientationInternallyConsistent") is True
        and binding.get("bindingAuthorityVerified") is False
        and binding.get("externalRuntimeAuthorityStatus")
        == EXTERNAL_RUNTIME_AUTHORITY_STATUS,
        "binding candidate makes an unsupported runtime authority claim",
    )
    binding_sha = binding.get("bindingIdentitySha256")
    require(
        isinstance(binding_sha, str) and SHA256_PATTERN.fullmatch(binding_sha) is not None,
        "verified binding identity SHA is invalid",
    )
    face = _integer_vector(binding.get("mainGateFaceId"), "verified main-gate face")
    gate = _integer_vector(
        binding.get("mainGateIdBySelectedFace"), "verified gate id by face"
    )
    upstream = _integer_vector(
        binding.get("mainGateUpstreamCellId"), "verified upstream cell"
    )
    downstream = _integer_vector(
        binding.get("mainGateDownstreamCellId"), "verified downstream cell"
    )
    left = _integer_vector(binding.get("mainGateLeftCellId"), "verified left cell")
    right = _integer_vector(binding.get("mainGateRightCellId"), "verified right cell")
    lengths = _float_vector(
        binding.get("mainGateBaseFaceLengthM"), "verified base face length"
    )
    try:
        normals = np.asarray(
            binding.get("mainGateInternalNormalXY"), dtype=np.float64
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"[{ADAPTER_VERSION}] verified internal normal must be numeric"
        ) from error
    require(
        len(face)
        == len(gate)
        == len(upstream)
        == len(downstream)
        == len(left)
        == len(right)
        == len(lengths)
        and len(face) > 0,
        "verified binding arrays are not aligned",
    )
    require(
        normals.shape == (len(face), 2) and bool(np.isfinite(normals).all()),
        "verified internal normals are not aligned",
    )
    require(
        bool(np.all(np.abs(np.linalg.norm(normals, axis=1) - 1.0) <= 1.0e-9)),
        "verified internal normals are not unit vectors",
    )
    require(bool(np.all((gate >= 1) & (gate <= 8))), "verified gate ids left 1..8")
    require(set(int(value) for value in np.unique(gate)) == set(MAIN_GATE_IDS), "verified gate coverage changed")
    require(bool(np.all(((upstream == left) & (downstream == right)) | ((upstream == right) & (downstream == left)))), "verified orientation is inconsistent")
    require(bool(np.all(lengths > 0.0)), "verified base face length is invalid")
    hashes = binding.get("arraySha256")
    require(isinstance(hashes, Mapping), "verified binding SHA inventory is missing")
    require(set(hashes) == set(HASHED_ARRAY_LABELS), "verified SHA inventory keys changed")
    require(
        all(
            isinstance(hashes[label], str)
            and SHA256_PATTERN.fullmatch(hashes[label]) is not None
            for label in HASHED_ARRAY_LABELS
        ),
        "verified SHA inventory contains an invalid digest",
    )
    counts = _integer_vector(
        binding.get("faceCountByGateId1To8"), "verified face count by gate"
    )
    require(counts.shape == (8,), "verified face count must contain eight gates")
    actual_counts = np.asarray(
        [int(np.sum(gate == gate_id)) for gate_id in MAIN_GATE_IDS], dtype=np.int64
    )
    require(
        bool(np.array_equal(counts, actual_counts)) and int(np.sum(counts)) == len(face),
        "verified per-gate face counts changed",
    )
    selected_actual = {
        "mainGateFaceId": face,
        "mainGateIdBySelectedFace": gate,
        "mainGateUpstreamCellId": upstream,
        "mainGateLeftCellId": left,
        "mainGateRightCellId": right,
        "mainGateBaseFaceLengthM": lengths,
        "mainGateInternalNormalXY": normals,
    }
    for label, array in selected_actual.items():
        require(hashes.get(label) == array_sha256(array), f"verified {label} was mutated")
    require(
        binding_sha == _binding_identity_sha256(hashes, len(face), counts),
        "verified binding identity no longer matches its SHA inventory",
    )
    return {
        "bindingIdentitySha256": binding_sha,
        "face": face,
        "gate": gate,
        "upstream": upstream,
        "downstream": downstream,
        "left": left,
        "right": right,
        "lengths": lengths,
        "normals": normals.copy(),
    }


def per_gate_head_diagnostics(
    state: object,
    bed_elevation_m: object,
    verified_binding: Mapping[str, object],
) -> dict[str, object]:
    """Return weighted and worst-face heads independently for gates 1..8."""

    binding = _validated_binding(verified_binding)
    values = np.asarray(state, dtype=np.float64)
    bed = _float_vector(bed_elevation_m, "bed elevation")
    require(values.ndim == 2 and values.shape[1] == 3, "state shape must be cells by H/HU/HV")
    require(len(bed) == len(values), "bed length does not match state cells")
    require(bool(np.isfinite(values).all()), "state contains non-finite values")
    require(bool(np.all(values[:, 0] >= 0.0)), "state contains negative water depth")
    upstream = np.asarray(binding["upstream"], dtype=np.int64)
    downstream = np.asarray(binding["downstream"], dtype=np.int64)
    require(
        bool(np.all((upstream >= 0) & (upstream < len(values))))
        and bool(np.all((downstream >= 0) & (downstream < len(values)))),
        "bound face cell id is outside the state",
    )
    eta = values[:, 0] + bed
    upstream_depth = values[upstream, 0]
    downstream_depth = values[downstream, 0]
    unsafe_side = (
        (upstream_depth <= MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M)
        | (downstream_depth <= MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M)
    )
    if bool(np.any(unsafe_side)):
        selected_index = int(np.flatnonzero(unsafe_side)[0])
        raise ValueError(
            f"[{ADAPTER_VERSION}] selected main-gate face is dry or near-dry: "
            f"gate={int(binding['gate'][selected_index])} "
            f"face={int(binding['face'][selected_index])} "
            f"upstreamDepthM={float(upstream_depth[selected_index])} "
            f"downstreamDepthM={float(downstream_depth[selected_index])}; "
            "positive motion evidence rejected"
        )
    upstream_head = eta[upstream]
    downstream_head = eta[downstream]
    local_difference = upstream_head - downstream_head
    gate_by_face = np.asarray(binding["gate"], dtype=np.int64)
    face = np.asarray(binding["face"], dtype=np.int64)
    lengths = np.asarray(binding["lengths"], dtype=np.float64)
    rows: list[dict[str, object]] = []
    face_rows: list[dict[str, object]] = []
    weighted_differences: list[float] = []
    minimum_differences: list[float] = []
    weighted_upstream: list[float] = []
    weighted_downstream: list[float] = []
    minimum_upstream_depth: list[float] = []
    minimum_downstream_depth: list[float] = []
    for gate_id in MAIN_GATE_IDS:
        selected = np.flatnonzero(gate_by_face == gate_id)
        require(len(selected) > 0, f"gate {gate_id} has no verified faces")
        gate_lengths = lengths[selected]
        weight = gate_lengths / float(np.sum(gate_lengths))
        gate_upstream = upstream_head[selected]
        gate_downstream = downstream_head[selected]
        gate_difference = local_difference[selected]
        gate_upstream_depth = upstream_depth[selected]
        gate_downstream_depth = downstream_depth[selected]
        weighted_u = float(np.sum(weight * gate_upstream))
        weighted_d = float(np.sum(weight * gate_downstream))
        weighted_delta = float(np.sum(weight * gate_difference))
        worst_local_index = int(np.argmin(gate_difference))
        worst_selected_index = int(selected[worst_local_index])
        minimum = float(gate_difference[worst_local_index])
        weighted_upstream.append(weighted_u)
        weighted_downstream.append(weighted_d)
        weighted_differences.append(weighted_delta)
        minimum_differences.append(minimum)
        minimum_upstream_depth.append(float(np.min(gate_upstream_depth)))
        minimum_downstream_depth.append(float(np.min(gate_downstream_depth)))
        rows.append(
            {
                "gateId": gate_id,
                "faceCount": int(len(selected)),
                "faceIds": face[selected].tolist(),
                "totalBaseFaceLengthM": float(np.sum(gate_lengths)),
                "minimumBaseFaceLengthM": float(np.min(gate_lengths)),
                "maximumBaseFaceLengthM": float(np.max(gate_lengths)),
                "lengthWeightedUpstreamHeadM": weighted_u,
                "lengthWeightedDownstreamHeadM": weighted_d,
                "lengthWeightedMeanHeadDifferenceM": weighted_delta,
                "minimumLocalHeadDifferenceM": minimum,
                "p05LocalHeadDifferenceM": float(
                    np.percentile(gate_difference, 5.0)
                ),
                "maximumLocalHeadDifferenceM": float(np.max(gate_difference)),
                "minimumUpstreamDepthM": float(np.min(gate_upstream_depth)),
                "minimumDownstreamDepthM": float(np.min(gate_downstream_depth)),
                "minimumTrustedSelectedFaceDepthM": (
                    MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M
                ),
                "bothSidesWetAboveTrustedFloor": True,
                "worstFaceId": int(face[worst_selected_index]),
                "worstFaceUpstreamCellId": int(upstream[worst_selected_index]),
                "worstFaceDownstreamCellId": int(downstream[worst_selected_index]),
                "worstFaceBaseLengthM": float(lengths[worst_selected_index]),
                "weightedMeanCannotOverrideWorstFace": True,
            }
        )
        for selected_index in selected:
            face_rows.append(
                {
                    "gateId": gate_id,
                    "faceId": int(face[selected_index]),
                    "baseFaceLengthM": float(lengths[selected_index]),
                    "upstreamCellId": int(upstream[selected_index]),
                    "downstreamCellId": int(downstream[selected_index]),
                    "upstreamHeadM": float(upstream_head[selected_index]),
                    "downstreamHeadM": float(downstream_head[selected_index]),
                    "upstreamDepthM": float(upstream_depth[selected_index]),
                    "downstreamDepthM": float(downstream_depth[selected_index]),
                    "bothSidesWetAboveTrustedFloor": True,
                    "localHeadDifferenceM": float(local_difference[selected_index]),
                    "includedInGateWeightedMean": True,
                    "includedInGateWorstFaceMinimum": True,
                }
            )
    return {
        "schema": OBSERVATION_SCHEMA,
        "version": ADAPTER_VERSION,
        "bindingIdentitySha256": binding["bindingIdentitySha256"],
        "gateDiagnosticsById1To8": rows,
        "faceDiagnostics": face_rows,
        "lengthWeightedUpstreamHeadMByGateId1To8": weighted_upstream,
        "lengthWeightedDownstreamHeadMByGateId1To8": weighted_downstream,
        "lengthWeightedMeanHeadDifferenceMByGateId1To8": weighted_differences,
        "minimumLocalHeadDifferenceMByGateId1To8": minimum_differences,
        "minimumUpstreamDepthMByGateId1To8": minimum_upstream_depth,
        "minimumDownstreamDepthMByGateId1To8": minimum_downstream_depth,
        "minimumTrustedSelectedFaceDepthM": MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M,
        "allSelectedFaceSidesWetAboveTrustedFloor": True,
        "controllerSafetyHeadUsesMinimumLocalFace": True,
        "fullBarrageAverageCannotHidePerGateRisk": True,
        "mainGateOnly": True,
        "fishwayExcluded": True,
        "fishwayHydraulicConnectionPerformed": False,
        "fishwayIntegrationStatus": FISHWAY_INTEGRATION_STATUS,
        "solverConnectionPerformed": False,
        "solverIntegrationStatus": OFFLINE_INTEGRATION_STATUS,
    }


def controller_live_head_input(
    head_diagnostics: Mapping[str, object],
    *,
    state_sample_model_time_s: object,
    controller_model_time_s: object,
    state_array_sha256: object,
    bed_array_sha256: object,
    observation_source_authority_sha256: object,
    run_identity_sha256: object,
) -> dict[str, object]:
    """Return controller kwargs with age derived from one R1C state sample.

    The eight gate heads are spatially independent, but they come from the
    same solver state and therefore cannot truthfully carry caller-invented
    per-gate ages.  The adapter derives their common age from model times.
    """

    require(isinstance(head_diagnostics, Mapping), "per-gate head diagnostics are required")
    require(head_diagnostics.get("schema") == OBSERVATION_SCHEMA, "head observation schema mismatch")
    require(
        head_diagnostics.get("controllerSafetyHeadUsesMinimumLocalFace") is True,
        "head observation did not preserve the worst local face",
    )
    require(
        head_diagnostics.get("allSelectedFaceSidesWetAboveTrustedFloor") is True
        and head_diagnostics.get("minimumTrustedSelectedFaceDepthM")
        == MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M,
        "head observation lacks the fixed selected-face wet-depth proof",
    )
    require(head_diagnostics.get("mainGateOnly") is True, "head observation is not main-gate-only")
    require(head_diagnostics.get("fishwayExcluded") is True, "head observation includes fishway")
    require(
        head_diagnostics.get("fishwayHydraulicConnectionPerformed") is False
        and head_diagnostics.get("fishwayIntegrationStatus")
        == FISHWAY_INTEGRATION_STATUS,
        "head observation does not retain fishway-unconnected status",
    )
    require(
        head_diagnostics.get("solverConnectionPerformed") is False
        and head_diagnostics.get("solverIntegrationStatus")
        == OFFLINE_INTEGRATION_STATUS,
        "head observation does not retain offline solver status",
    )
    binding_sha = head_diagnostics.get("bindingIdentitySha256")
    require(
        isinstance(binding_sha, str) and SHA256_PATTERN.fullmatch(binding_sha) is not None,
        "head observation binding SHA is invalid",
    )
    state_sha = _require_sha256(state_array_sha256, "live state array SHA")
    bed_sha = _require_sha256(bed_array_sha256, "live bed array SHA")
    source_sha = _require_sha256(
        observation_source_authority_sha256,
        "live observation source authority SHA",
    )
    run_sha = _require_sha256(run_identity_sha256, "live observation run SHA")
    mean = _finite_gate_vector(
        head_diagnostics.get("lengthWeightedMeanHeadDifferenceMByGateId1To8"),
        "weighted mean head difference",
    )
    minimum = _finite_gate_vector(
        head_diagnostics.get("minimumLocalHeadDifferenceMByGateId1To8"),
        "minimum local head difference",
    )
    minimum_upstream_depth = _finite_gate_vector(
        head_diagnostics.get("minimumUpstreamDepthMByGateId1To8"),
        "minimum upstream depth",
    )
    minimum_downstream_depth = _finite_gate_vector(
        head_diagnostics.get("minimumDownstreamDepthMByGateId1To8"),
        "minimum downstream depth",
    )
    require(
        bool(
            np.all(minimum_upstream_depth > MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M)
            and np.all(
                minimum_downstream_depth > MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M
            )
        ),
        "head observation contains a dry or near-dry selected face side",
    )
    require(
        bool(np.all(minimum <= mean + 1.0e-12)),
        "minimum local head cannot exceed its weighted mean",
    )
    sample_time = _finite(state_sample_model_time_s, "state sample model time")
    controller_time = _finite(controller_model_time_s, "controller model time")
    require(sample_time >= 0.0, "state sample model time must be nonnegative")
    require(controller_time >= 0.0, "controller model time must be nonnegative")
    require(
        controller_time + 1.0e-12 >= sample_time,
        "controller model time precedes the R1C state sample",
    )
    common_age = max(0.0, controller_time - sample_time)
    age = np.full(8, common_age, dtype=np.float64)
    evidence_payload = {
        "schema": CONTROLLER_BRIDGE_SCHEMA,
        "version": ADAPTER_VERSION,
        "bindingIdentitySha256": binding_sha,
        "bindingAuthoritySha256": None,
        "bindingAuthorityVerified": False,
        "stateArraySha256": state_sha,
        "bedArraySha256": bed_sha,
        "observationSourceAuthoritySha256": source_sha,
        "runIdentitySha256": run_sha,
        "stateSampleModelTimeS": sample_time,
        "controllerModelTimeS": controller_time,
        "meanHeadDifferenceMByGateId1To8": mean.tolist(),
        "minimumLocalHeadDifferenceMByGateId1To8": minimum.tolist(),
        "minimumUpstreamDepthMByGateId1To8": minimum_upstream_depth.tolist(),
        "minimumDownstreamDepthMByGateId1To8": minimum_downstream_depth.tolist(),
        "minimumTrustedSelectedFaceDepthM": MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M,
    }
    evidence_sha = hashlib.sha256(
        json.dumps(
            evidence_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": CONTROLLER_BRIDGE_SCHEMA,
        "version": ADAPTER_VERSION,
        "bindingIdentitySha256": binding_sha,
        "bindingAuthoritySha256": None,
        "bindingAuthorityVerified": False,
        "externalRuntimeAuthorityStatus": EXTERNAL_RUNTIME_AUTHORITY_STATUS,
        "stateArraySha256": state_sha,
        "bedArraySha256": bed_sha,
        "observationSourceAuthoritySha256": source_sha,
        "runIdentitySha256": run_sha,
        "observationEvidenceSha256": evidence_sha,
        "stateSampleModelTimeS": sample_time,
        "controllerModelTimeS": controller_time,
        "commonObservationAgeS": common_age,
        "minimumUpstreamDepthMByGateId1To8": minimum_upstream_depth.tolist(),
        "minimumDownstreamDepthMByGateId1To8": minimum_downstream_depth.tolist(),
        "minimumTrustedSelectedFaceDepthM": MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M,
        "controllerKeywordArguments": {
            "mean_head_difference_m_by_gate_id_1_to_8": mean.tolist(),
            "local_head_difference_m_by_gate_id_1_to_8": minimum.tolist(),
            "head_observation_age_s_by_gate_id_1_to_8": age.tolist(),
        },
        "worstFaceHeadPassedToController": True,
        "perGateHeadValuesAreSpatiallyIndependent": True,
        "freshnessUsesSingleR1CStateSample": True,
        "callerSuppliedFreshnessAccepted": False,
        "allSelectedFaceSidesWetAboveTrustedFloor": True,
        "positiveMotionAuthorityVerified": False,
        "solverConnectionPerformed": False,
        "solverIntegrationStatus": OFFLINE_INTEGRATION_STATUS,
        "fishwayHydraulicConnectionPerformed": False,
        "fishwayIntegrationStatus": FISHWAY_INTEGRATION_STATUS,
    }


def validate_controller_live_head_input(
    controller_bridge: Mapping[str, object],
) -> dict[str, object]:
    """Validate the sealed offline R1C observation before controller use."""

    require(isinstance(controller_bridge, Mapping), "controller bridge is required")
    require(
        controller_bridge.get("schema") == CONTROLLER_BRIDGE_SCHEMA,
        "controller bridge schema mismatch",
    )
    require(
        controller_bridge.get("version") == ADAPTER_VERSION,
        "controller bridge version mismatch",
    )
    require(
        controller_bridge.get("solverConnectionPerformed") is False
        and controller_bridge.get("solverIntegrationStatus")
        == OFFLINE_INTEGRATION_STATUS,
        "controller bridge does not retain offline-only status",
    )
    require(
        controller_bridge.get("fishwayHydraulicConnectionPerformed") is False
        and controller_bridge.get("fishwayIntegrationStatus")
        == FISHWAY_INTEGRATION_STATUS,
        "controller bridge does not retain fishway exclusion status",
    )
    binding_sha = controller_bridge.get("bindingIdentitySha256")
    require(
        isinstance(binding_sha, str)
        and SHA256_PATTERN.fullmatch(binding_sha) is not None,
        "controller bridge binding SHA is invalid",
    )
    require(
        controller_bridge.get("bindingAuthoritySha256") is None
        and controller_bridge.get("bindingAuthorityVerified") is False
        and controller_bridge.get("externalRuntimeAuthorityStatus")
        == EXTERNAL_RUNTIME_AUTHORITY_STATUS,
        "controller bridge fabricated a binding authority",
    )
    state_sha = _require_sha256(
        controller_bridge.get("stateArraySha256"), "bridge state array SHA"
    )
    bed_sha = _require_sha256(
        controller_bridge.get("bedArraySha256"), "bridge bed array SHA"
    )
    source_sha = _require_sha256(
        controller_bridge.get("observationSourceAuthoritySha256"),
        "bridge observation source authority SHA",
    )
    run_sha = _require_sha256(
        controller_bridge.get("runIdentitySha256"), "bridge run identity SHA"
    )
    sample_time = _finite(
        controller_bridge.get("stateSampleModelTimeS"),
        "bridge state sample model time",
    )
    controller_time = _finite(
        controller_bridge.get("controllerModelTimeS"),
        "bridge controller model time",
    )
    common_age = _finite(
        controller_bridge.get("commonObservationAgeS"),
        "bridge observation age",
    )
    require(
        controller_time + 1.0e-12 >= sample_time
        and abs(common_age - (controller_time - sample_time)) <= 1.0e-12,
        "controller bridge observation time identity changed",
    )
    kwargs = controller_bridge.get("controllerKeywordArguments")
    require(isinstance(kwargs, Mapping), "controller keyword arguments are missing")
    require(
        set(kwargs)
        == {
            "mean_head_difference_m_by_gate_id_1_to_8",
            "local_head_difference_m_by_gate_id_1_to_8",
            "head_observation_age_s_by_gate_id_1_to_8",
        },
        "controller keyword argument keys changed",
    )
    mean = _explicit_finite_gate_vector(
        kwargs["mean_head_difference_m_by_gate_id_1_to_8"],
        "bridge weighted mean head difference",
    )
    minimum = _explicit_finite_gate_vector(
        kwargs["local_head_difference_m_by_gate_id_1_to_8"],
        "bridge minimum local head difference",
    )
    age = _explicit_finite_gate_vector(
        kwargs["head_observation_age_s_by_gate_id_1_to_8"],
        "bridge head observation age",
    )
    minimum_upstream_depth = _explicit_finite_gate_vector(
        controller_bridge.get("minimumUpstreamDepthMByGateId1To8"),
        "bridge minimum upstream depth",
    )
    minimum_downstream_depth = _explicit_finite_gate_vector(
        controller_bridge.get("minimumDownstreamDepthMByGateId1To8"),
        "bridge minimum downstream depth",
    )
    require(
        controller_bridge.get("allSelectedFaceSidesWetAboveTrustedFloor") is True
        and controller_bridge.get("minimumTrustedSelectedFaceDepthM")
        == MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M
        and bool(
            np.all(minimum_upstream_depth > MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M)
            and np.all(
                minimum_downstream_depth > MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M
            )
        ),
        "controller bridge contains a dry or near-dry selected face side",
    )
    require(
        bool(np.all(minimum <= mean + 1.0e-12)),
        "bridge minimum local head exceeds its weighted mean",
    )
    require(
        bool(np.all(np.abs(age - common_age) <= 1.0e-12)),
        "bridge per-gate age was not derived from the single R1C state sample",
    )
    evidence_payload = {
        "schema": CONTROLLER_BRIDGE_SCHEMA,
        "version": ADAPTER_VERSION,
        "bindingIdentitySha256": binding_sha,
        "bindingAuthoritySha256": None,
        "bindingAuthorityVerified": False,
        "stateArraySha256": state_sha,
        "bedArraySha256": bed_sha,
        "observationSourceAuthoritySha256": source_sha,
        "runIdentitySha256": run_sha,
        "stateSampleModelTimeS": sample_time,
        "controllerModelTimeS": controller_time,
        "meanHeadDifferenceMByGateId1To8": mean.tolist(),
        "minimumLocalHeadDifferenceMByGateId1To8": minimum.tolist(),
        "minimumUpstreamDepthMByGateId1To8": minimum_upstream_depth.tolist(),
        "minimumDownstreamDepthMByGateId1To8": minimum_downstream_depth.tolist(),
        "minimumTrustedSelectedFaceDepthM": MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M,
    }
    expected_sha = hashlib.sha256(
        json.dumps(
            evidence_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    require(
        controller_bridge.get("observationEvidenceSha256") == expected_sha,
        "controller bridge observation evidence SHA mismatch",
    )
    return {
        "bindingIdentitySha256": binding_sha,
        "observationEvidenceSha256": expected_sha,
        "controllerKeywordArguments": {
            "mean_head_difference_m_by_gate_id_1_to_8": mean.tolist(),
            "local_head_difference_m_by_gate_id_1_to_8": minimum.tolist(),
            "head_observation_age_s_by_gate_id_1_to_8": age.tolist(),
        },
    }


def build_sealed_forecast_evidence_package(
    *,
    forecast_source_sha256: object,
    forecast_model_sha256: object,
    forecast_run_sha256: object,
    forecast_time_window_sha256: object,
    forecast_issued_model_time_s: object,
    forecast_window_start_model_time_s: object,
    forecast_window_end_model_time_s: object,
    controller_model_time_s: object,
    predicted_minimum_control_head_difference_m_by_gate_id_1_to_8: object,
) -> dict[str, object]:
    """Seal source identity, time window, and exact per-gate forecast vectors."""

    source_sha = _require_sha256(forecast_source_sha256, "forecast source SHA")
    model_sha = _require_sha256(forecast_model_sha256, "forecast model SHA")
    run_sha = _require_sha256(forecast_run_sha256, "forecast run SHA")
    time_window_sha = _require_sha256(
        forecast_time_window_sha256, "forecast time-window SHA"
    )
    issued = _finite(forecast_issued_model_time_s, "forecast issued model time")
    window_start = _finite(
        forecast_window_start_model_time_s, "forecast window start model time"
    )
    window_end = _finite(
        forecast_window_end_model_time_s, "forecast window end model time"
    )
    controller_time = _finite(controller_model_time_s, "controller model time")
    require(
        issued >= 0.0 and window_start >= 0.0 and window_end >= 0.0,
        "forecast model times must be nonnegative",
    )
    require(issued <= controller_time + 1.0e-12, "forecast issue time is in the future")
    require(
        window_start <= controller_time + 1.0e-12
        and controller_time <= window_end + 1.0e-12,
        "controller time is outside the sealed forecast window",
    )
    require(window_start < window_end, "forecast window must have positive duration")
    predicted = _explicit_finite_gate_vector(
        predicted_minimum_control_head_difference_m_by_gate_id_1_to_8,
        "predicted minimum control head difference",
    )
    age = np.full(8, max(0.0, controller_time - issued), dtype=np.float64)
    coverage = np.full(8, max(0.0, window_end - controller_time), dtype=np.float64)
    vector_hashes = {
        "predictedMinimumControlHeadDifferenceMByGateId1To8": array_sha256(
            predicted
        ),
        "forecastAgeSByGateId1To8": array_sha256(age),
        "forecastRemainingCoverageSByGateId1To8": array_sha256(coverage),
    }
    payload: dict[str, object] = {
        "schema": FORECAST_EVIDENCE_SCHEMA,
        "producerAdapterVersion": ADAPTER_VERSION,
        "forecastSourceSha256": source_sha,
        "forecastModelSha256": model_sha,
        "forecastRunSha256": run_sha,
        "forecastTimeWindowSha256": time_window_sha,
        "forecastIssuedModelTimeS": issued,
        "forecastWindowStartModelTimeS": window_start,
        "forecastWindowEndModelTimeS": window_end,
        "controllerModelTimeS": controller_time,
        "predictedMinimumControlHeadDifferenceMByGateId1To8": predicted.tolist(),
        "forecastAgeSByGateId1To8": age.tolist(),
        "forecastRemainingCoverageSByGateId1To8": coverage.tolist(),
        "vectorSha256": vector_hashes,
        "perGateIndependentForecastVerified": True,
        "forecastProducerAuthorityVerified": False,
        "externalRuntimeAuthorityStatus": EXTERNAL_RUNTIME_AUTHORITY_STATUS,
        "callerSuppliedForecastAgeAccepted": False,
        "callerSuppliedForecastCoverageAccepted": False,
        "solverConnectionPerformed": False,
        "solverIntegrationStatus": OFFLINE_INTEGRATION_STATUS,
        "fishwayHydraulicConnectionPerformed": False,
        "fishwayIntegrationStatus": FISHWAY_INTEGRATION_STATUS,
    }
    payload["forecastEvidenceSha256"] = _json_sha256(payload)
    return payload


def validate_sealed_forecast_evidence_package(
    forecast_evidence_package: Mapping[str, object],
) -> dict[str, object]:
    """Fail closed on any forecast source, timing, vector, or seal change."""

    require(isinstance(forecast_evidence_package, Mapping), "forecast evidence is required")
    required = {
        "schema",
        "producerAdapterVersion",
        "forecastSourceSha256",
        "forecastModelSha256",
        "forecastRunSha256",
        "forecastTimeWindowSha256",
        "forecastIssuedModelTimeS",
        "forecastWindowStartModelTimeS",
        "forecastWindowEndModelTimeS",
        "controllerModelTimeS",
        "predictedMinimumControlHeadDifferenceMByGateId1To8",
        "forecastAgeSByGateId1To8",
        "forecastRemainingCoverageSByGateId1To8",
        "vectorSha256",
        "perGateIndependentForecastVerified",
        "forecastProducerAuthorityVerified",
        "externalRuntimeAuthorityStatus",
        "callerSuppliedForecastAgeAccepted",
        "callerSuppliedForecastCoverageAccepted",
        "solverConnectionPerformed",
        "solverIntegrationStatus",
        "fishwayHydraulicConnectionPerformed",
        "fishwayIntegrationStatus",
        "forecastEvidenceSha256",
    }
    require(set(forecast_evidence_package) == required, "forecast evidence keys are invalid")
    require(
        forecast_evidence_package["schema"] == FORECAST_EVIDENCE_SCHEMA
        and forecast_evidence_package["producerAdapterVersion"] == ADAPTER_VERSION,
        "forecast evidence schema or producer mismatch",
    )
    for key, label in (
        ("forecastSourceSha256", "forecast source SHA"),
        ("forecastModelSha256", "forecast model SHA"),
        ("forecastRunSha256", "forecast run SHA"),
        ("forecastTimeWindowSha256", "forecast time-window SHA"),
    ):
        _require_sha256(forecast_evidence_package[key], label)
    require(
        forecast_evidence_package["perGateIndependentForecastVerified"] is True
        and forecast_evidence_package["forecastProducerAuthorityVerified"] is False
        and forecast_evidence_package["externalRuntimeAuthorityStatus"]
        == EXTERNAL_RUNTIME_AUTHORITY_STATUS
        and forecast_evidence_package["callerSuppliedForecastAgeAccepted"] is False
        and forecast_evidence_package["callerSuppliedForecastCoverageAccepted"] is False,
        "forecast evidence does not retain derived per-gate timing semantics",
    )
    require(
        forecast_evidence_package["solverConnectionPerformed"] is False
        and forecast_evidence_package["solverIntegrationStatus"]
        == OFFLINE_INTEGRATION_STATUS,
        "forecast evidence does not retain offline solver status",
    )
    require(
        forecast_evidence_package["fishwayHydraulicConnectionPerformed"] is False
        and forecast_evidence_package["fishwayIntegrationStatus"]
        == FISHWAY_INTEGRATION_STATUS,
        "forecast evidence does not retain fishway-unconnected status",
    )
    issued = _finite(
        forecast_evidence_package["forecastIssuedModelTimeS"],
        "sealed forecast issue time",
    )
    window_start = _finite(
        forecast_evidence_package["forecastWindowStartModelTimeS"],
        "sealed forecast window start",
    )
    window_end = _finite(
        forecast_evidence_package["forecastWindowEndModelTimeS"],
        "sealed forecast window end",
    )
    controller_time = _finite(
        forecast_evidence_package["controllerModelTimeS"],
        "sealed forecast controller time",
    )
    require(
        issued <= controller_time + 1.0e-12
        and window_start <= controller_time + 1.0e-12
        and controller_time <= window_end + 1.0e-12
        and window_start < window_end,
        "sealed forecast time window is inconsistent",
    )
    predicted = _explicit_finite_gate_vector(
        forecast_evidence_package[
            "predictedMinimumControlHeadDifferenceMByGateId1To8"
        ],
        "sealed predicted minimum control head difference",
    )
    age = _explicit_finite_gate_vector(
        forecast_evidence_package["forecastAgeSByGateId1To8"],
        "sealed forecast age",
    )
    coverage = _explicit_finite_gate_vector(
        forecast_evidence_package["forecastRemainingCoverageSByGateId1To8"],
        "sealed forecast remaining coverage",
    )
    require(
        bool(np.all(np.abs(age - (controller_time - issued)) <= 1.0e-12)),
        "sealed forecast age was not derived from source issue time",
    )
    require(
        bool(np.all(np.abs(coverage - (window_end - controller_time)) <= 1.0e-12)),
        "sealed forecast coverage was not derived from the time window",
    )
    hashes = forecast_evidence_package["vectorSha256"]
    require(isinstance(hashes, Mapping), "forecast vector SHA inventory is missing")
    expected_hashes = {
        "predictedMinimumControlHeadDifferenceMByGateId1To8": array_sha256(
            predicted
        ),
        "forecastAgeSByGateId1To8": array_sha256(age),
        "forecastRemainingCoverageSByGateId1To8": array_sha256(coverage),
    }
    require(dict(hashes) == expected_hashes, "forecast vector SHA inventory mismatch")
    sealed_body = dict(forecast_evidence_package)
    forecast_sha = sealed_body.pop("forecastEvidenceSha256")
    _require_sha256(forecast_sha, "forecast evidence SHA")
    require(
        _json_sha256(sealed_body) == forecast_sha,
        "forecast evidence package SHA mismatch",
    )
    return {
        "forecastEvidenceSha256": forecast_sha,
        "controllerModelTimeS": controller_time,
        "predictedMinimumControlHeadDifferenceMByGateId1To8": predicted.tolist(),
        "forecastAgeSByGateId1To8": age.tolist(),
        "forecastRemainingCoverageSByGateId1To8": coverage.tolist(),
    }


def resolve_and_advance_from_verified_r1c_observation(
    *,
    controller_observation_package: Mapping[str, object],
    requested_capacity_by_gate_id_1_to_8: object,
    controller_state: Mapping[str, object],
    policy: Mapping[str, object],
    forecast_evidence_package: Mapping[str, object],
    elapsed_seconds: object,
) -> dict[str, object]:
    """Use only the controller's sealed atomic path for an offline R1C step.

    The result remains an integration candidate.  It neither advances the
    hydrodynamic solver nor changes any gate interface in an R1C runner.
    """

    require(
        isinstance(controller_observation_package, Mapping),
        "controller observation package is required",
    )
    require(
        controller_observation_package.get("solverConnectionPerformed") is False
        and controller_observation_package.get("solverRunPerformed") is False
        and controller_observation_package.get("solverIntegrationStatus")
        == OFFLINE_INTEGRATION_STATUS,
        "controller observation package is not offline-only",
    )
    bridge = controller_observation_package.get("controllerInput")
    require(isinstance(bridge, Mapping), "controller observation bridge is missing")
    verified = validate_controller_live_head_input(bridge)
    requested = _capacity_vector(requested_capacity_by_gate_id_1_to_8)
    require(
        bool(np.all(requested == 0.0)),
        "positive motion blocked: immutable external preflight activation root is unavailable",
    )
    forecast = validate_sealed_forecast_evidence_package(forecast_evidence_package)
    require(
        abs(
            float(forecast["controllerModelTimeS"])
            - float(bridge["controllerModelTimeS"])
        )
        <= 1.0e-12,
        "live-head and forecast controller times do not match",
    )
    state = control.validate_controller_state(controller_state)
    state_binding_sha = _require_sha256(
        state["stateBindingSha256"], "controller state binding SHA"
    )
    controller_kwargs = dict(verified["controllerKeywordArguments"])
    forecast_minimum = list(
        forecast["predictedMinimumControlHeadDifferenceMByGateId1To8"]
    )
    forecast_age = list(forecast["forecastAgeSByGateId1To8"])
    forecast_coverage = list(forecast["forecastRemainingCoverageSByGateId1To8"])
    argument_binding_sha = control.positive_motion_controller_argument_binding_sha256(
        mean_head_difference_m_by_gate_id_1_to_8=controller_kwargs[
            "mean_head_difference_m_by_gate_id_1_to_8"
        ],
        local_head_difference_m_by_gate_id_1_to_8=controller_kwargs[
            "local_head_difference_m_by_gate_id_1_to_8"
        ],
        head_observation_age_s_by_gate_id_1_to_8=controller_kwargs[
            "head_observation_age_s_by_gate_id_1_to_8"
        ],
        predicted_minimum_control_head_difference_m_by_gate_id_1_to_8=(
            forecast_minimum
        ),
        forecast_age_s_by_gate_id_1_to_8=forecast_age,
        forecast_remaining_coverage_s_by_gate_id_1_to_8=forecast_coverage,
    )
    positive_motion_evidence: dict[str, object] = {
        "schema": control.POSITIVE_MOTION_EVIDENCE_SCHEMA,
        "producerAdapterVersion": ADAPTER_VERSION,
        "liveHeadObservationEvidenceSha256": verified[
            "observationEvidenceSha256"
        ],
        "forecastEvidenceSha256": forecast["forecastEvidenceSha256"],
        "perGateIndependentHeadVerified": True,
        "perGateIndependentForecastVerified": True,
        "controllerArgumentBindingSha256": argument_binding_sha,
        "solverConnectionPerformed": False,
    }
    positive_motion_evidence["evidencePackageSha256"] = _json_sha256(
        positive_motion_evidence
    )
    controller_step = control.resolve_and_advance_controller_state(
        elapsed_seconds=elapsed_seconds,
        controller_state=controller_state,
        policy=policy,
        requested_capacity_by_gate_id_1_to_8=requested.tolist(),
        predicted_minimum_control_head_difference_m_by_gate_id_1_to_8=(
            forecast_minimum
        ),
        forecast_age_s_by_gate_id_1_to_8=forecast_age,
        forecast_remaining_coverage_s_by_gate_id_1_to_8=(
            forecast_coverage
        ),
        verified_positive_motion_evidence=positive_motion_evidence,
        **controller_kwargs,
    )
    decision = controller_step.get("decision")
    require(isinstance(decision, Mapping), "sealed controller decision is missing")
    decision_binding = decision.get("decisionBindingSha256")
    require(
        isinstance(decision_binding, str)
        and SHA256_PATTERN.fullmatch(decision_binding) is not None,
        "controller decision is not sealed",
    )
    require(
        decision.get("perGateIndependentHeadRepresented") is True,
        "controller did not retain explicit per-gate R1C heads",
    )
    require(
        decision.get("perGateIndependentForecastRepresented") is True
        and decision.get("runtimeMotionAuthorityClaimed") is False
        and decision.get("controlOutputIsDiagnosticMechanicsOnly") is True,
        "controller made an unsupported runtime motion authority claim",
    )
    target = _capacity_vector(decision.get("targetCapacityByGateId1To8"))
    require(
        bool(np.all(target == 0.0)),
        "positive motion escaped while external runtime authority is unavailable",
    )
    next_state = controller_step.get("controllerState")
    require(isinstance(next_state, Mapping), "sealed next controller state is missing")
    validated_next_state = control.validate_controller_state(next_state)
    require(
        validated_next_state["parentStateBindingSha256"] == state_binding_sha
        and validated_next_state["sourceDecisionBindingSha256"]
        == decision_binding,
        "controller state hash chain does not bind this state and decision",
    )
    requested_sha = array_sha256(requested)
    step_evidence_payload = {
        "bindingIdentitySha256": verified["bindingIdentitySha256"],
        "liveHeadObservationEvidenceSha256": verified[
            "observationEvidenceSha256"
        ],
        "forecastEvidenceSha256": forecast["forecastEvidenceSha256"],
        "positiveMotionEvidencePackageSha256": positive_motion_evidence[
            "evidencePackageSha256"
        ],
        "controllerStateBindingSha256": state_binding_sha,
        "requestedCapacityVectorSha256": requested_sha,
        "controllerDecisionBindingSha256": decision_binding,
        "nextControllerStateBindingSha256": validated_next_state[
            "stateBindingSha256"
        ],
        "elapsedSeconds": _finite(elapsed_seconds, "controller elapsed seconds"),
    }
    return {
        "schema": CONTROLLER_STEP_SCHEMA,
        "version": ADAPTER_VERSION,
        "bindingIdentitySha256": verified["bindingIdentitySha256"],
        "observationEvidenceSha256": verified["observationEvidenceSha256"],
        "forecastEvidenceSha256": forecast["forecastEvidenceSha256"],
        "verifiedPositiveMotionEvidence": positive_motion_evidence,
        "controllerStateBindingSha256": state_binding_sha,
        "controllerStateOrigin": state["origin"],
        "controllerStep": controller_step,
        "controllerDecisionBindingSha256": decision_binding,
        "nextControllerStateBindingSha256": validated_next_state[
            "stateBindingSha256"
        ],
        "controlStepEvidence": step_evidence_payload,
        "controlStepEvidenceSha256": _json_sha256(step_evidence_payload),
        "controllerCheckpointSealConnected": True,
        "controllerStateHashChainVerified": True,
        "positiveMotionPermitted": False,
        "externalRuntimeAuthorityStatus": EXTERNAL_RUNTIME_AUTHORITY_STATUS,
        "automaticRequestSemantics": decision.get("automaticRequestSemantics"),
        "solverConnectionPerformed": False,
        "solverRunPerformed": False,
        "solverIntegrationStatus": OFFLINE_INTEGRATION_STATUS,
        "fishwayHydraulicConnectionPerformed": False,
        "fishwayIntegrationStatus": FISHWAY_INTEGRATION_STATUS,
    }


def build_controller_live_head_observation(
    *,
    state: object,
    bed_elevation_m: object,
    geometry: Mapping[str, object],
    structure_face_ids: object,
    structure_face_roles: object,
    structure_main_gate_ids: object,
    main_gate_face_ids: object,
    main_gate_id_by_selected_face: object,
    main_gate_upstream_cell_id: object,
    binding_contract: Mapping[str, object],
    state_sample_model_time_s: object,
    controller_model_time_s: object,
    observation_source_authority_sha256: object,
    run_identity_sha256: object,
) -> dict[str, object]:
    """Inspect a self-hashed candidate and build diagnostic head evidence."""

    values = np.asarray(state, dtype=np.float64)
    bed = np.asarray(bed_elevation_m, dtype=np.float64)
    require(
        values.ndim == 2 and values.shape[1] == 3,
        "live state shape must be cells by H/HU/HV",
    )
    require(bed.shape == (len(values),), "live bed shape does not match state")
    state_sha = array_sha256(values)
    bed_sha = array_sha256(bed)
    binding = inspect_candidate_main_gate_faces(
        geometry=geometry,
        structure_face_ids=structure_face_ids,
        structure_face_roles=structure_face_roles,
        structure_main_gate_ids=structure_main_gate_ids,
        main_gate_face_ids=main_gate_face_ids,
        main_gate_id_by_selected_face=main_gate_id_by_selected_face,
        main_gate_upstream_cell_id=main_gate_upstream_cell_id,
        binding_contract=binding_contract,
    )
    heads = per_gate_head_diagnostics(state, bed_elevation_m, binding)
    bridge = controller_live_head_input(
        heads,
        state_sample_model_time_s=state_sample_model_time_s,
        controller_model_time_s=controller_model_time_s,
        state_array_sha256=state_sha,
        bed_array_sha256=bed_sha,
        observation_source_authority_sha256=(
            observation_source_authority_sha256
        ),
        run_identity_sha256=run_identity_sha256,
    )
    return {
        "version": ADAPTER_VERSION,
        "candidateBinding": binding,
        "bindingAuthorityVerified": False,
        "externalRuntimeAuthorityStatus": EXTERNAL_RUNTIME_AUTHORITY_STATUS,
        "stateArraySha256": state_sha,
        "bedArraySha256": bed_sha,
        "headDiagnostics": heads,
        "controllerInput": bridge,
        "solverConnectionPerformed": False,
        "solverRunPerformed": False,
        "solverIntegrationStatus": OFFLINE_INTEGRATION_STATUS,
        "fishwayHydraulicConnectionPerformed": False,
        "fishwayIntegrationStatus": FISHWAY_INTEGRATION_STATUS,
    }


def signed_outward_face_flux_from_r1c(
    *,
    state: object,
    bed_elevation_m: object,
    geometry: Mapping[str, object],
    effective_internal_lengths: object,
    interface_multiplier_by_face: object,
    verified_binding: Mapping[str, object],
) -> np.ndarray:
    """Reject mapped flux acceptance without a preflight mapping authority."""

    del (
        state,
        bed_elevation_m,
        geometry,
        effective_internal_lengths,
        interface_multiplier_by_face,
        verified_binding,
    )
    raise ValueError(
        f"[{ADAPTER_VERSION}] mapped signed flux authority unavailable: "
        f"{EXTERNAL_RUNTIME_AUTHORITY_STATUS}; caller-supplied effective lengths "
        "or multipliers cannot authorize flux acceptance"
    )


def diagnostic_signed_outward_face_flux_potential_from_r1c(
    *,
    state: object,
    bed_elevation_m: object,
    geometry: Mapping[str, object],
    candidate_binding: Mapping[str, object],
) -> np.ndarray:
    """Compute unmasked potential flux for diagnosis, never acceptance."""

    binding = _validated_binding(candidate_binding)
    geo = _geometry_arrays(geometry)
    values = np.asarray(state, dtype=np.float64)
    bed = np.asarray(bed_elevation_m, dtype=np.float64)
    require(
        values.ndim == 2 and values.shape[1] == 3,
        "R1C state shape must be cells by H/HU/HV",
    )
    require(bed.shape == (len(values),), "R1C bed shape does not match state")
    require(bool(np.isfinite(values).all()), "R1C state contains non-finite values")
    require(bool(np.isfinite(bed).all()), "R1C bed contains non-finite values")
    require(bool(np.all(values[:, 0] >= 0.0)), "R1C state contains negative water depth")
    faces = np.asarray(binding["face"], dtype=np.int64)
    upstream = np.asarray(binding["upstream"], dtype=np.int64)
    downstream = np.asarray(binding["downstream"], dtype=np.int64)
    require(
        bool(np.all((upstream >= 0) & (upstream < len(values))))
        and bool(np.all((downstream >= 0) & (downstream < len(values)))),
        "bound face cell id is outside the R1C state",
    )
    unsafe_side = (
        (values[upstream, 0] <= MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M)
        | (values[downstream, 0] <= MINIMUM_TRUSTED_SELECTED_FACE_DEPTH_M)
    )
    require(
        not bool(np.any(unsafe_side)),
        "R1C signed flux rejected because a selected face side is dry or near-dry",
    )
    require(
        bool(np.array_equal(geo["left"][faces], binding["left"])),
        "current geometry left cells differ from verified binding",
    )
    require(
        bool(np.array_equal(geo["right"][faces], binding["right"])),
        "current geometry right cells differ from verified binding",
    )
    require(
        bool(np.array_equal(geo["lengths"][faces], binding["lengths"])),
        "current geometry base lengths differ from verified binding",
    )
    normals = np.asarray(geo["normals"], dtype=np.float64)
    require(
        bool(np.array_equal(normals[faces], binding["normals"])),
        "current geometry normals differ from verified binding",
    )
    effective = np.asarray(geo["lengths"], dtype=np.float64)
    multiplier = np.ones(len(geo["left"]), dtype=np.float64)
    return legacy.base.signed_outward_gate_discharge_m3_s(
        values,
        bed,
        geometry,  # type: ignore[arg-type]
        faces,
        upstream,
        effective,
        multiplier,
    )


def aggregate_and_validate_signed_outward_flux_by_gate(
    signed_outward_discharge_m3_s_by_selected_face: object,
    current_opening_fraction_by_gate_id_1_to_8: object,
    verified_binding: Mapping[str, object],
    *,
    reverse_flux_tolerance_m3_s: object,
    capacity_zero_tolerance: object = 1.0e-12,
) -> dict[str, object]:
    """Reject reverse flow and closed-gate leakage before per-gate aggregation."""

    binding = _validated_binding(verified_binding)
    flux = _float_vector(
        signed_outward_discharge_m3_s_by_selected_face,
        "signed outward discharge by selected face",
    )
    faces = np.asarray(binding["face"], dtype=np.int64)
    gates = np.asarray(binding["gate"], dtype=np.int64)
    require(len(flux) == len(faces), "signed outward flux length does not match binding")
    opening = _capacity_vector(current_opening_fraction_by_gate_id_1_to_8)
    reverse_tolerance = _finite(reverse_flux_tolerance_m3_s, "reverse flux tolerance")
    zero_tolerance = _finite(capacity_zero_tolerance, "capacity zero tolerance")
    require(
        0.0 <= reverse_tolerance <= MAXIMUM_REVERSE_FLUX_TOLERANCE_M3_S,
        "reverse flux tolerance exceeds the fixed 1e-10 m3/s hard cap",
    )
    require(0.0 <= zero_tolerance < 1.0e-6, "capacity zero tolerance is invalid")
    rows: list[dict[str, object]] = []
    adverse_faces: list[tuple[int, int, float]] = []
    inactive_leakage: list[tuple[int, int, float]] = []
    adverse_gate_totals: list[tuple[int, float]] = []
    inactive_gate_leakage: list[tuple[int, float]] = []
    for gate_id in MAIN_GATE_IDS:
        selected = np.flatnonzero(gates == gate_id)
        gate_flux = flux[selected]
        gate_total = float(math.fsum(float(value) for value in gate_flux))
        gate_adverse_magnitude = float(
            math.fsum(max(-float(value), 0.0) for value in gate_flux)
        )
        gate_leakage_magnitude = float(
            math.fsum(abs(float(value)) for value in gate_flux)
        )
        active = bool(opening[gate_id - 1] > zero_tolerance)
        adverse = gate_flux < -reverse_tolerance
        for local_index in np.flatnonzero(adverse):
            selected_index = int(selected[int(local_index)])
            adverse_faces.append(
                (gate_id, int(faces[selected_index]), float(flux[selected_index]))
            )
        if not active:
            for local_index in np.flatnonzero(np.abs(gate_flux) > reverse_tolerance):
                selected_index = int(selected[int(local_index)])
                inactive_leakage.append(
                    (gate_id, int(faces[selected_index]), float(flux[selected_index]))
                )
            if gate_leakage_magnitude > reverse_tolerance:
                inactive_gate_leakage.append((gate_id, gate_leakage_magnitude))
        elif gate_adverse_magnitude > reverse_tolerance:
            adverse_gate_totals.append((gate_id, gate_adverse_magnitude))
        worst_local_index = int(np.argmin(gate_flux))
        worst_selected_index = int(selected[worst_local_index])
        rows.append(
            {
                "gateId": gate_id,
                "active": active,
                "openingFraction": float(opening[gate_id - 1]),
                "faceCount": int(len(selected)),
                "totalSignedOutwardDischargeM3S": gate_total,
                "cumulativeAdverseFluxMagnitudeM3S": gate_adverse_magnitude,
                "absoluteFluxMagnitudeM3S": gate_leakage_magnitude,
                "minimumSignedOutwardFaceDischargeM3S": float(
                    gate_flux[worst_local_index]
                ),
                "maximumSignedOutwardFaceDischargeM3S": float(np.max(gate_flux)),
                "adverseFaceCount": int(np.sum(adverse)),
                "worstFaceId": int(faces[worst_selected_index]),
                "perFaceAdverseCheckPrecedesGateSum": True,
                "reverseFluxToleranceM3S": reverse_tolerance,
            }
        )
    if adverse_faces:
        gate_id, face_id, value = adverse_faces[0]
        raise ValueError(
            f"[{ADAPTER_VERSION}] adverse main-gate face flux: "
            f"gate={gate_id} face={face_id} Q={value}; result rejected without clipping"
        )
    if inactive_leakage:
        gate_id, face_id, value = inactive_leakage[0]
        raise ValueError(
            f"[{ADAPTER_VERSION}] inactive main-gate face leakage: "
            f"gate={gate_id} face={face_id} Q={value}; closed-gate result rejected"
        )
    if adverse_gate_totals:
        gate_id, value = adverse_gate_totals[0]
        raise ValueError(
            f"[{ADAPTER_VERSION}] adverse per-gate aggregate flux magnitude: "
            f"gate={gate_id} adverseMagnitude={value}; "
            "sub-tolerance face values cannot accumulate"
        )
    if inactive_gate_leakage:
        gate_id, value = inactive_gate_leakage[0]
        raise ValueError(
            f"[{ADAPTER_VERSION}] inactive per-gate aggregate leakage: "
            f"gate={gate_id} absoluteMagnitude={value}; "
            "sub-tolerance face leakage accumulated"
        )
    active_face = np.asarray(
        [opening[gate_id - 1] > zero_tolerance for gate_id in gates], dtype=bool
    )
    active_total = float(math.fsum(float(value) for value in flux[active_face]))
    inactive_total = float(math.fsum(float(value) for value in flux[~active_face]))
    global_total = float(math.fsum(float(value) for value in flux))
    active_adverse_magnitude = float(
        math.fsum(max(-float(value), 0.0) for value in flux[active_face])
    )
    inactive_leakage_magnitude = float(
        math.fsum(abs(float(value)) for value in flux[~active_face])
    )
    require(
        active_adverse_magnitude <= reverse_tolerance,
        "global active aggregate reverse flux magnitude exceeds the fixed tolerance",
    )
    require(
        inactive_leakage_magnitude <= reverse_tolerance,
        "global inactive aggregate leakage magnitude exceeds the fixed tolerance",
    )
    require(
        global_total >= -reverse_tolerance,
        "global aggregate reverse flux exceeds the fixed tolerance",
    )
    return {
        "schema": FLUX_SCHEMA,
        "version": ADAPTER_VERSION,
        "bindingIdentitySha256": binding["bindingIdentitySha256"],
        "gateFluxDiagnosticsById1To8": rows,
        "activeFaceCount": int(np.sum(active_face)),
        "inactiveFaceCount": int(np.sum(~active_face)),
        "activeTotalSignedOutwardDischargeM3S": active_total,
        "inactiveTotalSignedOutwardDischargeM3S": inactive_total,
        "globalTotalSignedOutwardDischargeM3S": global_total,
        "activeAdverseFluxMagnitudeM3S": active_adverse_magnitude,
        "inactiveAbsoluteLeakageMagnitudeM3S": inactive_leakage_magnitude,
        "reverseFluxToleranceM3S": reverse_tolerance,
        "maximumReverseFluxToleranceM3S": MAXIMUM_REVERSE_FLUX_TOLERANCE_M3_S,
        "activeAdverseFaceCount": 0,
        "allFaceAdverseFluxRejected": True,
        "inactiveFaceLeakageRejected": True,
        "perGateAggregateReverseAndLeakageRejected": True,
        "globalAggregateReverseAndLeakageRejected": True,
        "reverseFlowPermitted": False,
        "reversePotentialWasNotClipped": True,
        "gateSumCannotHideAdverseFace": True,
    }
