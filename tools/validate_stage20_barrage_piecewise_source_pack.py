#!/usr/bin/env python3
"""Independently verify the Stage 20 piecewise pack against sealed snapshots.

This validator does not trust the pack manifest to define the expected payload.
It reconstructs the complete float32 byte stream from the digest-locked
float64 0%, 50%, and 100% source snapshots recorded in the sealed holdout
analysis, then requires byte-for-byte equality with the browser candidate pack.
No solver, network access, retry, or public connection is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = Path("config/stage20_barrage_holdout_recovery_analysis_v1.json")
RESULT_PATH = Path("config/stage20_barrage_holdout_recovery_result_v1.json")
MANIFEST_PATH = Path(
    "docs/results/stage20-barrage-piecewise-candidate-v1/"
    "barrage-piecewise-anchor-pack.json"
)
BINARY_PATH = Path(
    "docs/results/stage20-barrage-piecewise-candidate-v1/"
    "barrage-piecewise-anchor-pack.bin"
)
DEFAULT_OUTPUT_PATH = Path(
    "config/stage20_barrage_piecewise_source_pack_validation_v1.json"
)
EXPECTED_ANALYSIS_SHA256 = (
    "82ce4ece4dda010b846204266e604c01d26eaffba041bd4b04329a353fc834c2"
)
EXPECTED_RESULT_SHA256 = (
    "fe4be9be3112eafff9965abc68bf254c78d560344c99cb2d5f31e1e75af519ab"
)
EXPECTED_MANIFEST_SHA256 = (
    "f5770256962268f2e6e4a1bec2a124fada55568d3e4ab0fe74269bbf3f0eecbc"
)
EXPECTED_BINARY_SHA256 = (
    "d3a0b315d7fb3bf17c04a4715b1595242b501a50dacc163ae8716013ed638047"
)
EXPECTED_MESH_SHA256 = (
    "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659"
)
EXPECTED_HOURS = (-12, -11, -10, -9, -8)
OPENINGS = (0.0, 0.5, 1.0)
COMPONENTS = ("waterDepthM", "velocityUms", "velocityVms")
CELL_COUNT = 50_199


class ValidationError(RuntimeError):
    """The candidate pack or its sealed evidence chain is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"missing JSON: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def source_path(value: object, label: str) -> Path:
    require(isinstance(value, str) and value, f"{label} path is missing")
    path = (ROOT / value).resolve()
    require(path.is_relative_to(ROOT), f"{label} path escapes repository")
    require(path.is_file() and not path.is_symlink(), f"{label} path is unsafe")
    return path


def analysis_sources(
    analysis: Mapping[str, Any],
) -> dict[tuple[float, int], Mapping[str, Any]]:
    inventory = analysis.get("snapshotInventory")
    require(
        isinstance(inventory, Mapping)
        and inventory.get("passed") is True
        and inventory.get("exactBasisHourSetMatched") is True,
        "endpoint snapshot inventory is invalid",
    )
    endpoints = inventory.get("entries")
    direct = analysis.get("heldOutReference", {}).get("entries")
    require(isinstance(endpoints, list) and len(endpoints) == 10, "endpoint count mismatch")
    require(isinstance(direct, list) and len(direct) == 5, "50% source count mismatch")
    records: dict[tuple[float, int], Mapping[str, Any]] = {}
    for record in endpoints:
        require(isinstance(record, Mapping), "endpoint source record is invalid")
        basis = record.get("basisId")
        opening = 0.0 if basis == "barrage-closed" else 1.0 if basis == "barrage-open" else None
        require(opening is not None, f"unexpected endpoint basis: {basis}")
        key = (opening, int(record["modelHour"]))
        require(key not in records, f"duplicate endpoint source: {key}")
        records[key] = record
    for record in direct:
        require(isinstance(record, Mapping), "50% source record is invalid")
        key = (0.5, int(record["modelHour"]))
        require(key not in records, f"duplicate 50% source: {key}")
        records[key] = record
    expected = {
        (opening, hour)
        for opening in OPENINGS
        for hour in EXPECTED_HOURS
    }
    require(set(records) == expected, "source opening/hour set mismatch")
    return records


