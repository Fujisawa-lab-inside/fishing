#!/usr/bin/env python3
"""Run and analyze the approved bounded D1 fishway-interface diagnostic."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

import evaluate_stage20_R20_multizone_field_convergence_v1 as spatial
import run_stage20_barrage_C1_local_transition_600s_v1 as c1
import run_stage20_barrage_candidate_C_C2b_S1_all_closed_settling_v1 as s1
import run_stage20_barrage_candidate_C_R1C_E1_remaining_gate_opening_envelope_v1 as e1
import stage20_shallow_water_fishway_D1_candidate_v1 as d1
from stage20_fishway_internal_interface_v1 import (
    build_workspace,
    constant_flux_sources,
)


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = (
    ROOT
    / "config/stage20_fishway_internal_interface_D1_execution_approval_v1.json"
)
PLAN = (
    ROOT
    / "config/stage20_fishway_internal_interface_D1_60s_plan_candidate_v1.json"
)
PLAN_RESULT = (
    ROOT
    / "docs/results/stage20-fishway-internal-interface-D1-60s-plan-v1"
)
PLAN_STATIC = PLAN_RESULT / "static-validation.json"
PLAN_INDEPENDENT = PLAN_RESULT / "independent-validation.json"
PLAN_READINESS = PLAN_RESULT / "decision-readiness.json"
SCHEDULE = PLAN_RESULT / "operation-schedule.npz"
SOURCE_OUTPUT = (
    ROOT
    / "docs/results/stage20-barrage-candidate-C-R1C-E1-S1-all-open-settling-v1"
)
SOURCE_ARCHIVES = {
    "formalR20": SOURCE_OUTPUT / "formal-R20-settling-checkpoints.npz",
    "R1C": SOURCE_OUTPUT / "R1C-settling-checkpoints.npz",
}
OUTPUT = (
    ROOT
    / "docs/results/stage20-fishway-internal-interface-D1-60s-v1"
)
PREFLIGHT = OUTPUT / "preflight-validation.json"
JOURNAL = OUTPUT / "execution-journal.json"
RUN_ARCHIVES = {
    "formalR20": OUTPUT / "formal-R20-D1-checkpoints.npz",
    "R1C": OUTPUT / "R1C-D1-checkpoints.npz",
}
RUN_REPORTS = {
    "formalR20": OUTPUT / "formal-R20-run-report.json",
    "R1C": OUTPUT / "R1C-run-report.json",
}
SUMMARY = OUTPUT / "diagnostic-summary.json"
COMPARISON_FIELDS = OUTPUT / "comparison-fields.npz"
VALIDATION = OUTPUT / "static-validation.json"
INDEPENDENT = OUTPUT / "independent-validation.json"
MANIFEST = OUTPUT / "manifest.json"
KERNEL = ROOT / "tools/stage20_shallow_water_fishway_D1_candidate_v1.py"
RUNNER = ROOT / "tools/run_stage20_fishway_internal_interface_D1_v1.py"
STANDALONE = ROOT / "tools/stage20_fishway_internal_interface_v1.py"
HYDRO_SOURCE = (
    ROOT / "tools/run_stage20_R20_multizone_H2_dynamics_diagnostic_v1.py"
)
MESH_IDS = ("formalR20", "R1C")
ALL_OPEN = np.ones(8, dtype=np.float64)
Q0_M3_S = 0.25
RESERVE_DEPTH_M = 0.05
MAXIMUM_AVAILABLE_FRACTION = 0.02
MAXIMUM_EXPANSION_RANK = 3
MAXIMUM_SUPPORT_RADIUS_M = 12.0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {
            name: np.asarray(archive[name]).copy()
            for name in archive.files
        }


def binding(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": e1.sha256(path),
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


def protected_paths() -> dict[Path, str]:
    plan = read_json(PLAN)
    result = dict(e1.protected_paths())
    result[HYDRO_SOURCE] = d1.HYDRO_SOURCE_SHA256
    result[STANDALONE] = d1.INTERFACE_SOURCE_SHA256
    result[
        ROOT / "tools/run_stage20_barrage_C1_local_transition_600s_v1.py"
    ] = plan["bindings"]["currentHydrodynamicRunnerReference"]["sha256"]
    result[
        ROOT
        / "tools/run_stage20_barrage_candidate_C_C2b_S1_all_closed_settling_v1.py"
    ] = plan["bindings"]["currentTideFunctionReference"]["sha256"]
    return result


def load_initial_states() -> dict[str, np.ndarray]:
    states: dict[str, np.ndarray] = {}
    for mesh_id, path in SOURCE_ARCHIVES.items():
        archive = load_npz(path)
        times = archive["absoluteCheckpointTimeS"]
        capacity = archive["capacityFractionByGateId"]
        raw = archive["state_H_HU_HV"]
        c1.require(
            times.shape == (61,)
            and times[50] == 5300.0
            and raw.shape[0] == 61,
            f"{mesh_id} 5300s source endpoint changed",
        )
        c1.require(
            np.array_equal(capacity[50], ALL_OPEN),
            f"{mesh_id} 5300s source is not all-open",
        )
        promoted = raw[50].astype(np.float64)
        c1.require(
            np.array_equal(promoted.astype(np.float32), raw[50]),
            f"{mesh_id} state changed during float64 promotion",
        )
        states[mesh_id] = promoted
    return states


def build_interface_context(
    geometry: dict[str, np.ndarray],
    p2: tuple[np.ndarray, np.ndarray],
) -> tuple[Any, np.ndarray, np.ndarray]:
    markers = geometry["internalMarkers"]
    blocked = (markers == 200) | (
        (markers >= 101) & (markers <= 108)
    )
    workspace = build_workspace(
        geometry["areas"],
        geometry["left"],
        geometry["right"],
        blocked,
        p2[0],
        p2[1],
    )
    seed_centroid = np.average(
        geometry["centroids"][workspace.donor_seed_cell_ids],
        axis=0,
        weights=p2[0][workspace.donor_seed_cell_ids],
    )
    maximum_rank = int(np.max(workspace.expansion_rank))
    radius_by_rank = np.zeros(maximum_rank + 1, dtype=np.float64)
    for rank in range(maximum_rank + 1):
        selected = (
            (workspace.expansion_rank >= 0)
            & (workspace.expansion_rank <= rank)
        )
        radius_by_rank[rank] = float(
            np.max(
                np.linalg.norm(
                    geometry["centroids"][selected] - seed_centroid,
                    axis=1,
                )
            )
        )
    return workspace, radius_by_rank, seed_centroid


def preflight() -> tuple[dict[str, Any], dict[str, str]]:
    approval = read_json(APPROVAL)
    plan = read_json(PLAN)
    scope = approval["authorizedScope"]
    checks: list[dict[str, Any]] = []
    add(
        checks,
        "approval_is_exactly_two_D1_5300_to_5360s_runs",
        approval["status"]
        == "approved_dedicated_D1_kernel_runner_and_exactly_two_5300_to_5360s_runs"
        and approval["userEvidence"]["text"]
        == "推奨する方法を進めてください"
        and scope["newDedicatedFiles"]
        == [
            "tools/stage20_shallow_water_fishway_D1_candidate_v1.py",
            "tools/run_stage20_fishway_internal_interface_D1_v1.py",
        ]
        and scope["existingSolverOrRunnerFilesModified"] is False
        and scope["newSolverRunCount"] == 2
        and scope["meshIdsInRequiredOrder"] == ["formalR20", "R1C"]
        and scope["runCountPerMesh"] == 1
        and scope["initialAbsoluteTimeS"] == 5300
        and scope["finalAbsoluteTimeS"] == 5360
        and scope["physicalSecondsPerRun"] == 60
        and scope["checkpointIntervalS"] == 1
        and scope["checkpointCountPerRunIncludingInitial"] == 61
        and scope["capacityFractionByGate1To8"] == [1] * 8
        and scope["fishwayQ0M3S"] == Q0_M3_S
        and scope["fullQOrFailStop"] is True,
        scope,
    )
    binding_rows = []
    for name, item in approval["bindings"].items():
        path = ROOT / item["path"]
        actual = e1.sha256(path) if path.is_file() else None
        binding_rows.append(
            {
                "name": name,
                "expected": item["sha256"],
                "actual": actual,
                "passed": actual == item["sha256"],
            }
        )
    add(
        checks,
        "all_execution_approval_bindings_match",
        all(row["passed"] for row in binding_rows),
        binding_rows,
    )
    plan_static = read_json(PLAN_STATIC)
    plan_independent = read_json(PLAN_INDEPENDENT)
    plan_readiness = read_json(PLAN_READINESS)
    add(
        checks,
        "plan_validations_and_readiness_pass",
        plan_static["status"] == "PASS"
        and plan_static["passedCount"] == 24
        and plan_static["checkCount"] == 24
        and plan_independent["status"] == "PASS"
        and plan_independent["passedCount"] == 25
        and plan_independent["checkCount"] == 25
        and plan_readiness["status"]
        == "READY_FOR_EXPLICIT_D1_IMPLEMENTATION_AND_EXECUTION_JUDGMENT",
        {
            "static": [
                plan_static["status"],
                plan_static["passedCount"],
                plan_static["checkCount"],
            ],
            "independent": [
                plan_independent["status"],
                plan_independent["passedCount"],
                plan_independent["checkCount"],
            ],
            "readiness": plan_readiness["status"],
        },
    )
    plan_scope = plan["scope"]
    add(
        checks,
        "plan_and_approval_scopes_match",
        plan_scope["plannedNewSolverRunCount"]
        == scope["newSolverRunCount"]
        and plan_scope["meshIds"] == scope["meshIdsInRequiredOrder"]
        and plan_scope["initialAbsoluteTimeS"]
        == scope["initialAbsoluteTimeS"]
        and plan_scope["finalAbsoluteTimeS"]
        == scope["finalAbsoluteTimeS"]
        and plan_scope["physicalSecondsPerRun"]
        == scope["physicalSecondsPerRun"]
        and plan_scope["checkpointIntervalS"]
        == scope["checkpointIntervalS"]
        and plan_scope["diagnosticQ0M3S"] == scope["fishwayQ0M3S"],
        {"planScope": plan_scope, "approvalScope": scope},
    )
    schedule = load_npz(SCHEDULE)
    add(
        checks,
        "schedule_is_exact_61_all_open_Q0_0_25",
        np.array_equal(
            schedule["absolute_time_s"],
            np.arange(5300.0, 5361.0, 1.0),
        )
        and np.array_equal(
            schedule["capacity_fraction_by_gate_id"],
            np.ones((61, 8)),
        )
        and np.array_equal(
            schedule["fishway_Q0_m3_s"],
            np.full(61, Q0_M3_S),
        ),
    )
    initial = load_initial_states()
    initial_rows = {}
    initial_ok = True
    standalone_ok = True
    locality_ok = True
    for mesh_id, state in initial.items():
        context = e1.load_context(mesh_id, state)
        geometry = context[3]
        p2 = context[4]
        workspace, radius_by_rank, _ = build_interface_context(
            geometry,
            p2,
        )
        result = constant_flux_sources(
            state,
            workspace,
            Q0_M3_S,
            0.01,
            reserve_depth_m=RESERVE_DEPTH_M,
            maximum_available_volume_fraction_per_step=(
                MAXIMUM_AVAILABLE_FRACTION
            ),
        )
        diag = result["diagnostics"]
        radius = float(radius_by_rank[diag["selectedExpansionRank"]])
        initial_ok = (
            initial_ok
            and np.isfinite(state).all()
            and float(np.min(state[:, 0])) >= 0.0
        )
        standalone_ok = (
            standalone_ok
            and abs(diag["effectiveQ0M3S"] - Q0_M3_S) <= 1e-12
            and abs(diag["massResidualM3S"]) <= 1e-12
            and diag["minimumSelectedDonorPostSourceDepthM"]
            >= RESERVE_DEPTH_M - 1e-12
            and diag["maximumActualAvailableVolumeFractionRemoved"]
            <= MAXIMUM_AVAILABLE_FRACTION + 1e-12
        )
        locality_ok = (
            locality_ok
            and diag["selectedExpansionRank"] <= MAXIMUM_EXPANSION_RANK
            and radius <= MAXIMUM_SUPPORT_RADIUS_M
        )
        initial_rows[mesh_id] = {
            "shape": list(state.shape),
            "minimumDepthM": float(np.min(state[:, 0])),
            "effectiveQ0M3S": diag["effectiveQ0M3S"],
            "massResidualM3S": diag["massResidualM3S"],
            "selectedExpansionRank": diag["selectedExpansionRank"],
            "maximumSupportRadiusM": radius,
            "minimumSelectedDonorPostSourceDepthM": (
                diag["minimumSelectedDonorPostSourceDepthM"]
            ),
        }
    add(
        checks,
        "both_initial_states_are_finite_nonnegative",
        initial_ok,
        initial_rows,
    )
    add(
        checks,
        "standalone_candidate_initial_invariants_pass",
        standalone_ok,
        initial_rows,
    )
    add(
        checks,
        "initial_candidate_locality_is_bounded",
        locality_ok,
        initial_rows,
    )
    kernel_text = KERNEL.read_text(encoding="utf-8")
    add(
        checks,
        "dedicated_kernel_replaces_old_cap_and_binds_sources",
        d1.HYDRO_SOURCE_PATH
        == "tools/run_stage20_R20_multizone_H2_dynamics_diagnostic_v1.py"
        and d1.HYDRO_SOURCE_SHA256 == e1.sha256(HYDRO_SOURCE)
        and d1.INTERFACE_SOURCE_SHA256 == e1.sha256(STANDALONE)
        and "effective_q = min(" not in kernel_text
        and "fishway full-Q supply unavailable" in kernel_text
        and "fishway expansion rank guard exceeded" in kernel_text
        and "fishway support radius guard exceeded" in kernel_text,
        {
            "kernel": binding(KERNEL),
            "runner": binding(RUNNER),
            "hydroSourceSha256": e1.sha256(HYDRO_SOURCE),
            "interfaceSourceSha256": e1.sha256(STANDALONE),
        },
    )
    imported_by_existing = []
    for path in (ROOT / "tools").glob("*.py"):
        if path in (KERNEL, RUNNER):
            continue
        text = path.read_text(encoding="utf-8")
        if (
            "import stage20_shallow_water_fishway_D1_candidate_v1" in text
            or "from stage20_shallow_water_fishway_D1_candidate_v1 import"
            in text
        ):
            imported_by_existing.append(str(path.relative_to(ROOT)))
    add(
        checks,
        "candidate_kernel_is_connected_only_to_dedicated_runner",
        imported_by_existing == [],
        imported_by_existing,
    )
    protected_before: dict[str, str] = {}
    protected_rows = []
    for path, expected in protected_paths().items():
        actual = e1.sha256(path)
        protected_before[str(path.relative_to(ROOT))] = actual
        protected_rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "expected": expected,
                "actual": actual,
                "passed": actual == expected,
            }
        )
    add(
        checks,
        "all_protected_inputs_match",
        all(row["passed"] for row in protected_rows),
        protected_rows,
    )
    add(
        checks,
        "no_D1_solver_outputs_exist_before_execution",
        not any(path.exists() for path in RUN_ARCHIVES.values())
        and not any(path.exists() for path in RUN_REPORTS.values())
        and not JOURNAL.exists(),
        {
            "archives": {
                key: path.exists()
                for key, path in RUN_ARCHIVES.items()
            },
            "reports": {
                key: path.exists()
                for key, path in RUN_REPORTS.items()
            },
            "journal": JOURNAL.exists(),
        },
    )
    add(
        checks,
        "unauthorized_scopes_remain_excluded",
        {
            "a_third_mesh_or_repeat_run",
            "overwrite_of_either_authorized_run",
            "rerun_zero_to_5300",
            "E1_S1_600s_rerun",
            "modification_of_existing_solver_or_runner",
            "automatic_physical_model_acceptance",
            "production_adoption",
            "precomputation",
            "GUI_or_response_pack_change",
            "public_runtime_change",
            "main_merge",
        }
        <= set(approval["doesNotAuthorize"]),
        approval["doesNotAuthorize"],
    )
    failed = [row["id"] for row in checks if row["status"] == "FAIL"]
    result = {
        "schema": "onga-stage20-fishway-internal-interface-D1-preflight-v1",
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "bindings": {
            "approval": binding(APPROVAL),
            "plan": binding(PLAN),
            "kernel": binding(KERNEL),
            "runner": binding(RUNNER),
        },
        "protectedBefore": protected_before,
        "safeguards": {
            "preflightOnly": True,
            "newSolverRunCount": 0,
            "existingSolverModified": False,
            "precomputationRun": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
    }
    write_json(PREFLIGHT, result)
    if failed:
        raise RuntimeError(f"D1 preflight failed: {failed}")
    return result, protected_before


def run_diagnostic(
    mesh_id: str,
    initial_state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    geometry: dict[str, np.ndarray],
    p2: tuple[np.ndarray, np.ndarray],
    source: dict[str, Any],
    tide_candidate: dict[str, Any],
) -> tuple[list[np.ndarray], dict[str, Any], dict[str, np.ndarray]]:
    state = initial_state.copy()
    mapping_workspace = c1.build_mapping_workspace(geometry)
    c1.update_mapping_workspace(mapping_workspace, ALL_OPEN)
    interface_workspace, radius_by_rank, _ = build_interface_context(
        geometry,
        p2,
    )
    initial_absolute_time_s = 5300.0
    target_seconds = 60.0
    checkpoint_interval = 1.0
    checkpoint_count = 61
    cfl_target = 0.12
    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    capacity_checkpoints = np.ones(
        (checkpoint_count, 8),
        dtype=np.float64,
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
    flux_checkpoints = {
        name: np.zeros((checkpoint_count, 8), dtype=np.float64)
        for name in flux_names
    }
    relative_times = np.arange(0.0, 61.0, 1.0)
    absolute_times = initial_absolute_time_s + relative_times
    snapshots = [state.copy()]
    flux, mapping_exact = c1.record_checkpoint(
        state,
        bed,
        geometry,
        mapping_workspace,
        ALL_OPEN,
    )
    for name in flux_names:
        flux_checkpoints[name][0] = flux[name]
    mapping_exact_count = int(mapping_exact)

    elapsed = 0.0
    step = 0
    next_checkpoint_index = 1
    next_checkpoint = checkpoint_interval
    next_progress = 10.0
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_fishway_source_residual = 0.0
    maximum_gate_mass_residual = 0.0
    maximum_gate_face_mass_residual = 0.0
    minimum_effective_q = math.inf
    maximum_effective_q = 0.0
    maximum_effective_q_error = 0.0
    maximum_expansion_rank = 0
    maximum_support_radius = 0.0
    maximum_removed_fraction = 0.0
    minimum_selected_post_depth = math.inf
    maximum_independent_difference = 0.0
    independent_check_count = 0
    tide_clock_start = (
        float(source["contract"]["run"]["tideCurveStartHour"]) * 3600.0
        + float(read_json(c1.short.SOURCE_REPORT)["run"]["simulatedSeconds"])
        + initial_absolute_time_s
    )
    step_fields: dict[str, list[float]] = {
        "stepEndAbsoluteTimeS": [],
        "timeStepS": [],
        "effectiveQ0M3S": [],
        "massResidualM3S": [],
        "selectedExpansionRank": [],
        "selectedDonorCellCount": [],
        "selectedAvailableVolumeM3": [],
        "requiredAvailableVolumeM3": [],
        "maximumActualAvailableVolumeFractionRemoved": [],
        "minimumSelectedDonorPostSourceDepthM": [],
        "maximumSupportRadiusM": [],
    }
    wall_start = time.monotonic()
    print(
        json.dumps(
            {
                "event": "D1_run_started",
                "meshId": mesh_id,
                "initialAbsoluteTimeS": initial_absolute_time_s,
                "targetAbsoluteTimeS": initial_absolute_time_s + target_seconds,
                "physicalSeconds": target_seconds,
                "checkpointCount": checkpoint_count,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    while elapsed < target_seconds - 1e-12:
        c1.update_mapping_workspace(mapping_workspace, ALL_OPEN)
        gate_residual, gate_face_residual = c1._maximum_gate_mass_residual(
            state,
            bed,
            geometry["left"],
            geometry["right"],
            mapping_workspace["effectiveLengths"],
            geometry["internalNormals"],
            mapping_workspace["multipliers"],
            mapping_workspace["gateFaceIds"],
        )
        maximum_gate_mass_residual = max(
            maximum_gate_mass_residual,
            float(gate_residual),
        )
        maximum_gate_face_mass_residual = max(
            maximum_gate_face_mass_residual,
            float(gate_face_residual),
        )
        maximum_dt = min(target_seconds, next_checkpoint) - elapsed
        tide_target = s1.tide_anomaly_s1(
            tide_clock_start + elapsed,
            source["tide"],
            tide_candidate,
        )
        previous_state = state
        (
            next_state,
            dt,
            cfl,
            boundary_outflow,
            effective_q,
            fishway_source_residual,
            selected_rank,
            selected_count,
            selected_available,
            required_available,
            removed_fraction,
            selected_post_depth,
            support_radius,
        ) = d1.advance_h2_step(
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
            interface_workspace.donor_support_area_m2,
            interface_workspace.receiver_weights,
            interface_workspace.expansion_rank,
            radius_by_rank,
            Q0_M3_S,
            RESERVE_DEPTH_M,
            MAXIMUM_AVAILABLE_FRACTION,
            MAXIMUM_EXPANSION_RANK,
            MAXIMUM_SUPPORT_RADIUS_M,
            cfl_target,
            maximum_dt,
        )
        independent = constant_flux_sources(
            previous_state,
            interface_workspace,
            Q0_M3_S,
            dt,
            reserve_depth_m=RESERVE_DEPTH_M,
            maximum_available_volume_fraction_per_step=(
                MAXIMUM_AVAILABLE_FRACTION
            ),
        )
        independent_diag = independent["diagnostics"]
        differences = [
            abs(effective_q - independent_diag["effectiveQ0M3S"]),
            abs(
                fishway_source_residual
                - independent_diag["massResidualM3S"]
            ),
            abs(
                selected_available
                - independent_diag["selectedAvailableVolumeM3"]
            ),
            abs(
                required_available
                - independent_diag["requiredAvailableVolumeM3"]
            ),
            abs(
                removed_fraction
                - independent_diag[
                    "maximumActualAvailableVolumeFractionRemoved"
                ]
            ),
            abs(
                selected_post_depth
                - independent_diag[
                    "minimumSelectedDonorPostSourceDepthM"
                ]
            ),
            abs(
                support_radius
                - radius_by_rank[
                    independent_diag["selectedExpansionRank"]
                ]
            ),
            abs(
                float(selected_rank)
                - float(independent_diag["selectedExpansionRank"])
            ),
            abs(
                float(selected_count)
                - float(independent_diag["selectedDonorCellCount"])
            ),
        ]
        local_difference = max(differences)
        maximum_independent_difference = max(
            maximum_independent_difference,
            local_difference,
        )
        c1.require(
            local_difference <= 1e-10,
            f"{mesh_id} compiled and standalone fishway sources differ",
        )
        independent_check_count += 1
        state = next_state
        elapsed += dt
        step += 1
        expected_volume -= dt * boundary_outflow
        actual_volume = float(
            np.sum(state[:, 0] * geometry["areas"])
        )
        maximum_mass_error = max(
            maximum_mass_error,
            abs(actual_volume - expected_volume)
            / max(abs(initial_volume), 1.0),
        )
        maximum_cfl = max(maximum_cfl, float(cfl))
        maximum_fishway_source_residual = max(
            maximum_fishway_source_residual,
            abs(float(fishway_source_residual)),
        )
        minimum_effective_q = min(minimum_effective_q, float(effective_q))
        maximum_effective_q = max(maximum_effective_q, float(effective_q))
        maximum_effective_q_error = max(
            maximum_effective_q_error,
            abs(float(effective_q) - Q0_M3_S),
        )
        maximum_expansion_rank = max(
            maximum_expansion_rank,
            int(selected_rank),
        )
        maximum_support_radius = max(
            maximum_support_radius,
            float(support_radius),
        )
        maximum_removed_fraction = max(
            maximum_removed_fraction,
            float(removed_fraction),
        )
        minimum_selected_post_depth = min(
            minimum_selected_post_depth,
            float(selected_post_depth),
        )
        step_fields["stepEndAbsoluteTimeS"].append(
            initial_absolute_time_s + elapsed
        )
        step_fields["timeStepS"].append(float(dt))
        step_fields["effectiveQ0M3S"].append(float(effective_q))
        step_fields["massResidualM3S"].append(
            float(fishway_source_residual)
        )
        step_fields["selectedExpansionRank"].append(float(selected_rank))
        step_fields["selectedDonorCellCount"].append(float(selected_count))
        step_fields["selectedAvailableVolumeM3"].append(
            float(selected_available)
        )
        step_fields["requiredAvailableVolumeM3"].append(
            float(required_available)
        )
        step_fields[
            "maximumActualAvailableVolumeFractionRemoved"
        ].append(float(removed_fraction))
        step_fields[
            "minimumSelectedDonorPostSourceDepthM"
        ].append(float(selected_post_depth))
        step_fields["maximumSupportRadiusM"].append(float(support_radius))

        if (
            elapsed >= next_checkpoint - 1e-10
            or elapsed >= target_seconds - 1e-10
        ):
            c1.require(
                next_checkpoint_index < checkpoint_count,
                "too many D1 checkpoints",
            )
            c1.update_mapping_workspace(mapping_workspace, ALL_OPEN)
            snapshots.append(state.copy())
            flux, mapping_exact = c1.record_checkpoint(
                state,
                bed,
                geometry,
                mapping_workspace,
                ALL_OPEN,
            )
            for name in flux_names:
                flux_checkpoints[name][next_checkpoint_index] = flux[name]
            mapping_exact_count += int(mapping_exact)
            next_checkpoint_index += 1
            next_checkpoint += checkpoint_interval
            if elapsed >= next_progress - 1e-10:
                print(
                    json.dumps(
                        {
                            "event": "D1_run_progress",
                            "meshId": mesh_id,
                            "absoluteTimeS": round(
                                initial_absolute_time_s + elapsed,
                                9,
                            ),
                            "percent": round(
                                100.0 * elapsed / target_seconds,
                                1,
                            ),
                            "steps": step,
                            "wallSeconds": round(
                                time.monotonic() - wall_start,
                                3,
                            ),
                            "maximumExpansionRank": (
                                maximum_expansion_rank
                            ),
                            "maximumSupportRadiusM": (
                                maximum_support_radius
                            ),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                next_progress += 10.0
    c1.require(
        next_checkpoint_index == checkpoint_count,
        "missing D1 checkpoints",
    )
    approved = load_npz(SCHEDULE)
    c1.require(
        np.array_equal(
            capacity_checkpoints,
            approved["capacity_fraction_by_gate_id"],
        ),
        "saved D1 capacity checkpoints differ from approved schedule",
    )
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(
        depth,
        1e-12,
    )
    report = {
        "meshId": mesh_id,
        "classification": (
            "synthetic_fishway_interface_local_failure_recovery_"
            "not_physical_validation"
        ),
        "initialAbsoluteTimeS": initial_absolute_time_s,
        "finalAbsoluteTimeS": initial_absolute_time_s + elapsed,
        "simulatedContinuationSeconds": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "checkpointCount": checkpoint_count,
        "checkpointMappingIdentityCount": mapping_exact_count,
        "checkpointMappingIdentityAllPassed": (
            mapping_exact_count == checkpoint_count
        ),
        "gateMassResidualEvaluatedAtEveryStep": True,
        "gateMassResidualEvaluationCount": step,
        "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S": (
            maximum_gate_mass_residual
        ),
        "maximumAbsolutePerFaceLeftPlusRightGateMassResidualM3S": (
            maximum_gate_face_mass_residual
        ),
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "maximumAbsoluteFishwayInterfaceMassResidualM3SPerStep": (
            maximum_fishway_source_residual
        ),
        "minimumEffectiveFishwayDischargeM3S": minimum_effective_q,
        "maximumEffectiveFishwayDischargeM3S": maximum_effective_q,
        "maximumAbsoluteEffectiveQ0ErrorM3SPerStep": (
            maximum_effective_q_error
        ),
        "fishwayQ0WasCapped": False,
        "fishwaySupplyErrorCount": 0,
        "maximumSelectedExpansionRank": maximum_expansion_rank,
        "maximumSupportRadiusM": maximum_support_radius,
        "maximumActualAvailableVolumeFractionRemovedPerStep": (
            maximum_removed_fraction
        ),
        "minimumSelectedDonorPostSourceDepthM": (
            minimum_selected_post_depth
        ),
        "independentSourceOperatorCheckCount": independent_check_count,
        "maximumCompiledVsStandaloneDiagnosticDifference": (
            maximum_independent_difference
        ),
        "minimumCapacityFraction": 1.0,
        "maximumCapacityFraction": 1.0,
        "maximumCapacityChangePerAdaptiveStep": 0.0,
        "minimumDepthM": float(depth.min()),
        "maximumDepthM": float(depth.max()),
        "maximumSpeedMPS": float(speed.max()),
        "negativeDepthCount": int(np.sum(depth < 0.0)),
        "nonFiniteValueCount": int(
            state.size - np.isfinite(state).sum()
        ),
    }
    hard = read_json(PLAN)["hardNumericalAcceptance"]
    hard_checks = {
        "maximumCfl": (
            report["maximumCfl"] <= hard["maximumCfl"]
        ),
        "maximumRelativeMassBalanceError": (
            report["maximumRelativeMassBalanceError"]
            <= hard["maximumRelativeMassBalanceError"]
        ),
        "negativeDepthCount": (
            report["negativeDepthCount"] == hard["negativeDepthCount"]
        ),
        "nonFiniteValueCount": (
            report["nonFiniteValueCount"]
            == hard["nonFiniteValueCount"]
        ),
        "maximumAbsoluteGateMassResidualM3S": (
            report[
                "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S"
            ]
            <= hard["maximumAbsoluteGateMassResidualM3S"]
        ),
        "maximumAbsoluteFishwayInterfaceMassResidualM3SPerStep": (
            report[
                "maximumAbsoluteFishwayInterfaceMassResidualM3SPerStep"
            ]
            <= hard[
                "maximumAbsoluteFishwayInterfaceMassResidualM3SPerStep"
            ]
        ),
        "maximumAbsoluteEffectiveQ0ErrorM3SPerStep": (
            report["maximumAbsoluteEffectiveQ0ErrorM3SPerStep"]
            <= hard["maximumAbsoluteEffectiveQ0ErrorM3SPerStep"]
        ),
        "minimumSelectedDonorPostSourceDepthM": (
            report["minimumSelectedDonorPostSourceDepthM"]
            >= hard["minimumSelectedDonorPostSourceDepthM"]
        ),
        "maximumActualAvailableVolumeFractionRemovedPerStep": (
            report[
                "maximumActualAvailableVolumeFractionRemovedPerStep"
            ]
            <= hard[
                "maximumActualAvailableVolumeFractionRemovedPerStep"
            ]
        ),
        "fishwaySupplyErrorCount": (
            report["fishwaySupplyErrorCount"]
            == hard["fishwaySupplyErrorCount"]
        ),
        "all61CheckpointMappingsExact": (
            report["checkpointMappingIdentityAllPassed"]
            is hard["all61CheckpointMappingsExact"]
        ),
        "maximumExpansionRank": (
            report["maximumSelectedExpansionRank"]
            <= MAXIMUM_EXPANSION_RANK
        ),
        "maximumSupportRadiusM": (
            report["maximumSupportRadiusM"]
            <= MAXIMUM_SUPPORT_RADIUS_M
        ),
        "independentSourceOperatorEveryStep": (
            report["independentSourceOperatorCheckCount"]
            == report["stepsCompleted"]
            and report[
                "maximumCompiledVsStandaloneDiagnosticDifference"
            ]
            <= 1e-10
        ),
    }
    report["hardAcceptanceChecks"] = hard_checks
    report["hardAcceptancePassed"] = all(hard_checks.values())
    fields = {
        "absoluteCheckpointTimeS": absolute_times,
        "relativeCheckpointTimeS": relative_times,
        "capacityFractionByGateId": capacity_checkpoints,
        **{
            f"gateFlux__{name}": values
            for name, values in flux_checkpoints.items()
        },
        **{
            f"fishwayStep__{name}": np.asarray(values, dtype=np.float64)
            for name, values in step_fields.items()
        },
    }
    print(
        json.dumps(
            {
                "event": "D1_run_complete",
                "meshId": mesh_id,
                "steps": step,
                "wallSeconds": round(report["wallSeconds"], 3),
                "maximumCfl": report["maximumCfl"],
                "maximumRelativeMassBalanceError": (
                    report["maximumRelativeMassBalanceError"]
                ),
                "maximumExpansionRank": maximum_expansion_rank,
                "maximumSupportRadiusM": maximum_support_radius,
                "hardAcceptancePassed": report["hardAcceptancePassed"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return snapshots, report, fields


def save_run(
    mesh_id: str,
    snapshots: list[np.ndarray],
    report: dict[str, Any],
    fields: dict[str, np.ndarray],
) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        RUN_ARCHIVES[mesh_id],
        state_H_HU_HV=np.stack(snapshots).astype(np.float32),
        **fields,
    )
    write_json(RUN_REPORTS[mesh_id], report)
    preflight_result = read_json(PREFLIGHT)
    protected_after = {
        str(path.relative_to(ROOT)): e1.sha256(path)
        for path in protected_paths()
    }
    completed = [
        key
        for key in MESH_IDS
        if RUN_ARCHIVES[key].is_file() and RUN_REPORTS[key].is_file()
    ]
    write_json(
        JOURNAL,
        {
            "schema": (
                "onga-stage20-fishway-internal-interface-D1-"
                "execution-journal-v1"
            ),
            "version": 1,
            "status": (
                "RUNS_COMPLETE" if len(completed) == 2 else "RUNNING"
            ),
            "authorizedRunCount": 2,
            "completedRunCount": len(completed),
            "completedMeshIds": completed,
            "allCompletedRunsHardAcceptancePassed": all(
                read_json(RUN_REPORTS[key])["hardAcceptancePassed"]
                for key in completed
            ),
            "bindings": {
                key: {
                    "archive": binding(RUN_ARCHIVES[key]),
                    "report": binding(RUN_REPORTS[key]),
                }
                for key in completed
            },
            "executionFileBindings": {
                "kernel": binding(KERNEL),
                "runner": binding(RUNNER),
            },
            "protectedBefore": preflight_result["protectedBefore"],
            "protectedAfter": protected_after,
            "protectedAssetsUnchanged": (
                preflight_result["protectedBefore"] == protected_after
            ),
            "safeguards": {
                "thirdD1RunStarted": False,
                "zeroTo5300Rerun": False,
                "E1S1Rerun": False,
                "existingSolverModified": False,
                "precomputationRun": False,
                "publicRuntimeChanged": False,
                "mainMerged": False,
            },
        },
    )


def execute_mesh(mesh_id: str) -> None:
    c1.require(
        PREFLIGHT.is_file(),
        "D1 preflight must pass before solver execution",
    )
    preflight_result = read_json(PREFLIGHT)
    c1.require(
        preflight_result["status"] == "PASS"
        and preflight_result["bindings"]["approval"]["sha256"]
        == e1.sha256(APPROVAL)
        and preflight_result["bindings"]["kernel"]["sha256"]
        == e1.sha256(KERNEL)
        and preflight_result["bindings"]["runner"]["sha256"]
        == e1.sha256(RUNNER),
        "D1 preflight, approval, kernel, or runner binding changed",
    )
    c1.require(
        not RUN_ARCHIVES[mesh_id].exists()
        and not RUN_REPORTS[mesh_id].exists(),
        f"D1 result already exists for {mesh_id}; overwrite refused",
    )
    completed = [
        key
        for key in MESH_IDS
        if RUN_ARCHIVES[key].is_file() and RUN_REPORTS[key].is_file()
    ]
    if mesh_id == "R1C":
        c1.require(
            completed == ["formalR20"],
            "formal R20 must complete before R1C",
        )
        c1.require(
            read_json(RUN_REPORTS["formalR20"])[
                "hardAcceptancePassed"
            ],
            "formal R20 hard acceptance failed; R1C start refused",
        )
    else:
        c1.require(
            not completed,
            "formal R20 must be the first D1 run",
        )
    initial = load_initial_states()[mesh_id]
    context = e1.load_context(mesh_id, initial)
    snapshots, report, fields = run_diagnostic(mesh_id, *context)
    save_run(mesh_id, snapshots, report, fields)
    c1.require(
        report["hardAcceptancePassed"],
        f"{mesh_id} D1 hard acceptance failed",
    )
    print(
        json.dumps(
            {
                "event": "D1_mesh_saved",
                "meshId": mesh_id,
                "archive": binding(RUN_ARCHIVES[mesh_id]),
                "report": binding(RUN_REPORTS[mesh_id]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def weighted_rmse(
    values: np.ndarray,
    weights: np.ndarray,
) -> float:
    return float(
        np.sqrt(np.sum(weights * values * values) / np.sum(weights))
    )


def state_differences(
    candidate: np.ndarray,
    reference: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, float]:
    candidate_h = candidate[:, 0]
    reference_h = reference[:, 0]
    candidate_u = candidate[:, 1] / np.maximum(candidate_h, 1e-12)
    candidate_v = candidate[:, 2] / np.maximum(candidate_h, 1e-12)
    reference_u = reference[:, 1] / np.maximum(reference_h, 1e-12)
    reference_v = reference[:, 2] / np.maximum(reference_h, 1e-12)
    return (
        weighted_rmse(candidate_h - reference_h, weights),
        weighted_rmse(
            np.hypot(
                candidate_u - reference_u,
                candidate_v - reference_v,
            ),
            weights,
        ),
    )


def analyze() -> dict[str, Any]:
    c1.require(
        all(path.is_file() for path in RUN_ARCHIVES.values())
        and all(path.is_file() for path in RUN_REPORTS.values()),
        "both D1 runs must exist before analysis",
    )
    reports = {
        key: read_json(path)
        for key, path in RUN_REPORTS.items()
    }
    c1.require(
        all(report["hardAcceptancePassed"] for report in reports.values()),
        "D1 analysis refused because a run failed hard acceptance",
    )
    archives = {
        key: load_npz(path)
        for key, path in RUN_ARCHIVES.items()
    }
    initial = load_initial_states()
    contexts = {
        key: e1.load_context(key, initial[key])
        for key in MESH_IDS
    }
    formal_geometry = contexts["formalR20"][3]
    r1c_geometry = contexts["R1C"][3]
    formal_p2 = contexts["formalR20"][4]
    r1c_p2 = contexts["R1C"][4]
    r1c_finder = spatial.triangle_finder(
        r1c_geometry["vertices"],
        r1c_geometry["triangles"],
    )
    formal_to_r1c, mapping = spatial.containing_cells(
        r1c_finder,
        formal_geometry["centroids"],
        r1c_geometry["centroids"],
    )
    formal_p2_mask = (formal_p2[0] + formal_p2[1]) > 0.0
    formal_weights = formal_geometry["areas"][formal_p2_mask]
    formal_states = archives["formalR20"]["state_H_HU_HV"].astype(
        np.float64
    )
    r1c_states = archives["R1C"]["state_H_HU_HV"].astype(np.float64)
    comparison_eta = np.zeros(61, dtype=np.float64)
    comparison_velocity = np.zeros(61, dtype=np.float64)
    for checkpoint in range(61):
        formal_selected = formal_states[checkpoint][formal_p2_mask]
        r1c_selected = r1c_states[checkpoint][formal_to_r1c][
            formal_p2_mask
        ]
        eta_rmse, velocity_rmse = state_differences(
            r1c_selected,
            formal_selected,
            formal_weights,
        )
        comparison_eta[checkpoint] = eta_rmse
        comparison_velocity[checkpoint] = velocity_rmse

    old_comparison: dict[str, dict[str, np.ndarray]] = {}
    for mesh_id in MESH_IDS:
        old = load_npz(SOURCE_ARCHIVES[mesh_id])[
            "state_H_HU_HV"
        ][50:57].astype(np.float64)
        new = archives[mesh_id]["state_H_HU_HV"][::10].astype(
            np.float64
        )
        p2 = formal_p2 if mesh_id == "formalR20" else r1c_p2
        geometry = (
            formal_geometry if mesh_id == "formalR20" else r1c_geometry
        )
        mask = (p2[0] + p2[1]) > 0.0
        weights = geometry["areas"][mask]
        eta_values = np.zeros(7, dtype=np.float64)
        velocity_values = np.zeros(7, dtype=np.float64)
        for checkpoint in range(7):
            eta_values[checkpoint], velocity_values[checkpoint] = (
                state_differences(
                    new[checkpoint][mask],
                    old[checkpoint][mask],
                    weights,
                )
            )
        old_comparison[mesh_id] = {
            "waterSurfaceRmseM": eta_values,
            "velocityRmseMPS": velocity_values,
        }

    np.savez_compressed(
        COMPARISON_FIELDS,
        absoluteCheckpointTimeS=np.arange(5300.0, 5361.0, 1.0),
        formalR20_vs_R1C_P2_waterSurfaceRmseM=comparison_eta,
        formalR20_vs_R1C_P2_velocityRmseMPS=comparison_velocity,
        oldMethodComparisonAbsoluteTimeS=np.arange(
            5300.0,
            5361.0,
            10.0,
        ),
        formalR20_candidate_vs_old_P2_waterSurfaceRmseM=(
            old_comparison["formalR20"]["waterSurfaceRmseM"]
        ),
        formalR20_candidate_vs_old_P2_velocityRmseMPS=(
            old_comparison["formalR20"]["velocityRmseMPS"]
        ),
        R1C_candidate_vs_old_P2_waterSurfaceRmseM=(
            old_comparison["R1C"]["waterSurfaceRmseM"]
        ),
        R1C_candidate_vs_old_P2_velocityRmseMPS=(
            old_comparison["R1C"]["velocityRmseMPS"]
        ),
    )
    guide_eta = read_json(PLAN)["comparisonReview"][
        "formalR20VsR1CWaterSurfaceRmseGuideM"
    ]
    guide_velocity = read_json(PLAN)["comparisonReview"][
        "formalR20VsR1CVelocityRmseGuideMPS"
    ]
    journal = read_json(JOURNAL)
    summary = {
        "schema": (
            "onga-stage20-fishway-internal-interface-D1-"
            "diagnostic-summary-v1"
        ),
        "version": 1,
        "status": "PASS",
        "classification": (
            "synthetic_fishway_interface_local_failure_recovery_"
            "not_physical_validation"
        ),
        "runCount": 2,
        "runOrder": ["formalR20", "R1C"],
        "absoluteTimeS": [5300, 5360],
        "allEightMainGatesOpen": True,
        "fishwayQ0M3S": Q0_M3_S,
        "hardAcceptancePassedByMesh": {
            key: report["hardAcceptancePassed"]
            for key, report in reports.items()
        },
        "fishwayInterface": {
            "minimumEffectiveQ0M3S": min(
                report["minimumEffectiveFishwayDischargeM3S"]
                for report in reports.values()
            ),
            "maximumEffectiveQ0M3S": max(
                report["maximumEffectiveFishwayDischargeM3S"]
                for report in reports.values()
            ),
            "maximumAbsoluteMassResidualM3SPerStep": max(
                report[
                    "maximumAbsoluteFishwayInterfaceMassResidualM3SPerStep"
                ]
                for report in reports.values()
            ),
            "maximumSelectedExpansionRank": max(
                report["maximumSelectedExpansionRank"]
                for report in reports.values()
            ),
            "maximumSupportRadiusM": max(
                report["maximumSupportRadiusM"]
                for report in reports.values()
            ),
            "minimumSelectedDonorPostSourceDepthM": min(
                report["minimumSelectedDonorPostSourceDepthM"]
                for report in reports.values()
            ),
            "maximumActualAvailableVolumeFractionRemovedPerStep": max(
                report[
                    "maximumActualAvailableVolumeFractionRemovedPerStep"
                ]
                for report in reports.values()
            ),
            "supplyErrorCount": sum(
                report["fishwaySupplyErrorCount"]
                for report in reports.values()
            ),
            "independentSourceOperatorCheckCount": sum(
                report["independentSourceOperatorCheckCount"]
                for report in reports.values()
            ),
            "maximumCompiledVsStandaloneDiagnosticDifference": max(
                report[
                    "maximumCompiledVsStandaloneDiagnosticDifference"
                ]
                for report in reports.values()
            ),
        },
        "formalR20VsR1CP2": {
            "initialWaterSurfaceRmseM": float(comparison_eta[0]),
            "finalWaterSurfaceRmseM": float(comparison_eta[-1]),
            "maximumWaterSurfaceRmseM": float(np.max(comparison_eta)),
            "waterSurfaceGuideM": guide_eta,
            "waterSurfaceGuideExceeded": (
                float(np.max(comparison_eta)) > guide_eta
            ),
            "initialVelocityRmseMPS": float(comparison_velocity[0]),
            "finalVelocityRmseMPS": float(comparison_velocity[-1]),
            "maximumVelocityRmseMPS": float(
                np.max(comparison_velocity)
            ),
            "velocityGuideMPS": guide_velocity,
            "velocityGuideExceeded": (
                float(np.max(comparison_velocity)) > guide_velocity
            ),
            "guideRole": (
                "visible_warning_and_regression_reference_"
                "not_field_calibrated_hard_acceptance_limit"
            ),
            "mapping": mapping,
        },
        "candidateVsSavedOldMethodP2": {
            mesh_id: {
                "finalWaterSurfaceRmseM": float(
                    values["waterSurfaceRmseM"][-1]
                ),
                "maximumWaterSurfaceRmseM": float(
                    np.max(values["waterSurfaceRmseM"])
                ),
                "finalVelocityRmseMPS": float(
                    values["velocityRmseMPS"][-1]
                ),
                "maximumVelocityRmseMPS": float(
                    np.max(values["velocityRmseMPS"])
                ),
            }
            for mesh_id, values in old_comparison.items()
        },
        "numerical": {
            "maximumCfl": max(
                report["maximumCfl"] for report in reports.values()
            ),
            "maximumRelativeMassBalanceError": max(
                report["maximumRelativeMassBalanceError"]
                for report in reports.values()
            ),
            "maximumAbsoluteGateMassResidualM3S": max(
                report[
                    "maximumAbsoluteSummedLeftPlusRightGateMassResidualM3S"
                ]
                for report in reports.values()
            ),
            "negativeDepthCount": sum(
                report["negativeDepthCount"]
                for report in reports.values()
            ),
            "nonFiniteValueCount": sum(
                report["nonFiniteValueCount"]
                for report in reports.values()
            ),
            "totalSteps": sum(
                report["stepsCompleted"] for report in reports.values()
            ),
            "combinedWallSeconds": sum(
                report["wallSeconds"] for report in reports.values()
            ),
        },
        "safeguards": {
            "protectedAssetsUnchanged": (
                journal["protectedAssetsUnchanged"]
            ),
            "existingSolverModified": False,
            "thirdRunStarted": False,
            "precomputationRun": False,
            "productionAdopted": False,
            "publicRuntimeChanged": False,
            "mainMerged": False,
        },
        "requiredNextDecision": (
            "review_D1_result_visual_before_any_physical_model_"
            "or_production_decision"
        ),
    }
    write_json(SUMMARY, summary)

    checks: list[dict[str, Any]] = []
    add(
        checks,
        "exactly_two_authorized_runs_completed_in_order",
        journal["status"] == "RUNS_COMPLETE"
        and journal["completedRunCount"] == 2
        and journal["completedMeshIds"] == ["formalR20", "R1C"],
        journal["completedMeshIds"],
    )
    add(
        checks,
        "both_run_hard_acceptance_sets_pass",
        all(report["hardAcceptancePassed"] for report in reports.values()),
        {
            key: report["hardAcceptanceChecks"]
            for key, report in reports.items()
        },
    )
    add(
        checks,
        "Q0_is_full_and_uncapped_at_every_step",
        summary["fishwayInterface"]["minimumEffectiveQ0M3S"]
        >= Q0_M3_S - 1e-12
        and summary["fishwayInterface"]["maximumEffectiveQ0M3S"]
        <= Q0_M3_S + 1e-12
        and summary["fishwayInterface"]["supplyErrorCount"] == 0,
        summary["fishwayInterface"],
    )
    add(
        checks,
        "fishway_interface_mass_is_conservative",
        summary["fishwayInterface"][
            "maximumAbsoluteMassResidualM3SPerStep"
        ]
        <= 1e-12,
        summary["fishwayInterface"][
            "maximumAbsoluteMassResidualM3SPerStep"
        ],
    )
    add(
        checks,
        "donor_reserve_and_two_percent_cap_hold",
        summary["fishwayInterface"][
            "minimumSelectedDonorPostSourceDepthM"
        ]
        >= 0.049999999999
        and summary["fishwayInterface"][
            "maximumActualAvailableVolumeFractionRemovedPerStep"
        ]
        <= 0.020000000001,
        summary["fishwayInterface"],
    )
    add(
        checks,
        "rank_and_radius_locality_guards_hold",
        summary["fishwayInterface"]["maximumSelectedExpansionRank"] <= 3
        and summary["fishwayInterface"]["maximumSupportRadiusM"] <= 12.0,
        summary["fishwayInterface"],
    )
    add(
        checks,
        "standalone_operator_checked_every_adaptive_step",
        summary["fishwayInterface"][
            "independentSourceOperatorCheckCount"
        ]
        == summary["numerical"]["totalSteps"]
        and summary["fishwayInterface"][
            "maximumCompiledVsStandaloneDiagnosticDifference"
        ]
        <= 1e-10,
        summary["fishwayInterface"],
    )
    add(
        checks,
        "CFL_mass_gate_depth_and_finite_checks_pass",
        summary["numerical"]["maximumCfl"] <= 0.120000000001
        and summary["numerical"]["maximumRelativeMassBalanceError"]
        <= 1e-8
        and summary["numerical"][
            "maximumAbsoluteGateMassResidualM3S"
        ]
        <= 1e-10
        and summary["numerical"]["negativeDepthCount"] == 0
        and summary["numerical"]["nonFiniteValueCount"] == 0,
        summary["numerical"],
    )
    add(
        checks,
        "both_archives_have_exact_61_checkpoint_schedule",
        all(
            np.array_equal(
                archive["absoluteCheckpointTimeS"],
                np.arange(5300.0, 5361.0, 1.0),
            )
            and np.array_equal(
                archive["capacityFractionByGateId"],
                np.ones((61, 8)),
            )
            and archive["state_H_HU_HV"].shape[0] == 61
            for archive in archives.values()
        ),
    )
    add(
        checks,
        "formal_R20_vs_R1C_P2_comparison_has_61_points",
        comparison_eta.shape == (61,)
        and comparison_velocity.shape == (61,)
        and np.isfinite(comparison_eta).all()
        and np.isfinite(comparison_velocity).all(),
    )
    add(
        checks,
        "candidate_vs_old_method_P2_comparison_has_7_points_per_mesh",
        all(
            values["waterSurfaceRmseM"].shape == (7,)
            and values["velocityRmseMPS"].shape == (7,)
            and np.isfinite(values["waterSurfaceRmseM"]).all()
            and np.isfinite(values["velocityRmseMPS"]).all()
            for values in old_comparison.values()
        ),
    )
    protected_after = {
        str(path.relative_to(ROOT)): e1.sha256(path)
        for path in protected_paths()
    }
    add(
        checks,
        "protected_assets_are_unchanged",
        journal["protectedBefore"] == protected_after
        and journal["protectedAssetsUnchanged"],
        protected_after,
    )
    add(
        checks,
        "no_unauthorized_runtime_adoption_occurred",
        all(
            value is False
            for key, value in summary["safeguards"].items()
            if key != "protectedAssetsUnchanged"
        )
        and summary["safeguards"]["protectedAssetsUnchanged"],
        summary["safeguards"],
    )
    add(
        checks,
        "result_remains_synthetic_not_physical_validation",
        "not_physical_validation" in summary["classification"]
        and "not_field_calibrated" in (
            summary["formalR20VsR1CP2"]["guideRole"]
        ),
        {
            "classification": summary["classification"],
            "guideRole": summary["formalR20VsR1CP2"]["guideRole"],
        },
    )
    failed = [row["id"] for row in checks if row["status"] == "FAIL"]
    validation = {
        "schema": (
            "onga-stage20-fishway-internal-interface-D1-"
            "static-validation-v1"
        ),
        "version": 1,
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "failed": failed,
        "checks": checks,
        "newSolverRunCount": 2,
    }
    write_json(VALIDATION, validation)
    independent = {
        "schema": (
            "onga-stage20-fishway-internal-interface-D1-"
            "independent-validation-v1"
        ),
        "version": 1,
        "status": (
            "PASS"
            if (
                summary["fishwayInterface"][
                    "independentSourceOperatorCheckCount"
                ]
                == summary["numerical"]["totalSteps"]
                and summary["fishwayInterface"][
                    "maximumCompiledVsStandaloneDiagnosticDifference"
                ]
                <= 1e-10
                and journal["protectedAssetsUnchanged"]
            )
            else "FAIL"
        ),
        "method": (
            "standalone_numpy_candidate_recomputed_from_each_pre_step_"
            "state_and_compared_with_the_compiled_D1_kernel"
        ),
        "adaptiveStepCount": summary["numerical"]["totalSteps"],
        "standaloneRecomputationCount": summary["fishwayInterface"][
            "independentSourceOperatorCheckCount"
        ],
        "maximumDiagnosticDifference": summary["fishwayInterface"][
            "maximumCompiledVsStandaloneDiagnosticDifference"
        ],
        "protectedAssetsUnchanged": journal[
            "protectedAssetsUnchanged"
        ],
        "existingSolverModified": False,
        "newSolverRunCount": 2,
    }
    write_json(INDEPENDENT, independent)
    files = [
        APPROVAL,
        PLAN,
        KERNEL,
        RUNNER,
        PREFLIGHT,
        RUN_ARCHIVES["formalR20"],
        RUN_REPORTS["formalR20"],
        RUN_ARCHIVES["R1C"],
        RUN_REPORTS["R1C"],
        JOURNAL,
        COMPARISON_FIELDS,
        SUMMARY,
        VALIDATION,
        INDEPENDENT,
    ]
    write_json(
        MANIFEST,
        {
            "schema": (
                "onga-stage20-fishway-internal-interface-D1-manifest-v1"
            ),
            "version": 1,
            "status": (
                "PASS"
                if not failed and independent["status"] == "PASS"
                else "FAIL"
            ),
            "files": {
                path.name: binding(path)
                for path in files
            },
            "newSolverRunCount": 2,
            "existingSolverModified": False,
            "precomputationRun": False,
            "productionAdopted": False,
        },
    )
    if failed or independent["status"] != "PASS":
        raise RuntimeError(
            f"D1 result validation failed: {failed}; "
            f"independent={independent['status']}"
        )
    print(
        json.dumps(
            {
                "event": "D1_analysis_complete",
                "status": validation["status"],
                "checks": validation["checkCount"],
                "independent": independent["status"],
                "formalVsR1C": summary["formalR20VsR1CP2"],
                "solverRuns": 2,
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
        parser.error("choose exactly one of --preflight-only, --mesh, --analyze")
    if args.preflight_only:
        result, _ = preflight()
        print(
            json.dumps(
                {
                    "event": "D1_preflight_complete",
                    "status": result["status"],
                    "checks": result["checkCount"],
                    "solverRun": False,
                },
                ensure_ascii=False,
            )
        )
        return
    if args.mesh:
        execute_mesh(args.mesh)
        return
    analyze()


if __name__ == "__main__":
    main()
