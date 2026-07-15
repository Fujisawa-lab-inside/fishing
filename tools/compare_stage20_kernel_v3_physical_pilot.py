#!/usr/bin/env python3
"""Compare the completed kernel v3 pilot with the retained kernel v2 pilot."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel-v2", default="docs/results/stage20-physical-pilot-v2-29396657600")
    parser.add_argument("--kernel-v3", default="docs/results/stage20-kernel-v3-physical-pilot-29411976467")
    parser.add_argument("--output", default="config/stage20_kernel_v3_physical_pilot_comparison_v1.json")
    args = parser.parse_args()
    v2_root = Path(args.kernel_v2)
    v3_root = Path(args.kernel_v3)
    v2_report = json.loads((v2_root / "pilot-report.json").read_text(encoding="utf-8"))
    v3_report = json.loads((v3_root / "pilot-report.json").read_text(encoding="utf-8"))
    v2 = np.load(v2_root / "pilot-final-fields.npz", allow_pickle=False)
    v3 = np.load(v3_root / "pilot-final-fields.npz", allow_pickle=False)

    fields = {}
    maximum_relative = 0.0
    for name in ("waterDepthM", "velocityUms", "velocityVms"):
        left = v2[name].astype(np.float64)
        right = v3[name].astype(np.float64)
        difference = np.abs(left - right)
        maximum_absolute = float(difference.max())
        maximum_relative_field = maximum_absolute / max(float(np.max(np.abs(left))), 1.0)
        maximum_relative = max(maximum_relative, maximum_relative_field)
        fields[name] = {
            "maximumAbsoluteDifference": maximum_absolute,
            "rootMeanSquareDifference": float(np.sqrt(np.mean(difference * difference))),
            "maximumRelativeDifference": maximum_relative_field,
        }

    v2_wall = float(v2_report["run"]["wallSeconds"])
    v3_wall = float(v3_report["run"]["wallSeconds"])
    speedup = v2_wall / v3_wall
    one_basis_hours = 89.55683413279073 / speedup
    eleven_basis_hours = 985.1251754606981 / speedup
    wall_per_physical = v3_wall / float(v3_report["run"]["simulatedSeconds"])
    physical_hours_per_segment = 5.0 / wall_per_physical
    segments_per_basis = math.ceil(36.0 / physical_hours_per_segment)

    result = {
        "schema": "onga-stage20-kernel-v3-physical-pilot-comparison-v1",
        "status": "passed_equivalent_physical_result_and_speedup",
        "kernelV2": {
            "runId": 29396657600,
            "wallSeconds": v2_wall,
            "steps": v2_report["run"]["stepsCompleted"],
            "simulatedSeconds": v2_report["run"]["simulatedSeconds"],
        },
        "kernelV3": {
            "runId": 29411976467,
            "wallSeconds": v3_wall,
            "steps": v3_report["run"]["stepsCompleted"],
            "simulatedSeconds": v3_report["run"]["simulatedSeconds"],
        },
        "equivalence": {
            "fields": fields,
            "maximumRelativeDifferenceAcrossFields": maximum_relative,
            "stepCountDifference": v3_report["run"]["stepsCompleted"] - v2_report["run"]["stepsCompleted"],
            "simulatedTimeDifferenceSeconds": v3_report["run"]["simulatedSeconds"] - v2_report["run"]["simulatedSeconds"],
            "maximumCflDifference": v3_report["diagnostics"]["maximumCfl"] - v2_report["diagnostics"]["maximumCfl"],
            "maximumMassErrorDifference": v3_report["diagnostics"]["maximumRelativeMassBalanceError"] - v2_report["diagnostics"]["maximumRelativeMassBalanceError"],
            "correctedMapJpegsByteIdentical": all(
                (v2_root / "maps" / name).read_bytes() == (v3_root / "maps" / name).read_bytes()
                for name in ("pilot-estuary.jpg", "pilot-barrage.jpg", "pilot-confluence.jpg", "pilot-fishway.jpg")
            ),
        },
        "speed": {
            "physicalPilotSpeedup": speedup,
            "wallTimeReductionPercent": (1.0 - v3_wall / v2_wall) * 100.0,
        },
        "updated36HourProjection": {
            "oneBasisRunnerHours": one_basis_hours,
            "allElevenRunnerHours": eleven_basis_hours,
            "physicalHoursPerFiveHourSegment": physical_hours_per_segment,
            "segmentsPerBasis": segments_per_basis,
            "totalSegments": segments_per_basis * 11,
            "idealElevenChainElapsedHours": one_basis_hours,
            "notAnExecuted36HourResult": True,
            "queueSetupTransferAndCheckpointOverheadExcluded": True,
        },
        "safeguards": {
            "additionalPhysicalRunAuthorized": False,
            "elevenBasisCampaignAuthorized": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False,
            "physicalValidationClaimAllowed": False,
        },
    }
    if maximum_relative > 1e-12:
        raise RuntimeError("kernel v3 physical state differs from kernel v2 beyond tolerance")
    if not result["equivalence"]["correctedMapJpegsByteIdentical"]:
        raise RuntimeError("corrected v2 and v3 maps differ")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