def validate(args: argparse.Namespace) -> dict[str, Any]:
    require(Path(__file__).resolve().is_relative_to(ROOT), "validator is outside repository")
    analysis_file = ROOT / ANALYSIS_PATH
    result_file = ROOT / RESULT_PATH
    manifest_file = ROOT / MANIFEST_PATH
    binary_file = ROOT / BINARY_PATH
    require(sha256_file(analysis_file) == EXPECTED_ANALYSIS_SHA256, "analysis digest changed")
    require(sha256_file(result_file) == EXPECTED_RESULT_SHA256, "result digest changed")
    require(sha256_file(manifest_file) == EXPECTED_MANIFEST_SHA256, "pack manifest digest changed")
    require(sha256_file(binary_file) == EXPECTED_BINARY_SHA256, "pack binary digest changed")

    analysis = load_json(analysis_file)
    result = load_json(result_file)
    manifest = load_json(manifest_file)
    require(
        analysis.get("schema")
        == "onga-stage20-barrage-holdout-recovery-postrun-analysis-v1",
        "analysis schema mismatch",
    )
    require(analysis.get("status") == "evaluated_failed_thresholds", "analysis status mismatch")
    require(
        result.get("schema") == "onga-stage20-barrage-holdout-recovery-result-v1",
        "result schema mismatch",
    )
    require(
        result.get("decision", {}).get("optionA")
        == "retain_direct_50_percent_s02_as_middle_anchor_and_prepare_code_only_piecewise_0_50_50_100_interpolation_candidate",
        "selected source decision changed",
    )
    require(
        manifest.get("schema") == "onga-stage20-barrage-piecewise-anchor-pack-v1",
        "pack manifest schema mismatch",
    )
    require(
        manifest.get("binary", {}).get("sha256") == EXPECTED_BINARY_SHA256,
        "pack manifest binary identity mismatch",
    )
    require(
        manifest.get("mesh", {}).get("binarySha256") == EXPECTED_MESH_SHA256,
        "pack mesh identity mismatch",
    )
    require(
        manifest.get("sourceAnalysis", {}).get("sha256")
        == EXPECTED_ANALYSIS_SHA256,
        "pack source analysis identity mismatch",
    )
    require(
        manifest.get("sourceDecision", {}).get("sha256")
        == EXPECTED_RESULT_SHA256,
        "pack source decision identity mismatch",
    )

    records = analysis_sources(analysis)
    expected_anchors = np.empty(
        (len(OPENINGS), len(EXPECTED_HOURS), len(COMPONENTS), CELL_COUNT),
        dtype="<f4",
    )
    expected_manifest_sources: list[tuple[float, int, str, str, int]] = []
    maximum_depth_error = 0.0
    maximum_velocity_component_error = 0.0
    maximum_velocity_vector_error = 0.0
    maximum_velocity_vector_rmse = 0.0
    for opening_index, opening in enumerate(OPENINGS):
        for hour_index, hour in enumerate(EXPECTED_HOURS):
            record = records[(opening, hour)]
            path = source_path(record.get("path"), f"source {opening}:{hour}")
            digest = str(record.get("sha256"))
            require(sha256_file(path) == digest, f"source digest mismatch: {opening}:{hour}")
            with np.load(path, allow_pickle=False) as package:
                require(set(package.files) == set(COMPONENTS), f"component set mismatch: {path}")
                fields = {
                    component: np.asarray(package[component]).copy()
                    for component in COMPONENTS
                }
            for component, values in fields.items():
                require(values.dtype == np.dtype("float64"), f"source dtype mismatch: {path}:{component}")
                require(values.shape == (CELL_COUNT,), f"source shape mismatch: {path}:{component}")
                require(np.isfinite(values).all(), f"non-finite source: {path}:{component}")
            require(np.all(fields["waterDepthM"] >= 0.0), f"negative source depth: {path}")
            for component_index, component in enumerate(COMPONENTS):
                expected_anchors[opening_index, hour_index, component_index] = fields[component]

            packed_depth = expected_anchors[opening_index, hour_index, 0].astype(np.float64)
            packed_u = expected_anchors[opening_index, hour_index, 1].astype(np.float64)
            packed_v = expected_anchors[opening_index, hour_index, 2].astype(np.float64)
            u_error = packed_u - fields["velocityUms"]
            v_error = packed_v - fields["velocityVms"]
            vector_error = np.hypot(u_error, v_error)
            maximum_depth_error = max(
                maximum_depth_error,
                float(np.max(np.abs(packed_depth - fields["waterDepthM"]))),
            )
            maximum_velocity_component_error = max(
                maximum_velocity_component_error,
                float(max(np.max(np.abs(u_error)), np.max(np.abs(v_error)))),
            )
            maximum_velocity_vector_error = max(
                maximum_velocity_vector_error,
                float(np.max(vector_error)),
            )
            maximum_velocity_vector_rmse = max(
                maximum_velocity_vector_rmse,
                float(np.sqrt(np.mean(np.square(u_error) + np.square(v_error)))),
            )
            expected_manifest_sources.append(
                (
                    opening,
                    hour,
                    path.relative_to(ROOT).as_posix(),
                    digest,
                    path.stat().st_size,
                )
            )

    expected_payload = expected_anchors.tobytes(order="C")
    actual_payload = binary_file.read_bytes()
    require(len(expected_payload) == 9_035_820, "reconstructed payload length mismatch")
    require(actual_payload == expected_payload, "pack payload differs from source float32 reconstruction")
    require(sha256_bytes(expected_payload) == EXPECTED_BINARY_SHA256, "reconstructed payload digest mismatch")

    manifest_sources = manifest.get("sourceAnchors")
    require(isinstance(manifest_sources, list) and len(manifest_sources) == 15, "manifest source count mismatch")
    actual_manifest_sources = [
        (
            float(record["openingFraction"]),
            int(record["modelHour"]),
            str(record["path"]),
            str(record["sha256"]),
            int(record["byteLength"]),
        )
        for record in manifest_sources
    ]
    require(
        actual_manifest_sources == expected_manifest_sources,
        "manifest source inventory differs from sealed analysis",
    )

    observed_quantization = {
        "maximumDepthAbsoluteErrorM": maximum_depth_error,
        "maximumVelocityComponentAbsoluteErrorMPS": maximum_velocity_component_error,
        "maximumVelocityVectorAbsoluteErrorMPS": maximum_velocity_vector_error,
        "maximumVelocityVectorRmseMPS": maximum_velocity_vector_rmse,
    }
    manifest_quantization = manifest.get("float32Quantization", {})
    for key, value in observed_quantization.items():
        require(
            manifest_quantization.get(key) == value,
            f"quantization metric mismatch: {key}",
        )
        require(
            value <= float(manifest_quantization.get("acceptanceLimits", {}).get(key)),
            f"quantization limit failed: {key}",
        )
    require(manifest_quantization.get("passed") is True, "quantization pass flag is false")

    report = {
        "schema": "onga-stage20-barrage-piecewise-source-pack-validation-v1",
        "status": "passed_exact_source_to_pack_reconstruction_not_physical_validation",
        "validatedDate": "2026-07-17",
        "sourceAnalysis": {
            "path": ANALYSIS_PATH.as_posix(),
            "sha256": EXPECTED_ANALYSIS_SHA256,
        },
        "sourceDecision": {
            "path": RESULT_PATH.as_posix(),
            "sha256": EXPECTED_RESULT_SHA256,
            "selectedOption": "A",
        },
        "pack": {
            "manifest": MANIFEST_PATH.as_posix(),
            "manifestSha256": EXPECTED_MANIFEST_SHA256,
            "binary": BINARY_PATH.as_posix(),
            "binarySha256": EXPECTED_BINARY_SHA256,
            "binaryBytes": len(actual_payload),
            "openingFractions": list(OPENINGS),
            "modelHours": list(EXPECTED_HOURS),
            "components": list(COMPONENTS),
            "cellCount": CELL_COUNT,
        },
        "checks": {
            "sourceAnchorCount": len(expected_manifest_sources),
            "allSourceDigestsMatched": True,
            "manifestSourceInventoryMatchedAnalysis": True,
            "payloadMatchedIndependentFloat32ReconstructionByteForByte": True,
            "reconstructedPayloadSha256": sha256_bytes(expected_payload),
            "quantizationMetricsRecomputedAndMatched": True,
            "quantizationPassed": True,
        },
        "float32Quantization": observed_quantization,
        "toolchain": {
            "validator": Path(__file__).resolve().relative_to(ROOT).as_posix(),
            "validatorSha256": sha256_file(Path(__file__).resolve()),
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
    if not args.no_write:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path = output_path.resolve()
        require(output_path.is_relative_to(ROOT), "output path escapes repository")
        require(not output_path.is_symlink(), "output path is a symlink")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="validate and print the report without writing an output file",
    )
    return parser.parse_args()


def main() -> int:
    try:
        report = validate(parse_args())
    except (ValidationError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"status": "failed_source_pack_validation", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
