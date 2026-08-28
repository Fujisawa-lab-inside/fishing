#!/usr/bin/env python3
"""Run the approved 60 s H2 comparison for the corrected H3b mesh."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

import correct_stage20_R20_multizone_H3_river_coverage_v1 as coverage
import run_stage20_R20_multizone_H2_60s_extension_v1 as runner


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-R20-multizone-H3b-H2-60s-diagnostic-v1"
SUMMARY = OUTPUT / "diagnostic-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
FIELDS = OUTPUT / "comparison-fields.npz"
MANIFEST = OUTPUT / "manifest.json"
APPROVAL = (
    ROOT
    / "config/stage20_R20_multizone_H3b_H2_60s_diagnostic_approval_v1.json"
)
H3B_MESH = (
    ROOT
    / "docs/results/stage20-R20-multizone-H3b-main-channel-patch-mesh-v1"
    / "review-mesh.npz"
)
H3B_SUMMARY = (
    ROOT
    / "docs/results/stage20-R20-multizone-H3b-main-channel-patch-mesh-v1"
    / "mesh-summary.json"
)
H3B_STATIC_VALIDATION = (
    ROOT
    / "docs/results/stage20-R20-multizone-H3b-main-channel-patch-mesh-v1"
    / "static-validation.json"
)
SUPERSEDED_H3_MESH = (
    ROOT
    / "docs/results/stage20-R20-multizone-H3-local-patch-mesh-v1"
    / "review-mesh.npz"
)

SIDE_REGIONS = (
    (1, "formerH3NishikawaSideFixedPatch", 873),
    (2, "formerH3MagarigawaSideFixedPatch", 483),
)


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
        return {key: np.asarray(archive[key]).copy() for key in archive.files}


def side_source_masks(
    formal_cell_count: int,
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]], set[int]]:
    old_h3 = load_npz(SUPERSEDED_H3_MESH)
    fixed = old_h3["fixed_R20_cell_mask"].astype(bool)
    source_ids = old_h3["fixed_R20_source_cell_id"].astype(np.int64)
    assignment, component_records = coverage.fixed_component_assignment(
        old_h3["vertices_m"],
        old_h3["triangles"],
        fixed,
    )
    masks: dict[str, np.ndarray] = {}
    records: list[dict[str, Any]] = []
    all_side_source_ids: set[int] = set()
    for component_index, region_id, expected_count in SIDE_REGIONS:
        candidate_mask = fixed & (assignment == component_index)
        selected_ids = source_ids[candidate_mask]
        if (
            len(selected_ids) != expected_count
            or len(np.unique(selected_ids)) != expected_count
            or np.any(selected_ids < 0)
            or np.any(selected_ids >= formal_cell_count)
        ):
            raise ValueError(
                f"unexpected source-cell mapping for {region_id}: "
                f"{len(selected_ids)} cells"
            )
        formal_mask = np.zeros(formal_cell_count, dtype=bool)
        formal_mask[selected_ids] = True
        masks[region_id] = formal_mask
        all_side_source_ids.update(int(value) for value in selected_ids)
        component_record = component_records[component_index]
        records.append(
            {
                "regionId": region_id,
                "sourceComponentIndex": component_index,
                "formalR20SourceCellCount": int(formal_mask.sum()),
                "areaM2FromSupersededH3Component": component_record["areaM2"],
                "sourceComponent": component_record["id"],
            }
        )
    return masks, records, all_side_source_ids


def main() -> None:
    runner.OUTPUT = OUTPUT
    runner.SUMMARY = SUMMARY
    runner.VALIDATION = VALIDATION
    runner.FIELDS = FIELDS
    runner.MANIFEST = MANIFEST
    runner.APPROVAL = APPROVAL
    runner.MULTIZONE_MESH = H3B_MESH
    runner.MULTIZONE_SUMMARY = H3B_SUMMARY

    guide_failure: RuntimeError | None = None
    try:
        runner.main()
    except RuntimeError as error:
        if "60 s extension validation failed" not in str(error):
            raise
        guide_failure = error

    summary = read_json(SUMMARY)
    validation = read_json(VALIDATION)
    fields = load_npz(FIELDS)
    case_ids = [str(value) for value in fields["case_ids"].tolist()]
    areas = fields["formal_R20_cell_area_m2"].astype(np.float64)
    eta_error = fields["final_water_surface_elevation_error_m"].astype(
        np.float64
    )
    velocity_error = fields["final_velocity_vector_error_mps"].astype(
        np.float64
    )
    side_masks, side_mask_records, side_source_ids = side_source_masks(
        len(areas)
    )
    guides = read_json(APPROVAL)["acceptance"]["screeningGuides"]

    final_comparisons: list[dict[str, Any]] = []
    for region_id, mask in side_masks.items():
        weights = areas[mask]
        for case_index, case_id in enumerate(case_ids):
            eta_rmse = float(
                np.sqrt(
                    np.sum(weights * np.square(eta_error[case_index, mask]))
                    / np.sum(weights)
                )
            )
            velocity_rmse = float(
                np.sqrt(
                    np.sum(
                        weights
                        * np.square(velocity_error[case_index, mask])
                    )
                    / np.sum(weights)
                )
            )
            final_comparisons.append(
                {
                    "caseId": case_id,
                    "timeS": 60.0,
                    "regionId": region_id,
                    "formalR20SourceCellCount": int(mask.sum()),
                    "formalR20SourceAreaM2": float(np.sum(weights)),
                    "waterSurfaceElevationRmseM": {
                        "measured": eta_rmse,
                        "guideMaximum": guides[
                            "waterSurfaceElevationRmseM"
                        ],
                        "passed": eta_rmse
                        <= guides["waterSurfaceElevationRmseM"],
                    },
                    "velocityVectorRmseMPS": {
                        "measured": velocity_rmse,
                        "guideMaximum": guides["velocityVectorRmseMPS"],
                        "passed": velocity_rmse
                        <= guides["velocityVectorRmseMPS"],
                    },
                }
            )

    for region_id, mask in side_masks.items():
        fields[f"{region_id}_formal_R20_source_mask"] = mask.astype(np.uint8)
    np.savez_compressed(FIELDS, **fields)

    h3b_mesh = load_npz(H3B_MESH)
    h3b_fixed_source_ids = set(
        int(value)
        for value in h3b_mesh["fixed_R20_source_cell_id"]
        if value >= 0
    )
    h3b_static = read_json(H3B_STATIC_VALIDATION)
    all_side_guides_pass = all(
        row["waterSurfaceElevationRmseM"]["passed"]
        and row["velocityVectorRmseMPS"]["passed"]
        for row in final_comparisons
    )

    def append_check(check_id: str, passed: bool, observed: Any) -> None:
        validation["checks"].append(
            {"id": check_id, "passed": bool(passed), "observed": observed}
        )

    append_check(
        "former_H3_side_patch_source_masks_exact",
        all(
            int(side_masks[region_id].sum()) == expected_count
            for _, region_id, expected_count in SIDE_REGIONS
        )
        and not (
            side_masks[SIDE_REGIONS[0][1]]
            & side_masks[SIDE_REGIONS[1][1]]
        ).any(),
        side_mask_records,
    )
    append_check(
        "H3b_fixed_patch_excludes_all_former_H3_side_source_cells",
        not (h3b_fixed_source_ids & side_source_ids),
        {
            "formerH3SideSourceCellCount": len(side_source_ids),
            "intersectionWithH3bFixedSourceCells": len(
                h3b_fixed_source_ids & side_source_ids
            ),
        },
    )
    append_check(
        "former_H3_side_patch_final_60s_guides_pass",
        all_side_guides_pass,
        {
            "passed": sum(
                row["waterSurfaceElevationRmseM"]["passed"]
                and row["velocityVectorRmseMPS"]["passed"]
                for row in final_comparisons
            ),
            "total": len(final_comparisons),
        },
    )
    append_check(
        "H3b_mesh_source_static_validation_was_PASS",
        h3b_static["status"] == "PASS",
        {
            "status": h3b_static["status"],
            "binding": runner.binding(H3B_STATIC_VALIDATION),
        },
    )
    failed = [
        item for item in validation["checks"] if not item["passed"]
    ]
    validation["schema"] = (
        "onga-stage20-R20-multizone-H3b-H2-60s-diagnostic-v1-"
        "static-validation"
    )
    validation["version"] = 1
    validation["status"] = "PASS" if not failed else "FAIL"
    validation["checkCount"] = len(validation["checks"])
    validation["failedCount"] = len(failed)
    validation["passedCount"] = validation["checkCount"] - len(failed)
    validation["screeningGuideMeaning"] = (
        "mesh_difference_diagnostic_only_not_physical_validation_or_"
        "automatic_adoption"
    )

    summary["schema"] = (
        "onga-stage20-R20-multizone-H3b-H2-60s-diagnostic-v1"
    )
    summary["version"] = 1
    summary["status"] = (
        "PASS_bounded_60s_H2_H3b_complete_pending_600s_judgment"
        if validation["status"] == "PASS"
        else "COMPLETE_bounded_60s_H2_H3b_with_screening_or_static_failure"
    )
    summary["method"]["candidateVersion"] = (
        "R20_multizone_H3b_main_channel_fixed_side_channels_45m2"
    )
    summary["mesh"]["candidateId"] = "H3b"
    summary["bindings"]["H3bMesh"] = summary["bindings"].pop(
        "multizoneMesh"
    )
    summary["bindings"]["H3bSummary"] = summary["bindings"].pop(
        "multizoneSummary"
    )
    summary["bindings"]["comparisonFields"] = runner.binding(FIELDS)
    summary["H3bSideChannelFinalComparison"] = {
        "purpose": (
            "verify the Nishikawa and Magarigawa portions removed from the "
            "former H3 fixed-R20 patch after they were remeshed at 45 m2"
        ),
        "maskDefinitions": side_mask_records,
        "comparisonCount": len(final_comparisons),
        "passedCount": sum(
            row["waterSurfaceElevationRmseM"]["passed"]
            and row["velocityVectorRmseMPS"]["passed"]
            for row in final_comparisons
        ),
        "allPassed": all_side_guides_pass,
        "comparisons": final_comparisons,
    }
    write_json(SUMMARY, summary)
    write_json(VALIDATION, validation)

    manifest = {
        "schema": (
            "onga-stage20-R20-multizone-H3b-H2-60s-diagnostic-v1-manifest"
        ),
        "version": 1,
        "status": "complete_pending_600s_judgment",
        "files": [
            runner.binding(SUMMARY),
            runner.binding(VALIDATION),
            runner.binding(FIELDS),
        ],
        "safeguards": summary["safeguards"],
    }
    write_json(MANIFEST, manifest)

    print(
        json.dumps(
            {
                "result": summary["status"],
                "summary": runner.binding(SUMMARY),
                "validation": runner.binding(VALIDATION),
                "fields": runner.binding(FIELDS),
                "manifest": runner.binding(MANIFEST),
                "cellCountReductionPercent": summary["mesh"][
                    "cellCountReductionPercent"
                ],
                "screening": summary["screening"],
                "sideChannelFinalComparison": summary[
                    "H3bSideChannelFinalComparison"
                ],
                "numericalSafety": summary["numericalSafety"],
                "fullDomainTimeSeries": summary["fullDomainTimeSeries"],
                "underlyingGuideFailure": (
                    str(guide_failure) if guide_failure else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
