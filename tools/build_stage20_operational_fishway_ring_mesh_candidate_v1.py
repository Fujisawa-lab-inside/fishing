#!/usr/bin/env python3
"""Build a non-adopted mesh candidate with a regularized fishway ring."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import LineString, Polygon

import generate_stage20_barrage_H2_boundary_spacing_comparison_v1 as base


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-operational-fishway-ring-5p5m-mesh-candidate-v1"
REPORT = OUTPUT / "report.json"
CANDIDATE_ID = "OPERATIONAL_FISHWAY_RING_5P5M"
RADIUS_M = 5.5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_inputs() -> dict[str, Any]:
    integrated = base.read_json(base.INTEGRATED)
    by_id = {feature["id"]: feature for feature in integrated["features"]}
    source_ring = base.old.project_many(
        np.asarray(
            by_id["estuary_water_extent_authority_v2"]["geometry"]["coordinates"][0][:-1],
            dtype=np.float64,
        )
    )
    cut_features = base.read_json(base.CUT)["features"]
    cut_lonlat = [cut_features[0]["geometry"]["coordinates"][0]] + [
        feature["geometry"]["coordinates"][1] for feature in cut_features
    ]
    cut_points = base.old.project_many(cut_lonlat)
    protected_lonlat = []
    for boundary in ("M", "N", "O", "G"):
        protected_lonlat.extend(
            by_id[f"open_boundary_{boundary}_authority_v2"]["geometry"]["coordinates"]
        )
    protected_lonlat.extend([cut_lonlat[0], cut_lonlat[-1]])
    protected_outer = base.old.project_many(protected_lonlat)
    source_ring = base.insert_protected_points(source_ring, protected_outer)
    protected_outer_indices = base.protected_indices(source_ring, protected_outer)
    source_water = Polygon(source_ring)
    open_lines = {
        boundary: LineString(
            base.old.project_many(
                by_id[f"open_boundary_{boundary}_authority_v2"]["geometry"]["coordinates"]
            )
        )
        for boundary in ("M", "N", "O", "G")
    }
    p2_approval = base.read_json(base.P2_APPROVAL)["approvedPair"]
    p2_source = base.read_json(base.P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_centres = {
        side: base.old.project_many([p2_approval[side]["coordinate"]])[0]
        for side in ("upstream", "downstream")
    }
    p2_footprints = {
        side: Polygon(
            base.old.project_many(p2_source[side]["footprint"]["coordinates"][0][:-1])
        )
        for side in ("upstream", "downstream")
    }
    angles = np.arange(16, dtype=np.float64) * 2.0 * math.pi / 16.0
    refinement_rings = {
        side: p2_centres[side]
        + RADIUS_M * np.column_stack([np.cos(angles), np.sin(angles)])
        for side in ("upstream", "downstream")
    }
    footprint_clearance = {
        side: RADIUS_M
        - float(
            np.max(
                np.linalg.norm(
                    np.asarray(p2_footprints[side].exterior.coords[:-1]) - p2_centres[side],
                    axis=1,
                )
            )
        )
        for side in ("upstream", "downstream")
    }
    return {
        "sourceRing": source_ring,
        "sourceWater": source_water,
        "protectedOuter": protected_outer,
        "protectedOuterIndices": protected_outer_indices,
        "cutFeatures": cut_features,
        "cutPoints": cut_points,
        "openLines": open_lines,
        "p2Centres": p2_centres,
        "p2Footprints": p2_footprints,
        "refinementRings": refinement_rings,
        "footprintClearanceM": footprint_clearance,
    }


def main() -> None:
    for path, expected in {**base.EXPECTED, **base.PROTECTED_RUNTIME}.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"pinned input changed: {path}: {actual} != {expected}")
    inputs = build_inputs()
    if min(inputs["footprintClearanceM"].values()) <= 0.0:
        raise RuntimeError("5.5 m ring does not contain the P2 footprint")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    previous_output = base.OUTPUT
    base.OUTPUT = OUTPUT
    try:
        row, *_ = base.build_candidate(
            {
                "id": CANDIDATE_ID,
                "label": "魚道数値リング5.5m候補",
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
        base.OUTPUT = previous_output

    mesh_path = OUTPUT / f"{CANDIDATE_ID.lower()}-review-mesh.npz"
    baseline = base.read_json(base.SUMMARY)
    baseline_r20 = next(item for item in baseline["candidates"] if item["id"] == "R20")
    checks = {
        "minimumEdgeAtLeast0p75M": row["mesh"]["minimumCellEdgeM"] >= 0.75,
        "noAreaBelow0p25M2": row["mesh"]["cellAreaBelow0_25M2Count"] == 0,
        "noEdgeBelow0p25M": row["mesh"]["cellMinimumEdgeBelow0_25MCount"] == 0,
        "allClosedMainCutTwoComponents": row["hydraulic"]["allClosedMainCutComponents"] == 2,
        "anyOpenMainCutOneComponent": row["hydraulic"]["anyOpenMainCutOne"],
        "fishwayAll256OneComponent": row["hydraulic"]["fishwayAll256One"],
        "P2FootprintsInsideRing": min(inputs["footprintClearanceM"].values()) > 0.0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"candidate static gate failed: {checks}")

    report = {
        "schema": "onga-stage20-operational-fishway-ring-mesh-candidate-v1",
        "version": 1,
        "status": "PASS_STATIC_NONADOPTED_CANDIDATE_DYNAMIC_COMPARISON_REQUIRED",
        "classification": "NUMERICAL_REFINEMENT_CANDIDATE_NOT_PHYSICAL_MESH_ADOPTION_NOT_RELEASE",
        "change": {
            "fishwayRefinementRingRadiusM": {"baseline": 6.0, "candidate": RADIUS_M},
            "fishwayCentresMovedM": 0.0,
            "physicalP2FootprintsMovedM": 0.0,
            "barrageAndGateGeometryMovedM": 0.0,
            "openBoundaryEndpointsMovedM": 0.0,
            "minimumP2FootprintClearanceM": inputs["footprintClearanceM"],
        },
        "baselineR20": {
            "cellCount": baseline_r20["mesh"]["cellCount"],
            "minimumCellEdgeM": baseline_r20["mesh"]["minimumCellEdgeM"],
            "minimumAreaM2": baseline_r20["mesh"]["minimumAreaM2"],
        },
        "currentR1C": {
            "cellCount": 37724,
            "role": "current_900_second_dynamic_reference",
        },
        "candidate": row,
        "checks": checks,
        "artifact": {
            "path": str(mesh_path.relative_to(ROOT)),
            "sha256": sha256(mesh_path),
            "byteLength": mesh_path.stat().st_size,
        },
        "decision": {
            "adopted": False,
            "mechanismDemonstrated": "shrinking_only_the_numerical_fishway_refinement_ring_removes_the_submetre_CFL_sliver_without_moving_physical_anchors",
            "next": "apply_the_same_ring_regularization_to_the_28892_cell_multizone_candidate_before_any_dynamic_run",
            "longRunPermitted": False,
            "runThis44734CellCandidateNext": False,
            "reason": "This 44,734-cell proof removes the sliver but has more cells than the 37,724-cell dynamic reference. It proves the mechanism; it is not the cost-optimal dynamic candidate.",
        },
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "report": str(REPORT)}))


if __name__ == "__main__":
    main()
