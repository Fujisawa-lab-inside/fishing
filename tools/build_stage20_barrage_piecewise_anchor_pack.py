#!/usr/bin/env python3
"""Build the inactive five-hour Stage 20 barrage piecewise anchor pack.

The builder reads only the already-sealed 0%, 50%, and 100% snapshots.  It
does not run the physical solver, interpolate in time, access the network, or
connect anything to the public simulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np


PACK_SCHEMA = "onga-stage20-barrage-piecewise-anchor-pack-v1"
PACK_STATUS = "code_only_piecewise_candidate_not_physical_validation_not_public_simulator"
ANALYSIS_SCHEMA = "onga-stage20-barrage-holdout-recovery-postrun-analysis-v1"
RESULT_SCHEMA = "onga-stage20-barrage-holdout-recovery-result-v1"
ANALYSIS_PATH = Path("config/stage20_barrage_holdout_recovery_analysis_v1.json")
RESULT_PATH = Path("config/stage20_barrage_holdout_recovery_result_v1.json")
MESH_MANIFEST_PATH = Path("public/data/onga/stage20/mesh-v2.json")
DEFAULT_OUTPUT_DIR = Path("docs/results/stage20-barrage-piecewise-candidate-v1")
DEFAULT_MANIFEST_NAME = "barrage-piecewise-anchor-pack.json"
DEFAULT_BINARY_NAME = "barrage-piecewise-anchor-pack.bin"
EXPECTED_ANALYSIS_SHA256 = "82ce4ece4dda010b846204266e604c01d26eaffba041bd4b04329a353fc834c2"
EXPECTED_RESULT_SHA256 = "fe4be9be3112eafff9965abc68bf254c78d560344c99cb2d5f31e1e75af519ab"
EXPECTED_MESH_BINARY_SHA256 = "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659"
EXPECTED_HOURS = (-12, -11, -10, -9, -8)
OPENING_RECORDS = (
    (0.0, "barrage-closed"),
    (0.5, "direct-reference-50"),
    (1.0, "barrage-open"),
)
FIELD_KEYS = ("waterDepthM", "velocityUms", "velocityVms")
CELL_COUNT = 50199


class BuildError(RuntimeError):
    """A source record is missing, changed, or unsafe."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"JSON input is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildError(f"invalid JSON input {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def safe_repo_path(repo_root: Path, value: str, label: str) -> Path:
    require(isinstance(value, str) and value, f"{label} path is missing")
    candidate = (repo_root / value).resolve()
    require(candidate.is_relative_to(repo_root.resolve()), f"{label} escapes the repository")
    require(candidate.is_file() and not candidate.is_symlink(), f"{label} is missing or unsafe")
    return candidate


def portable(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def load_fields(path: Path, expected_sha256: str) -> dict[str, np.ndarray]:
    require(sha256_file(path) == expected_sha256, f"source snapshot digest mismatch: {path}")
    try:
        with np.load(path, allow_pickle=False) as package:
            require(set(package.files) == set(FIELD_KEYS), f"field inventory mismatch: {path}")
            fields = {key: np.asarray(package[key]).copy() for key in FIELD_KEYS}
    except (OSError, ValueError, KeyError) as error:
        raise BuildError(f"invalid snapshot {path}: {error}") from error
    for key, values in fields.items():
        require(values.dtype == np.dtype("float64"), f"{path}:{key} is not float64")
        require(values.shape == (CELL_COUNT,), f"{path}:{key} shape mismatch")
        require(np.isfinite(values).all(), f"{path}:{key} contains a non-finite value")
    require(np.all(fields["waterDepthM"] >= 0.0), f"{path} contains negative depth")
    return fields


def snapshot_records(analysis: Mapping[str, Any]) -> dict[tuple[float, int], Mapping[str, Any]]:
    inventory = analysis.get("snapshotInventory")
    require(isinstance(inventory, dict) and inventory.get("passed") is True, "endpoint inventory did not pass")
    require(inventory.get("exactBasisHourSetMatched") is True, "endpoint inventory is incomplete")
    endpoints = inventory.get("entries")
    require(isinstance(endpoints, list) and len(endpoints) == 10, "expected ten endpoint snapshots")
    reference = analysis.get("heldOutReference")
    require(isinstance(reference, dict) and reference.get("passed") is True, "direct 50% reference did not pass")
    direct = reference.get("entries")
    require(isinstance(direct, list) and len(direct) == 5, "expected five direct 50% snapshots")
    records: dict[tuple[float, int], Mapping[str, Any]] = {}
    for item in endpoints:
        require(isinstance(item, dict), "endpoint snapshot record is invalid")
        basis = item.get("basisId")
        fraction = 0.0 if basis == "barrage-closed" else 1.0 if basis == "barrage-open" else None
        require(fraction is not None, f"unexpected endpoint basis: {basis}")
        key = (fraction, int(item["modelHour"]))
        require(key not in records, f"duplicate endpoint snapshot: {key}")
        records[key] = item
    for item in direct:
        require(isinstance(item, dict), "direct snapshot record is invalid")
        key = (0.5, int(item["modelHour"]))
        require(key not in records, f"duplicate direct snapshot: {key}")
        records[key] = item
    expected = {(fraction, hour) for fraction, _ in OPENING_RECORDS for hour in EXPECTED_HOURS}
    require(set(records) == expected, "0%, 50%, and 100% snapshot coverage mismatch")
    return records


def validate_sources(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    analysis_path = repo_root / ANALYSIS_PATH
    result_path = repo_root / RESULT_PATH
    require(sha256_file(analysis_path) == EXPECTED_ANALYSIS_SHA256, "source analysis digest changed")
    require(sha256_file(result_path) == EXPECTED_RESULT_SHA256, "source result digest changed")
    analysis = load_json(analysis_path)
    result = load_json(result_path)
    require(analysis.get("schema") == ANALYSIS_SCHEMA, "source analysis schema mismatch")
    require(analysis.get("status") == "evaluated_failed_thresholds", "source analysis status mismatch")
    require(result.get("schema") == RESULT_SCHEMA, "source result schema mismatch")
    require(result.get("status") == "evidence_valid_interpolation_failed_thresholds", "source result status mismatch")
    decision = result.get("decision")
    require(isinstance(decision, dict), "source decision is missing")
    require(
        decision.get("optionA")
        == "retain_direct_50_percent_s02_as_middle_anchor_and_prepare_code_only_piecewise_0_50_50_100_interpolation_candidate",
        "source option A changed",
    )
    require(decision.get("choiceAStartsPhysicalRun") is False, "option A unexpectedly permits a physical run")
    require(decision.get("choiceAConnectsPublicSimulator") is False, "option A unexpectedly permits public connection")
    safeguards = analysis.get("safeguards")
    require(isinstance(safeguards, dict), "source safeguards are missing")
    for key in (
        "solverInvoked",
        "networkAccessAttempted",
        "automaticRetryPerformed",
        "additionalPhysicalRunPerformed",
        "publicSimulatorConnected",
        "physicalValidationClaimAllowed",
        "dailyForecastClaimAllowed",
    ):
        require(safeguards.get(key) is False, f"source safeguard {key} is not false")

    mesh_manifest_path = repo_root / MESH_MANIFEST_PATH
    mesh_manifest = load_json(mesh_manifest_path)
    require(mesh_manifest.get("schema") == "onga-stage20-browser-mesh-v2", "mesh schema mismatch")
    require(mesh_manifest.get("counts", {}).get("cells") == CELL_COUNT, "mesh cell count mismatch")
    binary_record = mesh_manifest.get("binary")
    require(isinstance(binary_record, dict), "mesh binary record is missing")
    mesh_binary = safe_repo_path(mesh_manifest_path.parent, str(binary_record.get("url")), "mesh binary")
    require(
        sha256_file(mesh_binary) == EXPECTED_MESH_BINARY_SHA256 == binary_record.get("sha256"),
        "mesh binary digest mismatch",
    )
    return analysis, result, {
        "manifest": portable(mesh_manifest_path, repo_root),
        "manifestSha256": sha256_file(mesh_manifest_path),
        "binary": portable(mesh_binary, repo_root),
        "binarySha256": EXPECTED_MESH_BINARY_SHA256,
        "cellCount": CELL_COUNT,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    require(repo_root.is_dir(), "--repo-root is not a directory")
    expected_builder = repo_root / "tools/build_stage20_barrage_piecewise_anchor_pack.py"
    require(Path(__file__).resolve() == expected_builder.resolve(), "--repo-root does not contain this builder")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir = output_dir.resolve()
    require(output_dir.is_relative_to(repo_root), "output directory must stay inside the repository")
    require(not output_dir.is_symlink(), "output directory may not be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    require(output_dir.is_dir(), "output directory is invalid")
    for name, label in (
        (args.manifest_name, "manifest name"),
        (args.binary_name, "binary name"),
    ):
        candidate_name = Path(name)
        require(
            isinstance(name, str)
            and name
            and not candidate_name.is_absolute()
            and candidate_name.name == name
            and name not in {".", ".."},
            f"{label} must be one simple basename",
        )
    require(
        args.manifest_name != args.binary_name,
        "manifest and binary names must be distinct",
    )
    manifest_path = (output_dir / args.manifest_name).resolve()
    binary_path = (output_dir / args.binary_name).resolve()
    require(
        manifest_path.parent == output_dir
        and binary_path.parent == output_dir,
        "output names must stay inside the output directory",
    )
    for path in (manifest_path, binary_path):
        require(not path.is_symlink(), f"output may not be a symlink: {path}")

    analysis, result, mesh_record = validate_sources(repo_root)
    records = snapshot_records(analysis)
    anchors = np.empty((3, len(EXPECTED_HOURS), len(FIELD_KEYS), CELL_COUNT), dtype="<f4")
    source_records: list[dict[str, Any]] = []
    max_depth_error = 0.0
    max_velocity_component_error = 0.0
    max_velocity_vector_error = 0.0
    max_velocity_vector_rmse = 0.0
    for opening_index, (fraction, basis_id) in enumerate(OPENING_RECORDS):
        for hour_index, hour in enumerate(EXPECTED_HOURS):
            source = records[(fraction, hour)]
            path = safe_repo_path(repo_root, str(source.get("path")), f"anchor {fraction}:{hour}")
            digest = str(source.get("sha256"))
            require(len(digest) == 64, f"anchor digest is invalid: {fraction}:{hour}")
            fields = load_fields(path, digest)
            for component_index, key in enumerate(FIELD_KEYS):
                anchors[opening_index, hour_index, component_index] = fields[key]
            quantized_depth = anchors[opening_index, hour_index, 0].astype(np.float64)
            quantized_u = anchors[opening_index, hour_index, 1].astype(np.float64)
            quantized_v = anchors[opening_index, hour_index, 2].astype(np.float64)
            depth_error = float(np.max(np.abs(quantized_depth - fields["waterDepthM"])))
            u_error = quantized_u - fields["velocityUms"]
            v_error = quantized_v - fields["velocityVms"]
            vector_error = np.hypot(u_error, v_error)
            component_error = float(max(np.max(np.abs(u_error)), np.max(np.abs(v_error))))
            vector_max = float(np.max(vector_error))
            vector_rmse = float(np.sqrt(np.mean(np.square(u_error) + np.square(v_error))))
            max_depth_error = max(max_depth_error, depth_error)
            max_velocity_component_error = max(max_velocity_component_error, component_error)
            max_velocity_vector_error = max(max_velocity_vector_error, vector_max)
            max_velocity_vector_rmse = max(max_velocity_vector_rmse, vector_rmse)
            source_records.append(
                {
                    "openingFraction": fraction,
                    "basisId": basis_id,
                    "modelHour": hour,
                    "path": portable(path, repo_root),
                    "byteLength": path.stat().st_size,
                    "sha256": digest,
                    "sourceDtype": "float64",
                    "packedDtype": "float32",
                    "maximumDepthAbsoluteQuantizationErrorM": depth_error,
                    "maximumVelocityComponentAbsoluteQuantizationErrorMPS": component_error,
                    "maximumVelocityVectorAbsoluteQuantizationErrorMPS": vector_max,
                    "velocityVectorQuantizationRmseMPS": vector_rmse,
                }
            )
    require(np.isfinite(anchors).all(), "packed anchors contain a non-finite value")
    require(np.all(anchors[:, :, 0, :] >= 0), "packed anchors contain negative depth")
    payload = anchors.tobytes(order="C")
    expected_length = 3 * 5 * 3 * CELL_COUNT * 4
    require(len(payload) == expected_length == 9_035_820, "packed anchor byte length mismatch")
    binary_sha = sha256_bytes(payload)
    binary_path.write_bytes(payload)
    require(sha256_file(binary_path) == binary_sha, "written binary digest mismatch")

    builder_path = Path(__file__).resolve()
    manifest = {
        "schema": PACK_SCHEMA,
        "version": "stage20-barrage-piecewise-anchor-pack-v1",
        "status": PACK_STATUS,
        "builtDate": "2026-07-17",
        "sourceDecision": {
            "path": portable(repo_root / RESULT_PATH, repo_root),
            "sha256": EXPECTED_RESULT_SHA256,
            "selectedOption": "A",
            "sourceStatement": "A（推奨）：直接計算済み50%を中間基準にし、0～50%と50～100%を分けた補間候補を作る。追加の物理計算はしません。",
        },
        "sourceAnalysis": {
            "path": portable(repo_root / ANALYSIS_PATH, repo_root),
            "sha256": EXPECTED_ANALYSIS_SHA256,
            "status": analysis["status"],
        },
        "builder": {
            "path": portable(builder_path, repo_root),
            "sha256": sha256_file(builder_path),
            "mode": "offline_existing_sealed_snapshots_only",
        },
        "mesh": mesh_record,
        "openingContract": {
            "anchorFractions": [0.0, 0.5, 1.0],
            "inputKind": "one_scalar_constant_for_all_five_hours",
            "minimum": 0.0,
            "maximum": 1.0,
            "timeVaryingScheduleAllowed": False,
            "extrapolationAllowed": False,
            "segments": [
                {
                    "id": "opening-0-to-50",
                    "range": [0.0, 0.5],
                    "formula": "F(p,h)=(1-2p)*F0(h)+2p*F50(h)",
                },
                {
                    "id": "opening-50-to-100",
                    "range": [0.5, 1.0],
                    "formula": "F(p,h)=(2-2p)*F50(h)+(2p-1)*F100(h)",
                },
            ],
            "middleAnchorRule": "p_equals_0.5_returns_the_packed_direct_50_percent_anchor_exactly",
        },
        "timeContract": {
            "anchorHours": list(EXPECTED_HOURS),
            "intervalHours": 1,
            "snapshotCount": len(EXPECTED_HOURS),
            "timeInterpolationAllowed": False,
            "timeExtrapolationAllowed": False,
            "missingHourFallbackAllowed": False,
        },
        "componentOrder": list(FIELD_KEYS),
        "arrays": {
            "anchors": {
                "dtype": "float32-le",
                "shape": [3, 5, 3, CELL_COUNT],
                "axisOrder": ["openingAnchor", "modelHour", "component", "cell"],
                "byteOffset": 0,
                "byteLength": len(payload),
                "sha256": binary_sha,
            }
        },
        "binary": {
            "url": f"./{binary_path.name}",
            "byteLength": len(payload),
            "sha256": binary_sha,
        },
        "sourceAnchors": source_records,
        "float32Quantization": {
            "maximumDepthAbsoluteErrorM": max_depth_error,
            "maximumVelocityComponentAbsoluteErrorMPS": max_velocity_component_error,
            "maximumVelocityVectorAbsoluteErrorMPS": max_velocity_vector_error,
            "maximumVelocityVectorRmseMPS": max_velocity_vector_rmse,
            "acceptanceLimits": {
                "maximumDepthAbsoluteErrorM": 1e-6,
                "maximumVelocityComponentAbsoluteErrorMPS": 5e-8,
                "maximumVelocityVectorAbsoluteErrorMPS": 5e-8,
                "maximumVelocityVectorRmseMPS": 1e-7,
            },
            "passed": (
                max_depth_error <= 1e-6
                and max_velocity_component_error <= 5e-8
                and max_velocity_vector_error <= 5e-8
                and max_velocity_vector_rmse <= 1e-7
            ),
        },
        "scope": {
            "modelHours": list(EXPECTED_HOURS),
            "boundaryInputs": {
                "M": "approved_fixed_relative_tide_trajectory_from_source_runs",
                "NDischargeM3S": 2.0,
                "ODischargeM3S": 35.0,
                "GDischargeM3S": 1.0,
            },
            "openingMustRemainConstantAcrossAllFiveHours": True,
            "supportedUse": "inactive_browser_candidate_consistency_and_visual_review_only",
            "unsupportedUses": [
                "36_hour_past12_future24_service",
                "different_tide_or_river_discharge_inputs",
                "rain_scenario_inference",
                "time_varying_barrage_operation",
                "observed_or_forecast_accuracy_claim",
            ],
        },
        "limitations": {
            "directTruthAvailableAtOpeningFractions": [0.0, 0.5, 1.0],
            "directTruthUnavailableAtOpeningFractions": [0.25, 0.75],
            "valueContinuityAtMiddleAnchor": "guaranteed_by_construction",
            "slopeContinuityAtMiddleAnchor": "not_guaranteed_and_known_to_have_a_kink",
            "physicalInterpolationAccuracyValidated": False,
        },
        "safeguards": {
            "physicalSolverInvoked": False,
            "additionalPhysicalRunPerformed": False,
            "automaticRetryPerformed": False,
            "referenceS03RunPerformed": False,
            "networkAccessAttempted": False,
            "publicSimulatorConnected": False,
            "mainMerged": False,
            "physicalValidationClaimAllowed": False,
            "forecastValidationClaimAllowed": False,
        },
    }
    require(manifest["float32Quantization"]["passed"], "float32 quantization exceeded its code-only limits")
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_payload)
    return {
        "status": PACK_STATUS,
        "manifest": portable(manifest_path, repo_root),
        "manifestSha256": sha256_bytes(manifest_payload),
        "binary": portable(binary_path, repo_root),
        "binarySha256": binary_sha,
        "binaryBytes": len(payload),
        "sourceAnchorCount": len(source_records),
        "float32Quantization": manifest["float32Quantization"],
        "physicalSolverInvoked": False,
        "publicSimulatorConnected": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--manifest-name", default=DEFAULT_MANIFEST_NAME)
    parser.add_argument("--binary-name", default=DEFAULT_BINARY_NAME)
    return parser.parse_args()


def main() -> int:
    try:
        result = build(parse_args())
    except BuildError as error:
        print(json.dumps({"status": "not_built", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception as error:
        print(
            json.dumps(
                {"status": "not_built_unexpected_error", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
