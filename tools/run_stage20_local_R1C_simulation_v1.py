#!/usr/bin/env python3
"""Run one bounded local R1C physics simulation.

This runner reuses the hash-bound C2.2 hydrodynamic and fishway coupling
kernel, but accepts a caller-supplied constant eight-gate capacity vector.
It is intentionally local, uncalibrated, fail-closed, and never overwrites an
existing output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_stage20_fishway_C2_2_coupled_standard_cycle_v1 as c22


RUNNER = ROOT / "tools/run_stage20_local_R1C_simulation_v1.py"
R1C_MESH = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1"
    / "review-mesh.npz"
)
EXPECTED_R1C_MESH_SHA256 = (
    "7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164"
)
RUNTIME_CAPABILITIES_PATH = "config/stage20_runtime_capabilities_v2.json"
RUNTIME_ASSETS_PATH = "config/stage20_runtime_assets_v2.json"
EXPECTED_RUNTIME_ASSETS: dict[str, tuple[str, int, str]] = {
    "r1c_review_mesh": (
        "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1/review-mesh.npz",
        564856,
        "7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164",
    ),
    "r1c_initial_checkpoint": (
        "docs/results/stage20-barrage-candidate-C-R1C-D2-full-history-v1/R1C-full-history-checkpoints.npz",
        178050685,
        "2ce73ec98cd84eb7dc60d2fee474eceab0de543c3e40b875dd7a07904382182f",
    ),
    "r1c_diagnostic_replay_binary": (
        "docs/results/stage20-R1C-browser-replay-candidate-v1/replay-fields.bin",
        78210991,
        "4056d994cf91bef37af2eabbc67f10ead1a753e6c2018845b8d88382590c336a",
    ),
    "fishway_constant_weak_flow_coupling_candidate": (
        "config/stage20_fishway_constant_weak_flow_coupling_candidate_v1.json",
        60680,
        "7afe958520537b4f0ca2c1bf493160919b85a897cabb63639b83b07104be5313",
    ),
    "r1c_review_mesh_summary": (
        "docs/results/stage20-barrage-candidate-C-R1C-review-mesh-v1/mesh-summary.json",
        17521,
        "bfb67225311e55c2c4cd10b297329a04a928a126801f0e1b4e8c4a17eed19490",
    ),
    "fishway_c2_storage_candidate": (
        "config/stage20_fishway_1d_link_C2_storage_candidate_v1.json",
        7257,
        "0deb8c16bdfe97548781115a7ea337584577a71f6aadef0f5e88b1ad7507b8b6",
    ),
    "physical_pilot_source_contract": (
        "config/stage20_physical_pilot_v2_contract_v1.json",
        3878,
        "17e391749ffad8dc7ef1ea4a73bca3e0d0c5a374f9f92ee532b51be84a1d8f1f",
    ),
    "physical_pilot_source_mesh_manifest": (
        "public/data/onga/stage20/mesh-v2.json",
        3832,
        "17850a07821f409f13bd3c38446982ae6124743ad9e6437d5d612da447f421c8",
    ),
    "synthetic_mesh_binary": (
        "public/data/onga/stage20/mesh-v2.bin",
        2296216,
        "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659",
    ),
    "onga_water_mask_manifest_r3": (
        "data/onga_unified_water_manifest_r3.json",
        4311,
        "964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7",
    ),
    "onga_water_mask_rows_r3_0": (
        "data/onga_water_rows_r3_0.json",
        3845,
        "ecbedb7475c53357f60650e194b58e88f25f9cbc13aa6b6277ecb2293a0a47c0",
    ),
    "onga_water_mask_rows_r3_1": (
        "data/onga_water_rows_r3_1.json",
        6295,
        "ef373644c0b325d396ed8f03c1fcf6b4a34dfb8d4330e363e99118b5bdaa0ee8",
    ),
    "onga_water_mask_rows_r3_2": (
        "data/onga_water_rows_r3_2.json",
        8595,
        "0bebd9f5b735bfc990f7d9e00b564e7d9a9aca64bb1b17006fe128bcd452f443",
    ),
    "onga_water_mask_rows_r3_3": (
        "data/onga_water_rows_r3_3.json",
        10155,
        "9e55ca5fc0fddfbbfdd83d0dcea6b28ad41c91eb78adf5e39fc8eca1cf5ee48e",
    ),
    "physical_pilot_final_fields": (
        "docs/results/stage20-kernel-v3-physical-pilot-29411976467/pilot-final-fields.npz",
        1138726,
        "3e8fed6ee564a34761081728aa2c1d244cdccfee8a78e9203641f2c985613c3b",
    ),
    "stage19_m_boundary_tide_candidate": (
        "config/stage19_m_boundary_tide_candidate_v1.json",
        3754,
        "a780f618089d295731dc6a87484b6a30f8a7895aac17c507876ede06c20720ea",
    ),
    "physical_pilot_report": (
        "docs/results/stage20-kernel-v3-physical-pilot-29411976467/pilot-report.json",
        3581,
        "5ab3f0285c362c853732df6303f9ac3261f0685294b21f9a595286f76d4e0670",
    ),
}
REQUEST_SCHEMA = "onga-stage20-local-R1C-simulation-request-v1"
RESULT_SCHEMA = "onga-stage20-local-R1C-simulation-result-v1"
MANIFEST_SCHEMA = "onga-stage20-local-R1C-browser-result-manifest-v1"
CELL_COUNT = 37724
GATE_COUNT = 8
MINIMUM_DURATION_S = 1.0
MAXIMUM_DURATION_S = 300.0
MINIMUM_CHECKPOINT_INTERVAL_S = 1.0
MAXIMUM_SNAPSHOT_COUNT = 61
DISPLAY_WET_DEPTH_M = 0.05


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_request(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_object(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"regular JSON required: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def secure_runtime_asset(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and relative, "runtime asset path is absent")
    pure = PurePosixPath(relative)
    require(
        not pure.is_absolute()
        and "." not in pure.parts
        and ".." not in pure.parts
        and pure.as_posix() == relative,
        f"runtime asset path is unsafe: {relative}",
    )
    safe_root = root.resolve(strict=True)
    candidate = safe_root.joinpath(*pure.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError):
        raise RuntimeError(f"runtime asset is absent: {relative}") from None
    require(
        resolved == candidate and candidate.is_file() and not candidate.is_symlink(),
        f"runtime asset must be a contained regular file: {relative}",
    )
    return candidate


def validate_runtime_asset_closure(
    root: Path = ROOT,
    expected_assets: dict[str, tuple[str, int, str]] = EXPECTED_RUNTIME_ASSETS,
) -> list[dict[str, Any]]:
    """Recheck the full local-mode data closure immediately before execution."""

    safe_root = root.resolve(strict=True)
    capabilities = read_json_object(safe_root / RUNTIME_CAPABILITIES_PATH)
    registry = read_json_object(safe_root / RUNTIME_ASSETS_PATH)
    require(
        capabilities.get("schema") == "onga-stage20-runtime-capabilities-v2",
        "runtime capability contract identity changed",
    )
    require(
        registry.get("schema") == "onga-stage20-runtime-assets-v2",
        "runtime asset registry identity changed",
    )
    modes = capabilities.get("modes")
    assets = registry.get("assets")
    require(isinstance(modes, list), "runtime modes are absent")
    require(isinstance(assets, list), "runtime assets are absent")
    local_mode = next(
        (
            mode
            for mode in modes
            if isinstance(mode, dict) and mode.get("id") == "local_r1c_experiment"
        ),
        None,
    )
    require(isinstance(local_mode, dict), "local runtime mode is absent")
    required_ids = local_mode.get("requiredAssets")
    require(
        required_ids == list(expected_assets),
        "local runtime dependency closure changed",
    )
    asset_by_id = {
        asset.get("id"): asset
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("id"), str)
    }
    require(len(asset_by_id) == len(assets), "runtime asset ids are duplicated")

    bindings: list[dict[str, Any]] = []
    for asset_id, (relative, byte_length, expected_sha256) in expected_assets.items():
        asset = asset_by_id.get(asset_id)
        require(isinstance(asset, dict), f"runtime asset is undeclared: {asset_id}")
        require(
            asset.get("path") == relative
            and asset.get("byteLength") == byte_length
            and asset.get("sha256") == expected_sha256
            and "local_r1c_experiment" in asset.get("requiredByModes", []),
            f"runtime asset authority changed: {asset_id}",
        )
        path = secure_runtime_asset(safe_root, relative)
        require(path.stat().st_size == byte_length, f"runtime asset size changed: {asset_id}")
        require(sha256(path) == expected_sha256, f"runtime asset digest changed: {asset_id}")
        bindings.append(
            {
                "id": asset_id,
                "path": relative,
                "byteLength": byte_length,
                "sha256": expected_sha256,
            }
        )
    return bindings


def validate_request(request: dict[str, Any]) -> dict[str, Any]:
    require(request.get("schema") == REQUEST_SCHEMA, "request schema changed")
    request_id = request.get("requestId")
    require(
        isinstance(request_id, str)
        and 1 <= len(request_id) <= 80
        and all(character.isalnum() or character in "-_" for character in request_id),
        "requestId must use 1-80 safe characters",
    )
    capacities = np.asarray(
        request.get("gateCapacityFractionById"),
        dtype=np.float64,
    )
    require(capacities.shape == (GATE_COUNT,), "exactly eight gate capacities required")
    require(np.isfinite(capacities).all(), "gate capacities must be finite")
    require(
        bool(np.all((capacities >= 0.0) & (capacities <= 1.0))),
        "gate capacities must be within 0..1",
    )
    duration_s = float(request.get("durationS"))
    interval_s = float(request.get("checkpointIntervalS"))
    require(
        math.isfinite(duration_s)
        and MINIMUM_DURATION_S <= duration_s <= MAXIMUM_DURATION_S,
        "durationS is outside the bounded local range",
    )
    require(
        math.isfinite(interval_s)
        and MINIMUM_CHECKPOINT_INTERVAL_S <= interval_s <= duration_s,
        "checkpointIntervalS is outside the bounded local range",
    )
    ratio = duration_s / interval_s
    require(
        abs(ratio - round(ratio)) <= 1e-12,
        "durationS must be an exact multiple of checkpointIntervalS",
    )
    snapshot_count = int(round(ratio)) + 1
    require(
        2 <= snapshot_count <= MAXIMUM_SNAPSHOT_COUNT,
        "snapshot count exceeds the bounded local limit",
    )
    require(
        request.get("fishwayMode") == "always_enabled_C2_1_storage_tau60",
        "fishway must remain always enabled with the validated C2.1 tau60 law",
    )
    require(
        request.get("classification")
        == "local_uncalibrated_physics_not_field_prediction",
        "uncalibrated classification is required",
    )
    return {
        "requestId": request_id,
        "capacities": capacities,
        "durationS": duration_s,
        "checkpointIntervalS": interval_s,
        "snapshotCount": snapshot_count,
    }


def validate_runtime_inputs() -> dict[str, Any]:
    runtime_assets = validate_runtime_asset_closure()
    require(R1C_MESH.is_file(), "R1C mesh is absent")
    actual_mesh_sha256 = sha256(R1C_MESH)
    require(
        actual_mesh_sha256 == EXPECTED_R1C_MESH_SHA256,
        "R1C mesh identity changed",
    )
    require(c22.R1C_MESH == R1C_MESH, "C2.2 R1C mesh binding changed")
    require(c22.HYDRO_Q0_M3_S == 0.0, "legacy constant fishway source is enabled")
    require(c22.RESIDENCE_TIME_S == 60.0, "validated fishway residence time changed")
    return {
        "R1CMeshSha256": actual_mesh_sha256,
        "C2_2RunnerSha256": sha256(c22.RUNNER),
        "localRunnerSha256": sha256(RUNNER),
        "runtimeAssetCount": len(runtime_assets),
        "runtimeAssets": runtime_assets,
    }


def run_local_stage_solver(
    stage: dict[str, Any],
    initial_state: np.ndarray,
) -> tuple[dict[str, Any], dict[str, np.ndarray], np.ndarray, float]:
    """Enter the shared numerical core with the local-only report context."""

    return c22.run_stage_solver(
        stage,
        initial_state,
        None,
        None,
        report_context=c22.LOCAL_REPORT_CONTEXT,
    )


def array_descriptor(
    name: str,
    array: np.ndarray,
    offset: int,
) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    payload = contiguous.tobytes(order="C")
    return {
        "name": name,
        "dtype": str(contiguous.dtype),
        "shape": list(contiguous.shape),
        "byteOffset": offset,
        "byteLength": len(payload),
        "sha256": bytes_sha256(payload),
        "payload": payload,
    }


def write_browser_pack(
    output_dir: Path,
    request: dict[str, Any],
    arrays: dict[str, np.ndarray],
    result: dict[str, Any],
) -> dict[str, Any]:
    state = np.asarray(arrays["state_H_HU_HV"], dtype=np.float32)
    depth = np.asarray(state[:, :, 0], dtype=np.float32)
    east_velocity = np.zeros_like(depth)
    north_velocity = np.zeros_like(depth)
    wet = depth >= DISPLAY_WET_DEPTH_M
    np.divide(state[:, :, 1], depth, out=east_velocity, where=wet)
    np.divide(state[:, :, 2], depth, out=north_velocity, where=wet)
    browser_arrays = {
        "absoluteTimeS": np.asarray(arrays["absoluteTimeS"], dtype=np.float64),
        "depthM": depth,
        "eastVelocityMPS": east_velocity,
        "northVelocityMPS": north_velocity,
        "capacityFractionByGateId": np.asarray(
            arrays["capacityFractionByGateId"],
            dtype=np.float64,
        ),
        "gateFluxM3SByGateId": np.asarray(
            arrays["gateFluxM3SByGateId"],
            dtype=np.float64,
        ),
        "upstreamP2HeadM": np.asarray(arrays["upstreamP2HeadM"], dtype=np.float64),
        "downstreamP2HeadM": np.asarray(
            arrays["downstreamP2HeadM"],
            dtype=np.float64,
        ),
        "headDifferenceM": np.asarray(arrays["headDifferenceM"], dtype=np.float64),
        "fishwayOutflowM3S": np.asarray(
            arrays["fishwayOutflowM3S"],
            dtype=np.float64,
        ),
        "fishwayStorageDepthM": np.asarray(
            arrays["fishwayStorageDepthM"],
            dtype=np.float64,
        ),
        "storedVolumeM3": np.asarray(arrays["storedVolumeM3"], dtype=np.float64),
    }
    descriptors: list[dict[str, Any]] = []
    offset = 0
    for name, value in browser_arrays.items():
        descriptor = array_descriptor(name, value, offset)
        descriptors.append(descriptor)
        offset += descriptor["byteLength"]
    binary = b"".join(descriptor.pop("payload") for descriptor in descriptors)
    binary_path = output_dir / "replay-fields.bin"
    binary_path.write_bytes(binary)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "version": 1,
        "status": "PASS_LOCAL_UNCALIBRATED_PHYSICS_RESULT",
        "requestId": request["requestId"],
        "classification": {
            "localPhysicsRun": True,
            "physicalCalibration": False,
            "fieldPrediction": False,
            "productionResponsePack": False,
        },
        "mesh": {
            "id": "candidate_C_R1C_exact_confluence_R20_patches",
            "cellCount": CELL_COUNT,
            "sha256": EXPECTED_R1C_MESH_SHA256,
            "geometryIncludedInBinary": False,
        },
        "timeline": {
            "absoluteStartS": 0.0,
            "absoluteEndS": request["durationS"],
            "intervalS": request["checkpointIntervalS"],
            "snapshotCount": request["snapshotCount"],
        },
        "operation": {
            "gateCapacityFractionById": request[
                "gateCapacityFractionById"
            ],
            "capacityMeaning": (
                "classification_face_capacity_multiplier_"
                "not_measured_gate_lift"
            ),
            "fishwayAlwaysEnabled": True,
        },
        "binary": {
            "path": "replay-fields.bin",
            "byteLength": len(binary),
            "sha256": sha256(binary_path),
        },
        "arrays": {
            descriptor["name"]: {
                key: value
                for key, value in descriptor.items()
                if key != "name"
            }
            for descriptor in descriptors
        },
        "solverResult": {
            "hardAcceptancePassed": result["hardAcceptancePassed"],
            "wallSeconds": result["wallSeconds"],
            "stepsCompleted": result["stepsCompleted"],
            "maximumCfl": result["maximumCfl"],
            "maximumRelativeExtendedMassBalanceError": result[
                "maximumRelativeExtendedMassBalanceError"
            ],
        },
    }
    write_json(output_dir / "browser-manifest.json", manifest)
    return manifest


def run(request_path: Path, output_dir: Path, validate_only: bool) -> dict[str, Any]:
    request = read_request(request_path)
    normalized = validate_request(request)
    bindings = validate_runtime_inputs()
    preflight = {
        "schema": "onga-stage20-local-R1C-simulation-preflight-v1",
        "version": 1,
        "status": "PASS",
        "request": {
            "path": str(request_path),
            "sha256": sha256(request_path),
        },
        "normalized": {
            "requestId": normalized["requestId"],
            "durationS": normalized["durationS"],
            "checkpointIntervalS": normalized["checkpointIntervalS"],
            "snapshotCount": normalized["snapshotCount"],
            "gateCapacityFractionById": normalized["capacities"].tolist(),
        },
        "bindings": bindings,
        "safeguards": {
            "localOnly": True,
            "physicalCalibrationClaimed": False,
            "productionPrecomputation": False,
            "publicRuntimeChanged": False,
            "existingResultOverwriteAllowed": False,
        },
    }
    if validate_only:
        return preflight
    require(not output_dir.exists(), "output directory exists; overwrite refused")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        output_dir / "status.json",
        {
            "schema": "onga-stage20-local-R1C-simulation-status-v1",
            "version": 1,
            "status": "RUNNING",
            "requestId": normalized["requestId"],
        },
    )
    write_json(output_dir / "preflight.json", preflight)

    original_capacity_function = c22.capacity_at_absolute_time
    capacity = normalized["capacities"].copy()

    def constant_capacity(_: float) -> np.ndarray:
        return capacity.copy()

    c22.capacity_at_absolute_time = constant_capacity
    stage = {
        "stageId": "LOCAL_R1C_" + normalized["requestId"],
        "meshId": "R1C",
        "phase": "local_constant_capacity",
        "absoluteStartS": 0.0,
        "absoluteEndS": normalized["durationS"],
        "checkpointCount": normalized["snapshotCount"],
        "initialRole": "validated_R1C_all_closed_initial_state",
    }
    old_checkpoint_interval = c22.CHECKPOINT_INTERVAL_S
    c22.CHECKPOINT_INTERVAL_S = normalized["checkpointIntervalS"]
    wall_start = time.monotonic()
    try:
        initial_state = c22.load_mesh_initial_state("R1C")
        report, arrays, _, _ = run_local_stage_solver(stage, initial_state)
    finally:
        c22.capacity_at_absolute_time = original_capacity_function
        c22.CHECKPOINT_INTERVAL_S = old_checkpoint_interval

    require(report["outcome"] == "COMPLETED", "local solver did not complete")
    require(report["hardAcceptancePassed"] is True, "local solver hard acceptance failed")
    require(
        np.array_equal(
            arrays["capacityFractionByGateId"],
            np.tile(capacity, (normalized["snapshotCount"], 1)),
        ),
        "saved gate capacity differs from the request",
    )
    archive_path = output_dir / "checkpoint-archive.npz"
    np.savez_compressed(archive_path, **arrays)
    result = {
        **report,
        "schema": RESULT_SCHEMA,
        "version": 1,
        "status": "PASS_LOCAL_UNCALIBRATED_PHYSICS",
        "requestId": normalized["requestId"],
        "requestSha256": sha256(request_path),
        "classification": {
            "localPhysicsRun": True,
            "physicalCalibration": False,
            "fieldPrediction": False,
            "productionPrecomputation": False,
        },
        "gateCapacityFractionById": capacity.tolist(),
        "capacityMeaning": (
            "classification_face_capacity_multiplier_not_measured_gate_lift"
        ),
        "fishwayAlwaysEnabled": True,
        "checkpointArchiveSha256": sha256(archive_path),
        "localRunnerSha256": bindings["localRunnerSha256"],
        "C2_2RunnerSha256": bindings["C2_2RunnerSha256"],
        "R1CMeshSha256": bindings["R1CMeshSha256"],
        "totalWallSecondsIncludingSetup": time.monotonic() - wall_start,
        "publicRuntimeChanged": False,
        "mainMerged": False,
    }
    write_json(output_dir / "result.json", result)
    browser_request = {
        "requestId": normalized["requestId"],
        "durationS": normalized["durationS"],
        "checkpointIntervalS": normalized["checkpointIntervalS"],
        "snapshotCount": normalized["snapshotCount"],
        "gateCapacityFractionById": normalized["capacities"].tolist(),
    }
    manifest = write_browser_pack(output_dir, browser_request, arrays, result)
    result["browserManifestSha256"] = sha256(output_dir / "browser-manifest.json")
    result["browserBinarySha256"] = manifest["binary"]["sha256"]
    write_json(output_dir / "result.json", result)
    write_json(
        output_dir / "status.json",
        {
            "schema": "onga-stage20-local-R1C-simulation-status-v1",
            "version": 1,
            "status": "PASS",
            "requestId": normalized["requestId"],
            "resultSha256": sha256(output_dir / "result.json"),
            "browserManifestSha256": sha256(
                output_dir / "browser-manifest.json"
            ),
            "browserBinarySha256": sha256(output_dir / "replay-fields.bin"),
        },
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    try:
        result = run(
            args.request.resolve(),
            output_dir,
            args.validate_only,
        )
    except Exception as error:
        if output_dir.is_dir():
            write_json(
                output_dir / "status.json",
                {
                    "schema": "onga-stage20-local-R1C-simulation-status-v1",
                    "version": 1,
                    "status": "FAILED",
                    "errorType": type(error).__name__,
                    "message": str(error),
                    "automaticRetryPerformed": False,
                },
            )
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
