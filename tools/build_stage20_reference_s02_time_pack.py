#!/usr/bin/env python3
"""Build an inactive time-indexed browser comparison pack from exact S02 snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--result-root", default="docs/results/stage20-reference-s02-29434250546")
    parser.add_argument("--output-dir", default="docs/results/stage20-reference-s02-29434250546/browser-comparison")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    result_root = root / args.result_root
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads((result_root / "segment-report.json").read_text(encoding="utf-8"))
    hours = []
    arrays = []
    sources = []
    quantization = []
    for record in report["outputs"]["snapshots"]:
        source = result_root / record["path"]
        with np.load(source, allow_pickle=False) as fields:
            direct = np.stack((fields["waterDepthM"], fields["velocityUms"], fields["velocityVms"])).astype(np.float64)
        packed = direct.astype("<f4")
        error = packed.astype(np.float64) - direct
        quantization.append({
            "modelHour": record["modelHour"],
            "maximumAbsoluteDepthErrorM": float(np.max(np.abs(error[0]))),
            "velocityVectorRmseMPS": float(np.sqrt(np.mean(error[1] ** 2 + error[2] ** 2))),
            "maximumVelocityVectorErrorMPS": float(np.max(np.hypot(error[1], error[2]))),
        })
        hours.append(record["modelHour"])
        arrays.append(packed)
        sources.append({
            "modelHour": record["modelHour"],
            "path": str(source.relative_to(root)),
            "sha256": record["sha256"],
        })
    if hours != [-12, -11, -10, -9, -8]:
        raise RuntimeError("unexpected S02 snapshot hours")
    basis = np.stack(arrays).astype("<f4", copy=False)
    if basis.shape != (5, 3, 50199) or not np.isfinite(basis).all() or np.any(basis[:, 0] < 0):
        raise RuntimeError("invalid time-indexed basis")
    binary_path = output_dir / "reference-s02-time-pack.bin"
    binary_path.write_bytes(basis.tobytes(order="C"))
    binary_sha = sha256(binary_path)
    manifest = {
        "schema": "onga-stage20-reference-time-pack-candidate-v1",
        "version": "stage20-reference-s02-time-pack-candidate-v1",
        "status": "direct_solver_reference_candidate_not_public_simulator",
        "mesh": {
            "manifest": "public/data/onga/stage20/mesh-v2.json",
            "sha256": "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659",
            "cellCount": 50199,
        },
        "binary": {
            "url": "./reference-s02-time-pack.bin",
            "byteLength": binary_path.stat().st_size,
            "sha256": binary_sha,
        },
        "componentOrder": ["depthM", "eastVelocityMPS", "northVelocityMPS"],
        "arrays": {
            "snapshots": {
                "dtype": "float32",
                "shape": [5, 3, 50199],
                "byteOffset": 0,
                "byteLength": binary_path.stat().st_size,
                "sha256": binary_sha,
            }
        },
        "timeContract": {
            "anchorHours": hours,
            "interpolation": "piecewise_linear_between_adjacent_direct_solver_snapshots",
            "extrapolationAllowed": False,
        },
        "sources": sources,
        "float32Quantization": {
            "perSnapshot": quantization,
            "maximumAbsoluteDepthErrorM": max(item["maximumAbsoluteDepthErrorM"] for item in quantization),
            "maximumVelocityVectorRmseMPS": max(item["velocityVectorRmseMPS"] for item in quantization),
            "maximumVelocityVectorErrorMPS": max(item["maximumVelocityVectorErrorMPS"] for item in quantization),
        },
        "validationPlan": {
            "exactAnchorReconstruction": hours,
            "leaveOneHourOutTargets": [-11, -10, -9],
            "leaveOneHourOutRule": "linearly_interpolate_the_two_neighboring_direct_solver_snapshots_and_compare_to_the_held_out_snapshot",
            "testsTemporalInterpolationOnly": True,
            "testsCrossConditionInterpolation": False,
        },
        "safeguards": {
            "additionalPhysicalRunPerformed": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False,
            "physicalValidationClaimAllowed": False,
            "dailyForecastClaimAllowed": False,
        },
    }
    manifest_path = output_dir / "reference-s02-time-pack.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path.relative_to(root)),
        "manifestSha256": sha256(manifest_path),
        "binary": str(binary_path.relative_to(root)),
        "binarySha256": binary_sha,
        "binaryBytes": binary_path.stat().st_size,
        "shape": list(basis.shape),
        "additionalPhysicalRunPerformed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
