#!/usr/bin/env python3
"""Benchmark Stage 20 kernel v2 on a deterministic non-physical fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage19_shallow_water_kernel_v1 as reference  # noqa: E402
import stage20_shallow_water_kernel_v2 as optimized  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mesh(path: Path) -> tuple[dict, dict[str, np.ndarray]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    binary_path = path.parent / manifest["binary"]["url"]
    require(sha256(binary_path) == manifest["binary"]["sha256"], "mesh digest mismatch")
    payload = binary_path.read_bytes()
    arrays = {}
    for name, descriptor in manifest["arrays"].items():
        dtype = np.dtype("<i4") if descriptor["dtype"] == "int32" else np.dtype("u1")
        arrays[name] = np.frombuffer(
            payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])
    return manifest, arrays


def fixture(package: dict[str, np.ndarray]) -> tuple[np.ndarray, dict, dict]:
    vertices = package["vertex_local_mm"].astype(np.float64) * 1e-3
    triangles = package["triangles"].astype(np.int64)
    centres = vertices[triangles].mean(axis=1)
    span = np.maximum(centres.max(axis=0) - centres.min(axis=0), 1.0)
    normalised = (centres - centres.min(axis=0)) / span
    depth = 3.0 + 0.015 * np.sin(2.0 * np.pi * normalised[:, 0]) * np.cos(2.0 * np.pi * normalised[:, 1])
    state = np.zeros((len(triangles), 3), dtype=np.float64)
    state[:, 0] = depth
    state[:, 1] = depth * 0.012 * np.sin(2.0 * np.pi * normalised[:, 1])
    state[:, 2] = depth * 0.008 * np.cos(2.0 * np.pi * normalised[:, 0])
    fields = {
        "bedElevationM": np.full(len(triangles), -3.0, dtype=np.float64),
        "manningN": np.full(len(triangles), 0.03, dtype=np.float64),
        "barrageTransmissivity": 0.65,
        "boundaryDischargeM3S": {"N": 0.0, "O": 0.0, "G": 0.0},
        "tide": {"phaseShiftMinutes": 0.0, "amplitudeMultiplier": 1.0, "meanOffsetM": None},
        "fishway": {"mode": "disabled", "effectiveDischargeCoefficient": 0.0, "effectiveAreaM2": 0.0},
    }
    candidate = {
        "candidateCurve": {
            "relativeAnomalyM": [0.0] * 24,
            "nextDayZeroHourRelativeAnomalyM": 0.0,
        }
    }
    return state, fields, candidate


def run_steps(kernel, state, fields, geometry, package, candidate, steps: int) -> dict:
    current = state.copy()
    elapsed = 0.0
    time_steps = []
    started = time.perf_counter()
    for _ in range(steps):
        current, dt, _ = kernel.advance_one_step(
            current, elapsed, fields, geometry, package, candidate
        )
        elapsed += dt
        time_steps.append(dt)
    wall = time.perf_counter() - started
    return {
        "state": current,
        "wallSeconds": wall,
        "simulatedSeconds": elapsed,
        "secondsPerStep": wall / steps,
        "simulatedSecondsPerWallSecond": elapsed / wall,
        "minimumTimeStepSeconds": min(time_steps),
        "maximumTimeStepSeconds": max(time_steps),
        "nonFiniteValueCount": int(current.size - np.isfinite(current).sum()),
        "negativeDepthCount": int(np.sum(current[:, 0] < 0)),
    }


def public_result(value: dict) -> dict:
    return {key: item for key, item in value.items() if key != "state"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=80)
    parser.add_argument("--output", default="config/stage20_kernel_v2_synthetic_benchmark_v1.json")
    args = parser.parse_args()
    require(10 <= args.steps <= 500, "benchmark steps must be between 10 and 500")

    meshes = {}
    for version in ("v1", "v2"):
        path = Path(f"public/data/onga/stage20/mesh-{version}.json")
        manifest, package = load_mesh(path)
        state, fields, candidate = fixture(package)
        meshes[version] = {
            "path": path,
            "manifest": manifest,
            "package": package,
            "state": state,
            "fields": fields,
            "candidate": candidate,
        }

    geometries = {
        "v1-reference": reference.build_solver_geometry(meshes["v1"]["package"]),
        "v2-reference": reference.build_solver_geometry(meshes["v2"]["package"]),
        "v2-optimized": optimized.build_solver_geometry(meshes["v2"]["package"]),
    }

    # Warm the NumPy code paths before timed measurements.
    for key, kernel, version in (
        ("v1-reference", reference, "v1"),
        ("v2-reference", reference, "v2"),
        ("v2-optimized", optimized, "v2"),
    ):
        item = meshes[version]
        run_steps(kernel, item["state"], item["fields"], geometries[key], item["package"], item["candidate"], 2)

    runs = {}
    for key, kernel, version in (
        ("meshV1KernelV1", reference, "v1"),
        ("meshV2KernelV1", reference, "v2"),
        ("meshV2KernelV2", optimized, "v2"),
    ):
        item = meshes[version]
        geometry_key = "v1-reference" if key == "meshV1KernelV1" else ("v2-reference" if key == "meshV2KernelV1" else "v2-optimized")
        runs[key] = run_steps(
            kernel,
            item["state"],
            item["fields"],
            geometries[geometry_key],
            item["package"],
            item["candidate"],
            args.steps,
        )
        require(runs[key]["nonFiniteValueCount"] == 0, f"{key} produced non-finite values")
        require(runs[key]["negativeDepthCount"] == 0, f"{key} produced negative depth")

    reference_v2 = runs["meshV2KernelV1"]
    optimized_v2 = runs["meshV2KernelV2"]
    maximum_absolute_state_difference = float(np.max(np.abs(reference_v2["state"] - optimized_v2["state"])))
    maximum_relative_state_difference = maximum_absolute_state_difference / max(float(np.max(np.abs(reference_v2["state"]))), 1.0)
    require(maximum_relative_state_difference <= 1e-12, "optimized kernel changed the synthetic result")
    require(abs(reference_v2["simulatedSeconds"] - optimized_v2["simulatedSeconds"]) <= 1e-12, "optimized kernel changed simulated time")

    baseline = runs["meshV1KernelV1"]["simulatedSecondsPerWallSecond"]
    mesh_only = runs["meshV2KernelV1"]["simulatedSecondsPerWallSecond"]
    combined = runs["meshV2KernelV2"]["simulatedSecondsPerWallSecond"]
    mesh_speedup = mesh_only / baseline
    kernel_speedup = combined / mesh_only
    combined_speedup = combined / baseline
    old_pilot_estimate_seconds = 31442.69615608
    projected_seconds = old_pilot_estimate_seconds / combined_speedup

    report = {
        "schema": "onga-stage20-kernel-v2-synthetic-benchmark-v1",
        "status": "passed_nonphysical_fixture_only",
        "stepsPerRun": args.steps,
        "fixture": {
            "description": "deterministic_smooth_perturbation_zero_discharge_zero_tide_disabled_fishway",
            "physicalBoundaryInputsUsed": False,
            "physicalSolverRunAuthorized": False,
        },
        "meshes": {
            version: {
                "manifest": str(item["path"]),
                "binarySha256": item["manifest"]["binary"]["sha256"],
                "cells": item["manifest"]["counts"]["cells"],
                "minimumCellAreaM2": float(geometries[f"{version}-reference"]["areas"].min()),
            }
            for version, item in meshes.items()
        },
        "runs": {key: public_result(value) for key, value in runs.items()},
        "equivalence": {
            "maximumAbsoluteStateDifference": maximum_absolute_state_difference,
            "maximumRelativeStateDifference": maximum_relative_state_difference,
            "simulatedTimeDifferenceSeconds": abs(reference_v2["simulatedSeconds"] - optimized_v2["simulatedSeconds"]),
            "tolerance": 1e-12,
        },
        "speedup": {
            "meshV2VersusMeshV1": mesh_speedup,
            "kernelV2VersusKernelV1OnMeshV2": kernel_speedup,
            "combinedV2VersusV1": combined_speedup,
        },
        "planningProjection": {
            "source": "failed physical pilot sealed 60-second checkpoint extrapolation",
            "oldEstimatedWallSecondsFor600PhysicalSeconds": old_pilot_estimate_seconds,
            "syntheticSpeedupApplied": combined_speedup,
            "projectedWallSecondsFor600PhysicalSeconds": projected_seconds,
            "projectedWallMinutesFor600PhysicalSeconds": projected_seconds / 60.0,
            "notAnExecutedPhysicalResult": True,
            "notAGuarantee": True,
        },
        "safeguards": {
            "physicalPrecomputationExecuted": False,
            "newPhysicalPilotExecuted": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
