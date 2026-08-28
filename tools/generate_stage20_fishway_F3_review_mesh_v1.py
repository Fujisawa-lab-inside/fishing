#!/usr/bin/env python3
"""Generate the one-time review-only F3 mesh authorized by option B approval."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import triangle as tr
from rasterio.warp import transform
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import split
from shapely.strtree import STRtree


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-fishway-F3-review-mesh-v1"
MESH = OUTPUT / "review-mesh.npz"
SUMMARY = OUTPUT / "mesh-summary.json"
GEOMETRY = OUTPUT / "review-geometry.geojson"
VISUAL_DATA = OUTPUT / "visual-data.json"

APPROVAL = ROOT / "config/stage20_fishway_F3_diagnostic_mesh_generation_approval_v1.json"
PLAN = ROOT / "config/stage20_fishway_F3_diagnostic_mesh_plan_candidate_v1.json"
CLOSURE = ROOT / "config/stage20_premesh_problem_closure_v13.json"
INTEGRATED = ROOT / "config/stage20_estuary_confirmed_integration_v2.geojson"
INTEGRATION = ROOT / "config/stage20_estuary_confirmed_integration_v2.json"
WATER_APPROVAL = ROOT / "config/stage20_estuary_water_extent_approval_v1.json"
P2_CANDIDATE = ROOT / "config/stage20_fishway_constant_weak_flow_coupling_candidate_v1.json"
P2_APPROVAL = ROOT / "config/stage20_fishway_constant_weak_flow_coupling_approval_v1.json"
P0_P8 = ROOT / "config/stage20_barrage_p0_p8_structure_reference_lonlat_v1.geojson"
P0_P8_APPROVAL = ROOT / "config/stage20_barrage_p0_p8_structure_reference_approval_v1.json"
P0_P8_METRIC = ROOT / "config/stage20_barrage_p0_p8_structure_reference_metric_lock_v1.json"
BARRAGE_CONTRACT = ROOT / "docs/results/stage20-barrage-authority-review-v1/geometry-contract.json"
TOPOLOGY = ROOT / "config/stage20_barrage_hydraulic_topology_approval_v2.json"

EXPECTED = {
    APPROVAL: "225c9dac6fb93f9cd4f31f4ada3afa14fa79e4efa11fe845ab81f19a90d24ed5",
    PLAN: "3916b8d19881084e47d50f0385d987ab7d93e4f54640ef293fd63ba7a0b229d0",
    CLOSURE: "c29bcfdb9058963f458a7d9e235a86e79f33e9b2cbbb8649074c98a305accf58",
    INTEGRATED: "f16b4893a3a4e8bfb8696ec9aa8908c49091e800a3bccd00afaac654794ed794",
    INTEGRATION: "975efdc9b02e727a884de78648e381f5927b91c38ee86d767125c45a751bc002",
    WATER_APPROVAL: "437e2d5ecfc35daebfc553e4dce3b55f5389c2e69964a42002a60ed9afc6fdfd",
    P2_CANDIDATE: "7afe958520537b4f0ca2c1bf493160919b85a897cabb63639b83b07104be5313",
    P2_APPROVAL: "b31faab8c28fccadd97cf8c25d66f908fa4aa58fcedd448ef92fcd4b60713e86",
    P0_P8: "e2eddc791d3b14dc7fc845f9d69bf132cddb78ab6f6e9b1c044032bfa0dab44e",
    P0_P8_APPROVAL: "538e8b6cefcd3642ed12a369a0508877ee9ffaf7ca1740a4888180ad6fdce147",
    P0_P8_METRIC: "0c45ec50a2dc81d5c443c84115ea6b0cbfdef9519557b236e84509e29b5153ad",
    BARRAGE_CONTRACT: "267dd5105e4710652c8da3385a46bdcc8f1d55a6b86c1d764bfdbba73772002c",
    TOPOLOGY: "ee064a215f82e5d87080ac54865949f7b118fda58ca494f967cb845f5423caf7",
}

PROTECTED = {
    ROOT / "public/data/onga/onga_geometry.geojson": "8593f67c5157ed1d55b717ba6ed691674694cfa499f7f7d533fc9950acdfc536",
    ROOT / "public/data/onga/stage20/mesh-v2.json": "17850a07821f409f13bd3c38446982ae6124743ad9e6437d5d612da447f421c8",
    ROOT / "public/data/onga/stage20/mesh-v2.bin": "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659",
    ROOT / "public/data/onga/stage20/response-pack-synthetic-v2.json": "f7ad29902c195559ddbffca831a916c652bd3a99fbb16c39acc3e351934ceada",
    ROOT / "public/data/onga/stage20/response-pack-synthetic-v2.bin": "2d92e67d2ececf8e3c9e540003cd5546e3f6a38b234de7b5122aa4448c3478a3",
}

OUTER_TAGS = {"shoreline": 10, "M": 11, "N": 12, "O": 13, "G": 14}
GATE_TAG_BASE = 100
FIXED_TAG = 200
REFINEMENT_TAGS = {"upstream": 301, "downstream": 302}


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


def project_many(coordinates: Iterable[Iterable[float]], src: str = "EPSG:4326", dst: str = "EPSG:32652") -> np.ndarray:
    array = np.asarray(list(coordinates), dtype=np.float64)
    xs, ys = transform(src, dst, array[:, 0].tolist(), array[:, 1].tolist())
    return np.column_stack([xs, ys]).astype(np.float64)


def unproject_many(coordinates: np.ndarray) -> list[list[float]]:
    xs, ys = transform("EPSG:32652", "EPSG:4326", coordinates[:, 0].tolist(), coordinates[:, 1].tolist())
    return [[float(x), float(y)] for x, y in zip(xs, ys, strict=True)]


def add_vertex(vertices: list[list[float]], lookup: dict[tuple[int, int], int], point: np.ndarray) -> int:
    key = (round(float(point[0]) * 1e9), round(float(point[1]) * 1e9))
    if key in lookup:
        return lookup[key]
    index = len(vertices)
    vertices.append([float(point[0]), float(point[1])])
    lookup[key] = index
    return index


def boundary_ray_hit(water: Polygon, origin: np.ndarray, direction: np.ndarray, sign: float) -> np.ndarray:
    line = LineString([origin, origin + sign * 3000.0 * direction])
    intersection = water.boundary.intersection(line)
    points: list[np.ndarray] = []
    for geometry in getattr(intersection, "geoms", [intersection]):
        if geometry.geom_type == "Point":
            points.append(np.asarray(geometry.coords[0], dtype=np.float64))
        elif geometry.geom_type == "LineString":
            points.extend(np.asarray([geometry.coords[0], geometry.coords[-1]], dtype=np.float64))
    candidates = []
    for point in points:
        distance = float(np.dot(point - origin, direction) * sign)
        if distance > 1e-7:
            candidates.append((distance, point))
    if not candidates:
        raise ValueError("No water-boundary intersection found for barrage ray")
    return min(candidates, key=lambda item: item[0])[1]


def insert_ring_points(ring: np.ndarray, points: list[np.ndarray]) -> np.ndarray:
    entries: dict[int, list[tuple[float, np.ndarray]]] = {}
    closed = np.vstack([ring, ring[0]])
    for point in points:
        best = None
        for index, (a, b) in enumerate(zip(closed[:-1], closed[1:], strict=True)):
            delta = b - a
            length2 = float(np.dot(delta, delta))
            if length2 == 0.0:
                continue
            t = float(np.clip(np.dot(point - a, delta) / length2, 0.0, 1.0))
            projection = a + t * delta
            distance = float(np.linalg.norm(point - projection))
            if best is None or distance < best[0]:
                best = (distance, index, t)
        if best is None or best[0] > 1e-5:
            raise ValueError(f"Barrage endpoint is not on water ring: residual={None if best is None else best[0]}")
        if best[2] > 1e-10 and best[2] < 1.0 - 1e-10:
            entries.setdefault(best[1], []).append((best[2], point))
    result: list[np.ndarray] = []
    for index, point in enumerate(ring):
        result.append(point)
        for _, inserted in sorted(entries.get(index, []), key=lambda item: item[0]):
            result.append(inserted)
    return np.asarray(result, dtype=np.float64)


class UnionFind:
    def __init__(self, count: int, parent: np.ndarray | None = None):
        self.parent = np.arange(count, dtype=np.int32) if parent is None else parent.copy()

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = int(self.parent[value])
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root

    def component_count(self) -> int:
        return len({self.find(index) for index in range(len(self.parent))})


def main() -> None:
    for path, expected in {**EXPECTED, **PROTECTED}.items():
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Pinned input changed: {path} {actual} != {expected}")
    if tr.__version__ != "20250106":
        raise ValueError(f"Triangle runtime changed: {tr.__version__}")

    approval = read_json(APPROVAL)
    plan = read_json(PLAN)
    if not approval["authorizedNow"]["generateReviewOnlyCandidateMeshOnce"]:
        raise ValueError("Review-only generation is not authorized")
    if plan["recommendation"]["options"] != "pq30aADzQ":
        raise ValueError("Approved Triangle options changed")

    integrated = read_json(INTEGRATED)
    by_id = {feature["id"]: feature for feature in integrated["features"]}
    water_feature = by_id["estuary_water_extent_authority_v2"]
    water_lonlat = shape(water_feature["geometry"])
    if water_lonlat.geom_type != "Polygon" or not water_lonlat.is_valid or len(water_lonlat.interiors) != 0:
        raise ValueError("Expected one valid hole-free water polygon")
    water_ring_lonlat = np.asarray(water_feature["geometry"]["coordinates"][0][:-1], dtype=np.float64)
    water_ring = project_many(water_ring_lonlat)
    water = Polygon(water_ring)
    if not water.is_valid:
        raise ValueError("Projected water polygon is invalid")

    p0_p8 = read_json(P0_P8)
    p0_p8_features = sorted(p0_p8["features"], key=lambda feature: feature["properties"]["orderWestToEast"])
    p0_p8_metric = project_many([feature["geometry"]["coordinates"] for feature in p0_p8_features])
    barrage_axis = p0_p8_metric[-1] - p0_p8_metric[0]
    barrage_axis = barrage_axis / np.linalg.norm(barrage_axis)

    gate_features = sorted(
        [feature for feature in integrated["features"] if feature["id"].startswith("barrage_gate_center_")],
        key=lambda feature: feature["properties"]["gate_no"],
    )
    gate_centres = project_many([feature["geometry"]["coordinates"] for feature in gate_features])
    gate_half_width = 46.5 / 2.0
    gate_starts = gate_centres - gate_half_width * barrage_axis
    gate_ends = gate_centres + gate_half_width * barrage_axis
    west_bank = boundary_ray_hit(water, gate_starts[0], barrage_axis, -1.0)
    east_bank = boundary_ray_hit(water, gate_centres[-1], barrage_axis, 1.0)
    east_bank_raw = east_bank.copy()
    east_vertex_distances = np.linalg.norm(water_ring - east_bank, axis=1)
    east_nearest_index = int(np.argmin(east_vertex_distances))
    east_bank_snap_distance = float(east_vertex_distances[east_nearest_index])
    if east_bank_snap_distance <= 0.01:
        east_bank = water_ring[east_nearest_index].copy()
    else:
        east_bank_snap_distance = 0.0
    water_ring = insert_ring_points(water_ring, [west_bank, east_bank])
    water = Polygon(water_ring)

    p2_candidate = read_json(P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_approval = read_json(P2_APPROVAL)["approvedPair"]
    p2_footprints: dict[str, Polygon] = {}
    p2_footprints_lonlat: dict[str, dict[str, Any]] = {}
    p2_centres: dict[str, np.ndarray] = {}
    refinement_rings: dict[str, np.ndarray] = {}
    for side in ("upstream", "downstream"):
        p2_centres[side] = project_many([p2_approval[side]["coordinate"]])[0]
        footprint_coords = p2_candidate[side]["footprint"]["coordinates"][0][:-1]
        p2_footprints_lonlat[side] = p2_candidate[side]["footprint"]
        footprint = Polygon(project_many(footprint_coords))
        if not water.contains(footprint):
            raise ValueError(f"P2 {side} footprint leaves confirmed water")
        p2_footprints[side] = footprint
        angles = np.arange(16, dtype=np.float64) * (2.0 * math.pi / 16.0)
        ring = p2_centres[side] + 6.0 * np.column_stack([np.cos(angles), np.sin(angles)])
        if not water.contains(Polygon(ring)):
            raise ValueError(f"P2 {side} refinement ring leaves confirmed water")
        refinement_rings[side] = ring

    open_lines = {
        boundary: LineString(project_many(by_id[f"open_boundary_{boundary}_authority_v2"]["geometry"]["coordinates"]))
        for boundary in ("M", "N", "O", "G")
    }

    vertices: list[list[float]] = water_ring.tolist()
    lookup = {(round(point[0] * 1e9), round(point[1] * 1e9)): index for index, point in enumerate(water_ring)}
    segments: list[list[int]] = []
    markers: list[int] = []
    for index in range(len(water_ring)):
        next_index = (index + 1) % len(water_ring)
        a = water_ring[index]
        b = water_ring[next_index]
        midpoint = Point(*((a + b) / 2.0))
        tag = OUTER_TAGS["shoreline"]
        for boundary, line in open_lines.items():
            if midpoint.distance(line) <= 1e-5 and Point(*a).distance(line) <= 1e-5 and Point(*b).distance(line) <= 1e-5:
                tag = OUTER_TAGS[boundary]
                break
        segments.append([index, next_index])
        markers.append(tag)

    def add_segment(a: np.ndarray, b: np.ndarray, marker: int) -> None:
        ia = add_vertex(vertices, lookup, a)
        ib = add_vertex(vertices, lookup, b)
        if ia == ib:
            raise ValueError("Zero-length PSLG segment")
        segments.append([ia, ib])
        markers.append(marker)

    add_segment(west_bank, gate_starts[0], FIXED_TAG)
    for gate_index in range(8):
        gate = gate_index + 1
        start = gate_starts[gate_index]
        centre = gate_centres[gate_index]
        end = gate_ends[gate_index]
        if gate == 8 and np.dot(east_bank - centre, barrage_axis) < gate_half_width:
            end = east_bank
        add_segment(start, centre, GATE_TAG_BASE + gate)
        add_segment(centre, end, GATE_TAG_BASE + gate)
        if gate_index < 7:
            add_segment(gate_ends[gate_index], gate_starts[gate_index + 1], FIXED_TAG)
        elif np.linalg.norm(east_bank - end) > 1e-7:
            add_segment(end, east_bank, FIXED_TAG)

    for side in ("upstream", "downstream"):
        ring = refinement_rings[side]
        indices = [add_vertex(vertices, lookup, point) for point in ring]
        for index in range(len(indices)):
            segments.append([indices[index], indices[(index + 1) % len(indices)]])
            markers.append(REFINEMENT_TAGS[side])

    protected_points: dict[str, np.ndarray] = {}
    p0_p8_outside_water = [
        feature["properties"]["structureId"]
        for feature, point in zip(p0_p8_features, p0_p8_metric, strict=True)
        if not water.covers(Point(*point))
    ]
    for gate, point in enumerate(gate_centres, start=1):
        protected_points[f"gate_center_{gate}"] = point
    for boundary, line in open_lines.items():
        protected_points[f"open_{boundary}_start"] = np.asarray(line.coords[0])
        protected_points[f"open_{boundary}_end"] = np.asarray(line.coords[-1])

    main_channel_regions = list(split(water, LineString([west_bank, east_bank])).geoms)
    if len(main_channel_regions) != 2:
        raise ValueError(f"Barrage cut did not split confirmed water into two regions: {len(main_channel_regions)}")
    region_rows = []
    for region in main_channel_regions:
        available = region.difference(Polygon(refinement_rings["upstream"])).difference(Polygon(refinement_rings["downstream"]))
        representative = available.representative_point()
        region_rows.append([representative.x, representative.y, 1.0, 30.0])
    region_rows.extend([
        [p2_centres["upstream"][0], p2_centres["upstream"][1], 2.0, 3.0],
        [p2_centres["downstream"][0], p2_centres["downstream"][1], 3.0, 3.0],
    ])
    regions = np.asarray(region_rows, dtype=np.float64)

    tri_input = {
        "vertices": np.asarray(vertices, dtype=np.float64),
        "segments": np.asarray(segments, dtype=np.int32),
        "segment_markers": np.asarray(markers, dtype=np.int32).reshape(-1, 1),
        "regions": regions,
    }
    result = tr.triangulate(tri_input, "pq30aADzQ")
    mesh_vertices = np.asarray(result["vertices"], dtype=np.float64)
    triangles = np.asarray(result["triangles"], dtype=np.int32)
    output_segments = np.asarray(result["segments"], dtype=np.int32)
    output_markers = np.asarray(result["segment_markers"], dtype=np.int32).reshape(-1)
    attributes = np.asarray(result["triangle_attributes"], dtype=np.float64).reshape(-1)
    if len(triangles) > 80000:
        raise ValueError(f"Review mesh exceeds 80000-cell limit: {len(triangles)}")

    triangle_points = mesh_vertices[triangles]
    signed_double_area = (
        (triangle_points[:, 1, 0] - triangle_points[:, 0, 0]) * (triangle_points[:, 2, 1] - triangle_points[:, 0, 1])
        - (triangle_points[:, 1, 1] - triangle_points[:, 0, 1]) * (triangle_points[:, 2, 0] - triangle_points[:, 0, 0])
    )
    areas = np.abs(signed_double_area) / 2.0
    sides = np.stack([
        np.linalg.norm(triangle_points[:, 1] - triangle_points[:, 0], axis=1),
        np.linalg.norm(triangle_points[:, 2] - triangle_points[:, 1], axis=1),
        np.linalg.norm(triangle_points[:, 0] - triangle_points[:, 2], axis=1),
    ], axis=1)
    cosine = np.clip((sides[:, [1, 2, 0]] ** 2 + sides[:, [2, 0, 1]] ** 2 - sides ** 2) / (2.0 * sides[:, [1, 2, 0]] * sides[:, [2, 0, 1]]), -1.0, 1.0)
    angles = np.degrees(np.arccos(cosine))
    minimum_angles = angles.min(axis=1)

    segment_marker_by_edge = {
        tuple(sorted((int(edge[0]), int(edge[1])))): int(marker)
        for edge, marker in zip(output_segments, output_markers, strict=True)
    }
    edge_cells: dict[tuple[int, int], list[int]] = {}
    for cell, triangle_vertices in enumerate(triangles):
        for left, right in ((triangle_vertices[0], triangle_vertices[1]), (triangle_vertices[1], triangle_vertices[2]), (triangle_vertices[2], triangle_vertices[0])):
            edge_cells.setdefault(tuple(sorted((int(left), int(right)))), []).append(cell)
    nonmanifold = sum(len(cells) > 2 for cells in edge_cells.values())
    internal_edges = [(edge, cells, segment_marker_by_edge.get(edge, 0)) for edge, cells in edge_cells.items() if len(cells) == 2]
    boundary_edges = [(edge, cells[0], segment_marker_by_edge.get(edge, 0)) for edge, cells in edge_cells.items() if len(cells) == 1]
    below_target_cells = np.where(minimum_angles < 30.0 - 1e-8)[0].tolist()
    constrained_below_target_cells = []
    unattributed_below_target_cells = []
    for cell in below_target_cells:
        tv = triangles[cell]
        triangle_edges = [
            tuple(sorted((int(tv[0]), int(tv[1])))),
            tuple(sorted((int(tv[1]), int(tv[2])))),
            tuple(sorted((int(tv[2]), int(tv[0])))),
        ]
        if any(segment_marker_by_edge.get(edge, 0) != 0 for edge in triangle_edges):
            constrained_below_target_cells.append(cell)
        else:
            unattributed_below_target_cells.append(cell)
    duplicate_cell_count = len(triangles) - len({tuple(sorted(map(int, triangle_vertices))) for triangle_vertices in triangles})

    baseline = UnionFind(len(triangles))
    gate_edges: dict[int, list[tuple[int, int]]] = {gate: [] for gate in range(1, 9)}
    fixed_edges: list[tuple[int, int]] = []
    for _, cells, marker in internal_edges:
        pair = (cells[0], cells[1])
        if GATE_TAG_BASE + 1 <= marker <= GATE_TAG_BASE + 8:
            gate_edges[marker - GATE_TAG_BASE].append(pair)
        elif marker == FIXED_TAG:
            fixed_edges.append(pair)
        else:
            baseline.union(*pair)
    baseline_count = baseline.component_count()

    triangle_polygons = [Polygon(points) for points in triangle_points]
    tree = STRtree(triangle_polygons)
    p2_weights: dict[str, Any] = {}
    representative_cells: dict[str, int] = {}
    for side in ("upstream", "downstream"):
        footprint = p2_footprints[side]
        indices = tree.query(footprint, predicate="intersects")
        overlaps = []
        for index in indices:
            area = float(triangle_polygons[int(index)].intersection(footprint).area)
            if area > 1e-12:
                overlaps.append((int(index), area))
        overlaps.sort()
        overlap_sum = sum(area for _, area in overlaps)
        weights = [(cell, area, area / overlap_sum) for cell, area in overlaps]
        representative_cells[side] = max(weights, key=lambda item: item[2])[0]
        p2_weights[side] = {
            "footprintAreaM2": float(footprint.area),
            "positiveOverlapCellCount": len(weights),
            "overlapAreaSumM2": overlap_sum,
            "overlapAreaRelativeResidual": abs(overlap_sum - footprint.area) / footprint.area,
            "weightSum": sum(weight for _, _, weight in weights),
            "weightSumAbsoluteResidual": abs(sum(weight for _, _, weight in weights) - 1.0),
            "cellIds": [cell for cell, _, _ in weights],
            "overlapAreasM2": [area for _, area, _ in weights],
            "weights": [weight for _, _, weight in weights],
        }
    shared_p2_cells = sorted(set(p2_weights["upstream"]["cellIds"]) & set(p2_weights["downstream"]["cellIds"]))

    topology_results = []
    for state in range(256):
        union = UnionFind(len(triangles), baseline.parent)
        open_gates = []
        for gate in range(1, 9):
            if state & (1 << (gate - 1)):
                open_gates.append(gate)
                for pair in gate_edges[gate]:
                    union.union(*pair)
        main_cut_components = union.component_count()
        union.union(representative_cells["upstream"], representative_cells["downstream"])
        total_components = union.component_count()
        topology_results.append({
            "state": state,
            "openGates": open_gates,
            "mainCutOnlyComponentCount": main_cut_components,
            "completeHydraulicComponentCount": total_components,
            "fishwayEnabled": True,
        })

    boundary_chain_counts = {}
    for boundary, marker in ((name, OUTER_TAGS[name]) for name in ("M", "N", "O", "G")):
        edges = [edge for edge, _, edge_marker in boundary_edges if edge_marker == marker]
        adjacency: dict[int, set[int]] = {}
        for left, right in edges:
            adjacency.setdefault(left, set()).add(right)
            adjacency.setdefault(right, set()).add(left)
        components = 0
        unseen = set(adjacency)
        while unseen:
            components += 1
            stack = [unseen.pop()]
            while stack:
                current = stack.pop()
                for neighbour in adjacency[current]:
                    if neighbour in unseen:
                        unseen.remove(neighbour)
                        stack.append(neighbour)
        boundary_chain_counts[boundary] = {"faceCount": len(edges), "chainCount": components, "degreeOneEndpointCount": sum(len(values) == 1 for values in adjacency.values())}

    protected_missing = []
    protected_movement = {}
    for name, point in protected_points.items():
        distances = np.linalg.norm(mesh_vertices - point, axis=1)
        movement = float(distances.min())
        protected_movement[name] = movement
        if movement > 1e-9:
            protected_missing.append(name)

    output_segment_counts = {str(marker): int(np.sum(output_markers == marker)) for marker in sorted(set(output_markers.tolist()))}
    gate_wet_lengths = {}
    for gate in range(1, 9):
        marker = GATE_TAG_BASE + gate
        gate_segments = output_segments[output_markers == marker]
        length = float(np.linalg.norm(mesh_vertices[gate_segments[:, 1]] - mesh_vertices[gate_segments[:, 0]], axis=1).sum()) if len(gate_segments) else 0.0
        gate_wet_lengths[str(gate)] = length

    OUTPUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MESH,
        vertices_m=mesh_vertices,
        triangles=triangles,
        triangle_region_attribute=attributes,
        segments=output_segments,
        segment_markers=output_markers,
        upstream_cell_ids=np.asarray(p2_weights["upstream"]["cellIds"], dtype=np.int32),
        upstream_weights=np.asarray(p2_weights["upstream"]["weights"], dtype=np.float64),
        downstream_cell_ids=np.asarray(p2_weights["downstream"]["cellIds"], dtype=np.int32),
        downstream_weights=np.asarray(p2_weights["downstream"]["weights"], dtype=np.float64),
    )

    review_features = []
    for gate in range(1, 9):
        gate_lines = output_segments[output_markers == GATE_TAG_BASE + gate]
        for sequence, edge in enumerate(gate_lines):
            coords = unproject_many(mesh_vertices[edge])
            review_features.append({"type": "Feature", "id": f"gate_{gate}_edge_{sequence}", "properties": {"kind": "review_only_gate_interface", "gate": gate}, "geometry": {"type": "LineString", "coordinates": coords}})
    for side in ("upstream", "downstream"):
        review_features.append({"type": "Feature", "id": f"P2_{side}_footprint", "properties": {"kind": "approved_P2_footprint", "side": side}, "geometry": p2_footprints_lonlat[side]})
        ring_coords = unproject_many(np.vstack([refinement_rings[side], refinement_rings[side][0]]))
        review_features.append({"type": "Feature", "id": f"P2_{side}_refinement", "properties": {"kind": "review_only_refinement_control", "side": side}, "geometry": {"type": "Polygon", "coordinates": [ring_coords]}})
    write_json(GEOMETRY, {"type": "FeatureCollection", "name": "stage20_fishway_F3_review_geometry_v1", "features": review_features})

    centres = triangle_points.mean(axis=1)
    fishway = project_many([by_id["fishway_center_v2_authority"]["geometry"]["coordinates"]])[0]
    barrage_indices = np.where(np.linalg.norm(centres - fishway, axis=1) <= 180.0)[0]
    visual_triangles = []
    upstream_set = set(p2_weights["upstream"]["cellIds"])
    downstream_set = set(p2_weights["downstream"]["cellIds"])
    for cell in barrage_indices:
        category = "ordinary"
        if int(cell) in upstream_set:
            category = "P2_upstream"
        elif int(cell) in downstream_set:
            category = "P2_downstream"
        visual_triangles.append({"cell": int(cell), "category": category, "coordinates": unproject_many(np.vstack([triangle_points[cell], triangle_points[cell][0]]))})
    write_json(VISUAL_DATA, {
        "schema": "onga-stage20-fishway-F3-review-mesh-visual-data-v1",
        "trianglesWithin180M": visual_triangles,
        "gateCentres": [{"gate": feature["properties"]["gate_no"], "coordinate": feature["geometry"]["coordinates"]} for feature in gate_features],
        "fishwayCenter": by_id["fishway_center_v2_authority"]["geometry"]["coordinates"],
        "P2": {
            side: {
                "footprint": p2_footprints_lonlat[side],
                "refinement": {
                    "type": "Polygon",
                    "coordinates": [unproject_many(np.vstack([refinement_rings[side], refinement_rings[side][0]]))],
                },
            }
            for side in ("upstream", "downstream")
        },
        "water": water_feature["geometry"],
        "reviewGeometry": review_features,
    })

    summary = {
        "schema": "onga-stage20-fishway-F3-review-mesh-summary-v1",
        "version": 1,
        "generatedAtLocal": "2026-07-23",
        "status": "review_only_candidate_generated_pending_G3_visual_judgment_not_physical",
        "authorization": binding(APPROVAL),
        "inputs": {name: binding(path) for name, path in {
            "plan": PLAN,
            "integratedAuthority": INTEGRATED,
            "integrationRegistry": INTEGRATION,
            "waterApproval": WATER_APPROVAL,
            "P2Candidate": P2_CANDIDATE,
            "P2Approval": P2_APPROVAL,
            "P0P8": P0_P8,
            "P0P8Approval": P0_P8_APPROVAL,
            "P0P8MetricLock": P0_P8_METRIC,
            "barrageContract": BARRAGE_CONTRACT,
            "topology": TOPOLOGY,
        }.items()},
        "runtime": {"triangleVersion": tr.__version__, "options": "pq30aADzQ", "metricCrs": "EPSG:32652"},
        "counts": {
            "inputVertices": len(vertices),
            "vertices": len(mesh_vertices),
            "cells": len(triangles),
            "segments": len(output_segments),
            "internalFaces": len(internal_edges),
            "boundaryFaces": len(boundary_edges),
            "nonmanifoldFaces": nonmanifold,
            "outputSegmentCountsByMarker": output_segment_counts,
            "gateFaceCounts": {str(gate): len(gate_edges[gate]) for gate in range(1, 9)},
            "fixedCutFaceCount": len(fixed_edges),
        },
        "quality": {
            "minimumAreaM2": float(areas.min()),
            "maximumAreaM2": float(areas.max()),
            "maximumOuterRegionAreaM2": float(areas[attributes == 1].max()),
            "maximumUpstreamRegionAreaM2": float(areas[attributes == 2].max()),
            "maximumDownstreamRegionAreaM2": float(areas[attributes == 3].max()),
            "minimumEdgeM": float(sides.min()),
            "minimumAngleDegree": float(minimum_angles.min()),
            "triangleBelow30DegreeCount": int(np.sum(minimum_angles < 30.0 - 1e-8)),
            "constrainedTriangleBelow30DegreeCount": len(constrained_below_target_cells),
            "unattributedTriangleBelow30DegreeCount": len(unattributed_below_target_cells),
            "unattributedTriangleBelow30DegreeCellIds": unattributed_below_target_cells,
            "duplicateCellCount": duplicate_cell_count,
            "nonpositiveAreaCount": int(np.sum(areas <= 0.0)),
            "nonfiniteCoordinateCount": int(np.sum(~np.isfinite(mesh_vertices))),
        },
        "geometry": {
            "waterAreaM2": float(water.area),
            "waterRingInputCoordinateCount": len(water_ring_lonlat),
            "westBankCutCoordinate": unproject_many(np.asarray([west_bank]))[0],
            "eastBankCutCoordinate": unproject_many(np.asarray([east_bank]))[0],
            "eastBankRawIntersectionCoordinate": unproject_many(np.asarray([east_bank_raw]))[0],
            "eastBankExistingVertexSnapDistanceM": east_bank_snap_distance,
            "gateNominalWidthM": 46.5,
            "gateHydraulicWetLengthsM": gate_wet_lengths,
            "gate8NominalMinusWetM": 46.5 - gate_wet_lengths["8"],
            "P0P8ReferencePointCount": len(p0_p8_metric),
            "P0P8InsertedAsMeshVertexCount": 0,
            "P0P8DisplayOnlyLockedReferences": True,
            "protectedPointMissingNames": protected_missing,
            "maximumProtectedPointMovementM": max(protected_movement.values()),
            "P0P8ReferencePointsOutsideWater": sorted(p0_p8_outside_water),
            "P8UsedByAnyTriangle": False,
        },
        "P2Weights": {**p2_weights, "sharedCellIds": shared_p2_cells},
        "topology": {
            "baselineAllMainGatesClosedMainCutOnlyComponentCount": baseline_count,
            "all256StateCount": len(topology_results),
            "mainCutOnlyAllClosedTwo": topology_results[0]["mainCutOnlyComponentCount"] == 2,
            "mainCutOnlyAnyOpenOne": all(item["mainCutOnlyComponentCount"] == 1 for item in topology_results[1:]),
            "completeHydraulicAll256One": all(item["completeHydraulicComponentCount"] == 1 for item in topology_results),
            "fishwayEnabledStateCount": sum(item["fishwayEnabled"] for item in topology_results),
            "boundaryChains": boundary_chain_counts,
            "states": topology_results,
        },
        "knownReviewExceptions": [
            {
                "id": "gate8_hydraulic_wet_span_clipped_by_approved_water_boundary",
                "nominalWidthM": 46.5,
                "wetLengthM": gate_wet_lengths["8"],
                "differenceM": 46.5 - gate_wet_lengths["8"],
                "requiresG3Judgment": True,
            }
        ],
        "outputs": {},
        "safeguards": {
            "reviewOnly": True,
            "solverSourceChanged": False,
            "solverRun": False,
            "precomputationRun": False,
            "physicalMeshChanged": False,
            "responsePackChanged": False,
            "publicChanged": False,
            "mainMerged": False,
        },
        "protectedArtifacts": {str(path.relative_to(ROOT)): sha256(path) for path in PROTECTED},
    }
    summary["outputs"] = {str(path.relative_to(ROOT)): binding(path) for path in (MESH, GEOMETRY, VISUAL_DATA)}
    write_json(SUMMARY, summary)
    print(json.dumps({
        "result": "PASS_GENERATED_REVIEW_ONLY_MESH_PENDING_G3",
        "summary": binding(SUMMARY),
        "cells": len(triangles),
        "P2CellCounts": {side: p2_weights[side]["positiveOverlapCellCount"] for side in ("upstream", "downstream")},
        "all256CompleteHydraulicOne": summary["topology"]["completeHydraulicAll256One"],
        "gate8WetLengthM": gate_wet_lengths["8"],
        "solverRun": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
