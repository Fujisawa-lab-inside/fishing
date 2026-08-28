#!/usr/bin/env python3
"""Run the approved three-case 60 s H2 mesh-comparison extension."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import MultiLineString, Point, Polygon

import evaluate_stage20_R20_multizone_field_convergence_v1 as spatial
import generate_stage20_barrage_H2_boundary_spacing_comparison_v1 as base
import generate_stage20_fishway_F3_review_mesh_v1 as old
import run_stage20_R20_multizone_H2_dynamics_diagnostic_v1 as short
import stage19_shallow_water_kernel_v1 as reference


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-R20-multizone-H2-60s-extension-v1"
SUMMARY = OUTPUT / "diagnostic-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
FIELDS = OUTPUT / "comparison-fields.npz"
MANIFEST = OUTPUT / "manifest.json"

APPROVAL = ROOT / "config/stage20_R20_multizone_H2_60s_extension_approval_v1.json"
FORMAL_MESH = short.FORMAL_MESH
FORMAL_SUMMARY = short.FORMAL_SUMMARY
MULTIZONE_MESH = short.MULTIZONE_MESH
MULTIZONE_SUMMARY = short.MULTIZONE_SUMMARY
SOURCE_REPORT = short.SOURCE_REPORT
P2_CANDIDATE = base.P2_CANDIDATE
CUT = base.CUT
PROTECTED = short.PROTECTED


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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


def run_case_with_snapshots(
    initial_state: np.ndarray,
    bed: np.ndarray,
    manning: np.ndarray,
    geometry: dict[str, np.ndarray],
    p2: tuple[np.ndarray, np.ndarray],
    source: dict[str, Any],
    tide_candidate: dict[str, Any],
    case: dict[str, Any],
    *,
    target_seconds: float,
    checkpoint_interval: float,
    cfl_target: float,
) -> tuple[list[np.ndarray], dict[str, Any]]:
    state = initial_state.copy()
    multiplier = short.interface_multiplier(geometry, list(case["openGates"]))
    target_flux_by_tag = np.zeros(5, dtype=np.float64)
    for tag, boundary_id in ((2, "N"), (3, "O"), (4, "G")):
        target_flux_by_tag[tag] = (
            -float(source["boundaryDischargeM3S"][boundary_id])
            / float(geometry["boundaryTagLengthSums"][tag])
        )
    elapsed = 0.0
    step = 0
    next_checkpoint = checkpoint_interval
    checkpoint_times = [0.0]
    snapshots = [state.copy()]
    initial_volume = float(np.sum(state[:, 0] * geometry["areas"]))
    expected_volume = initial_volume
    maximum_cfl = 0.0
    maximum_mass_error = 0.0
    maximum_fishway_source_residual = 0.0
    minimum_effective_q = math.inf
    maximum_effective_q = 0.0
    wall_start = time.monotonic()
    tide_clock_start = (
        float(source["contract"]["run"]["tideCurveStartHour"]) * 3600.0
        + float(read_json(SOURCE_REPORT)["run"]["simulatedSeconds"])
    )
    while elapsed < target_seconds - 1e-12:
        stop_at = min(target_seconds, next_checkpoint)
        maximum_dt = stop_at - elapsed
        tide_target = reference.tide_anomaly_m(
            tide_clock_start + elapsed,
            source["tide"],
            tide_candidate,
        )
        (
            state,
            dt,
            cfl,
            boundary_outflow,
            effective_q,
            fishway_source_residual,
        ) = short._advance_h2_step(
            state,
            bed,
            manning,
            geometry["areas"],
            geometry["inverseAreas"],
            geometry["left"],
            geometry["right"],
            geometry["internalLengths"],
            geometry["internalNormals"],
            multiplier,
            geometry["boundaryCells"],
            geometry["boundaryLengths"],
            geometry["boundaryNormals"],
            geometry["boundaryTags"],
            tide_target,
            target_flux_by_tag,
            p2[0],
            p2[1],
            float(case["Q0M3S"]),
            cfl_target,
            maximum_dt,
        )
        elapsed += dt
        step += 1
        expected_volume -= dt * boundary_outflow
        actual_volume = float(np.sum(state[:, 0] * geometry["areas"]))
        mass_error = abs(actual_volume - expected_volume) / max(
            abs(initial_volume),
            1.0,
        )
        maximum_cfl = max(maximum_cfl, float(cfl))
        maximum_mass_error = max(maximum_mass_error, mass_error)
        maximum_fishway_source_residual = max(
            maximum_fishway_source_residual,
            abs(float(fishway_source_residual)),
        )
        minimum_effective_q = min(minimum_effective_q, float(effective_q))
        maximum_effective_q = max(maximum_effective_q, float(effective_q))
        if elapsed >= next_checkpoint - 1e-10 or elapsed >= target_seconds - 1e-10:
            checkpoint_times.append(elapsed)
            snapshots.append(state.copy())
            next_checkpoint += checkpoint_interval
    depth = state[:, 0]
    speed = np.hypot(state[:, 1], state[:, 2]) / np.maximum(depth, 1e-12)
    return snapshots, {
        "simulatedSeconds": elapsed,
        "stepsCompleted": step,
        "wallSeconds": time.monotonic() - wall_start,
        "checkpointTimesS": checkpoint_times,
        "maximumCfl": maximum_cfl,
        "maximumRelativeMassBalanceError": maximum_mass_error,
        "maximumAbsoluteFishwayMassSourceResidualM3S":
            maximum_fishway_source_residual,
        "minimumEffectiveFishwayDischargeM3S": minimum_effective_q,
        "maximumEffectiveFishwayDischargeM3S": maximum_effective_q,
        "fishwayQ0WasCapped":
            minimum_effective_q < float(case["Q0M3S"]) - 1e-12,
        "minimumDepthM": float(depth.min()),
        "maximumDepthM": float(depth.max()),
        "maximumSpeedMPS": float(speed.max()),
        "negativeDepthCount": int(np.sum(depth < 0.0)),
        "nonFiniteValueCount": int(state.size - np.isfinite(state).sum()),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    approval = read_json(APPROVAL)
    require(
        approval["status"]
        == "approved_bounded_60s_H2_extension_three_representative_cases",
        "60 s extension is not approved",
    )
    for key, record in approval["bindings"].items():
        path = ROOT / record["path"]
        require(path.is_file(), f"missing approval binding: {key}")
        require(sha256(path) == record["sha256"], f"approval binding changed: {key}")
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, f"protected runtime changed: {path}")

    source, tide_candidate = short.initial_condition_data()
    p2_source = read_json(P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_polygons = {
        side: Polygon(
            old.project_many(
                p2_source[side]["footprint"]["coordinates"][0][:-1]
            )
        )
        for side in ("upstream", "downstream")
    }
    mesh_records: dict[str, dict[str, Any]] = {
        "formalR20": {
            "path": FORMAL_MESH,
            "summaryPath": FORMAL_SUMMARY,
        },
        "multizone": {
            "path": MULTIZONE_MESH,
            "summaryPath": MULTIZONE_SUMMARY,
        },
    }
    for mesh_id, record in mesh_records.items():
        mesh = short.mesh_arrays(record["path"])
        geometry = short.build_review_geometry(mesh)
        summary = read_json(record["summaryPath"])
        initial_state, bed, manning, mapping = short.initialize_mesh(
            mesh,
            geometry,
            source,
        )
        record.update(
            {
                "mesh": mesh,
                "geometry": geometry,
                "summary": summary,
                "initialState": initial_state,
                "bed": bed,
                "manning": manning,
                "sourceMapping": mapping,
                "P2": short.p2_arrays(geometry, summary, p2_polygons),
            }
        )

    formal = mesh_records["formalR20"]
    multizone = mesh_records["multizone"]
    multizone_finder = spatial.triangle_finder(
        multizone["geometry"]["vertices"],
        multizone["geometry"]["triangles"],
    )
    formal_centroids = formal["geometry"]["centroids"]
    formal_to_multizone, comparison_mapping = spatial.containing_cells(
        multizone_finder,
        formal_centroids,
        multizone["geometry"]["centroids"],
    )
    cut_features = read_json(CUT)["features"]
    cut_line = MultiLineString(
        [
            old.project_many(feature["geometry"]["coordinates"])
            for feature in cut_features
            if feature["geometry"]["type"] == "LineString"
        ]
    )
    barrage_distance = np.asarray(
        [cut_line.distance(Point(point)) for point in formal_centroids],
        dtype=np.float64,
    )
    p2_mask = np.asarray(
        [
            p2_polygons["upstream"].covers(Point(point))
            or p2_polygons["downstream"].covers(Point(point))
            for point in formal_centroids
        ],
        dtype=bool,
    )
    regions = {
        "fullConfirmedDomain": np.ones(len(formal_centroids), dtype=bool),
        "barrageWithin100M": barrage_distance <= 100.0,
        "fishwayP2Footprints": p2_mask,
        "nishikawaConfluenceWithin150M":
            np.linalg.norm(formal_centroids - short.NISHIKAWA, axis=1) <= 150.0,
        "magarigawaConfluenceWithin180M":
            np.linalg.norm(formal_centroids - short.MAGARIGAWA, axis=1) <= 180.0,
    }
    require(all(np.any(mask) for mask in regions.values()), "empty comparison region")

    target_seconds = float(
        approval["authorizedDiagnostic"]["targetPhysicalSecondsPerCase"]
    )
    checkpoint_interval = float(
        approval["authorizedDiagnostic"]["checkpointIntervalPhysicalSeconds"]
    )
    cfl_target = float(approval["authorizedDiagnostic"]["cflTarget"])
    case_results = []
    final_eta_errors = []
    final_velocity_errors = []
    time_series_eta = []
    time_series_velocity = []
    checkpoint_times_reference = None

    for case in approval["authorizedDiagnostic"]["cases"]:
        snapshots: dict[str, list[np.ndarray]] = {}
        reports: dict[str, dict[str, Any]] = {}
        for mesh_id, record in mesh_records.items():
            mesh_snapshots, report = run_case_with_snapshots(
                record["initialState"],
                record["bed"],
                record["manning"],
                record["geometry"],
                record["P2"],
                source,
                tide_candidate,
                case,
                target_seconds=target_seconds,
                checkpoint_interval=checkpoint_interval,
                cfl_target=cfl_target,
            )
            snapshots[mesh_id] = mesh_snapshots
            reports[mesh_id] = report
        formal_times = np.asarray(reports["formalR20"]["checkpointTimesS"])
        multizone_times = np.asarray(reports["multizone"]["checkpointTimesS"])
        require(np.allclose(formal_times, multizone_times), "checkpoint times differ")
        if checkpoint_times_reference is None:
            checkpoint_times_reference = formal_times
        else:
            require(
                np.allclose(checkpoint_times_reference, formal_times),
                "case checkpoint times differ",
            )

        checkpoint_rows = []
        case_eta_time = []
        case_velocity_time = []
        final_eta = None
        final_velocity = None
        for index, checkpoint_time in enumerate(formal_times):
            regional_rows = []
            for region_id, region_mask in regions.items():
                measured, eta_error, velocity_error = short.direct_metrics(
                    snapshots["formalR20"][index],
                    formal["bed"],
                    snapshots["multizone"][index],
                    multizone["bed"],
                    formal_to_multizone,
                    formal["geometry"]["areas"],
                    region_mask,
                )
                regional_rows.append({"regionId": region_id, **measured})
                if region_id == "fullConfirmedDomain":
                    case_eta_time.append(measured["waterSurfaceElevationRmseM"])
                    case_velocity_time.append(measured["velocityVectorRmseMPS"])
                    if index == len(formal_times) - 1:
                        final_eta = eta_error
                        final_velocity = velocity_error
            checkpoint_rows.append(
                {
                    "timeS": float(checkpoint_time),
                    "regionalComparison": regional_rows,
                }
            )
        require(final_eta is not None and final_velocity is not None, "missing final fields")
        final_eta_errors.append(final_eta.astype(np.float32))
        final_velocity_errors.append(final_velocity.astype(np.float32))
        time_series_eta.append(np.asarray(case_eta_time, dtype=np.float64))
        time_series_velocity.append(np.asarray(case_velocity_time, dtype=np.float64))
        case_results.append(
            {
                "caseId": case["caseId"],
                "openGates": case["openGates"],
                "Q0M3S": case["Q0M3S"],
                "selectionReason": case["selectionReason"],
                "meshRuns": reports,
                "checkpoints": checkpoint_rows,
            }
        )

    require(checkpoint_times_reference is not None, "no checkpoints")
    case_ids = [case["caseId"] for case in approval["authorizedDiagnostic"]["cases"]]
    eta_errors = np.stack(final_eta_errors)
    velocity_errors = np.stack(final_velocity_errors)
    np.savez_compressed(
        FIELDS,
        case_ids=np.asarray(case_ids, dtype="U48"),
        checkpoint_time_s=np.asarray(checkpoint_times_reference, dtype=np.float64),
        full_domain_water_surface_elevation_rmse_m=np.stack(time_series_eta),
        full_domain_velocity_vector_rmse_mps=np.stack(time_series_velocity),
        formal_R20_centroids_m=formal_centroids.astype(np.float64),
        formal_R20_cell_area_m2=formal["geometry"]["areas"].astype(np.float64),
        barrage_distance_m=barrage_distance.astype(np.float64),
        fishway_P2_mask=p2_mask.astype(np.uint8),
        final_water_surface_elevation_error_m=eta_errors,
        final_velocity_vector_error_mps=velocity_errors,
        maximum_final_absolute_water_surface_elevation_error_m=np.max(
            np.abs(eta_errors),
            axis=0,
        ).astype(np.float32),
        maximum_final_velocity_vector_error_mps=np.max(
            velocity_errors,
            axis=0,
        ).astype(np.float32),
    )

    screening_rows = []
    guides = approval["acceptance"]["screeningGuides"]
    for case in case_results:
        for checkpoint in case["checkpoints"]:
            for region in checkpoint["regionalComparison"]:
                screening_rows.append(
                    {
                        "caseId": case["caseId"],
                        "timeS": checkpoint["timeS"],
                        "regionId": region["regionId"],
                        "waterSurfaceElevationRmseM": {
                            "measured": region["waterSurfaceElevationRmseM"],
                            "guideMaximum": guides["waterSurfaceElevationRmseM"],
                            "passed": region["waterSurfaceElevationRmseM"]
                                <= guides["waterSurfaceElevationRmseM"],
                        },
                        "velocityVectorRmseMPS": {
                            "measured": region["velocityVectorRmseMPS"],
                            "guideMaximum": guides["velocityVectorRmseMPS"],
                            "passed": region["velocityVectorRmseMPS"]
                                <= guides["velocityVectorRmseMPS"],
                        },
                    }
                )
    worst_eta = max(
        screening_rows,
        key=lambda row: row["waterSurfaceElevationRmseM"]["measured"],
    )
    worst_velocity = max(
        screening_rows,
        key=lambda row: row["velocityVectorRmseMPS"]["measured"],
    )
    full_series = {
        case_ids[index]: {
            "checkpointTimeS": checkpoint_times_reference.tolist(),
            "waterSurfaceElevationRmseM":
                np.stack(time_series_eta)[index].tolist(),
            "velocityVectorRmseMPS":
                np.stack(time_series_velocity)[index].tolist(),
            "tenToSixtySecondRatio": {
                "waterSurfaceElevationRmse":
                    float(np.stack(time_series_eta)[index, -1])
                    / float(np.stack(time_series_eta)[index, 1]),
                "velocityVectorRmse":
                    float(np.stack(time_series_velocity)[index, -1])
                    / float(np.stack(time_series_velocity)[index, 1]),
            },
        }
        for index in range(len(case_ids))
    }
    run_reports = [
        report
        for case in case_results
        for report in case["meshRuns"].values()
    ]
    summary = {
        "schema": "onga-stage20-R20-multizone-H2-60s-extension-v1",
        "version": 1,
        "status": "bounded_60s_H2_extension_complete_pending_user_mesh_judgment",
        "method": {
            "caseCount": len(case_results),
            "meshRunCount": len(run_reports),
            "targetPhysicalSecondsPerCase": target_seconds,
            "checkpointIntervalPhysicalSeconds": checkpoint_interval,
            "checkpointTimesS": checkpoint_times_reference.tolist(),
            "initialConditionAndLawsInheritedExactlyFrom10sDiagnostic": True,
            "physicalValidationClaimAllowed": False,
            "productionMeshAdoptionAutomaticallyAuthorized": False,
        },
        "mesh": {
            "formalR20CellCount": int(len(formal["geometry"]["triangles"])),
            "multizoneCellCount": int(len(multizone["geometry"]["triangles"])),
            "cellCountReductionPercent": 100.0
                * (
                    len(formal["geometry"]["triangles"])
                    - len(multizone["geometry"]["triangles"])
                )
                / len(formal["geometry"]["triangles"]),
            "formalToMultizone": comparison_mapping,
        },
        "cases": case_results,
        "fullDomainTimeSeries": full_series,
        "screening": {
            "guideMeaning": (
                "non_authoritative_mesh_difference_screening_only;"
                "_not_physical_validation_or_automatic_adoption"
            ),
            "comparisonCount": len(screening_rows),
            "passedCount": sum(
                row["waterSurfaceElevationRmseM"]["passed"]
                and row["velocityVectorRmseMPS"]["passed"]
                for row in screening_rows
            ),
            "allPassed": all(
                row["waterSurfaceElevationRmseM"]["passed"]
                and row["velocityVectorRmseMPS"]["passed"]
                for row in screening_rows
            ),
            "worstWaterSurfaceElevationRmse": worst_eta,
            "worstVelocityVectorRmse": worst_velocity,
        },
        "numericalSafety": {
            "maximumCfl": max(report["maximumCfl"] for report in run_reports),
            "maximumRelativeMassBalanceError": max(
                report["maximumRelativeMassBalanceError"] for report in run_reports
            ),
            "maximumAbsoluteFishwayMassSourceResidualM3S": max(
                report["maximumAbsoluteFishwayMassSourceResidualM3S"]
                for report in run_reports
            ),
            "negativeDepthCount": sum(
                report["negativeDepthCount"] for report in run_reports
            ),
            "nonFiniteValueCount": sum(
                report["nonFiniteValueCount"] for report in run_reports
            ),
            "fishwayQ0CappedRunCount": sum(
                report["fishwayQ0WasCapped"] for report in run_reports
            ),
        },
        "bindings": {
            "approval": binding(APPROVAL),
            "formalMesh": binding(FORMAL_MESH),
            "formalSummary": binding(FORMAL_SUMMARY),
            "multizoneMesh": binding(MULTIZONE_MESH),
            "multizoneSummary": binding(MULTIZONE_SUMMARY),
            "comparisonFields": binding(FIELDS),
        },
        "safeguards": approval["safeguards"],
    }
    write_json(SUMMARY, summary)

    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, observed: Any) -> None:
        checks.append(
            {"id": check_id, "passed": bool(passed), "observed": observed}
        )

    acceptance = approval["acceptance"]
    check("approval_binding_valid", True, binding(APPROVAL))
    check("three_cases_two_meshes_completed", len(run_reports) == 6, len(run_reports))
    check(
        "all_required_checkpoints_present",
        np.allclose(
            checkpoint_times_reference,
            np.asarray(acceptance["checkpointsRequiredS"], dtype=np.float64),
        ),
        checkpoint_times_reference.tolist(),
    )
    check(
        "maximum_cfl_within_limit",
        summary["numericalSafety"]["maximumCfl"] <= acceptance["maximumCfl"],
        summary["numericalSafety"]["maximumCfl"],
    )
    check(
        "mass_balance_within_limit",
        summary["numericalSafety"]["maximumRelativeMassBalanceError"]
        <= acceptance["maximumRelativeMassBalanceError"],
        summary["numericalSafety"]["maximumRelativeMassBalanceError"],
    )
    check(
        "fishway_mass_source_conservative",
        summary["numericalSafety"][
            "maximumAbsoluteFishwayMassSourceResidualM3S"
        ]
        <= acceptance["maximumAbsoluteFishwayMassSourceResidualM3S"],
        summary["numericalSafety"][
            "maximumAbsoluteFishwayMassSourceResidualM3S"
        ],
    )
    check(
        "negative_depth_count_zero",
        summary["numericalSafety"]["negativeDepthCount"]
        == acceptance["negativeDepthCount"],
        summary["numericalSafety"]["negativeDepthCount"],
    )
    check(
        "nonfinite_value_count_zero",
        summary["numericalSafety"]["nonFiniteValueCount"]
        == acceptance["nonFiniteValueCount"],
        summary["numericalSafety"]["nonFiniteValueCount"],
    )
    check(
        "P2_Q0_not_safety_capped",
        summary["numericalSafety"]["fishwayQ0CappedRunCount"] == 0,
        summary["numericalSafety"]["fishwayQ0CappedRunCount"],
    )
    check(
        "all_105_checkpoint_region_guides_pass",
        summary["screening"]["allPassed"]
        and summary["screening"]["comparisonCount"] == 105,
        {
            "passed": summary["screening"]["passedCount"],
            "total": summary["screening"]["comparisonCount"],
        },
    )
    check(
        "protected_runtime_unchanged",
        all(sha256(path) == expected for path, expected in PROTECTED.items()),
        {str(path.relative_to(ROOT)): sha256(path) for path in PROTECTED},
    )
    check(
        "no_production_or_precompute_changes",
        not any(
            (
                summary["safeguards"]["productionMeshChanged"],
                summary["safeguards"]["productionSolverSourceChanged"],
                summary["safeguards"]["precomputationRun"],
                summary["safeguards"]["responsePackChanged"],
                summary["safeguards"]["publicRuntimeChanged"],
                summary["safeguards"]["mainMerged"],
            )
        ),
        summary["safeguards"],
    )
    failed = [item for item in checks if not item["passed"]]
    validation = {
        "schema": "onga-stage20-R20-multizone-H2-60s-extension-v1-static-validation",
        "status": "PASS" if not failed else "FAIL",
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "checks": checks,
    }
    write_json(VALIDATION, validation)
    manifest = {
        "schema": "onga-stage20-R20-multizone-H2-60s-extension-v1-manifest",
        "status": "complete_pending_user_mesh_judgment",
        "files": [
            binding(SUMMARY),
            binding(VALIDATION),
            binding(FIELDS),
        ],
        "safeguards": summary["safeguards"],
    }
    write_json(MANIFEST, manifest)
    require(
        not failed,
        f"60 s extension validation failed: {[item['id'] for item in failed]}",
    )
    print(
        json.dumps(
            {
                "result": "PASS_BOUNDED_H2_60S_EXTENSION",
                "summary": binding(SUMMARY),
                "validation": binding(VALIDATION),
                "fields": binding(FIELDS),
                "manifest": binding(MANIFEST),
                "screening": summary["screening"],
                "numericalSafety": summary["numericalSafety"],
                "fullDomainTimeSeries": summary["fullDomainTimeSeries"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
