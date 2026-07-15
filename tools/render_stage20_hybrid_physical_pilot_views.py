#!/usr/bin/env python3
"""Render the approved four views from a completed Stage 20 physical pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from render_stage20_hypothetical_routing_preview import (
    image_point_to_world,
    load_mesh,
    project_vertices,
    render_view,
)
from stage19_solver_inputs import mesh_geometry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fields")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest-output", required=True)
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    mesh_manifest, package = load_mesh(root / "public/data/onga/stage20/mesh-v1.json")
    geometry = mesh_geometry(package)
    data = np.load(args.fields, allow_pickle=False)
    depth = data["waterDepthM"].astype(np.float64)
    velocity_local = np.column_stack((data["velocityUms"], data["velocityVms"])).astype(np.float64)
    speed = np.linalg.norm(velocity_local, axis=1)
    if len(depth) != mesh_manifest["counts"]["cells"] or not np.isfinite(depth).all() or not np.isfinite(speed).all():
        raise RuntimeError("physical pilot fields do not match the approved mesh")
    positive = speed[speed > 1e-8]
    ceiling = float(np.percentile(positive, 95.0)) if len(positive) else 0.01

    water_manifest = json.loads((root / "data/onga_unified_water_manifest_r3.json").read_text(encoding="utf-8"))
    geographic = water_manifest["coordinateSystem"]["geographic"]
    triangles = geometry["triangles"]
    image_vertices = geometry["imageVertices"]
    image_centres = geometry["imageCentroids"]
    projections = {}
    for zoom in (16, 18):
        p_vertices = project_vertices(image_vertices, geographic, zoom)
        p_centres = p_vertices[triangles].mean(axis=1)
        endpoint_image = image_centres + np.column_stack((velocity_local[:, 0], -velocity_local[:, 1]))
        endpoint_world = np.asarray([image_point_to_world(point, geographic, zoom) for point in endpoint_image])
        velocity_screen = endpoint_world - p_centres
        velocity_screen *= np.divide(
            speed,
            np.maximum(np.linalg.norm(velocity_screen, axis=1), 1e-12),
        )[:, None]
        projections[zoom] = (p_vertices, p_centres, velocity_screen)

    internal_vertices = package["internal_face_vertices"].astype(np.int64)
    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    fishway_cells = package["fishway_cells"].astype(np.int64)
    confluence_image = np.asarray([1168.0, 441.0])
    tile_root = root / "data/external/gsi/seamlessphoto"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("pilot-estuary.jpg", "1／4　河口全域", 16, (56553, 26201, 56558, 26204), None, None, 68, False, ("barrage", "confluence")),
        ("pilot-barrage.jpg", "2／4　河口堰付近", 18, (226225, 104811, 226231, 104816), "barrage", (1100, 580), 58, True, ("barrage",)),
        ("pilot-confluence.jpg", "3／4　曲川・遠賀川合流地点付近", 18, (226224, 104808, 226231, 104814), "confluence", (1180, 625), 58, True, ("confluence",)),
        ("pilot-fishway.jpg", "4／4　魚道付近", 18, (226224, 104812, 226231, 104816), "fishway", (1040, 550), 52, True, ("fishway", "barrage")),
    ]
    views = []
    for filename, title, zoom, tile_box, centre_kind, crop_size, bins, mesh_lines, marks in specs:
        p_vertices, p_centres, velocity_screen = projections[zoom]
        barrage_segments = p_vertices[internal_vertices[barrage_ids]]
        fish_centres = p_centres[fishway_cells]
        confluence_world = image_point_to_world(confluence_image, geographic, zoom)
        centre = None
        if centre_kind == "barrage":
            centre = barrage_segments.mean(axis=(0, 1))
        elif centre_kind == "confluence":
            centre = confluence_world
        elif centre_kind == "fishway":
            centre = fish_centres.mean(axis=0)
        view = render_view(
            output=output_dir / filename,
            title=title,
            zoom=zoom,
            tile_box=tile_box,
            crop_center_world=centre,
            crop_size_world=crop_size,
            tile_root=tile_root,
            projected_vertices=p_vertices,
            triangles=triangles,
            projected_centres=p_centres,
            velocity_screen=velocity_screen,
            speed=speed,
            depth=depth,
            area=geometry["areas"],
            ceiling=ceiling,
            barrage_segments=barrage_segments,
            fishway_centres=fish_centres,
            confluence_world=confluence_world,
            bin_pixels=bins,
            draw_mesh=mesh_lines,
            marks=marks,
            scenario_label="推論入力：雨後3日相当・河口堰全開・大潮相当・下げ三分／開始後10分",
            disclaimer_label="一回限り物理パイロット／観測検証済みではない",
        )
        view["path"] = filename
        views.append(view)
    result = {
        "schema": "onga-stage20-hybrid-physical-pilot-visual-manifest-v1",
        "status": "rendered_not_physical_validation",
        "meshSha256": mesh_manifest["binary"]["sha256"],
        "cellCount": mesh_manifest["counts"]["cells"],
        "displayCeilingMPS": ceiling,
        "views": views,
        "fieldsSha256": hashlib.sha256(Path(args.fields).read_bytes()).hexdigest(),
        "safeguards": {"physicalValidationClaimAllowed": False, "publicSimulatorConnected": False},
    }
    Path(args.manifest_output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
