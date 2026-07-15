#!/usr/bin/env python3
"""Build the execution-disabled Stage 20 36-hour segmented plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASIS = [
    ("reference", "constant", "reference", {}),
    ("tide-low", "tideAmplitudeMultiplier", "low", {"tideAmplitudeMultiplier": 0.6}),
    ("tide-high", "tideAmplitudeMultiplier", "high", {"tideAmplitudeMultiplier": 1.4}),
    ("onga-low", "ongaDischargeM3S", "low", {"ongaDischargeM3S": 5.0}),
    ("onga-high", "ongaDischargeM3S", "high", {"ongaDischargeM3S": 180.0}),
    ("nishi-low", "nishiDischargeM3S", "low", {"nishiDischargeM3S": 0.2}),
    ("nishi-high", "nishiDischargeM3S", "high", {"nishiDischargeM3S": 12.0}),
    ("magari-low", "magariDischargeM3S", "low", {"magariDischargeM3S": 0.1}),
    ("magari-high", "magariDischargeM3S", "high", {"magariDischargeM3S": 8.0}),
    ("barrage-closed", "barrageOpeningFraction", "low", {"barrageOpeningFraction": 0.0}),
    ("barrage-open", "barrageOpeningFraction", "high", {"barrageOpeningFraction": 1.0}),
]
SEGMENTS = [(-24, -16), (-16, -8), (-8, 0), (0, 8), (8, 16), (16, 24)]
REFERENCE = {
    "tideAmplitudeMultiplier": 1.0,
    "tidePhaseShiftMinutes": 0.0,
    "ongaDischargeM3S": 35.0,
    "nishiDischargeM3S": 2.0,
    "magariDischargeM3S": 1.0,
    "barrageOpeningFraction": 0.5,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_hours(start: int, end: int) -> list[int]:
    return [hour for hour in range(-12, 25) if start < hour <= end]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="config/stage20_36h_segmented_precompute_plan_v1.json")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    bases = []
    jobs = []
    for basis_id, dimension, level, overrides in BASIS:
        inputs = dict(REFERENCE)
        inputs.update(overrides)
        bases.append({
            "id": basis_id,
            "dimension": dimension,
            "level": level,
            "inputs": inputs,
            "classification": "public_range_and_declared_inference_not_observation",
        })
        for index, (start, end) in enumerate(SEGMENTS, start=1):
            job_id = f"{basis_id}-s{index:02d}"
            predecessor = None if index == 1 else f"{basis_id}-s{index - 1:02d}"
            jobs.append({
                "id": job_id,
                "basisId": basis_id,
                "segmentIndex": index,
                "modelHourStart": start,
                "modelHourEnd": end,
                "physicalSeconds": (end - start) * 3600,
                "phase": "warmup" if end <= -12 else "retained_window",
                "dependsOn": predecessor,
                "snapshotHours": snapshot_hours(start, end),
                "inputCheckpoint": None if predecessor is None else f"artifacts/{predecessor}/restart-final.npz",
                "outputCheckpoint": f"artifacts/{job_id}/restart-final.npz",
                "evidenceManifest": f"artifacts/{job_id}/evidence-manifest.json",
            })

    plan = {
        "schema": "onga-stage20-36h-segmented-precompute-plan-v1",
        "status": "detailed_candidate_execution_disabled_awaiting_canary_decision",
        "recordedDate": "2026-07-15",
        "approval": {
            "path": "config/stage20_kernel_v3_segmented_plan_approval_v1.json",
            "sha256": sha256(root / "config/stage20_kernel_v3_segmented_plan_approval_v1.json"),
        },
        "identity": {
            "meshManifest": "public/data/onga/stage20/mesh-v2.json",
            "meshBinarySha256": "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659",
            "cellCount": 50199,
            "kernel": "tools/stage20_shallow_water_kernel_v3.py",
            "kernelSha256": sha256(root / "tools/stage20_shallow_water_kernel_v3.py"),
            "physicalPilotResult": "config/stage20_kernel_v3_physical_pilot_result_v1.json",
            "physicalPilotResultSha256": sha256(root / "config/stage20_kernel_v3_physical_pilot_result_v1.json"),
        },
        "fixedPhysics": {
            "bathymetry": {"sigma": 0.36, "mainstemMeanDepthM": 4.0, "tributaryMeanDepthM": 1.8},
            "roughness": {"manningOpenChannel": 0.03, "shallowMarginMultiplier": 1.25, "structureVicinityMultiplier": 1.15},
            "barrageEffectiveDischargeCoefficient": 0.65,
            "fishway": {"mode": "head_difference_relation_ensemble", "effectiveDischargeCoefficient": 0.6, "effectiveAreaM2": 1.0},
        },
        "inputEvidence": {
            "ranges": {"path": "config/stage19_inferred_scenario_ranges_v1.json", "sha256": sha256(root / "config/stage19_inferred_scenario_ranges_v1.json")},
            "tide": {"path": "config/stage19_m_boundary_tide_candidate_v1.json", "sha256": sha256(root / "config/stage19_m_boundary_tide_candidate_v1.json"), "curveRule": "repeat_the_approved_mean_removed_24_hour_curve_with_piecewise_linear_interpolation"},
            "absoluteMouthLevelAssigned": False,
        },
        "target": {
            "requestedWindow": {"startHour": -12, "endHour": 24, "displayIntervalHours": 1, "snapshotCount": 37},
            "modeledWindow": {"startHour": -24, "endHour": 24, "physicalHours": 48},
            "warmupHours": 12,
            "warmupPurpose": "avoid_presenting_a_cold_start_as_the_requested_past_12_hours",
        },
        "basisCount": len(bases),
        "bases": bases,
        "segmentContract": {
            "segmentPhysicalHours": 8,
            "segmentsPerBasis": len(SEGMENTS),
            "totalSegments": len(jobs),
            "segmentBoundariesModelHours": [-24, -16, -8, 0, 8, 16, 24],
            "maximumWallSecondsPerSegment": 18000,
            "githubJobTimeoutMinutes": 330,
            "projectedWallSecondsPerEightHourSegment": 14601.589940062682,
            "projectedWallMarginSeconds": 3398.410059937318,
            "projectionIsGuarantee": False,
        },
        "resourceProjection": {
            "provider": "GitHub-hosted standard Linux x86_64 runner",
            "repositoryVisibilityChecked": "PUBLIC",
            "runnerLabel": "ubuntu-latest",
            "githubDefaultJobTimeoutMinutes": 360,
            "plannedJobTimeoutMinutes": 330,
            "oneBasisRunnerHours": 24.3359832334378,
            "allElevenRunnerHours": 267.6958155678159,
            "idealElevenChainElapsedHours": 24.3359832334378,
            "totalSegments": len(jobs),
            "queueSetupTransferRestartAndFailureOverheadExcluded": True,
            "githubTermsAndLimitsMayChange": True,
        },
        "jobs": jobs,
        "checkpointContract": {
            "stateDtype": "float64",
            "requiredArrays": ["state", "elapsed_seconds", "step", "expected_volume_m3", "maximum_cfl", "maximum_mass_error"],
            "atomicWriteRequired": True,
            "sha256Required": True,
            "predecessorDigestMatchRequired": True,
            "crossBasisCheckpointForbidden": True,
            "corruptOrMissingCheckpointAction": "stop_without_numerical_step",
        },
        "snapshotContract": {
            "retainedHours": list(range(-12, 25)),
            "fieldDtype": "float64",
            "componentOrder": ["waterDepthM", "velocityUms", "velocityVms"],
            "browserFloat32ConversionAllowedOnlyAfterQuantizationErrorValidation": True,
            "duplicateOrMissingHourAction": "reject_basis_output",
        },
        "acceptancePerSegment": {
            "maximumCfl": 0.95,
            "maximumRelativeMassBalanceError": 1e-8,
            "nonFiniteValueCount": 0,
            "negativeDepthCount": 0,
            "targetPhysicalSecondsRequired": True,
            "evidenceManifestRequired": True,
        },
        "failurePolicy": {
            "matrixFailFast": True,
            "downstreamSegmentRunsAfterPredecessorFailure": False,
            "automaticRetryAllowed": False,
            "automaticResumeAllowed": False,
            "partialBasisPublished": False,
            "newVisualAuthorizationRequiredForAnyRetryOrResume": True,
        },
        "artifactContract": {
            "perSegment": ["execution-receipt.json", "progress.json", "segment-report.json", "restart-final.npz", "hourly-fields.npz", "evidence-manifest.json"],
            "githubRetentionDays": 90,
            "downloadAndDigestVerifyBeforeExpiry": True,
            "permanentResultRecordRequiredBeforeBrowserUse": True,
        },
        "modelLimitations": {
            "anchorTrajectoriesAreNotPhysicalValidation": True,
            "affineBrowserSynthesisIsNotYetValidatedAgainstHeldOutPhysicalTrajectories": True,
            "heldOutFullSolverComparisonsRequiredBeforePublicConnection": True,
            "absoluteMouthLevelUnassigned": True,
            "inputsIncludeDeclaredInference": True,
        },
        "canary": {
            "jobId": "reference-s01",
            "scope": "one_reference_warmup_segment_from_model_hour_minus_24_to_minus_16",
            "physicalHours": 8,
            "projectedWallHours": 4.055997205572967,
            "maximumWallHours": 5,
            "automaticRetryAllowed": False,
            "outputs": [
                "restart_checkpoint_with_sha256",
                "complete_numerical_evidence",
                "one_diagnostic_map_at_model_hour_minus_16",
            ],
            "authorizationRequired": True,
            "currentlyAuthorized": False,
            "remainingSegmentsAuthorized": False,
        },
        "execution": {
            "physicalRunnerConnected": False,
            "workflowPresent": False,
            "authorizationPresent": False,
            "gatePresent": False,
            "physicalSegmentAuthorized": False,
            "campaignAuthorized": False,
            "automaticRetryAllowed": False,
            "paidResourceProvisioningAuthorized": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False,
        },
        "sources": [
            "https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax",
            "https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts",
            "https://docs.github.com/en/actions/reference/runners/github-hosted-runners",
        ],
    }

    output = root / args.output
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "built_execution_disabled_segmented_plan",
        "output": str(output.relative_to(root)),
        "basisCount": len(bases),
        "segmentsPerBasis": len(SEGMENTS),
        "totalSegments": len(jobs),
        "snapshotCount": len(plan["snapshotContract"]["retainedHours"]),
        "physicalSolverExecuted": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
