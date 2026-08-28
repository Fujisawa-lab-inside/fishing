#!/usr/bin/env python3
"""Build a non-adopted multizone mesh with the 5.5 m fishway ring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import triangle as tr
from shapely.geometry import LineString

import build_stage20_operational_fishway_ring_mesh_candidate_v1 as ring
import generate_stage20_R20_multizone_mesh_v1 as multizone
import generate_stage20_barrage_H2_boundary_spacing_comparison_v1 as base


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-regularized-multizone-mesh-candidate-v1"
V90_MESH = OUTPUT / "regularized-v90-base-mesh.npz"
MESH = OUTPUT / "regularized-multizone-review-mesh.npz"
REPORT = OUTPUT / "report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mesh_metrics(
    vertices: np.ndarray,
    triangles: np.ndarray,
    target: np.ndarray,
) -> dict[str, Any]:
    areas, sides, angles = base.mesh_quality(vertices, triangles)
    return {
        "vertexCount": len(vertices),
        "cellCount": len(triangles),
        "minimumAreaM2": float(areas.min()),
        "medianAreaM2": float(np.median(areas)),
        "maximumAreaM2": float(areas.max()),
        "minimumCellEdgeM": float(sides.min()),
        "medianCellMinimumEdgeM": float(np.median(sides.min(axis=1))),
        "minimumAngleDegree": float(angles.min()),
        "cellAreaBelow0_25M2Count": int(np.sum(areas < 0.25)),
        "cellMinimumEdgeBelow0_25MCount": int(np.sum(sides.min(axis=1) < 0.25)),
        "triangleBelow30DegreeCount": int(np.sum(angles < 30.0 - 1e-8)),
        "nonpositiveAreaCount": int(np.sum(areas <= 0.0)),
        "nonfiniteCoordinateCount": int(np.sum(~np.isfinite(vertices))),
        "areaRuleViolationCount": int(np.sum(areas > target + 1e-8)),
    }


def build_v90(inputs: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    previous_output = base.OUTPUT
    original_triangulate = base.tr.triangulate
    base.OUTPUT = OUTPUT

    def area_wrapper(values: dict[str, Any], options: str) -> dict[str, Any]:
        copied = dict(values)
        regions = np.asarray(values["regions"], dtype=np.float64).copy()
        regions[np.isclose(regions[:, 3], 30.0), 3] = 90.0
        copied["regions"] = regions
        return original_triangulate(copied, options)

    base.tr.triangulate = area_wrapper
    try:
        row, *_ = base.build_candidate(
            {
                "id": "REGULARIZED_V90_BASE",
                "label": "魚道リング5.5m・遠方90m2基底",
                "simplificationToleranceM": 2.0,
            },
            inputs["sourceRing"],
            inputs["sourceWater"],
            inputs["protectedOuter"],
            inputs["protectedOuterIndices"],
            inputs["cutFeatures"],
            inputs["cutPoints"],
            inputs["openLines"],
            inputs["p2Centres"],
            inputs["p2Footprints"],
            inputs["refinementRings"],
        )
    finally:
        base.tr.triangulate = original_triangulate
        base.OUTPUT = previous_output
    generated = OUTPUT / "regularized_v90_base-review-mesh.npz"
    generated.replace(V90_MESH)
    return row, V90_MESH


def main() -> None:
    for path, expected in {**base.EXPECTED, **base.PROTECTED_RUNTIME}.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"pinned input changed: {path}: {actual} != {expected}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inputs = ring.build_inputs()
    if min(inputs["footprintClearanceM"].values()) <= 0.0:
        raise RuntimeError("regularized ring does not contain P2 footprints")
    v90_row, v90_path = build_v90(inputs)

    with np.load(v90_path, allow_pickle=False) as source:
        current = {
            "vertices": np.asarray(source["vertices_m"], dtype=np.float64),
            "triangles": np.asarray(source["triangles"], dtype=np.int32),
            "triangle_attributes": np.asarray(
                source["triangle_region_attribute"], dtype=np.float64
            ).reshape(-1, 1),
            "segments": np.asarray(source["segments"], dtype=np.int32),
            "segment_markers": np.asarray(
                source["segment_markers"], dtype=np.int32
            ).reshape(-1, 1),
        }
    cut_line = LineString(inputs["cutPoints"])
    confluences = base.old.project_many(
        [multizone.NISHIKAWA_CONFLUENCE, multizone.MAGARIGAWA_CONFLUENCE]
    )
    iterations = []
    for iteration in range(1, 6):
        centroids = current["vertices"][current["triangles"]].mean(axis=1)
        attributes = current["triangle_attributes"].reshape(-1)
        target = multizone.target_areas(
            centroids, attributes, cut_line, inputs["openLines"], confluences
        )
        areas, _, _ = base.mesh_quality(current["vertices"], current["triangles"])
        violation = areas > target + 1e-8
        iterations.append(
            {
                "iteration": iteration,
                "inputCellCount": len(current["triangles"]),
                "violationCount": int(np.sum(violation)),
                "maximumAreaExcessM2": float(max(0.0, np.max(areas - target))),
            }
        )
        if not np.any(violation):
            break
        current["triangle_max_area"] = target.reshape(-1, 1)
        refined = tr.triangulate(current, "prq30aADzQ")
        current = {
            "vertices": np.asarray(refined["vertices"], dtype=np.float64),
            "triangles": np.asarray(refined["triangles"], dtype=np.int32),
            "triangle_attributes": np.asarray(
                refined["triangle_attributes"], dtype=np.float64
            ).reshape(-1, 1),
            "segments": np.asarray(refined["segments"], dtype=np.int32),
            "segment_markers": np.asarray(
                refined["segment_markers"], dtype=np.int32
            ).reshape(-1, 1),
        }
    else:
        raise RuntimeError("regularized multizone refinement did not converge")

    vertices = current["vertices"]
    triangles = current["triangles"]
    attributes = current["triangle_attributes"].reshape(-1)
    segments = current["segments"]
    markers = current["segment_markers"].reshape(-1)
    centroids = vertices[triangles].mean(axis=1)
    target = multizone.target_areas(
        centroids, attributes, cut_line, inputs["openLines"], confluences
    )
    metrics = mesh_metrics(vertices, triangles, target)
    hydraulic = multizone.hydraulic_evidence(
        vertices, triangles, segments, markers, inputs["p2Footprints"]
    )
    np.savez_compressed(
        MESH,
        vertices_m=vertices,
        triangles=triangles,
        triangle_region_attribute=attributes,
        triangle_maximum_area_m2=target,
        segments=segments,
        segment_markers=markers,
    )

    checks = {
        "areaRulesPass": metrics["areaRuleViolationCount"] == 0,
        "minimumEdgeAtLeast0p75M": metrics["minimumCellEdgeM"] >= 0.75,
        "noAreaBelow0p25M2": metrics["cellAreaBelow0_25M2Count"] == 0,
        "noEdgeBelow0p25M": metrics["cellMinimumEdgeBelow0_25MCount"] == 0,
        "minimumAngleAtLeast30Degree": metrics["minimumAngleDegree"] >= 30.0 - 1e-8,
        "allClosedMainCutTwoComponents": hydraulic["allClosedMainCutComponents"] == 2,
        "anyOpenMainCutOneComponent": hydraulic["anyOpenMainCutOne"],
        "fishwayAll256OneComponent": hydraulic["fishwayAll256One"],
        "openBoundariesSingleChains": all(
            item["chainCount"] == 1 and item["endpointCount"] == 2
            for item in hydraulic["boundaryChains"].values()
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"regularized multizone static gate failed: {checks}")

    old_summary = json.loads(multizone.SUMMARY.read_text(encoding="utf-8"))
    old_metrics = old_summary["mesh"]
    reference_cells = 37724
    reference_edge = 0.3870142296069747
    cell_ratio = metrics["cellCount"] / reference_cells
    edge_ratio = metrics["minimumCellEdgeM"] / reference_edge
    conservative_work_proxy = cell_ratio / edge_ratio
    measured_reference_36h = 348.18228123150766 * 144.0 / 3600.0
    report = {
        "schema": "onga-stage20-regularized-multizone-mesh-candidate-v1",
        "version": 1,
        "status": "PASS_STATIC_NONADOPTED_REGULARIZED_MULTIZONE_DYNAMIC_COMPARISON_REQUIRED",
        "classification": "NUMERICAL_MESH_CANDIDATE_NOT_PHYSICAL_ADOPTION_NOT_FORECAST_NOT_RELEASE",
        "change": {
            "fishwayRefinementRingRadiusM": {"baseline": 6.0, "candidate": 5.5},
            "physicalAnchorMovementM": 0.0,
            "minimumP2FootprintClearanceM": inputs["footprintClearanceM"],
        },
        "v90Base": {"mesh": v90_row["mesh"], "sha256": sha256(v90_path)},
        "refinementIterations": iterations,
        "baselineMultizone": old_metrics,
        "candidate": {"mesh": metrics, "hydraulic": hydraulic},
        "checks": checks,
        "artifact": {
            "path": str(MESH.relative_to(ROOT)),
            "sha256": sha256(MESH),
            "byteLength": MESH.stat().st_size,
        },
        "costProxy": {
            "referenceR1CCellCount": reference_cells,
            "candidateToReferenceCellRatio": cell_ratio,
            "candidateToReferenceMinimumEdgeRatio": edge_ratio,
            "conservativeCellTimesInverseEdgeWorkRatio": conservative_work_proxy,
            "estimatedSpeedup": 1.0 / conservative_work_proxy,
            "reference900sLinear36hWallHours": measured_reference_36h,
            "candidateLinear36hWallHours": measured_reference_36h * conservative_work_proxy,
            "evidenceClass": "STATIC_CELL_AND_MINIMUM_EDGE_PROXY_NOT_MEASURED_DYNAMIC_RUNTIME",
        },
        "decision": {
            "adopted": False,
            "YodaRunAuthorized": False,
            "next": "transfer_continuous_bathymetry_and_freeze_matched_dynamic_acceptance_thresholds",
            "longRunPermitted": False,
        },
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "report": str(REPORT)}))


if __name__ == "__main__":
    main()
