#!/usr/bin/env python3
"""Generate and validate the corrected review-only H2 barrage mesh."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import triangle as tr
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import split
from shapely.strtree import STRtree

import generate_stage20_fishway_F3_review_mesh_v1 as old


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/results/stage20-barrage-H2-review-mesh-v2"
MESH = OUTPUT / "review-mesh.npz"
SUMMARY = OUTPUT / "mesh-summary.json"
GEOMETRY = OUTPUT / "review-geometry.geojson"
VISUAL_DATA = OUTPUT / "visual-data.json"
VALIDATION = OUTPUT / "static-validation.json"

AUTHORIZATION = ROOT / "config/stage20_barrage_H2_review_mesh_generation_authority_v1.json"
CUT = ROOT / "config/stage20_barrage_bank_to_bank_cut_authority_v1.geojson"
CUT_APPROVAL = ROOT / "config/stage20_barrage_bank_to_bank_cut_approval_v1.json"
INTEGRATED = ROOT / "config/stage20_estuary_confirmed_integration_v3.geojson"
GATES = ROOT / "config/stage20_barrage_gate_photo_visible_faces_authority_v1.geojson"
H2_APPROVAL = ROOT / "config/stage20_barrage_hydraulic_width_representation_approval_v1.json"
H2_CONTRACT = ROOT / "config/stage20_barrage_h2_static_interface_contract_v1.json"
B_APPROVAL = ROOT / "config/stage20_fishway_F3_diagnostic_mesh_generation_approval_v1.json"
P2_CANDIDATE = ROOT / "config/stage20_fishway_constant_weak_flow_coupling_candidate_v1.json"
P2_APPROVAL = ROOT / "config/stage20_fishway_constant_weak_flow_coupling_approval_v1.json"
F2C_APPROVAL = ROOT / "config/stage20_fishway_F2c_safety_approval_v1.json"
Q0_APPROVAL = ROOT / "config/stage20_fishway_Q0_diagnostic_band_approval_v1.json"

EXPECTED = {
    AUTHORIZATION: "d2f2a3b878f77c3a8381036e1aeb91875eb56bd7a680412f4a45545ac0ff010e",
    CUT: "f8cc19aab4983b5f22b786021ae1b64550db49c3170a1bec3503bcfc8c26b132",
    CUT_APPROVAL: "25d3a98b8dd7affd91e79bc08764fa25003d497bef7ee080156fb7a1c3660b31",
    INTEGRATED: "2868cf998e9b8886d0306db7d774b2de6c0591474ef6755506ce76a18ad4233e",
    GATES: "f88deeb2b81de85b3550e1252bf4a194b1d6a8c02482f7cc2ba3109326c7db78",
    H2_APPROVAL: "9f63f6c35da688aaa26451919c380b31620d54dc768dab6057538893821cb218",
    H2_CONTRACT: "3b9beef0f0d7744c6ce6ec040fcf523ec420540c3b274840baaf3e20340c9e07",
    B_APPROVAL: "225c9dac6fb93f9cd4f31f4ada3afa14fa79e4efa11fe845ab81f19a90d24ed5",
    P2_CANDIDATE: "7afe958520537b4f0ca2c1bf493160919b85a897cabb63639b83b07104be5313",
    P2_APPROVAL: "b31faab8c28fccadd97cf8c25d66f908fa4aa58fcedd448ef92fcd4b60713e86",
    F2C_APPROVAL: "1a8adb1f36fcfb5f4b718b53f47b21bf659b716c5bae29fc4d09dd849c651af6",
    Q0_APPROVAL: "ef4f6a6b4fa2709917b0b4d08db71458cd97f3971cd66251a48ad353c4f05cdf",
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


def insert_boundary_contacts(
    ring: np.ndarray, contacts: list[np.ndarray]
) -> tuple[np.ndarray, list[float], list[float]]:
    entries: dict[int, list[tuple[float, np.ndarray]]] = {}
    residuals: list[float] = []
    replacement_distances: list[float] = []
    closed = np.vstack([ring, ring[0]])
    for contact in contacts:
        nearest_index = int(np.argmin(np.linalg.norm(ring - contact, axis=1)))
        nearest_distance = float(np.linalg.norm(ring[nearest_index] - contact))
        if nearest_distance <= 0.05:
            # Keep the approved contact exactly and omit only the near-duplicate
            # shoreline sampling vertex in the disposable mesh.  The shoreline
            # authority itself is not changed.
            ring[nearest_index] = contact
            replacement_distances.append(nearest_distance)
            residuals.append(0.0)
            closed = np.vstack([ring, ring[0]])
            continue
        best: tuple[float, int, float] | None = None
        for index, (a, b) in enumerate(zip(closed[:-1], closed[1:], strict=True)):
            delta = b - a
            length2 = float(np.dot(delta, delta))
            if length2 == 0.0:
                continue
            t = float(np.clip(np.dot(contact - a, delta) / length2, 0.0, 1.0))
            residual = float(np.linalg.norm(contact - (a + t * delta)))
            if best is None or residual < best[0]:
                best = (residual, index, t)
        if best is None or best[0] > 0.003:
            raise ValueError(f"Approved cut contact is not on the confirmed water boundary: {best}")
        residuals.append(best[0])
        replacement_distances.append(0.0)
        if 1e-10 < best[2] < 1.0 - 1e-10:
            entries.setdefault(best[1], []).append((best[2], contact))
    result: list[np.ndarray] = []
    for index, point in enumerate(ring):
        result.append(point)
        for _, inserted in sorted(entries.get(index, []), key=lambda item: item[0]):
            result.append(inserted)
    return np.asarray(result, dtype=np.float64), residuals, replacement_distances


def chain_count(edges: list[tuple[int, int]]) -> tuple[int, int]:
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
    return components, sum(len(neighbours) == 1 for neighbours in adjacency.values())


def main() -> None:
    for path, expected in {**EXPECTED, **PROTECTED}.items():
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Pinned input changed: {path} {actual} != {expected}")
    if tr.__version__ != "20250106":
        raise ValueError(f"Triangle runtime changed: {tr.__version__}")

    integrated = read_json(INTEGRATED)
    by_id = {feature["id"]: feature for feature in integrated["features"]}
    water_feature = by_id["estuary_water_extent_authority_v2"]
    water_lonlat = shape(water_feature["geometry"])
    if water_lonlat.geom_type != "Polygon" or not water_lonlat.is_valid or water_lonlat.interiors:
        raise ValueError("Expected one valid hole-free confirmed water polygon")
    water_ring_source = np.asarray(water_feature["geometry"]["coordinates"][0][:-1], dtype=np.float64)
    water_ring = old.project_many(water_ring_source)

    cut = read_json(CUT)
    cut_features = cut["features"]
    if len(cut_features) != 17:
        raise ValueError("Complete cut must contain 17 ordered segments")
    cut_lonlat = [cut_features[0]["geometry"]["coordinates"][0]]
    for previous, feature in zip(cut_features[:-1], cut_features[1:], strict=True):
        if previous["geometry"]["coordinates"][1] != feature["geometry"]["coordinates"][0]:
            raise ValueError("Cut has a continuity gap")
        cut_lonlat.append(previous["geometry"]["coordinates"][1])
    cut_lonlat.append(cut_features[-1]["geometry"]["coordinates"][1])
    cut_points = old.project_many(cut_lonlat)
    west_contact, east_contact = cut_points[0], cut_points[-1]
    water_ring, contact_residuals, contact_replacement_distances = insert_boundary_contacts(
        water_ring, [west_contact, east_contact]
    )
    water = Polygon(water_ring)
    cut_line = LineString(cut_points)
    if not water.buffer(0.003).covers(cut_line):
        raise ValueError("Approved complete cut leaves confirmed water")
    split_regions = list(split(water, cut_line).geoms)
    if len(split_regions) != 2:
        raise ValueError(f"Approved complete cut did not split water into two regions: {len(split_regions)}")

    gate_authority = sorted(
        read_json(GATES)["features"],
        key=lambda feature: int(feature["properties"]["gate_no"]),
    )
    gate_cut_features = [
        feature for feature in cut_features if "gate_no" in feature["properties"]
    ]
    if len(gate_cut_features) != 8:
        raise ValueError("Expected eight gate segments")
    for gate, (cut_feature, gate_feature) in enumerate(zip(gate_cut_features, gate_authority, strict=True), start=1):
        if cut_feature["geometry"]["coordinates"] != gate_feature["geometry"]["coordinates"]:
            raise ValueError(f"Gate {gate} cut endpoints differ from gate authority")

    p2_candidate = read_json(P2_CANDIDATE)["candidatePairs"]["separated"]
    p2_approval = read_json(P2_APPROVAL)["approvedPair"]
    p2_centres: dict[str, np.ndarray] = {}
    p2_footprints: dict[str, Polygon] = {}
    p2_footprints_lonlat: dict[str, dict[str, Any]] = {}
    refinement_rings: dict[str, np.ndarray] = {}
    for side in ("upstream", "downstream"):
        p2_centres[side] = old.project_many([p2_approval[side]["coordinate"]])[0]
        footprint_geometry = p2_candidate[side]["footprint"]
        p2_footprints_lonlat[side] = footprint_geometry
        p2_footprints[side] = Polygon(old.project_many(footprint_geometry["coordinates"][0][:-1]))
        angles = np.arange(16, dtype=np.float64) * (2.0 * math.pi / 16.0)
        refinement_rings[side] = p2_centres[side] + 6.0 * np.column_stack([np.cos(angles), np.sin(angles)])
        if not water.contains(p2_footprints[side]) or not water.contains(Polygon(refinement_rings[side])):
            raise ValueError(f"Approved P2 {side} region leaves confirmed water")
    if cut_line.distance(Point(*p2_centres["upstream"])) == 0.0 or cut_line.distance(Point(*p2_centres["downstream"])) == 0.0:
        raise ValueError("P2 centre lies on cut")

    open_lines = {
        boundary: LineString(old.project_many(by_id[f"open_boundary_{boundary}_authority_v2"]["geometry"]["coordinates"]))
        for boundary in ("M", "N", "O", "G")
    }

    vertices: list[list[float]] = water_ring.tolist()
    lookup = {(round(point[0] * 1e9), round(point[1] * 1e9)): index for index, point in enumerate(water_ring)}
    segments: list[list[int]] = []
    markers: list[int] = []
    for index in range(len(water_ring)):
        next_index = (index + 1) % len(water_ring)
        a, b = water_ring[index], water_ring[next_index]
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
            raise ValueError("Zero-length constraint segment")
        segments.append([left, right])
        markers.append(marker)

    protected_points: dict[str, np.ndarray] = {
        "west_shore_contact": west_contact,
        "east_shore_contact": east_contact,
    }
    for feature_index, feature in enumerate(cut_features):
        coordinates = old.project_many(feature["geometry"]["coordinates"])
        marker = GATE_TAG_BASE + int(feature["properties"]["gate_no"]) if "gate_no" in feature["properties"] else FIXED_TAG
        add_segment(coordinates[0], coordinates[1], marker)
        protected_points[f"cut_{feature_index}_start"] = coordinates[0]
        protected_points[f"cut_{feature_index}_end"] = coordinates[1]
        if "gate_no" in feature["properties"]:
            gate = int(feature["properties"]["gate_no"])
            protected_points[f"gate_{gate}_west"] = coordinates[0]
            protected_points[f"gate_{gate}_east"] = coordinates[1]

    for side in ("upstream", "downstream"):
        ring = refinement_rings[side]
        indices = [old.add_vertex(vertices, lookup, point) for point in ring]
        for index in range(len(indices)):
            segments.append([indices[index], indices[(index + 1) % len(indices)]])
            markers.append(REFINEMENT_TAGS[side])
    for boundary, line in open_lines.items():
        protected_points[f"open_{boundary}_start"] = np.asarray(line.coords[0])
        protected_points[f"open_{boundary}_end"] = np.asarray(line.coords[-1])

    region_rows = []
    for region in split_regions:
        available = region.difference(Polygon(refinement_rings["upstream"])).difference(Polygon(refinement_rings["downstream"]))
        representative = available.representative_point()
        region_rows.append([representative.x, representative.y, 1.0, 30.0])
    region_rows.extend(
        [
            [p2_centres["upstream"][0], p2_centres["upstream"][1], 2.0, 3.0],
            [p2_centres["downstream"][0], p2_centres["downstream"][1], 3.0, 3.0],
        ]
    )
    tri_input = {
        "vertices": np.asarray(vertices, dtype=np.float64),
        "segments": np.asarray(segments, dtype=np.int32),
        "segment_markers": np.asarray(markers, dtype=np.int32).reshape(-1, 1),
        "regions": np.asarray(region_rows, dtype=np.float64),
    }
    result = tr.triangulate(tri_input, "pq30aADzQ")
    mesh_vertices = np.asarray(result["vertices"], dtype=np.float64)
    triangles = np.asarray(result["triangles"], dtype=np.int32)
    output_segments = np.asarray(result["segments"], dtype=np.int32)
    output_markers = np.asarray(result["segment_markers"], dtype=np.int32).reshape(-1)
    attributes = np.asarray(result["triangle_attributes"], dtype=np.float64).reshape(-1)

    triangle_points = mesh_vertices[triangles]
    signed_double_area = (
        (triangle_points[:, 1, 0] - triangle_points[:, 0, 0]) * (triangle_points[:, 2, 1] - triangle_points[:, 0, 1])
        - (triangle_points[:, 1, 1] - triangle_points[:, 0, 1]) * (triangle_points[:, 2, 0] - triangle_points[:, 0, 0])
    )
    areas = np.abs(signed_double_area) / 2.0
    sides = np.stack(
        [
            np.linalg.norm(triangle_points[:, 1] - triangle_points[:, 0], axis=1),
            np.linalg.norm(triangle_points[:, 2] - triangle_points[:, 1], axis=1),
            np.linalg.norm(triangle_points[:, 0] - triangle_points[:, 2], axis=1),
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

    segment_marker_by_edge = {
        tuple(sorted((int(edge[0]), int(edge[1])))): int(marker)
        for edge, marker in zip(output_segments, output_markers, strict=True)
    }
    edge_cells: dict[tuple[int, int], list[int]] = {}
    for cell, triangle in enumerate(triangles):
        for left, right in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            edge_cells.setdefault(tuple(sorted((int(left), int(right)))), []).append(cell)
    internal_edges = [(edge, cells, segment_marker_by_edge.get(edge, 0)) for edge, cells in edge_cells.items() if len(cells) == 2]
    boundary_edges = [(edge, cells[0], segment_marker_by_edge.get(edge, 0)) for edge, cells in edge_cells.items() if len(cells) == 1]
    nonmanifold = sum(len(cells) > 2 for cells in edge_cells.values())
    duplicate_cells = len(triangles) - len({tuple(sorted(map(int, triangle))) for triangle in triangles})
    below_target = np.where(minimum_angles < 30.0 - 1e-8)[0].tolist()
    unattributed_below = []
    for cell in below_target:
        a, b, c = map(int, triangles[cell])
        if not any(segment_marker_by_edge.get(tuple(sorted(edge)), 0) for edge in ((a, b), (b, c), (c, a))):
            unattributed_below.append(cell)

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

    triangle_polygons = [Polygon(points) for points in triangle_points]
    tree = STRtree(triangle_polygons)
    p2_weights: dict[str, Any] = {}
    representative_cells: dict[str, int] = {}
    for side in ("upstream", "downstream"):
        footprint = p2_footprints[side]
        overlaps: list[tuple[int, float]] = []
        for index in tree.query(footprint, predicate="intersects"):
            area = float(triangle_polygons[int(index)].intersection(footprint).area)
            if area > 1e-12:
                overlaps.append((int(index), area))
        overlaps.sort()
        overlap_sum = sum(area for _, area in overlaps)
        weights = [(cell, area, area / overlap_sum) for cell, area in overlaps]
        representative_cells[side] = max(weights, key=lambda row: row[2])[0]
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

    topology_states = []
    for state in range(256):
        union = old.UnionFind(len(triangles), baseline.parent)
        open_gates = []
        for gate in range(1, 9):
            if state & (1 << (gate - 1)):
                open_gates.append(gate)
                for pair in gate_edges[gate]:
                    union.union(*pair)
        main_components = union.component_count()
        union.union(representative_cells["upstream"], representative_cells["downstream"])
        topology_states.append(
            {
                "state": state,
                "openGates": open_gates,
                "mainCutOnlyComponentCount": main_components,
                "completeHydraulicComponentCount": union.component_count(),
                "fishwayEnabled": True,
            }
        )

    boundary_chains = {}
    for boundary in ("M", "N", "O", "G"):
        edges = [edge for edge, _, marker in boundary_edges if marker == OUTER_TAGS[boundary]]
        components, endpoints = chain_count(edges)
        boundary_chains[boundary] = {"faceCount": len(edges), "chainCount": components, "degreeOneEndpointCount": endpoints}

    protected_movement = {
        name: float(np.linalg.norm(mesh_vertices - point, axis=1).min())
        for name, point in protected_points.items()
    }
    gate_face_lengths: dict[str, float] = {}
    gate_h2_factors: dict[str, float] = {}
    for gate in range(1, 9):
        gate_segments = output_segments[output_markers == GATE_TAG_BASE + gate]
        length = float(
            np.linalg.norm(mesh_vertices[gate_segments[:, 1]] - mesh_vertices[gate_segments[:, 0]], axis=1).sum()
        )
        gate_face_lengths[str(gate)] = length
        gate_h2_factors[str(gate)] = 46.5 / length
    h2_reference = read_json(H2_APPROVAL)["referenceMetricLengthsM"]

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

    review_features = json.loads(json.dumps(cut_features))
    for feature in review_features:
        feature["properties"]["kind"] = (
            "review_only_gate_interface_constraint"
            if "gate_no" in feature["properties"]
            else "review_only_fixed_cut_constraint"
        )
    for side in ("upstream", "downstream"):
        review_features.append(
            {
                "type": "Feature",
                "id": f"P2_{side}_footprint",
                "properties": {"kind": "approved_P2_footprint", "side": side},
                "geometry": p2_footprints_lonlat[side],
            }
        )
        review_features.append(
            {
                "type": "Feature",
                "id": f"P2_{side}_refinement",
                "properties": {"kind": "review_only_refinement_control", "side": side},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        old.unproject_many(np.vstack([refinement_rings[side], refinement_rings[side][0]]))
                    ],
                },
            }
        )
    write_json(
        GEOMETRY,
        {
            "type": "FeatureCollection",
            "name": "stage20_barrage_H2_review_geometry_v2",
            "properties": {"status": "review_only_not_physical"},
            "features": review_features,
        },
    )

    centres = triangle_points.mean(axis=1)
    barrage_midpoint = cut_points.mean(axis=0)
    local_cells = np.where(np.linalg.norm(centres - barrage_midpoint, axis=1) <= 260.0)[0]
    upstream_set = set(p2_weights["upstream"]["cellIds"])
    downstream_set = set(p2_weights["downstream"]["cellIds"])
    visual_triangles = []
    for cell in local_cells:
        category = "ordinary"
        if int(cell) in upstream_set:
            category = "P2_upstream"
        elif int(cell) in downstream_set:
            category = "P2_downstream"
        visual_triangles.append(
            {
                "cell": int(cell),
                "category": category,
                "region": int(round(attributes[cell])),
                "coordinates": old.unproject_many(np.vstack([triangle_points[cell], triangle_points[cell][0]])),
            }
        )
    write_json(
        VISUAL_DATA,
        {
            "schema": "onga-stage20-barrage-H2-review-mesh-visual-data-v2",
            "status": "actual_generated_review_mesh_not_illustration",
            "trianglesWithin260M": visual_triangles,
            "water": water_feature["geometry"],
            "cut": cut,
            "P2": {
                side: {
                    "center": p2_approval[side]["coordinate"],
                    "footprint": p2_footprints_lonlat[side],
                    "refinement": review_features[-3 if side == "upstream" else -1]["geometry"],
                    "positiveOverlapCellIds": p2_weights[side]["cellIds"],
                }
                for side in ("upstream", "downstream")
            },
            "fishwayCenter": by_id["fishway_center_v2_authority"]["geometry"]["coordinates"],
            "H2": {
                "effectiveWidthM": 46.5,
                "exactGateFaceLengthsM": gate_face_lengths,
                "exactScaleFactors": gate_h2_factors,
            },
        },
    )

    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, value: Any, expected: Any) -> None:
        checks.append({"id": check_id, "pass": bool(passed), "value": value, "expected": expected})

    check("triangle_runtime", tr.__version__ == "20250106", tr.__version__, "20250106")
    check("cell_limit", len(triangles) <= 80000, len(triangles), "<=80000")
    check("finite_coordinates", bool(np.isfinite(mesh_vertices).all()), int(np.sum(~np.isfinite(mesh_vertices))), 0)
    check("positive_areas", bool(np.all(areas > 0.0)), int(np.sum(areas <= 0.0)), 0)
    check("global_area_limit", float(areas[attributes == 1].max()) <= 30.000001, float(areas[attributes == 1].max()), "<=30.000001")
    check("upstream_area_limit", float(areas[attributes == 2].max()) <= 3.000001, float(areas[attributes == 2].max()), "<=3.000001")
    check("downstream_area_limit", float(areas[attributes == 3].max()) <= 3.000001, float(areas[attributes == 3].max()), "<=3.000001")
    check("duplicate_cells", duplicate_cells == 0, duplicate_cells, 0)
    check("nonmanifold_faces", nonmanifold == 0, nonmanifold, 0)
    check("unattributed_below_30", len(unattributed_below) == 0, len(unattributed_below), 0)
    check("cut_continuity", len(cut_points) == 18, len(cut_points), 18)
    check("shore_contact_residual", max(contact_residuals) <= 0.003, max(contact_residuals), "<=0.003m")
    check(
        "review_mesh_near_duplicate_shore_vertex_replacement",
        max(contact_replacement_distances) <= 0.03,
        max(contact_replacement_distances),
        "<=0.03m; authority unchanged",
    )
    check("protected_coordinate_movement", max(protected_movement.values()) <= 1e-9, max(protected_movement.values()), "<=1e-9m")
    check("fixed_cut_faces", len(fixed_edges) > 0, len(fixed_edges), ">0")
    for gate in range(1, 9):
        check(f"gate_{gate}_face_count", len(gate_edges[gate]) > 0, len(gate_edges[gate]), ">0")
        check(
            f"gate_{gate}_exact_face_length",
            abs(gate_face_lengths[str(gate)] - h2_reference[gate - 1]) <= 1e-8,
            gate_face_lengths[str(gate)],
            h2_reference[gate - 1],
        )
        check(
            f"gate_{gate}_H2_effective_width",
            abs(gate_h2_factors[str(gate)] * gate_face_lengths[str(gate)] - 46.5) <= 1e-12,
            gate_h2_factors[str(gate)] * gate_face_lengths[str(gate)],
            46.5,
        )
    check("all_closed_main_cut_two_components", topology_states[0]["mainCutOnlyComponentCount"] == 2, topology_states[0]["mainCutOnlyComponentCount"], 2)
    check("any_open_main_cut_one_component", all(row["mainCutOnlyComponentCount"] == 1 for row in topology_states[1:]), sum(row["mainCutOnlyComponentCount"] == 1 for row in topology_states[1:]), 255)
    check("fishway_all_256_connected", all(row["completeHydraulicComponentCount"] == 1 for row in topology_states), sum(row["completeHydraulicComponentCount"] == 1 for row in topology_states), 256)
    for side in ("upstream", "downstream"):
        check(f"P2_{side}_cell_count", p2_weights[side]["positiveOverlapCellCount"] >= 27, p2_weights[side]["positiveOverlapCellCount"], ">=27")
        check(f"P2_{side}_weight_sum", p2_weights[side]["weightSumAbsoluteResidual"] <= 1e-12, p2_weights[side]["weightSumAbsoluteResidual"], "<=1e-12")
        check(f"P2_{side}_overlap_area", p2_weights[side]["overlapAreaRelativeResidual"] <= 1e-10, p2_weights[side]["overlapAreaRelativeResidual"], "<=1e-10")
    check("P2_disjoint_cells", len(shared_p2_cells) == 0, len(shared_p2_cells), 0)
    for boundary in ("M", "N", "O", "G"):
        check(f"open_{boundary}_single_chain", boundary_chains[boundary]["chainCount"] == 1, boundary_chains[boundary], "one chain")
    for path, expected in PROTECTED.items():
        check(f"protected_{path.name}", sha256(path) == expected, sha256(path), expected)

    failed = [row for row in checks if not row["pass"]]
    write_json(
        VALIDATION,
        {
            "schema": "onga-stage20-barrage-H2-review-mesh-static-validation-v2",
            "version": 2,
            "validatedAtLocal": "2026-07-23",
            "status": "PASS" if not failed else "FAIL",
            "passCount": len(checks) - len(failed),
            "checkCount": len(checks),
            "failedCount": len(failed),
            "checks": checks,
        },
    )
    if failed:
        raise ValueError(f"Static validation failed: {[row['id'] for row in failed]}")

    summary = {
        "schema": "onga-stage20-barrage-H2-review-mesh-summary-v2",
        "version": 2,
        "generatedAtLocal": "2026-07-23",
        "status": "review_only_actual_mesh_generated_static_PASS_pending_user_visual_judgment_not_physical",
        "authorization": binding(AUTHORIZATION),
        "inputs": {
            name: binding(path)
            for name, path in {
                "completeCut": CUT,
                "completeCutApproval": CUT_APPROVAL,
                "confirmedWaterAndOpenBoundaries": INTEGRATED,
                "gateEndpointAuthority": GATES,
                "H2Approval": H2_APPROVAL,
                "H2Contract": H2_CONTRACT,
                "BLocalRefinementApproval": B_APPROVAL,
                "P2Footprints": P2_CANDIDATE,
                "P2Approval": P2_APPROVAL,
                "F2cApproval": F2C_APPROVAL,
                "Q0Approval": Q0_APPROVAL,
            }.items()
        },
        "runtime": {"triangleVersion": tr.__version__, "options": "pq30aADzQ", "metricCrs": "EPSG:32652"},
        "counts": {
            "inputVertices": len(vertices),
            "vertices": len(mesh_vertices),
            "cells": len(triangles),
            "segments": len(output_segments),
            "internalFaces": len(internal_edges),
            "boundaryFaces": len(boundary_edges),
            "fixedCutFaceCount": len(fixed_edges),
            "gateFaceCounts": {str(gate): len(gate_edges[gate]) for gate in range(1, 9)},
            "nonmanifoldFaces": nonmanifold,
        },
        "quality": {
            "minimumAreaM2": float(areas.min()),
            "maximumAreaM2": float(areas.max()),
            "maximumOuterRegionAreaM2": float(areas[attributes == 1].max()),
            "maximumUpstreamRegionAreaM2": float(areas[attributes == 2].max()),
            "maximumDownstreamRegionAreaM2": float(areas[attributes == 3].max()),
            "minimumEdgeM": float(sides.min()),
            "minimumAngleDegree": float(minimum_angles.min()),
            "triangleBelow30DegreeCount": len(below_target),
            "unattributedTriangleBelow30DegreeCount": len(unattributed_below),
            "duplicateCellCount": duplicate_cells,
        },
        "geometry": {
            "waterAreaM2": float(water.area),
            "completeCutSegmentCount": len(cut_features),
            "gateSegmentCount": 8,
            "fixedSegmentCount": 9,
            "westShoreContact": cut_lonlat[0],
            "eastShoreContact": cut_lonlat[-1],
            "shoreContactBoundaryResidualsM": contact_residuals,
            "reviewMeshOnlyNearDuplicateShoreVertexReplacementDistancesM": contact_replacement_distances,
            "shorelineAuthorityChanged": False,
            "maximumProtectedCoordinateMovementM": max(protected_movement.values()),
            "gateExactMeshFaceLengthsM": gate_face_lengths,
            "gateH2ExactScaleFactors": gate_h2_factors,
            "gateH2EffectiveWidthsM": {
                gate: gate_h2_factors[gate] * gate_face_lengths[gate] for gate in gate_face_lengths
            },
        },
        "P2Weights": {**p2_weights, "sharedCellIds": shared_p2_cells},
        "topology": {
            "all256StateCount": len(topology_states),
            "allClosedMainCutOnlyComponentCount": topology_states[0]["mainCutOnlyComponentCount"],
            "mainCutOnlyAnyOpenOne": all(row["mainCutOnlyComponentCount"] == 1 for row in topology_states[1:]),
            "completeHydraulicAll256One": all(row["completeHydraulicComponentCount"] == 1 for row in topology_states),
            "fishwayEnabledStateCount": sum(row["fishwayEnabled"] for row in topology_states),
            "boundaryChains": boundary_chains,
            "states": topology_states,
        },
        "validation": binding(VALIDATION),
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
    summary["outputs"] = {
        str(path.relative_to(ROOT)): binding(path)
        for path in (MESH, GEOMETRY, VISUAL_DATA, VALIDATION)
    }
    write_json(SUMMARY, summary)
    print(
        json.dumps(
            {
                "result": "PASS_GENERATED_CORRECTED_REVIEW_ONLY_H2_MESH",
                "summary": binding(SUMMARY),
                "validation": binding(VALIDATION),
                "cells": len(triangles),
                "checks": f"{len(checks)}/{len(checks)}",
                "P2CellCounts": {
                    side: p2_weights[side]["positiveOverlapCellCount"] for side in ("upstream", "downstream")
                },
                "all256CompleteHydraulicOne": True,
                "solverRun": False,
                "precomputationRun": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
