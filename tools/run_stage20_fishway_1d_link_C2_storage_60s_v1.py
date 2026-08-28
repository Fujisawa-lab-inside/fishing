#!/usr/bin/env python3
"""Run the bounded C2 independent-storage fishway diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

import run_stage20_fishway_internal_interface_D1_v1 as base
from stage20_fishway_1d_link_C2_storage_candidate_v1 import (
    FishwayC2StorageParameters,
    build_workspace,
    equilibrium_storage_volume_m3,
    link_step,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    ROOT
    / "config/stage20_fishway_1d_link_C2_storage_60s_plan_candidate_v1.json"
)
APPROVAL = (
    ROOT
    / "config/stage20_fishway_1d_link_C2_storage_60s_execution_approval_v1.json"
)
C2_APPROVAL = (
    ROOT / "config/stage20_fishway_1d_link_C2_storage_approval_v1.json"
)
CANDIDATE = (
    ROOT / "config/stage20_fishway_1d_link_C2_storage_candidate_v1.json"
)
MODULE = (
    ROOT / "tools/stage20_fishway_1d_link_C2_storage_candidate_v1.py"
)
C2_STATIC = (
    ROOT
    / "docs/results/stage20-fishway-1d-link-C2-storage-static-v1/"
    "static-validation.json"
)
C2_INDEPENDENT = (
    ROOT
    / "docs/results/stage20-fishway-1d-link-C2-storage-static-v1/"
    "independent-validation.json"
)
RUNNER = (
    ROOT / "tools/run_stage20_fishway_1d_link_C2_storage_60s_v1.py"
)
OUTPUT = (
    ROOT / "docs/results/stage20-fishway-1d-link-C2-storage-60s-v1"
)
PREFLIGHT = OUTPUT / "preflight-validation.json"
JOURNAL = OUTPUT / "execution-journal.json"
SUMMARY = OUTPUT / "diagnostic-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
INDEPENDENT = OUTPUT / "independent-validation.json"
MANIFEST = OUTPUT / "manifest.json"
MESH_IDS = ("formalR20", "R1C")
RUN_ARCHIVES = {
    "formalR20": OUTPUT / "formal-R20-C2-storage-checkpoints.npz",
    "R1C": OUTPUT / "R1C-C2-storage-checkpoints.npz",
}
RUN_REPORTS = {
    "formalR20": OUTPUT / "formal-R20-run-report.json",
    "R1C": OUTPUT / "R1C-run-report.json",
}
FAILURE_STATES = {
    "formalR20": OUTPUT / "formal-R20-failure-state.npz",
    "R1C": OUTPUT / "R1C-failure-state.npz",
}
ALL_OPEN = np.ones(8, dtype=np.float64)
TARGET_SECONDS = 60.0
CHECKPOINT_INTERVAL = 1.0
CHECKPOINT_COUNT = 61


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def add(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    observed: Any = None,
) -> None:
    row: dict[str, Any] = {
        "id": check_id,
        "status": "PASS" if passed else "FAIL",
    }
    if observed is not None:
        row["observed"] = observed
    checks.append(row)


def parameters() -> FishwayC2StorageParameters:
    p = read_json(CANDIDATE)[
        "diagnosticPriorsNotPhysicalCalibration"
    ]
    return FishwayC2StorageParameters(
        basal_discharge_m3_s=p["basalDischargeM3S"],
        head_sqrt_gain_m2p5_s=p["headSqrtGainM2p5S"],
        maximum_discharge_m3_s=p["maximumDischargeM3S"],
        adverse_head_shutdown_m=p["adverseHeadShutdownM"],
        storage_area_m2=p["storageAreaM2"],
        residence_time_s=p["residenceTimeS"],
        local_invert_datum_m=p["localInvertDatumM"],
        reserve_depth_m=p["reserveDepthM"],
        maximum_available_volume_fraction_per_step=p[
            "maximumAvailableVolumeFractionPerStep"
        ],
    )


def protected_paths() -> dict[Path, str]:
    result: dict[Path, str] = {}
    for document in (PLAN, APPROVAL):
        data = read_json(document)
        for item in data["bindings"].values():
            result[ROOT / item["path"]] = item["sha256"]
    return result


def protected_snapshot() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): sha256(path)
        for path in protected_paths()
    }


def attempted_mesh_ids() -> list[str]:
    return [
        mesh_id
        for mesh_id in MESH_IDS
        if RUN_ARCHIVES[mesh_id].is_file()
        and RUN_REPORTS[mesh_id].is_file()
    ]


def C2_workspace(
    geometry: dict[str, np.ndarray],
    p2: tuple[np.ndarray, np.ndarray],
) -> Any:
    markers = geometry["internalMarkers"]
    structure = (markers == 200) | (
        (markers >= 101) & (markers <= 108)
    )
    return build_workspace(
        geometry["areas"],
        geometry["left"],
        geometry["right"],
        structure,
        p2[0],
        p2[1],
    )


def preflight() -> dict[str, Any]:
    plan = read_json(PLAN)
    approval = read_json(APPROVAL)
    c2_approval = read_json(C2_APPROVAL)
    checks: list[dict[str, Any]] = []
    add(
        checks,
        "C2_and_bounded_execution_are_authorized",
        c2_approval["userEvidence"]["text"] == "承認する"
        and approval["status"]
        == "authorized_under_explicit_C2_approval_and_bounded_diagnostic_delegation"
        and approval["userEvidence"]["C2ApprovalText"] == "承認する"
        and approval["authorizedScope"]["maximumNewSolverRunCount"] == 2,
    )
    scope = approval["authorizedScope"]
    add(
        checks,
        "scope_is_exactly_two_conditional_60s_runs",
        scope["meshIdsInRequiredOrder"] == list(MESH_IDS)
        and scope["formalR20MustPassBeforeR1C"]
        and scope["runCountPerMesh"] == 1
        and scope["initialAbsoluteTimeS"] == 5300
        and scope["finalAbsoluteTimeS"] == 5360
        and scope["physicalSecondsPerMesh"] == 60
        and scope["checkpointIntervalS"] == 1
        and scope["checkpointCountIncludingInitial"] == 61,
        scope,
    )
    p = plan["diagnosticPriorsNotPhysicalCalibration"]
    add(
        checks,
        "geometry_solver_P2_safety_and_2D_bathymetry_are_frozen",
        scope[
            "existingSolverKernelGeometryMeshP2SafetyAnd2DBathymetryModified"
        ]
        is False
        and p["reserveDepthM"] == 0.05
        and p["maximumAvailableVolumeFractionPerStep"] == 0.02
        and p["physicalDefault"] is False
        and p["calibrated"] is False
        and plan["execution"]["operatorOrderClassification"]
        == "diagnostic_candidate_not_production_integration",
        p,
    )
    rows = []
    for name, item in approval["bindings"].items():
        path = ROOT / item["path"]
        actual = sha256(path) if path.is_file() else None
        rows.append(
            {
                "name": name,
                "expected": item["sha256"],
                "actual": actual,
                "passed": actual == item["sha256"],
            }
        )
    add(
        checks,
        "all_execution_bindings_match",
        all(row["passed"] for row in rows),
        rows,
    )
    static = read_json(C2_STATIC)
    independent = read_json(C2_INDEPENDENT)
    add(
        checks,
        "unconnected_C2_static_and_independent_validations_pass",
        static["status"] == "PASS"
        and static["passedCount"] == static["checkCount"] == 31
        and independent["status"] == "PASS"
        and independent["passedCount"]
        == independent["checkCount"]
        == 16
        and static["newSolverRunCount"] == 0
        and static["candidateConnectedToSolver"] is False,
        {
            "static": [
                static["status"],
                static["passedCount"],
                static["checkCount"],
            ],
            "independent": [
                independent["status"],
                independent["passedCount"],
                independent["checkCount"],
            ],
        },
    )
    initial_rows: dict[str, Any] = {}
    for mesh_id, state in base.load_initial_states().items():
        context = base.e1.load_context(mesh_id, state)
        bed = context[1]
        geometry = context[3]
        p2 = context[4]
        workspace = C2_workspace(geometry, p2)
        storage = equilibrium_storage_volume_m3(
            state, bed, workspace, parameters()
        )
        row = link_step(
            state,
            bed,
            workspace,
            parameters(),
            0.01,
            storage,
        )["diagnostics"]
        initial_rows[mesh_id] = {
            "P2DepthM": row[
                "upstreamP2OverlapWeighted2DDepthM"
            ],
            "headDifferenceM": row["headDifferenceM"],
            "inflowM3S": row["inflowM3S"],
            "outflowM3S": row["outflowM3S"],
            "storageDepthM": row["storageDepthBeforeM"],
            "upstreamComponentCellCount": row[
                "upstreamHydraulicComponentCellCount"
            ],
        }
    expected = plan["expectedInitialCondition"]
    add(
        checks,
        "both_actual_initial_states_match_the_hash_bound_audit",
        all(
            abs(
                initial_rows[mesh_id]["P2DepthM"]
                - expected[mesh_id][
                    "upstreamP2OverlapWeighted2DDepthM"
                ]
            )
            <= 1e-12
            and abs(
                initial_rows[mesh_id]["inflowM3S"]
                - expected[mesh_id]["initialInflowM3S"]
            )
            <= 1e-12
            and abs(
                initial_rows[mesh_id]["outflowM3S"]
                - expected[mesh_id]["initialOutflowM3S"]
            )
            <= 1e-12
            and initial_rows[mesh_id]["P2DepthM"] < 0.05
            and initial_rows[mesh_id]["inflowM3S"] > 0.0
            for mesh_id in MESH_IDS
        ),
        initial_rows,
    )
    existing = [
        str(path.relative_to(ROOT))
        for path in (
            *RUN_ARCHIVES.values(),
            *RUN_REPORTS.values(),
            *FAILURE_STATES.values(),
            JOURNAL,
            SUMMARY,
            VALIDATION,
            INDEPENDENT,
            MANIFEST,
        )
        if path.exists()
    ]
    add(
        checks,
        "no_C2_60s_solver_result_exists_before_execution",
        not existing,
        existing,
    )
    before = protected_snapshot()
    add(
        checks,
        "all_protected_inputs_match_expected_hashes",
        all(
            before[str(path.relative_to(ROOT))] == expected_hash
            for path, expected_hash in protected_paths().items()
        ),
    )
    failed = [row["id"] for row in checks if row["status"] == "FAIL"]
    result = {
        "schema": (
            "onga-stage20-fishway-1d-link-C2-storage-"
            "60s-preflight-validation-v1"
        ),
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "solverRun": False,
        "initialStateAudit": initial_rows,
        "protectedBefore": before,
        "bindings": {
            "plan": binding(PLAN),
            "approval": binding(APPROVAL),
            "C2Approval": binding(C2_APPROVAL),
            "candidate": binding(CANDIDATE),
            "module": binding(MODULE),
            "D1Kernel": binding(base.KERNEL),
            "D1Runner": binding(base.RUNNER),
            "C2Runner": binding(RUNNER),
        },
    }
    write_json(PREFLIGHT, result)
    if failed:
        raise RuntimeError(f"C2 preflight failed: {failed}")
    print(
        json.dumps(
            {
                "event": "C2_preflight_complete",
                "status": result["status"],
                "checks": result["checkCount"],
                "solverRun": False,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return result


def run_diagnostic(
    mesh_id: str,
    initial_state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    geometry: dict[str, np.ndarray],
    p2: tuple[np.ndarray, np.ndarray],
    source: dict[str, Any],
    tide_candidate: dict[str, Any],
) -> tuple[
    list[np.ndarray],
    dict[str, Any],
    dict[str, np.ndarray],
    np.ndarray | None,
]:
    state = initial_state.copy()
    params = parameters()
    mapping_workspace = base.c1.build_mapping_workspace(geometry)
    base.c1.update_mapping_workspace(mapping_workspace, ALL_OPEN)
    zero_workspace, radius_by_rank, _ = base.build_interface_context(
        geometry, p2
    )
    workspace = C2_workspace(geometry, p2)
    stored_volume = equilibrium_storage_volume_m3(
        state, bed, workspace, params
    )
    initial_stored_volume = stored_volume
    initial_absolute_time_s = 5300.0
    cfl_target = 0.12
    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    tide_clock_start = (
        float(source["contract"]["run"]["tideCurveStartHour"])
        * 3600.0
        + float(
            read_json(base.c1.short.SOURCE_REPORT)["run"][
                "simulatedSeconds"
            ]
        )
        + initial_absolute_time_s
    )
    flux_names = (
        "openLeftM3S",
        "openRightM3S",
        "wallLeftM3S",
        "wallRightM3S",
        "blendedLeftM3S",
        "blendedRightM3S",
        "leftPlusRightResidualM3S",
    )
    snapshots = [state.copy()]
    checkpoint_times = [initial_absolute_time_s]
    capacity_checkpoints = [ALL_OPEN.copy()]
    flux_checkpoints = {name: [] for name in flux_names}
    flux, mapping_exact = base.c1.record_checkpoint(
        state,
        bed,
        geometry,
        mapping_workspace,
        ALL_OPEN,
    )
    for name in flux_names:
        flux_checkpoints[name].append(flux[name].copy())
    initial_result = link_step(
        state,
        bed,
        workspace,
        params,
        0.01,
        stored_volume,
    )
    initial_diag = initial_result["diagnostics"]
    checkpoint_fields: dict[str, list[float]] = {
        "upstreamP2DepthM": [
            initial_diag["upstreamP2OverlapWeighted2DDepthM"]
        ],
        "headDifferenceM": [initial_diag["headDifferenceM"]],
        "commandM3S": [initial_diag["commandM3S"]],
        "inflowM3S": [initial_diag["inflowM3S"]],
        "outflowM3S": [initial_diag["outflowM3S"]],
        "storedVolumeM3": [stored_volume],
        "storageDepthM": [initial_diag["storageDepthBeforeM"]],
        "upstreamAvailableVolumeM3": [
            initial_diag["upstreamComponentAvailableVolumeM3"]
        ],
    }
    step_fields: dict[str, list[float]] = {
        "stepEndAbsoluteTimeS": [],
        "timeStepS": [],
        "upstreamP2DepthM": [],
        "headDifferenceM": [],
        "commandM3S": [],
        "inflowM3S": [],
        "outflowM3S": [],
        "storedVolumeBeforeM3": [],
        "storedVolumeAfterM3": [],
        "storageDepthAfterM": [],
        "upstreamAvailableVolumeM3": [],
        "maximumAvailableFractionRemoved": [],
        "extendedMassResidualM3S": [],
    }
    mapping_exact_count = int(mapping_exact)
    elapsed = 0.0
    step = 0
    next_checkpoint = CHECKPOINT_INTERVAL
    next_progress = 10.0
    initial_2d_volume = float(
        np.sum(state[:, 0] * geometry["areas"])
    )
    initial_extended_volume = initial_2d_volume + stored_volume
    expected_extended_volume = initial_extended_volume
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_source_residual = 0.0
    maximum_gate_residual = 0.0
    minimum_inflow = math.inf
    maximum_inflow = 0.0
    minimum_outflow = math.inf
    maximum_outflow = 0.0
    minimum_storage_depth = math.inf
    maximum_storage_depth = 0.0
    minimum_head = math.inf
    maximum_head = -math.inf
    minimum_p2_depth = math.inf
    maximum_p2_depth = -math.inf
    maximum_removed_fraction = 0.0
    link_available_count = 0
    graph_edge_count = 0
    failure: dict[str, Any] | None = None
    failure_state: np.ndarray | None = None
    last_diag = initial_diag
    wall_start = time.monotonic()
    print(
        json.dumps(
            {
                "event": "C2_run_started",
                "meshId": mesh_id,
                "initialAbsoluteTimeS": initial_absolute_time_s,
                "targetAbsoluteTimeS": (
                    initial_absolute_time_s + TARGET_SECONDS
                ),
                "initialInflowM3S": initial_diag["inflowM3S"],
                "initialOutflowM3S": initial_diag["outflowM3S"],
                "initialStorageDepthM": initial_diag[
                    "storageDepthBeforeM"
                ],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    while elapsed < TARGET_SECONDS - 1e-12:
        base.c1.update_mapping_workspace(mapping_workspace, ALL_OPEN)
        gate_residual, _ = base.c1._maximum_gate_mass_residual(
            state,
            bed,
            geometry["left"],
            geometry["right"],
            mapping_workspace["effectiveLengths"],
            geometry["internalNormals"],
            mapping_workspace["multipliers"],
            mapping_workspace["gateFaceIds"],
        )
        maximum_gate_residual = max(
            maximum_gate_residual, float(gate_residual)
        )
        maximum_dt = min(TARGET_SECONDS, next_checkpoint) - elapsed
        tide_target = base.s1.tide_anomaly_s1(
            tide_clock_start + elapsed,
            source["tide"],
            tide_candidate,
        )
        previous_state = state
        previous_storage = stored_volume
        try:
            (
                hydro_state,
                dt,
                cfl,
                boundary_outflow,
                zero_q,
                zero_residual,
                _,
                _,
                _,
                _,
                _,
                _,
                _,
            ) = base.d1.advance_h2_step(
                previous_state,
                bed,
                manning,
                geometry["areas"],
                geometry["inverseAreas"],
                geometry["left"],
                geometry["right"],
                mapping_workspace["effectiveLengths"],
                geometry["internalNormals"],
                mapping_workspace["multipliers"],
                geometry["boundaryCells"],
                geometry["boundaryLengths"],
                geometry["boundaryNormals"],
                geometry["boundaryTags"],
                tide_target,
                target_flux_by_tag,
                zero_workspace.donor_support_area_m2,
                zero_workspace.receiver_weights,
                zero_workspace.expansion_rank,
                radius_by_rank,
                0.0,
                base.RESERVE_DEPTH_M,
                base.MAXIMUM_AVAILABLE_FRACTION,
                base.MAXIMUM_EXPANSION_RANK,
                base.MAXIMUM_SUPPORT_RADIUS_M,
                cfl_target,
                maximum_dt,
            )
            if (
                abs(float(zero_q)) > 1e-15
                or abs(float(zero_residual)) > 1e-15
            ):
                raise ValueError(
                    "hydrodynamic substep has nonzero legacy fishway"
                )
            result = link_step(
                hydro_state,
                bed,
                workspace,
                params,
                dt,
                previous_storage,
            )
            diag = result["diagnostics"]
            next_state = hydro_state.copy()
            next_state[:, 0] = result["postSourceDepthM"]
            next_state[:, 1] += (
                dt
                * result["horizontalMomentumRateXByCell"]
                * geometry["inverseAreas"]
            )
            next_state[:, 2] += (
                dt
                * result["horizontalMomentumRateYByCell"]
                * geometry["inverseAreas"]
            )
            next_storage = float(result["nextStoredVolumeM3"])
            if not np.isfinite(next_state).all() or not np.isfinite(
                next_storage
            ):
                raise ValueError("C2 produced nonfinite state")
            if np.any(next_state[:, 0] < -1e-12):
                raise ValueError("C2 produced negative depth")
            if diag["storageDepthAfterM"] < 0.05 - 1e-12:
                raise ValueError("C2 storage reserve violated")
        except ValueError as error:
            failure_state = previous_state.copy()
            failure = {
                "category": "NUMERICAL_OR_C2_GUARD",
                "message": str(error),
                "elapsedSeconds": elapsed,
                "absoluteTimeS": initial_absolute_time_s + elapsed,
                "stepsCompletedBeforeFailure": step,
                "storedVolumeBeforeFailureM3": previous_storage,
                "stateMutationOnFailedStep": False,
                "timeStepWasReducedForFishway": False,
                "guardWasRelaxed": False,
            }
            print(
                json.dumps(
                    {
                        "event": "C2_guard_triggered",
                        "meshId": mesh_id,
                        **failure,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            break

        state = next_state
        stored_volume = next_storage
        elapsed += dt
        step += 1
        expected_extended_volume -= dt * boundary_outflow
        actual_extended_volume = (
            float(np.sum(state[:, 0] * geometry["areas"]))
            + stored_volume
        )
        maximum_mass_error = max(
            maximum_mass_error,
            abs(actual_extended_volume - expected_extended_volume)
            / max(abs(initial_extended_volume), 1.0),
        )
        maximum_cfl = max(maximum_cfl, float(cfl))
        maximum_source_residual = max(
            maximum_source_residual,
            abs(float(diag["extendedMassResidualM3S"])),
        )
        inflow = float(diag["inflowM3S"])
        outflow = float(diag["outflowM3S"])
        minimum_inflow = min(minimum_inflow, inflow)
        maximum_inflow = max(maximum_inflow, inflow)
        minimum_outflow = min(minimum_outflow, outflow)
        maximum_outflow = max(maximum_outflow, outflow)
        minimum_storage_depth = min(
            minimum_storage_depth,
            float(diag["storageDepthAfterM"]),
        )
        maximum_storage_depth = max(
            maximum_storage_depth,
            float(diag["storageDepthAfterM"]),
        )
        minimum_head = min(
            minimum_head, float(diag["headDifferenceM"])
        )
        maximum_head = max(
            maximum_head, float(diag["headDifferenceM"])
        )
        p2_depth = float(
            diag["upstreamP2OverlapWeighted2DDepthM"]
        )
        minimum_p2_depth = min(minimum_p2_depth, p2_depth)
        maximum_p2_depth = max(maximum_p2_depth, p2_depth)
        maximum_removed_fraction = max(
            maximum_removed_fraction,
            float(
                diag[
                    "maximumActualAvailableVolumeFractionRemoved"
                ]
            ),
        )
        link_available_count += int(diag["linkAvailable"])
        graph_edge_count += int(diag["graphEdgePresent"])
        step_fields["stepEndAbsoluteTimeS"].append(
            initial_absolute_time_s + elapsed
        )
        step_fields["timeStepS"].append(float(dt))
        step_fields["upstreamP2DepthM"].append(p2_depth)
        step_fields["headDifferenceM"].append(
            float(diag["headDifferenceM"])
        )
        step_fields["commandM3S"].append(
            float(diag["commandM3S"])
        )
        step_fields["inflowM3S"].append(inflow)
        step_fields["outflowM3S"].append(outflow)
        step_fields["storedVolumeBeforeM3"].append(previous_storage)
        step_fields["storedVolumeAfterM3"].append(stored_volume)
        step_fields["storageDepthAfterM"].append(
            float(diag["storageDepthAfterM"])
        )
        step_fields["upstreamAvailableVolumeM3"].append(
            float(diag["upstreamComponentAvailableVolumeM3"])
        )
        step_fields["maximumAvailableFractionRemoved"].append(
            float(
                diag[
                    "maximumActualAvailableVolumeFractionRemoved"
                ]
            )
        )
        step_fields["extendedMassResidualM3S"].append(
            float(diag["extendedMassResidualM3S"])
        )
        last_diag = diag

        if (
            elapsed >= next_checkpoint - 1e-10
            or elapsed >= TARGET_SECONDS - 1e-10
        ):
            snapshots.append(state.copy())
            checkpoint_times.append(initial_absolute_time_s + elapsed)
            capacity_checkpoints.append(ALL_OPEN.copy())
            flux, mapping_exact = base.c1.record_checkpoint(
                state,
                bed,
                geometry,
                mapping_workspace,
                ALL_OPEN,
            )
            for name in flux_names:
                flux_checkpoints[name].append(flux[name].copy())
            mapping_exact_count += int(mapping_exact)
            checkpoint_fields["upstreamP2DepthM"].append(
                float(
                    last_diag[
                        "upstreamP2OverlapWeighted2DDepthM"
                    ]
                )
            )
            checkpoint_fields["headDifferenceM"].append(
                float(last_diag["headDifferenceM"])
            )
            checkpoint_fields["commandM3S"].append(
                float(last_diag["commandM3S"])
            )
            checkpoint_fields["inflowM3S"].append(
                float(last_diag["inflowM3S"])
            )
            checkpoint_fields["outflowM3S"].append(
                float(last_diag["outflowM3S"])
            )
            checkpoint_fields["storedVolumeM3"].append(stored_volume)
            checkpoint_fields["storageDepthM"].append(
                float(last_diag["storageDepthAfterM"])
            )
            checkpoint_fields["upstreamAvailableVolumeM3"].append(
                float(
                    last_diag["upstreamComponentAvailableVolumeM3"]
                )
            )
            next_checkpoint += CHECKPOINT_INTERVAL
            if elapsed >= next_progress - 1e-10:
                print(
                    json.dumps(
                        {
                            "event": "C2_run_progress",
                            "meshId": mesh_id,
                            "absoluteTimeS": round(
                                initial_absolute_time_s + elapsed, 9
                            ),
                            "percent": round(
                                100.0 * elapsed / TARGET_SECONDS, 1
                            ),
                            "steps": step,
                            "wallSeconds": round(
                                time.monotonic() - wall_start, 3
                            ),
                            "inflowM3S": last_diag["inflowM3S"],
                            "outflowM3S": last_diag["outflowM3S"],
                            "storageDepthM": last_diag[
                                "storageDepthAfterM"
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                next_progress += 10.0

    completed = (
        failure is None and elapsed >= TARGET_SECONDS - 1e-10
    )
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(
        depth, 1e-12
    )
    report = {
        "meshId": mesh_id,
        "stageId": "C2_storage_link_5300_to_5360s",
        "classification": (
            "review_only_uncalibrated_candidate_diagnostic_"
            "not_physical_validation"
        ),
        "outcome": "COMPLETED" if completed else "GUARD_TRIGGERED",
        "initialAbsoluteTimeS": initial_absolute_time_s,
        "targetAbsoluteTimeS": initial_absolute_time_s + TARGET_SECONDS,
        "finalAbsoluteTimeS": initial_absolute_time_s + elapsed,
        "simulatedContinuationSeconds": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "recordedCheckpointCount": len(snapshots),
        "checkpointMappingIdentityAllPassed": (
            mapping_exact_count == len(snapshots)
        ),
        "maximumCfl": maximum_cfl,
        "maximumRelativeExtendedMassBalanceError": maximum_mass_error,
        "maximumAbsoluteExtendedSourceMassResidualM3SPerStep": (
            maximum_source_residual
        ),
        "maximumAbsoluteGateMassResidualM3S": maximum_gate_residual,
        "initialStoredVolumeM3": initial_stored_volume,
        "finalStoredVolumeM3": stored_volume,
        "minimumInflowM3S": minimum_inflow if step else None,
        "maximumInflowM3S": maximum_inflow,
        "minimumOutflowM3S": minimum_outflow if step else None,
        "maximumOutflowM3S": maximum_outflow,
        "minimumStorageDepthM": (
            minimum_storage_depth if step else None
        ),
        "maximumStorageDepthM": maximum_storage_depth,
        "minimumHeadDifferenceM": minimum_head if step else None,
        "maximumHeadDifferenceM": maximum_head if step else None,
        "minimumUpstreamP2DepthM": (
            minimum_p2_depth if step else None
        ),
        "maximumUpstreamP2DepthM": (
            maximum_p2_depth if step else None
        ),
        "maximumActualAvailableVolumeFractionRemoved": (
            maximum_removed_fraction
        ),
        "linkAvailableAtEveryCompletedStep": (
            link_available_count == step
        ),
        "graphEdgePresentAtEveryCompletedStep": (
            graph_edge_count == step
        ),
        "upstreamHydraulicComponentCellCount": int(
            len(workspace.upstream_component_cell_ids)
        ),
        "graphRankExpansionUsed": False,
        "fishwayDrivenTimeStepReduction": False,
        "minimumDepthM": float(np.min(depth)),
        "maximumDepthM": float(np.max(depth)),
        "maximumSpeedMPS": float(np.max(speed)),
        "negativeDepthCount": int(np.sum(depth < 0.0)),
        "nonFiniteValueCount": int(
            state.size - np.isfinite(state).sum()
        ),
        "failure": failure,
        "existingSolverOrKernelModified": False,
        "meshGeometryP2SafetyOr2DBathymetryModified": False,
        "probeParametersArePhysical": False,
    }
    hard = read_json(PLAN)["hardNumericalAcceptance"]
    hard_checks = {
        "completed60s": completed,
        "maximumCfl": report["maximumCfl"] <= hard["maximumCfl"],
        "extendedMassBalance": (
            report["maximumRelativeExtendedMassBalanceError"]
            <= hard["maximumRelativeExtendedMassBalanceError"]
        ),
        "extendedSourceResidual": (
            report[
                "maximumAbsoluteExtendedSourceMassResidualM3SPerStep"
            ]
            <= hard[
                "maximumAbsoluteExtendedSourceMassResidualM3SPerStep"
            ]
        ),
        "storageReserve": (
            report["minimumStorageDepthM"] is not None
            and report["minimumStorageDepthM"]
            >= hard["minimumStorageDepthM"] - 1e-12
        ),
        "upstream2PercentSafety": (
            report["maximumActualAvailableVolumeFractionRemoved"]
            <= hard["maximumAvailableVolumeFractionPerStep"]
        ),
        "negativeDepthCount": (
            report["negativeDepthCount"] == hard["negativeDepthCount"]
        ),
        "nonFiniteValueCount": (
            report["nonFiniteValueCount"]
            == hard["nonFiniteValueCount"]
        ),
        "all61Checkpoints": (
            completed
            and report["recordedCheckpointCount"]
            == hard["checkpointCount"]
            and report["checkpointMappingIdentityAllPassed"]
        ),
        "linkAndGraphEdgeAlwaysPresent": (
            report["linkAvailableAtEveryCompletedStep"]
            and report["graphEdgePresentAtEveryCompletedStep"]
        ),
        "inflowWithinEnvelope": (
            report["minimumInflowM3S"] is not None
            and report["minimumInflowM3S"]
            >= hard["minimumInflowM3S"]
            and report["maximumInflowM3S"]
            <= hard["maximumInflowM3S"]
        ),
        "outflowWithinEnvelope": (
            report["minimumOutflowM3S"] is not None
            and report["minimumOutflowM3S"]
            >= hard["minimumOutflowM3S"]
            and report["maximumOutflowM3S"]
            <= hard["maximumOutflowM3S"]
        ),
        "noGraphRankExpansion": not report["graphRankExpansionUsed"],
        "noFishwayDrivenTimeStepReduction": (
            not report["fishwayDrivenTimeStepReduction"]
        ),
    }
    report["hardAcceptanceChecks"] = hard_checks
    report["hardAcceptancePassed"] = all(hard_checks.values())
    fields = {
        "absoluteCheckpointTimeS": np.asarray(
            checkpoint_times, dtype=np.float64
        ),
        "capacityFractionByGateId": np.asarray(
            capacity_checkpoints, dtype=np.float64
        ),
        **{
            f"gateFlux__{name}": np.asarray(values, dtype=np.float64)
            for name, values in flux_checkpoints.items()
        },
        **{
            f"linkCheckpoint__{name}": np.asarray(
                values, dtype=np.float64
            )
            for name, values in checkpoint_fields.items()
        },
        **{
            f"linkStep__{name}": np.asarray(
                values, dtype=np.float64
            )
            for name, values in step_fields.items()
        },
    }
    print(
        json.dumps(
            {
                "event": "C2_run_finished",
                "meshId": mesh_id,
                "outcome": report["outcome"],
                "absoluteTimeS": report["finalAbsoluteTimeS"],
                "steps": step,
                "wallSeconds": round(report["wallSeconds"], 3),
                "hardAcceptancePassed": report[
                    "hardAcceptancePassed"
                ],
                "inflowRangeM3S": [
                    report["minimumInflowM3S"],
                    report["maximumInflowM3S"],
                ],
                "outflowRangeM3S": [
                    report["minimumOutflowM3S"],
                    report["maximumOutflowM3S"],
                ],
                "storageDepthRangeM": [
                    report["minimumStorageDepthM"],
                    report["maximumStorageDepthM"],
                ],
                "failure": failure,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return snapshots, report, fields, failure_state


def update_journal() -> dict[str, Any]:
    attempted = attempted_mesh_ids()
    reports = {
        mesh_id: read_json(RUN_REPORTS[mesh_id])
        for mesh_id in attempted
    }
    after = protected_snapshot()
    before = read_json(PREFLIGHT)["protectedBefore"]
    journal = {
        "schema": (
            "onga-stage20-fishway-1d-link-C2-storage-"
            "60s-execution-journal-v1"
        ),
        "version": 1,
        "status": (
            "AUTHORIZED_RUNS_FINISHED"
            if attempted == list(MESH_IDS)
            else "FORMAL_COMPLETE"
            if attempted == ["formalR20"]
            and reports["formalR20"]["outcome"] == "COMPLETED"
            and reports["formalR20"]["hardAcceptancePassed"]
            else "FORMAL_DIAGNOSTIC_STOP"
        ),
        "authorizedRunCount": 2,
        "startedRunCount": len(attempted),
        "attemptedMeshIds": attempted,
        "outcomeByMesh": {
            mesh_id: report["outcome"]
            for mesh_id, report in reports.items()
        },
        "R1CStartAllowed": (
            "formalR20" in reports
            and reports["formalR20"]["outcome"] == "COMPLETED"
            and reports["formalR20"]["hardAcceptancePassed"]
        ),
        "protectedBefore": before,
        "protectedAfter": after,
        "protectedAssetsUnchanged": before == after,
        "safeguards": {
            "thirdRunStarted": False,
            "repeatRunStarted": False,
            "runBeyond60s": False,
            "existingSolverOrKernelModified": False,
            "meshGeometryP2SafetyOr2DBathymetryModified": False,
            "fishwayDrivenTimeStepReduction": False,
            "diagnosticPriorsClaimedPhysical": False,
            "precomputationRun": False,
            "productionAdopted": False,
            "GUIOrResponsePackChanged": False,
            "publicRuntimeChanged": False,
            "mainMerged": False
        },
    }
    write_json(JOURNAL, journal)
    return journal


def execute_mesh(mesh_id: str) -> None:
    base.c1.require(PREFLIGHT.is_file(), "C2 preflight is required")
    pre = read_json(PREFLIGHT)
    base.c1.require(
        pre["status"] == "PASS"
        and pre["bindings"]["plan"]["sha256"] == sha256(PLAN)
        and pre["bindings"]["approval"]["sha256"] == sha256(APPROVAL)
        and pre["bindings"]["module"]["sha256"] == sha256(MODULE)
        and pre["bindings"]["D1Kernel"]["sha256"]
        == sha256(base.KERNEL)
        and pre["bindings"]["D1Runner"]["sha256"]
        == sha256(base.RUNNER)
        and pre["bindings"]["C2Runner"]["sha256"] == sha256(RUNNER),
        "C2 preflight or execution binding changed",
    )
    base.c1.require(mesh_id in MESH_IDS, f"unknown mesh {mesh_id}")
    base.c1.require(
        not RUN_ARCHIVES[mesh_id].exists()
        and not RUN_REPORTS[mesh_id].exists()
        and not FAILURE_STATES[mesh_id].exists(),
        f"C2 result exists for {mesh_id}; overwrite refused",
    )
    attempted = attempted_mesh_ids()
    if mesh_id == "formalR20":
        base.c1.require(
            not attempted, "formal R20 must be the first C2 run"
        )
    else:
        base.c1.require(
            attempted == ["formalR20"],
            "formal R20 must run before R1C",
        )
        formal = read_json(RUN_REPORTS["formalR20"])
        base.c1.require(
            formal["outcome"] == "COMPLETED"
            and formal["hardAcceptancePassed"],
            "formal R20 must hard-pass before R1C",
        )
    initial = base.load_initial_states()[mesh_id]
    context = base.e1.load_context(mesh_id, initial)
    snapshots, report, fields, failure_state = run_diagnostic(
        mesh_id, *context
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        RUN_ARCHIVES[mesh_id],
        state_H_HU_HV=np.stack(snapshots).astype(np.float32),
        **fields,
    )
    write_json(RUN_REPORTS[mesh_id], report)
    if failure_state is not None:
        np.savez_compressed(
            FAILURE_STATES[mesh_id],
            state_H_HU_HV=failure_state.astype(np.float32),
            absoluteTimeS=np.asarray(
                [report["finalAbsoluteTimeS"]], dtype=np.float64
            ),
        )
    journal = update_journal()
    print(
        json.dumps(
            {
                "event": "C2_mesh_saved",
                "meshId": mesh_id,
                "outcome": report["outcome"],
                "hardAcceptancePassed": report[
                    "hardAcceptancePassed"
                ],
                "startedRunCount": journal["startedRunCount"],
                "R1CStartAllowed": journal["R1CStartAllowed"],
                "archive": binding(RUN_ARCHIVES[mesh_id]),
                "report": binding(RUN_REPORTS[mesh_id]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def analyze() -> dict[str, Any]:
    base.c1.require(
        attempted_mesh_ids() == list(MESH_IDS),
        "both authorized C2 results are required",
    )
    reports = {
        mesh_id: read_json(RUN_REPORTS[mesh_id])
        for mesh_id in MESH_IDS
    }
    journal = read_json(JOURNAL)
    numerical_pass = (
        journal["protectedAssetsUnchanged"]
        and all(
            report["outcome"] == "COMPLETED"
            and report["hardAcceptancePassed"]
            for report in reports.values()
        )
    )
    summary = {
        "schema": (
            "onga-stage20-fishway-1d-link-C2-storage-"
            "60s-diagnostic-summary-v1"
        ),
        "version": 1,
        "status": "PASS" if numerical_pass else "FAIL",
        "classification": (
            "review_only_uncalibrated_candidate_diagnostic_"
            "not_physical_validation"
        ),
        "authorizedRunCount": 2,
        "startedRunCount": 2,
        "attemptedMeshIds": list(MESH_IDS),
        "numericalAcceptancePassed": numerical_pass,
        "diagnosticFinding": (
            "C2_SHORT_TERM_NUMERICAL_FEASIBILITY_ESTABLISHED"
            if numerical_pass
            else "C2_NUMERICAL_ACCEPTANCE_FAILED"
        ),
        "byMesh": {
            mesh_id: {
                key: report[key]
                for key in (
                    "simulatedContinuationSeconds",
                    "stepsCompleted",
                    "wallSeconds",
                    "minimumInflowM3S",
                    "maximumInflowM3S",
                    "minimumOutflowM3S",
                    "maximumOutflowM3S",
                    "minimumStorageDepthM",
                    "maximumStorageDepthM",
                    "minimumHeadDifferenceM",
                    "maximumHeadDifferenceM",
                    "minimumUpstreamP2DepthM",
                    "maximumUpstreamP2DepthM",
                    "maximumRelativeExtendedMassBalanceError",
                    "maximumActualAvailableVolumeFractionRemoved",
                    "negativeDepthCount",
                    "nonFiniteValueCount",
                )
            }
            for mesh_id, report in reports.items()
        },
        "protectedAssetsUnchanged": journal[
            "protectedAssetsUnchanged"
        ],
        "diagnosticPriorsArePhysical": False,
        "physicalModelAccepted": False,
        "productionAdopted": False,
        "requiredNextDecision": (
            "visual_compare_mesh_trajectories_then_decide_how_to_"
            "obtain_or_bound_physical_storage_area_residence_time_"
            "invert_and_discharge_parameters"
        ),
        "safeguards": journal["safeguards"],
    }
    write_json(SUMMARY, summary)
    checks: list[dict[str, Any]] = []
    add(
        checks,
        "authorized_order_and_count_are_exact",
        journal["attemptedMeshIds"] == list(MESH_IDS)
        and journal["startedRunCount"] == 2,
    )
    add(
        checks,
        "both_runs_complete_and_hard_pass",
        numerical_pass,
        {
            mesh_id: {
                "outcome": report["outcome"],
                "hardAcceptancePassed": report[
                    "hardAcceptancePassed"
                ],
            }
            for mesh_id, report in reports.items()
        },
    )
    add(
        checks,
        "extended_mass_CFL_depth_finite_and_storage_invariants_hold",
        all(
            report["maximumRelativeExtendedMassBalanceError"]
            <= 1e-8
            and report[
                "maximumAbsoluteExtendedSourceMassResidualM3SPerStep"
            ]
            <= 1e-12
            and report["maximumCfl"] <= 0.120000000001
            and report["minimumStorageDepthM"] >= 0.05 - 1e-12
            and report[
                "maximumActualAvailableVolumeFractionRemoved"
            ]
            <= 0.020000000001
            and report["negativeDepthCount"] == 0
            and report["nonFiniteValueCount"] == 0
            for report in reports.values()
        ),
    )
    add(
        checks,
        "C2_flow_is_positive_without_using_P2_depth_as_link_depth",
        all(
            report["minimumInflowM3S"] > 0.0
            and report["minimumOutflowM3S"] > 0.0
            and report["maximumUpstreamP2DepthM"] < 0.05
            for report in reports.values()
        ),
        summary["byMesh"],
    )
    add(
        checks,
        "no_existing_asset_guard_or_scope_change",
        journal["protectedAssetsUnchanged"]
        and not journal["safeguards"]["runBeyond60s"]
        and not journal["safeguards"]["existingSolverOrKernelModified"]
        and not journal["safeguards"][
            "meshGeometryP2SafetyOr2DBathymetryModified"
        ]
        and not journal["safeguards"]["fishwayDrivenTimeStepReduction"],
    )
    add(
        checks,
        "diagnostic_priors_remain_uncalibrated_and_not_production",
        summary["diagnosticPriorsArePhysical"] is False
        and summary["physicalModelAccepted"] is False
        and summary["productionAdopted"] is False
        and not journal["safeguards"]["precomputationRun"]
        and not journal["safeguards"]["mainMerged"],
    )
    failed = [row["id"] for row in checks if row["status"] == "FAIL"]
    validation = {
        "schema": (
            "onga-stage20-fishway-1d-link-C2-storage-"
            "60s-static-validation-v1"
        ),
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "startedSolverRunCount": 2,
    }
    write_json(VALIDATION, validation)

    independent_rows: dict[str, Any] = {}
    independent_ok = True
    for mesh_id in MESH_IDS:
        archive = base.load_npz(RUN_ARCHIVES[mesh_id])
        times = archive["absoluteCheckpointTimeS"]
        capacities = archive["capacityFractionByGateId"]
        inflow = archive["linkCheckpoint__inflowM3S"]
        outflow = archive["linkCheckpoint__outflowM3S"]
        storage = archive["linkCheckpoint__storedVolumeM3"]
        storage_depth = archive["linkCheckpoint__storageDepthM"]
        row = {
            "checkpointCount": int(len(times)),
            "initialTimeS": float(times[0]),
            "finalTimeS": float(times[-1]),
            "allEightGatesOpenAtAllCheckpoints": bool(
                np.array_equal(capacities, np.ones_like(capacities))
            ),
            "minimumInflowM3S": float(np.min(inflow)),
            "maximumInflowM3S": float(np.max(inflow)),
            "minimumOutflowM3S": float(np.min(outflow)),
            "maximumOutflowM3S": float(np.max(outflow)),
            "minimumStorageDepthM": float(np.min(storage_depth)),
            "maximumStorageDepthM": float(np.max(storage_depth)),
            "maximumDiscreteStorageIdentityErrorM3": float(
                np.max(
                    np.abs(
                        np.diff(storage)
                        - np.asarray(
                            [
                                np.sum(
                                    archive["linkStep__timeStepS"][
                                        (
                                            archive[
                                                "linkStep__stepEndAbsoluteTimeS"
                                            ]
                                            > times[index] + 1e-12
                                        )
                                        & (
                                            archive[
                                                "linkStep__stepEndAbsoluteTimeS"
                                            ]
                                            <= times[index + 1] + 1e-12
                                        )
                                    ]
                                    * (
                                        archive["linkStep__inflowM3S"][
                                            (
                                                archive[
                                                    "linkStep__stepEndAbsoluteTimeS"
                                                ]
                                                > times[index] + 1e-12
                                            )
                                            & (
                                                archive[
                                                    "linkStep__stepEndAbsoluteTimeS"
                                                ]
                                                <= times[index + 1]
                                                + 1e-12
                                            )
                                        ]
                                        - archive["linkStep__outflowM3S"][
                                            (
                                                archive[
                                                    "linkStep__stepEndAbsoluteTimeS"
                                                ]
                                                > times[index] + 1e-12
                                            )
                                            & (
                                                archive[
                                                    "linkStep__stepEndAbsoluteTimeS"
                                                ]
                                                <= times[index + 1]
                                                + 1e-12
                                            )
                                        ]
                                    )
                                )
                                for index in range(len(times) - 1)
                            ],
                            dtype=np.float64,
                        )
                    )
                )
            ),
        }
        independent_rows[mesh_id] = row
        independent_ok &= (
            row["checkpointCount"] == 61
            and row["initialTimeS"] == 5300.0
            and row["finalTimeS"] == 5360.0
            and row["allEightGatesOpenAtAllCheckpoints"]
            and row["minimumInflowM3S"] > 0.0
            and row["minimumOutflowM3S"] > 0.0
            and row["minimumStorageDepthM"] >= 0.05
            and row["maximumDiscreteStorageIdentityErrorM3"] <= 1e-10
        )
    independent = {
        "schema": (
            "onga-stage20-fishway-1d-link-C2-storage-"
            "60s-independent-validation-v1"
        ),
        "version": 1,
        "status": (
            "PASS"
            if independent_ok and journal["protectedAssetsUnchanged"]
            else "FAIL"
        ),
        "method": (
            "direct_NPZ_time_gate_inflow_outflow_storage_and_"
            "discrete_storage_identity_recalculation"
        ),
        "byMesh": independent_rows,
        "protectedAssetsUnchanged": journal[
            "protectedAssetsUnchanged"
        ],
        "startedSolverRunCount": 2,
        "physicalCoefficientSelected": False,
    }
    write_json(INDEPENDENT, independent)
    files = [
        PLAN,
        APPROVAL,
        C2_APPROVAL,
        CANDIDATE,
        MODULE,
        base.KERNEL,
        base.RUNNER,
        RUNNER,
        PREFLIGHT,
        JOURNAL,
        SUMMARY,
        VALIDATION,
        INDEPENDENT,
        *RUN_ARCHIVES.values(),
        *RUN_REPORTS.values(),
    ]
    manifest = {
        "schema": (
            "onga-stage20-fishway-1d-link-C2-storage-"
            "60s-manifest-v1"
        ),
        "version": 1,
        "status": (
            "PASS"
            if not failed and independent["status"] == "PASS"
            else "FAIL"
        ),
        "files": {
            str(path.relative_to(ROOT)): binding(path)
            for path in files
        },
        "startedSolverRunCount": 2,
        "diagnosticFinding": summary["diagnosticFinding"],
        "existingSolverOrKernelModified": False,
        "meshGeometryP2SafetyOr2DBathymetryModified": False,
        "diagnosticPriorsClaimedPhysical": False,
        "precomputationRun": False,
        "productionAdopted": False,
    }
    write_json(MANIFEST, manifest)
    if failed or independent["status"] != "PASS":
        raise RuntimeError(
            f"C2 validation failed: {failed}; "
            f"independent={independent['status']}"
        )
    print(
        json.dumps(
            {
                "event": "C2_analysis_complete",
                "status": validation["status"],
                "checks": validation["checkCount"],
                "independent": independent["status"],
                "diagnosticFinding": summary["diagnosticFinding"],
                "byMesh": summary["byMesh"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--mesh", choices=MESH_IDS)
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    selected = sum(
        int(value)
        for value in (
            args.preflight_only,
            args.mesh is not None,
            args.analyze,
        )
    )
    if selected != 1:
        parser.error(
            "choose exactly one of --preflight-only, --mesh, --analyze"
        )
    if args.preflight_only:
        preflight()
    elif args.mesh:
        execute_mesh(args.mesh)
    else:
        analyze()


if __name__ == "__main__":
    main()
