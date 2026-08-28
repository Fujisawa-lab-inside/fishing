#!/usr/bin/env python3
"""Generate review-only outer-boundary spacing comparison meshes."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import triangle as tr
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import split
from shapely.strtree import STRtree

import generate_stage20_barrage_H2_review_mesh_v2 as h2
import generate_stage20_fishway_F3_review_mesh_v1 as old


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-barrage-H2-boundary-spacing-comparison-v1"
SUMMARY = OUTPUT / "comparison-summary.json"
VALIDATION = OUTPUT / "static-validation.json"
GEOMETRY = OUTPUT / "candidate-boundaries.geojson"

INTEGRATED = ROOT / "config/stage20_estuary_confirmed_integration_v3.geojson"
CUT = ROOT / "config/stage20_barrage_bank_to_bank_cut_authority_v1.geojson"
GATES = ROOT / "config/stage20_barrage_gate_photo_visible_faces_authority_v1.geojson"
P2_CANDIDATE = ROOT / "config/stage20_fishway_constant_weak_flow_coupling_candidate_v1.json"
P2_APPROVAL = ROOT / "config/stage20_fishway_constant_weak_flow_coupling_approval_v1.json"
CURRENT_MESH = ROOT / "docs/results/stage20-barrage-H2-review-mesh-v2/review-mesh.npz"
DIAGNOSIS = ROOT / "config/stage20_barrage_H2_small_cell_diagnosis_v1.json"
ERRATUM = ROOT / "config/stage20_barrage_H2_mesh_quality_exception_recommendation_erratum_v1.json"

EXPECTED = {
    INTEGRATED: "2868cf998e9b8886d0306db7d774b2de6c0591474ef6755506ce76a18ad4233e",
    CUT: "f8cc19aab4983b5f22b786021ae1b64550db49c3170a1bec3503bcfc8c26b132",
    GATES: "f88deeb2b81de85b3550e1252bf4a194b1d6a8c02482f7cc2ba3109326c7db78",
    P2_CANDIDATE: "7afe958520537b4f0ca2c1bf493160919b85a897cabb63639b83b07104be5313",
    P2_APPROVAL: "b31faab8c28fccadd97cf8c25d66f908fa4aa58fcedd448ef92fcd4b60713e86",
    CURRENT_MESH: "6b91c12cf3f0e0c48883d7ef808803a46f765d9a831d35d358f6707f12a306be",
    DIAGNOSIS: "c2c5caa1bdd6c71e9330098af33c0e1d41b92f39cdae10dd1e8d1acc9b082671",
    ERRATUM: "e9d743fda8330ba54113c9ad524b45a190733c3a1b6f32622701c7756dabc1eb",
}

PROTECTED_RUNTIME = h2.PROTECTED
OUTER_TAGS = h2.OUTER_TAGS
GATE_TAG_BASE = h2.GATE_TAG_BASE
FIXED_TAG = h2.FIXED_TAG
REFINEMENT_TAGS = h2.REFINEMENT_TAGS
CANDIDATES = [
    {"id": "R05", "label": "0.5m級", "simplificationToleranceM": 0.5},
    {"id": "R10", "label": "1.0m級", "simplificationToleranceM": 1.0},
    {"id": "R20", "label": "2.0m級", "simplificationToleranceM": 2.0},
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "byteLength": path.stat().st_size}


def insert_protected_points(ring: np.ndarray, points: np.ndarray) -> np.ndarray:
    result = ring.copy()
    for point in points:
        distances = np.linalg.norm(result - point, axis=1)
        nearest = int(np.argmin(distances))
        if distances[nearest] <= 0.03:
            result[nearest] = point
            continue
        best: tuple[float, int, float] | None = None
        for index in range(len(result)):
            a, b = result[index], result[(index + 1) % len(result)]
            delta = b - a
            t = float(np.clip(np.dot(point - a, delta) / np.dot(delta, delta), 0.0, 1.0))
            residual = float(np.linalg.norm(point - (a + t * delta)))
            if best is None or residual < best[0]:
                best = (residual, index, t)
        if best is None or best[0] > 0.003:
            raise ValueError(f"Protected outer point is not on source boundary: {best}")
        result = np.insert(result, best[1] + 1, point, axis=0)
    return result


def protected_indices(ring: np.ndarray, points: np.ndarray) -> list[int]:
    indices = []
    for point in points:
        distances = np.linalg.norm(ring - point, axis=1)
        if float(distances.min()) > 1e-9:
            raise ValueError("Protected point missing after insertion")
        indices.append(int(np.argmin(distances)))
    result = sorted(set(indices))
    if len(result) != len(points):
        raise ValueError("Protected outer points are not unique")
    return result


def simplify_ring(
    source_ring: np.ndarray,
    indices: list[int],
    tolerance_m: float,
    maximum_segment_m: float = 5.0,
) -> np.ndarray:
    output: list[np.ndarray] = []
    for sequence, start in enumerate(indices):
        end = indices[(sequence + 1) % len(indices)]
        chain = source_ring[start : end + 1] if end > start else np.vstack([source_ring[start:], source_ring[: end + 1]])
        simplified = np.asarray(LineString(chain).simplify(tolerance_m, preserve_topology=False).coords, dtype=np.float64)
        dense: list[np.ndarray] = []
        for a, b in zip(simplified[:-1], simplified[1:], strict=True):
            pieces = max(1, math.ceil(float(np.linalg.norm(b - a)) / maximum_segment_m))
            dense.extend(a + (b - a) * (piece / pieces) for piece in range(pieces))
        dense.append(simplified[-1])
        output = dense if not output else output + dense[1:]
    return np.asarray(output[:-1], dtype=np.float64)


def mesh_quality(vertices: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = vertices[triangles]
    areas = np.abs(
        (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
        - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
    ) / 2.0
    sides = np.stack(
        [
            np.linalg.norm(points[:, 1] - points[:, 0], axis=1),
            np.linalg.norm(points[:, 2] - points[:, 1], axis=1),
            np.linalg.norm(points[:, 0] - points[:, 2], axis=1),
        ],
        axis=1,
    )
    cosine = np.clip(
        (sides[:, [1, 2, 0]] ** 2 + sides[:, [2, 0, 1]] ** 2 - sides**2)
        / (2.0 * sides[:, [1, 2, 0]] * sides[:, [2, 0, 1]]),
        -1.0,
        1.0,
    )
    minimum_angles = np.degrees(np.arccos(cosine)).min(axis=1)
    return areas, sides, minimum_angles


def build_candidate(
    candidate: dict[str, Any],
    source_ring: np.ndarray,
    source_water: Polygon,
    protected_outer: np.ndarray,
    protected_outer_indices: list[int],
    cut_features: list[dict[str, Any]],
    cut_points: np.ndarray,
    open_lines: dict[str, LineString],
    p2_centres: dict[str, np.ndarray],
    p2_footprints: dict[str, Polygon],
    refinement_rings: dict[str, np.ndarray],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ring = simplify_ring(source_ring, protected_outer_indices, candidate["simplificationToleranceM"])
    water = Polygon(ring)
    if not water.is_valid:
        raise ValueError(f"{candidate['id']} polygon invalid")
    if not all(float(np.linalg.norm(ring - point, axis=1).min()) <= 1e-9 for point in protected_outer):
        raise ValueError(f"{candidate['id']} protected outer coordinate moved")
    cut_line = LineString(cut_points)
    if not water.buffer(1e-6).covers(cut_line):
        raise ValueError(f"{candidate['id']} cut leaves candidate water")
    split_regions = list(split(water, cut_line).geoms)
    if len(split_regions) != 2:
        raise ValueError(f"{candidate['id']} cut does not split candidate water")
    for side in ("upstream", "downstream"):
        if not water.contains(p2_footprints[side]) or not water.contains(Polygon(refinement_rings[side])):
            raise ValueError(f"{candidate['id']} P2 {side} leaves water")

    vertices: list[list[float]] = ring.tolist()
    lookup = {(round(point[0] * 1e9), round(point[1] * 1e9)): index for index, point in enumerate(ring)}
    segments: list[list[int]] = []
    markers: list[int] = []
    for index in range(len(ring)):
        next_index = (index + 1) % len(ring)
        a, b = ring[index], ring[next_index]
        midpoint = Point(*((a + b) / 2.0))
        marker = OUTER_TAGS["shoreline"]
        for boundary, line in open_lines.items():
            if midpoint.distance(line) <= 1e-5 and Point(*a).distance(line) <= 1e-5 and Point(*b).distance(line) <= 1e-5:
                marker = OUTER_TAGS[boundary]
                break
        segments.append([index, next_index])
        markers.append(marker)

    def add_segment(a: np.ndarray, b: np.ndarray, marker: int) -> None:
        left = old.add_vertex(vertices, lookup, a)
        right = old.add_vertex(vertices, lookup, b)
        if left == right:
            raise ValueError("Zero-length candidate constraint")
        segments.append([left, right])
        markers.append(marker)

    protected_points: dict[str, np.ndarray] = {}
    for feature_index, feature in enumerate(cut_features):
        coordinates = old.project_many(feature["geometry"]["coordinates"])
        marker = GATE_TAG_BASE + int(feature["properties"]["gate_no"]) if "gate_no" in feature["properties"] else FIXED_TAG
        add_segment(coordinates[0], coordinates[1], marker)
        protected_points[f"cut_{feature_index}_start"] = coordinates[0]
        protected_points[f"cut_{feature_index}_end"] = coordinates[1]
    for point_index, point in enumerate(protected_outer):
        protected_points[f"outer_{point_index}"] = point
    for side in ("upstream", "downstream"):
        indices = [old.add_vertex(vertices, lookup, point) for point in refinement_rings[side]]
        for index in range(len(indices)):
            segments.append([indices[index], indices[(index + 1) % len(indices)]])
            markers.append(REFINEMENT_TAGS[side])

    regions = []
    for region in split_regions:
        available = region.difference(Polygon(refinement_rings["upstream"])).difference(Polygon(refinement_rings["downstream"]))
        representative = available.representative_point()
        regions.append([representative.x, representative.y, 1.0, 30.0])
    regions.extend(
        [
            [p2_centres["upstream"][0], p2_centres["upstream"][1], 2.0, 3.0],
            [p2_centres["downstream"][0], p2_centres["downstream"][1], 3.0, 3.0],
        ]
    )
    result = tr.triangulate(
        {
            "vertices": np.asarray(vertices, dtype=np.float64),
            "segments": np.asarray(segments, dtype=np.int32),
            "segment_markers": np.asarray(markers, dtype=np.int32).reshape(-1, 1),
            "regions": np.asarray(regions, dtype=np.float64),
        },
        "pq30aADzQ",
    )
    mesh_vertices = np.asarray(result["vertices"], dtype=np.float64)
    triangles = np.asarray(result["triangles"], dtype=np.int32)
    output_segments = np.asarray(result["segments"], dtype=np.int32)
    output_markers = np.asarray(result["segment_markers"], dtype=np.int32).reshape(-1)
    attributes = np.asarray(result["triangle_attributes"], dtype=np.float64).reshape(-1)
    areas, sides, minimum_angles = mesh_quality(mesh_vertices, triangles)

    marker_by_edge = {
        tuple(sorted((int(edge[0]), int(edge[1])))): int(marker)
        for edge, marker in zip(output_segments, output_markers, strict=True)
    }
    edge_cells: dict[tuple[int, int], list[int]] = {}
    for cell, triangle in enumerate(triangles):
        for left, right in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            edge_cells.setdefault(tuple(sorted((int(left), int(right)))), []).append(cell)
    internal_edges = [(edge, cells, marker_by_edge.get(edge, 0)) for edge, cells in edge_cells.items() if len(cells) == 2]
    boundary_edges = [(edge, cells[0], marker_by_edge.get(edge, 0)) for edge, cells in edge_cells.items() if len(cells) == 1]
    nonmanifold = sum(len(cells) > 2 for cells in edge_cells.values())

    baseline = old.UnionFind(len(triangles))
    gate_edges: dict[int, list[tuple[int, int]]] = {gate: [] for gate in range(1, 9)}
    fixed_edges: list[tuple[int, int]] = []
    for _, cells, marker in internal_edges:
        pair = (cells[0], cells[1])
        if 101 <= marker <= 108:
            gate_edges[marker - 100].append(pair)
        elif marker == FIXED_TAG:
            fixed_edges.append(pair)
        else:
            baseline.union(*pair)

    triangle_polygons = [Polygon(points) for points in mesh_vertices[triangles]]
    tree = STRtree(triangle_polygons)
    p2_weights: dict[str, dict[str, Any]] = {}
    representative_cells: dict[str, int] = {}
    for side in ("upstream", "downstream"):
        overlaps = []
        for index in tree.query(p2_footprints[side], predicate="intersects"):
            area = float(triangle_polygons[int(index)].intersection(p2_footprints[side]).area)
            if area > 1e-12:
                overlaps.append((int(index), area))
        overlaps.sort()
        overlap_sum = sum(area for _, area in overlaps)
        weights = [(cell, area, area / overlap_sum) for cell, area in overlaps]
        representative_cells[side] = max(weights, key=lambda item: item[2])[0]
        p2_weights[side] = {
            "cellCount": len(weights),
            "weightSumResidual": abs(sum(weight for _, _, weight in weights) - 1.0),
            "overlapAreaResidual": abs(overlap_sum - p2_footprints[side].area) / p2_footprints[side].area,
            "cellIds": [cell for cell, _, _ in weights],
            "weights": [weight for _, _, weight in weights],
        }

    states = []
    for state in range(256):
        union = old.UnionFind(len(triangles), baseline.parent)
        for gate in range(1, 9):
            if state & (1 << (gate - 1)):
                for pair in gate_edges[gate]:
                    union.union(*pair)
        main_components = union.component_count()
        union.union(representative_cells["upstream"], representative_cells["downstream"])
        states.append((main_components, union.component_count()))

    boundary_chains = {}
    for boundary in ("M", "N", "O", "G"):
        edges = [edge for edge, _, marker in boundary_edges if marker == OUTER_TAGS[boundary]]
        components, endpoints = h2.chain_count(edges)
        boundary_chains[boundary] = {"faceCount": len(edges), "chainCount": components, "endpointCount": endpoints}

    protected_movement = max(
        float(np.linalg.norm(mesh_vertices - point, axis=1).min())
        for point in protected_points.values()
    )
    gate_lengths = {}
    for gate in range(1, 9):
        gate_segments = output_segments[output_markers == 100 + gate]
        gate_lengths[str(gate)] = float(
            np.linalg.norm(mesh_vertices[gate_segments[:, 1]] - mesh_vertices[gate_segments[:, 0]], axis=1).sum()
        )

    ring_segments = np.linalg.norm(np.roll(ring, -1, axis=0) - ring, axis=1)
    source_line = LineString(np.vstack([source_ring, source_ring[0]]))
    candidate_line = LineString(np.vstack([ring, ring[0]]))
    duplicate_cells = len(triangles) - len({tuple(sorted(map(int, triangle))) for triangle in triangles})
    row = {
        **candidate,
        "status": "review_only_candidate_not_physical",
        "boundary": {
            "vertexCount": len(ring),
            "minimumSegmentM": float(ring_segments.min()),
            "medianSegmentM": float(np.median(ring_segments)),
            "maximumSegmentM": float(ring_segments.max()),
            "segmentBelow0_25MCount": int(np.sum(ring_segments < 0.25)),
            "segmentBelow0_5MCount": int(np.sum(ring_segments < 0.5)),
            "segmentBelow1MCount": int(np.sum(ring_segments < 1.0)),
            "hausdorffDistanceFromAuthorityM": float(source_line.hausdorff_distance(candidate_line)),
            "waterAreaM2": float(water.area),
            "waterAreaDeltaM2": float(water.area - source_water.area),
            "waterAreaRelativeDelta": float((water.area - source_water.area) / source_water.area),
        },
        "mesh": {
            "vertexCount": len(mesh_vertices),
            "cellCount": len(triangles),
            "minimumAreaM2": float(areas.min()),
            "medianAreaM2": float(np.median(areas)),
            "maximumAreaM2": float(areas.max()),
            "cellAreaBelow0_01M2Count": int(np.sum(areas < 0.01)),
            "cellAreaBelow0_25M2Count": int(np.sum(areas < 0.25)),
            "minimumCellEdgeM": float(sides.min()),
            "medianCellMinimumEdgeM": float(sides.min(axis=1).median()) if hasattr(sides.min(axis=1), "median") else float(np.median(sides.min(axis=1))),
            "cellMinimumEdgeBelow0_1MCount": int(np.sum(sides.min(axis=1) < 0.1)),
            "cellMinimumEdgeBelow0_25MCount": int(np.sum(sides.min(axis=1) < 0.25)),
            "minimumAngleDegree": float(minimum_angles.min()),
            "triangleBelow30DegreeCount": int(np.sum(minimum_angles < 30.0 - 1e-8)),
            "nonmanifoldFaceCount": nonmanifold,
            "duplicateCellCount": duplicate_cells,
            "nonpositiveAreaCount": int(np.sum(areas <= 0.0)),
            "nonfiniteCoordinateCount": int(np.sum(~np.isfinite(mesh_vertices))),
        },
        "hydraulic": {
            "allClosedMainCutComponents": states[0][0],
            "anyOpenMainCutOne": all(main == 1 for main, _ in states[1:]),
            "fishwayAll256One": all(complete == 1 for _, complete in states),
            "fixedCutFaceCount": len(fixed_edges),
            "gateFaceCounts": {str(gate): len(gate_edges[gate]) for gate in range(1, 9)},
            "gateExactFaceLengthsM": gate_lengths,
            "P2": p2_weights,
            "boundaryChains": boundary_chains,
        },
        "protectedCoordinateMaximumMovementM": protected_movement,
    }
    mesh_path = OUTPUT / f"{candidate['id'].lower()}-review-mesh.npz"
    np.savez_compressed(
        mesh_path,
        vertices_m=mesh_vertices,
        triangles=triangles,
        triangle_region_attribute=attributes,
        segments=output_segments,
        segment_markers=output_markers,
    )
    row["meshArtifact"] = binding(mesh_path)
    return row, ring, mesh_vertices, triangles, output_segments, output_markers


def main() -> None:
    for path, expected in {**EXPECTED, **PROTECTED_RUNTIME}.items():
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Pinned input changed: {path}: {actual} != {expected}")
    if tr.__version__ != "20250106":
        raise ValueError(f"Triangle runtime changed: {tr.__version__}")

    integrated = read_json(INTEGRATED)
    by_id = {feature["id"]: feature for feature in integrated["features"]}
    water_feature = by_id["estuary_water_extent_authority_v2"]
    source_ring_lonlat = np.asarray(water_feature["geometry"]["coordinates"][0][:-1], dtype=np.float64)
    source_ring = old.project_many(source_ring_lonlat)
    cut_data = read_json(CUT)
    cut_features = cut_data["features"]
    cut_lonlat = [cut_features[0]["geometry"]["coordinates"][0]] + [
        feature["geometry"]["coordinates"][1] for feature in cut_features
    ]
    cut_points = old.project_many(cut_lonlat)
    protected_lonlat = []
    for boundary in ("M", "N", "O", "G"):
        protected_lonlat.extend(by_id[f"open_boundary_{boundary}_authority_v2"]["geometry"]["coordinates"])
    protected_lonlat.extend([cut_lonlat[0], cut_lonlat[-1]])
    protected_outer = old.project_many(protected_lonlat)
    source_ring = insert_protected_points(source_ring, protected_outer)
    indices = protected_indices(source_ring, protected_outer)
    source_water = Polygon(source_ring)
    if not source_water.is_valid:
        raise ValueError("Source water invalid after exact protected insertion")

    open_lines = {
        boundary: LineString(old.project_many(by_id[f"open_boundary_{boundary}_authority_v2"]["geometry"]["coordinates"]))
        for boundary in ("M", "N", "O", "G")
    }
    p2_approval = read_json(P2_APPROVAL)["approvedPair"]
    p2_source = read_json(P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_centres = {
        side: old.project_many([p2_approval[side]["coordinate"]])[0]
        for side in ("upstream", "downstream")
    }
    p2_footprints = {
        side: Polygon(old.project_many(p2_source[side]["footprint"]["coordinates"][0][:-1]))
        for side in ("upstream", "downstream")
    }
    refinement_rings = {}
    angles = np.arange(16, dtype=np.float64) * 2.0 * math.pi / 16.0
    for side in ("upstream", "downstream"):
        refinement_rings[side] = p2_centres[side] + 6.0 * np.column_stack([np.cos(angles), np.sin(angles)])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    geometry_features = [
        {
            "type": "Feature",
            "id": "current_authority_boundary",
            "properties": {"kind": "current_exact_authority", "status": "unchanged"},
            "geometry": {
                "type": "LineString",
                "coordinates": old.unproject_many(np.vstack([source_ring, source_ring[0]])),
            },
        }
    ]
    for candidate in CANDIDATES:
        row, ring, *_ = build_candidate(
            candidate,
            source_ring,
            source_water,
            protected_outer,
            indices,
            cut_features,
            cut_points,
            open_lines,
            p2_centres,
            p2_footprints,
            refinement_rings,
        )
        results.append(row)
        geometry_features.append(
            {
                "type": "Feature",
                "id": f"{candidate['id']}_boundary",
                "properties": {
                    "kind": "review_only_resampled_boundary_candidate",
                    "candidate": candidate["id"],
                    "toleranceM": candidate["simplificationToleranceM"],
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": old.unproject_many(np.vstack([ring, ring[0]])),
                },
            }
        )
    write_json(
        GEOMETRY,
        {
            "type": "FeatureCollection",
            "name": "stage20_barrage_H2_boundary_spacing_comparison_v1",
            "properties": {"status": "review_only_candidates_not_authority"},
            "features": geometry_features,
        },
    )

    current = read_json(DIAGNOSIS)["evidence"]
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, value: Any, expected: Any) -> None:
        checks.append({"id": check_id, "pass": bool(passed), "value": value, "expected": expected})

    for row in results:
        candidate_id = row["id"]
        check(f"{candidate_id}_polygon_valid", row["boundary"]["vertexCount"] > 3, row["boundary"]["vertexCount"], ">3")
        check(f"{candidate_id}_max_segment", row["boundary"]["maximumSegmentM"] <= 5.000001, row["boundary"]["maximumSegmentM"], "<=5.000001m")
        check(f"{candidate_id}_hausdorff", row["boundary"]["hausdorffDistanceFromAuthorityM"] <= row["simplificationToleranceM"] + 1e-9, row["boundary"]["hausdorffDistanceFromAuthorityM"], f"<={row['simplificationToleranceM']}m")
        check(f"{candidate_id}_protected_movement", row["protectedCoordinateMaximumMovementM"] <= 1e-9, row["protectedCoordinateMaximumMovementM"], "<=1e-9m")
        check(f"{candidate_id}_cell_limit", row["mesh"]["cellCount"] <= 80000, row["mesh"]["cellCount"], "<=80000")
        check(f"{candidate_id}_positive_area", row["mesh"]["nonpositiveAreaCount"] == 0, row["mesh"]["nonpositiveAreaCount"], 0)
        check(f"{candidate_id}_nonfinite", row["mesh"]["nonfiniteCoordinateCount"] == 0, row["mesh"]["nonfiniteCoordinateCount"], 0)
        check(f"{candidate_id}_duplicate", row["mesh"]["duplicateCellCount"] == 0, row["mesh"]["duplicateCellCount"], 0)
        check(f"{candidate_id}_nonmanifold", row["mesh"]["nonmanifoldFaceCount"] == 0, row["mesh"]["nonmanifoldFaceCount"], 0)
        check(f"{candidate_id}_all_closed", row["hydraulic"]["allClosedMainCutComponents"] == 2, row["hydraulic"]["allClosedMainCutComponents"], 2)
        check(f"{candidate_id}_any_open", row["hydraulic"]["anyOpenMainCutOne"], row["hydraulic"]["anyOpenMainCutOne"], True)
        check(f"{candidate_id}_fishway_256", row["hydraulic"]["fishwayAll256One"], row["hydraulic"]["fishwayAll256One"], True)
        for boundary in ("M", "N", "O", "G"):
            check(f"{candidate_id}_{boundary}_chain", row["hydraulic"]["boundaryChains"][boundary]["chainCount"] == 1, row["hydraulic"]["boundaryChains"][boundary], "one chain")
        for gate in range(1, 9):
            check(f"{candidate_id}_gate_{gate}_length", abs(row["hydraulic"]["gateExactFaceLengthsM"][str(gate)] - h2.read_json(h2.H2_APPROVAL)["referenceMetricLengthsM"][gate - 1]) <= 1e-8, row["hydraulic"]["gateExactFaceLengthsM"][str(gate)], "exact authority metric length")
    failed = [item for item in checks if not item["pass"]]
    write_json(
        VALIDATION,
        {
            "schema": "onga-stage20-barrage-H2-boundary-spacing-comparison-static-validation-v1",
            "version": 1,
            "status": "PASS" if not failed else "FAIL",
            "passCount": len(checks) - len(failed),
            "checkCount": len(checks),
            "failedCount": len(failed),
            "checks": checks,
        },
    )
    if failed:
        raise ValueError(f"Candidate comparison validation failed: {[item['id'] for item in failed]}")

    summary = {
        "schema": "onga-stage20-barrage-H2-boundary-spacing-comparison-summary-v1",
        "version": 1,
        "generatedAtLocal": "2026-07-23",
        "status": "review_only_candidate_mesh_comparison_PASS_pending_visual_spacing_decision",
        "method": {
            "metricCrs": "EPSG:32652",
            "protectedOuterPointCount": len(protected_outer),
            "protectedOuterPoints": protected_lonlat,
            "simplification": "split at every protected point; Douglas-Peucker per chain; densify to maximum 5m",
            "triangleVersion": tr.__version__,
            "triangleOptions": "pq30aADzQ",
            "globalMaximumAreaM2": 30.0,
            "P2MaximumAreaM2": 3.0,
        },
        "current": current,
        "candidates": results,
        "recommendationPendingVisualReview": None,
        "bindings": {
            "integration": binding(INTEGRATED),
            "cut": binding(CUT),
            "P2": binding(P2_APPROVAL),
            "diagnosis": binding(DIAGNOSIS),
            "erratum": binding(ERRATUM),
            "geometry": binding(GEOMETRY),
            "validation": binding(VALIDATION),
        },
        "safeguards": {
            "reviewOnly": True,
            "physicalMeshChanged": False,
            "solverSourceChanged": False,
            "solverRun": False,
            "precomputationRun": False,
            "responsePackChanged": False,
            "publicChanged": False,
            "mainMerged": False,
        },
        "protectedArtifacts": {str(path.relative_to(ROOT)): sha256(path) for path in PROTECTED_RUNTIME},
    }
    write_json(SUMMARY, summary)
    print(
        json.dumps(
            {
                "result": "PASS_REVIEW_ONLY_BOUNDARY_SPACING_COMPARISON",
                "summary": binding(SUMMARY),
                "validation": binding(VALIDATION),
                "candidates": [
                    {
                        "id": row["id"],
                        "boundaryVertices": row["boundary"]["vertexCount"],
                        "minimumSegmentM": row["boundary"]["minimumSegmentM"],
                        "hausdorffM": row["boundary"]["hausdorffDistanceFromAuthorityM"],
                        "cells": row["mesh"]["cellCount"],
                        "areaBelow0_25": row["mesh"]["cellAreaBelow0_25M2Count"],
                        "edgeBelow0_25": row["mesh"]["cellMinimumEdgeBelow0_25MCount"],
                    }
                    for row in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
