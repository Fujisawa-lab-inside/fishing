#!/usr/bin/env python3
"""Create a Stage 20 mesh candidate by remeshing only the barrage endpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import triangle as tr

from generate_stage16_metric_mesh import (
    barrage,
    coords,
    edges,
    fish,
    h,
    load_constraints,
    load_water,
    tags,
)


PACKAGE_KEYS = (
    "vertex_local_mm",
    "vertex_image_millipixel",
    "triangles",
    "internal_face_vertices",
    "internal_face_cells",
    "boundary_face_vertices",
    "boundary_face_cell",
    "boundary_face_tag",
    "barrage_face_ids",
    "barrage_gate_id",
    "fishway_cells",
    "fishway_components",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_current_mesh(root: Path) -> tuple[dict, dict[str, np.ndarray]]:
    sys.path.insert(0, str(root / "tools"))
    from run_stage20_hybrid_physical_pilot import load_mesh

    return load_mesh(root)


def boundary_cycle(boundary_edges: np.ndarray) -> list[int]:
    adjacency: dict[int, list[int]] = {}
    for first, second in boundary_edges:
        adjacency.setdefault(int(first), []).append(int(second))
        adjacency.setdefault(int(second), []).append(int(first))
    require(all(len(neighbors) == 2 for neighbors in adjacency.values()), "boundary is not a cycle")
    start = min(adjacency)
    cycle = [start]
    previous = None
    current = start
    while True:
        first, second = adjacency[current]
        following = first if first != previous else second
        if following == start:
            break
        cycle.append(following)
        previous, current = current, following
    require(len(cycle) == len(adjacency), "boundary cycle is incomplete")
    return cycle


def cross(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return first[..., 0] * second[..., 1] - first[..., 1] * second[..., 0]


def boundary_intersections(
    vertices: np.ndarray,
    cycle: list[int],
    endpoint0: np.ndarray,
    endpoint1: np.ndarray,
) -> tuple[list[dict], float, np.ndarray]:
    direction = endpoint1 - endpoint0
    length = float(np.linalg.norm(direction))
    require(length > 0, "zero-length barrage")
    unit = direction / length
    hits = []
    for index in range(len(cycle)):
        first = vertices[cycle[index]]
        second = vertices[cycle[(index + 1) % len(cycle)]]
        edge = second - first
        denominator = float(cross(unit, edge))
        if abs(denominator) <= 1e-12:
            continue
        delta = first - endpoint0
        along = float(cross(delta, edge) / denominator)
        fraction = float(cross(delta, unit) / denominator)
        if -1e-9 <= fraction <= 1.0 + 1e-9:
            hits.append({
                "cycleEdge": index,
                "along": along,
                "fraction": min(max(fraction, 0.0), 1.0),
                "point": first + fraction * edge,
            })
    before = [item for item in hits if item["along"] <= 1e-7]
    after = [item for item in hits if item["along"] >= length - 1e-7]
    require(before and after, "approved barrage axis is not bracketed by the water boundary")
    return [max(before, key=lambda item: item["along"]), min(after, key=lambda item: item["along"])], length, unit


def triangle_key(vertices: np.ndarray, triangle: np.ndarray) -> tuple:
    return tuple(sorted((round(float(vertices[index, 0]), 6), round(float(vertices[index, 1]), 6)) for index in triangle))


def assemble_local_candidate(
    package: dict[str, np.ndarray],
    constraints: dict,
) -> tuple[np.ndarray, np.ndarray, dict]:
    old_vertices = package["vertex_image_millipixel"].astype(np.float64) * 1e-3
    old_triangles = package["triangles"].astype(np.int64)
    old_boundary_edges = package["boundary_face_vertices"].astype(np.int64)
    approved = np.asarray([
        constraints["barrageHardConstraint"]["endpoint0Pixel"],
        constraints["barrageHardConstraint"]["endpoint1Pixel"],
    ], dtype=np.float64)
    patch_radius = float(constraints["endpointPatchRadiusPixel"])
    reversion_radius = float(constraints["localChangeMaximumRadiusPixel"])
    maximum_snap = float(constraints["barrageBoundarySnapMaximumPixel"])

    distance_to_endpoint = np.minimum(
        np.linalg.norm(old_vertices - approved[0], axis=1),
        np.linalg.norm(old_vertices - approved[1], axis=1),
    )
    removed = distance_to_endpoint < patch_radius
    kept_ids = np.where(~removed)[0]
    old_to_candidate = np.full(len(old_vertices), -1, dtype=np.int64)
    old_to_candidate[kept_ids] = np.arange(len(kept_ids))
    candidate_vertices = old_vertices[kept_ids].tolist()

    old_cycle = boundary_cycle(old_boundary_edges)
    filtered_cycle = [index for index in old_cycle if not removed[index]]
    intersections, barrage_length, unit = boundary_intersections(
        old_vertices, filtered_cycle, approved[0], approved[1]
    )
    effective = np.asarray([item["point"] for item in intersections])
    endpoint_shift = np.linalg.norm(effective - approved, axis=1)
    require(
        np.all(endpoint_shift <= maximum_snap),
        f"endpoint snap exceeds approved maximum {maximum_snap}: {endpoint_shift.tolist()}",
    )
    snap_ids = []
    for item in intersections:
        snap_ids.append(len(candidate_vertices))
        candidate_vertices.append(item["point"].tolist())

    segments: list[list[int]] = []
    markers: list[int] = []
    for cycle_edge in range(len(filtered_cycle)):
        chain = [int(old_to_candidate[filtered_cycle[cycle_edge]])]
        chain.extend(
            snap for item, snap in zip(intersections, snap_ids, strict=True)
            if int(item["cycleEdge"]) == cycle_edge
        )
        chain.append(int(old_to_candidate[filtered_cycle[(cycle_edge + 1) % len(filtered_cycle)]]))
        for first, second in zip(chain, chain[1:]):
            segments.append([first, second])
            markers.append(1)

    line_distance = np.abs(cross(
        old_vertices - approved[0],
        np.broadcast_to(unit, old_vertices.shape),
    ))
    along = (old_vertices - approved[0]) @ unit
    on_line = (
        (line_distance < 0.0015)
        & (along >= -0.01)
        & (along <= barrage_length + 0.01)
        & ~removed
    )
    line_ids = np.where(on_line)[0][np.argsort(along[on_line])]
    barrage_chain = [snap_ids[0]] + [int(old_to_candidate[index]) for index in line_ids] + [snap_ids[1]]
    for first, second in zip(barrage_chain, barrage_chain[1:]):
        segments.append([first, second])
        markers.append(3)

    triangulated = tr.triangulate(
        {
            "vertices": np.asarray(candidate_vertices, dtype=np.float64),
            "segments": np.asarray(segments, dtype=np.int32),
            "segment_markers": np.asarray(markers, dtype=np.int32)[:, None],
        },
        "pq30a30Q",
    )
    generated_vertices = np.asarray(triangulated["vertices"], dtype=np.float64)
    generated_triangles = np.asarray(triangulated["triangles"], dtype=np.int64)

    old_by_key = {triangle_key(old_vertices, triangle): triangle for triangle in old_triangles}
    generated_by_key = {
        triangle_key(generated_vertices, triangle): triangle for triangle in generated_triangles
    }
    common = set(old_by_key) & set(generated_by_key)
    old_only = set(old_by_key) - common
    generated_only = set(generated_by_key) - common

    def key_distance(key: tuple) -> float:
        centroid = np.mean(np.asarray(key, dtype=np.float64), axis=0)
        return float(min(np.linalg.norm(centroid - approved[0]), np.linalg.norm(centroid - approved[1])))

    old_far = {key for key in old_only if key_distance(key) >= reversion_radius}
    generated_near = {key for key in generated_only if key_distance(key) < reversion_radius}
    require(len(old_only - old_far) > 0 and len(generated_near) > 0, "local patch is empty")

    coordinate_to_generated = {
        (round(float(point[0]), 6), round(float(point[1]), 6)): index
        for index, point in enumerate(generated_vertices)
    }
    final_triangles = []
    final_keys = common | old_far | generated_near
    for triangle in generated_triangles:
        key = triangle_key(generated_vertices, triangle)
        if key in final_keys:
            final_triangles.append(triangle.tolist())
    generated_keys_used = {triangle_key(generated_vertices, np.asarray(item)) for item in final_triangles}
    for key in sorted(old_far - generated_keys_used):
        final_triangles.append([coordinate_to_generated[point] for point in key])

    final_triangles_array = np.asarray(final_triangles, dtype=np.int64)
    used_vertices = np.unique(final_triangles_array)
    compact = np.full(len(generated_vertices), -1, dtype=np.int64)
    compact[used_vertices] = np.arange(len(used_vertices))
    final_vertices = generated_vertices[used_vertices]
    final_triangles_array = compact[final_triangles_array].astype(np.int32)

    final_keys_check = {triangle_key(final_vertices, triangle) for triangle in final_triangles_array}
    require(final_keys_check == final_keys, "final triangle set differs from selected local patch")
    changed_old = old_only - old_far
    changed_new = generated_near
    changed_points = np.asarray([point for key in changed_old | changed_new for point in key])
    diagnostics = {
        "patchRadiusPixel": patch_radius,
        "localChangeMaximumRadiusPixel": reversion_radius,
        "removedVertexCount": int(removed.sum()),
        "unchangedOldTriangleCount": len(common) + len(old_far),
        "changedOldTriangleCount": len(changed_old),
        "changedNewTriangleCount": len(changed_new),
        "changedOldTriangleFraction": len(changed_old) / len(old_triangles),
        "changedRegionBboxPixel": [
            float(changed_points[:, 0].min()),
            float(changed_points[:, 1].min()),
            float(changed_points[:, 0].max()),
            float(changed_points[:, 1].max()),
        ],
        "approvedEndpointsPixel": approved.tolist(),
        "effectiveEndpointsPixel": effective.tolist(),
        "endpointShiftPixel": endpoint_shift.tolist(),
    }
    return final_vertices, final_triangles_array, diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--constraints", default="data/onga_stage20_mesh_constraints_v2.json")
    parser.add_argument("--water-manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--output", default="stage20-barrage-endpoint-mesh-v2-candidate")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    output = (root / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    constraints = load_constraints(root / args.constraints)
    water_manifest, water = load_water(root, root / args.water_manifest)
    old_manifest, old_package = load_current_mesh(root)
    image_vertices, triangles, patch = assemble_local_candidate(old_package, constraints)

    edge_map, internal, boundary, centroids = edges(image_vertices, triangles)
    boundary_tags, openings = tags(water_manifest, boundary)
    # barrage() needs the constrained chain as marker-3 segments. Reconstruct it from final edges.
    approved = np.asarray(patch["approvedEndpointsPixel"])
    direction = approved[1] - approved[0]
    length = float(np.linalg.norm(direction))
    unit = direction / length
    distance = np.abs(cross(image_vertices - approved[0], np.broadcast_to(unit, image_vertices.shape)))
    along = (image_vertices - approved[0]) @ unit
    on_line = (distance < 0.002) & (along >= -0.1) & (along <= length + 0.1)
    internal_edges = internal[:, :2].astype(np.int32)
    marker_edges = internal_edges[on_line[internal_edges[:, 0]] & on_line[internal_edges[:, 1]]]
    require(len(marker_edges) > 0, "barrage marker chain is empty")
    mesh_for_barrage = {
        "vertices": image_vertices,
        "triangles": triangles,
        "segments": marker_edges,
        "segment_markers": np.full(len(marker_edges), 3, dtype=np.int32),
    }
    cut, gate, wet0, wet1, cut0, cut1 = barrage(
        water, mesh_for_barrage, internal, centroids,
        constraints.get("barrageCutExtensionPixel", 0.0),
    )
    fishway_cells, fishway_components, _ = fish(
        water_manifest, constraints, internal, boundary, openings, cut, centroids
    )

    world, _ = coords(water_manifest["coordinateSystem"])
    metric = np.asarray([world(point) for point in image_vertices])
    origin = metric.mean(axis=0)
    local = metric - origin
    local_mm = np.rint(local * 1000).astype(np.int32)
    image_millipixel = np.rint(image_vertices * 1000).astype(np.int32)
    metric_points = local[triangles]
    areas = np.abs(
        (metric_points[:, 1, 0] - metric_points[:, 0, 0])
        * (metric_points[:, 2, 1] - metric_points[:, 0, 1])
        - (metric_points[:, 1, 1] - metric_points[:, 0, 1])
        * (metric_points[:, 2, 0] - metric_points[:, 0, 0])
    ) / 2.0
    internal_lengths = internal[:, 4]
    boundary_lengths = boundary[:, 3]
    perimeter = (
        np.bincount(internal[:, 2].astype(int), weights=internal_lengths, minlength=len(triangles))
        + np.bincount(internal[:, 3].astype(int), weights=internal_lengths, minlength=len(triangles))
        + np.bincount(boundary[:, 2].astype(int), weights=boundary_lengths, minlength=len(triangles))
    )
    area_perimeter = areas / perimeter
    require(float(areas.min()) >= float(constraints["meshQualityTarget"]["minimumCellAreaM2"]), "minimum cell area target failed")
    require(patch["changedOldTriangleFraction"] <= 0.01, "more than one percent of old cells changed")

    package = {
        "vertex_local_mm": local_mm,
        "vertex_image_millipixel": image_millipixel,
        "triangles": triangles.astype(np.int32),
        "internal_face_vertices": internal[:, :2].astype(np.int32),
        "internal_face_cells": internal[:, 2:4].astype(np.int32),
        "boundary_face_vertices": boundary[:, :2].astype(np.int32),
        "boundary_face_cell": boundary[:, 2].astype(np.int32),
        "boundary_face_tag": boundary_tags,
        "barrage_face_ids": cut,
        "barrage_gate_id": gate,
        "fishway_cells": fishway_cells,
        "fishway_components": fishway_components,
    }
    require(set(package) == set(PACKAGE_KEYS), "package array set mismatch")
    artifact = output / constraints["artifactFile"]
    with artifact.open("wb") as handle:
        np.savez_compressed(handle, **package)

    fishway_centroids = centroids[fishway_cells]
    approved_fishway = np.asarray(constraints["fishwayApprovedImagePixel"], dtype=np.float64)
    counts = {
        "vertices": len(image_vertices),
        "cells": len(triangles),
        "internalFaces": len(internal),
        "boundaryFaces": len(boundary),
        "barrageFaces": len(cut),
        "boundaryFaceCounts": {
            name: int(np.sum(boundary_tags == tag))
            for name, tag in (("shoreline", 0), ("M", 1), ("N", 2), ("O", 3), ("G", 4))
        },
        "gateFaceCounts": {str(index): int(np.sum(gate == index)) for index in range(1, 9)},
        "fishwayCells": fishway_cells.tolist(),
        "fishwayComponents": fishway_components.tolist(),
    }
    summary = {
        "schema": "onga-stage20-barrage-endpoint-patch-mesh-result-v1",
        "version": constraints["version"],
        "status": "local-darwin-arm64-candidate-not-canonical",
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "source": {
            "approvedBrowserMeshSha256": old_manifest["binary"]["sha256"],
            "constraints": args.constraints,
            "waterManifest": args.water_manifest,
        },
        "artifact": {
            "path": artifact.name,
            "sha256": sha256(artifact),
        },
        "counts": counts,
        "patch": patch,
        "quality": {
            "totalAreaM2": float(areas.sum()),
            "minimumCellAreaM2": float(areas.min()),
            "medianCellAreaM2": float(np.median(areas)),
            "cellsBelow0_25M2": int(np.sum(areas < 0.25)),
            "cellsBelow0_5M2": int(np.sum(areas < 0.5)),
            "minimumAreaPerimeterM": float(area_perimeter.min()),
        },
        "barrage": {
            "faceCount": len(cut),
            "gateFaceCounts": counts["gateFaceCounts"],
            "wetSpanImagePixel": [wet0.tolist(), wet1.tolist()],
            "cutSpanImagePixel": [cut0.tolist(), cut1.tolist()],
        },
        "fishway": {
            "approvedImagePixel": approved_fishway.tolist(),
            "cellCentroidsImagePixel": fishway_centroids.tolist(),
            "distanceToApprovedPixel": np.linalg.norm(fishway_centroids - approved_fishway, axis=1).tolist(),
        },
        "packageArrayHashes": {name: h(value) for name, value in package.items()},
        "safeguards": {
            "physicalValuesAssigned": False,
            "numericalExecutionPerformed": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False,
            "linuxCanonicalProbeCompleted": False,
        },
    }
    summary_path = output / "stage20_barrage_endpoint_patch_mesh_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
