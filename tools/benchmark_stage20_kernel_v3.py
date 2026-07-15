#!/usr/bin/env python3
"""Benchmark kernel v3 against kernel v2 on a deterministic nonphysical fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

import numba
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_stage20_kernel_v2 as benchmark_v2  # noqa: E402
import stage20_shallow_water_kernel_v2 as kernel_v2  # noqa: E402
import stage20_shallow_water_kernel_v3 as kernel_v3  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_fixture(package: dict[str, np.ndarray]) -> tuple[np.ndarray, dict, dict]:
    state, fields, candidate = benchmark_v2.fixture(package)
    fields["boundaryDischargeM3S"] = {"N": 18.0, "O": 7.0, "G": 3.0}
    fields["tide"] = {
        "phaseShiftMinutes": 17.0,
        "amplitudeMultiplier": 0.7,
        "meanOffsetM": None,
    }
    fields["fishway"] = {
        "mode": "head_difference_relation_ensemble",
        "effectiveDischargeCoefficient": 0.35,
        "effectiveAreaM2": 0.12,
    }
    hours = np.arange(24, dtype=np.float64)
    curve = 0.18 * np.sin(2.0 * np.pi * hours / 24.0)
    candidate = {
        "candidateCurve": {
            "relativeAnomalyM": curve.tolist(),
            "nextDayZeroHourRelativeAnomalyM": float(curve[0]),
        }
    }
    return state, fields, candidate


def run_steps(kernel, state, fields, geometry, package, candidate, steps: int) -> dict:
    current = state.copy()
    elapsed = 0.0
    min_dt = math.inf
    max_dt = 0.0
    max_cfl = 0.0
    started = time.perf_counter()
    for _ in range(steps):
        current, dt, diagnostics = kernel.advance_one_step(
            current, elapsed, fields, geometry, package, candidate
        )
        elapsed += dt
        min_dt = min(min_dt, dt)
        max_dt = max(max_dt, dt)
        max_cfl = max(max_cfl, diagnostics["maxCfl"])
    wall = time.perf_counter() - started
    return {
        "state": current,
        "wallSeconds": wall,
        "simulatedSeconds": elapsed,
        "secondsPerStep": wall / steps,
        "minimumTimeStepSeconds": min_dt,
        "maximumTimeStepSeconds": max_dt,
        "maximumCfl": max_cfl,
        "nonFiniteValueCount": int(current.size - np.isfinite(current).sum()),
        "negativeDepthCount": int(np.sum(current[:, 0] < 0)),
    }


def public_run(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "state"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--minimum-speedup", type=float, default=5.0)
    parser.add_argument("--output", default="config/stage20_kernel_v3_synthetic_benchmark_v1.json")
    args = parser.parse_args()
    require(args.steps == 300, "sealed kernel v3 benchmark requires exactly 300 steps")
    require(3 <= args.repeats <= 9 and args.repeats % 2 == 1, "repeats must be an odd number from 3 to 9")
    require(args.minimum_speedup == 5.0, "sealed speed target is exactly 5x")

    mesh_path = Path("public/data/onga/stage20/mesh-v2.json")
    manifest, package = benchmark_v2.load_mesh(mesh_path)
    state, fields, candidate = synthetic_fixture(package)
    geometry_v2 = kernel_v2.build_solver_geometry(package)
    geometry_v3 = kernel_v3.build_solver_geometry(package)

    compilation_started = time.perf_counter()
    compiled_once = run_steps(
        kernel_v3, state, fields, geometry_v3, package, candidate, 1
    )
    compilation_and_first_step_seconds = time.perf_counter() - compilation_started
    require(compiled_once["nonFiniteValueCount"] == 0, "compiled warm-up produced non-finite values")

    # Warm both steady-state paths outside the measured repetitions.
    run_steps(kernel_v2, state, fields, geometry_v2, package, candidate, 3)
    run_steps(kernel_v3, state, fields, geometry_v3, package, candidate, 3)

    v2_runs = []
    v3_runs = []
    representative_v2 = None
    representative_v3 = None
    for repeat in range(args.repeats):
        order = (
            ((kernel_v2, geometry_v2, v2_runs), (kernel_v3, geometry_v3, v3_runs))
            if repeat % 2 == 0
            else ((kernel_v3, geometry_v3, v3_runs), (kernel_v2, geometry_v2, v2_runs))
        )
        pair = []
        for kernel, geometry, collection in order:
            result = run_steps(kernel, state, fields, geometry, package, candidate, args.steps)
            require(result["nonFiniteValueCount"] == 0, "benchmark produced non-finite values")
            require(result["negativeDepthCount"] == 0, "benchmark produced negative depth")
            collection.append(result)
            pair.append((kernel, result))
        if repeat == 0:
            for kernel, result in pair:
                if kernel is kernel_v2:
                    representative_v2 = result
                else:
                    representative_v3 = result

    require(representative_v2 is not None and representative_v3 is not None, "missing representative run")
    maximum_absolute_state_difference = float(
        np.max(np.abs(representative_v2["state"] - representative_v3["state"]))
    )
    maximum_relative_state_difference = maximum_absolute_state_difference / max(
        float(np.max(np.abs(representative_v2["state"]))), 1.0
    )
    simulated_time_difference = abs(
        representative_v2["simulatedSeconds"] - representative_v3["simulatedSeconds"]
    )
    equivalence_passed = (
        maximum_relative_state_difference <= 1e-12
        and simulated_time_difference <= 1e-12
    )
    require(equivalence_passed, "kernel v3 changed the sealed synthetic result")

    v2_wall = [result["wallSeconds"] for result in v2_runs]
    v3_wall = [result["wallSeconds"] for result in v3_runs]
    median_v2_wall = statistics.median(v2_wall)
    median_v3_wall = statistics.median(v3_wall)
    speedup = median_v2_wall / median_v3_wall
    speed_target_passed = speedup >= args.minimum_speedup
    status = (
        "passed_code_only_equivalence_and_speed_target"
        if speed_target_passed
        else "equivalence_passed_speed_target_not_met"
    )

    report = {
        "schema": "onga-stage20-kernel-v3-synthetic-benchmark-v1",
        "status": status,
        "recordedDate": "2026-07-15",
        "authorization": "config/stage20_kernel_v3_code_only_approval_v1.json",
        "platform": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "numba": numba.__version__,
            "machine": __import__("platform").machine(),
            "system": __import__("platform").system(),
        },
        "mesh": {
            "manifest": str(mesh_path),
            "binarySha256": manifest["binary"]["sha256"],
            "cells": manifest["counts"]["cells"],
            "barrageFaces": manifest["counts"]["barrageFaces"],
        },
        "fixture": {
            "description": "deterministic smooth state with synthetic nonzero M N O G barrage and fishway paths",
            "physicalBoundaryInputsUsed": False,
            "physicalTimeCampaignExecuted": False,
            "stepsPerRun": args.steps,
            "repetitionsPerKernel": args.repeats,
        },
        "compilation": {
            "compilationAndFirstStepSeconds": compilation_and_first_step_seconds,
            "excludedFromSteadyStateTiming": True,
        },
        "representativeRuns": {
            "kernelV2": public_run(representative_v2),
            "kernelV3": public_run(representative_v3),
        },
        "timing": {
            "kernelV2WallSeconds": v2_wall,
            "kernelV3WallSeconds": v3_wall,
            "kernelV2MedianWallSeconds": median_v2_wall,
            "kernelV3MedianWallSeconds": median_v3_wall,
            "kernelV3Speedup": speedup,
            "minimumSpeedupTarget": args.minimum_speedup,
            "speedTargetPassed": speed_target_passed,
        },
        "equivalence": {
            "maximumAbsoluteStateDifference": maximum_absolute_state_difference,
            "maximumRelativeStateDifference": maximum_relative_state_difference,
            "simulatedTimeDifferenceSeconds": simulated_time_difference,
            "tolerance": 1e-12,
            "passed": equivalence_passed,
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
