#!/usr/bin/env python3
"""Render the actual Stage 20 synthetic hybrid-v2 snapshot in four approved views."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_stage20_hypothetical_routing_preview import (  # noqa: E402
    image_point_to_world,
    load_mesh,
    project_vertices,
    render_view,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_snapshot(root: Path, snapshot_index: int) -> tuple[dict, dict, np.ndarray]:
    manifest_path = root / "public/data/onga/stage20/response-pack-synthetic-v2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    binary_path = manifest_path.parent / manifest["binary"]["url"]
    payload = binary_path.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == manifest["binary"]["sha256"], "response-pack digest mismatch")
    descriptor = manifest["arrays"]["basis"]
    basis = np.frombuffer(payload, dtype="<f4").reshape(descriptor["shape"])
    inputs = json.loads((root / "public/data/onga/stage20/hybrid-synthetic-input-v1.json").read_text(encoding="utf-8"))
    require(inputs["hours"][snapshot_index] == 0, "selected snapshot is not the present hour")
    factors = []
    for mode in manifest["modes"]:
        if mode["kind"] == "constant":
            factors.append(1.0)
        else:
            value = inputs[mode["input"]][snapshot_index]
            factors.append((value - mode["offset"]) / mode["scale"])
    fields = np.tensordot(np.asarray(factors, dtype=np.float64), basis.astype(np.float64), axes=(0, 0))
    require(fields.shape == (3, manifest["mesh"]["cellCount"]), "snapshot shape mismatch")
    require(np.all(np.isfinite(fields)), "snapshot contains non-finite values")
    return manifest, inputs, fields


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default="docs/visuals")
    parser.add_argument("--report", default="config/stage20_hybrid_v2_visual_validation_v1.json")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    mesh_manifest, package = load_mesh(root / "public/data/onga/stage20/mesh-v2.json")
    response_manifest, _, fields = load_snapshot(root, snapshot_index=12)
    require(response_manifest["mesh"]["sha256"] == mesh_manifest["binary"]["sha256"], "mesh identity mismatch")

    image_vertices = package["vertex_image_millipixel"].astype(np.float64) / 1000.0
    local_vertices = package["vertex_local_mm"].astype(np.float64) / 1000.0
    triangles = package["triangles"].astype(np.int64)
    image_centres = image_vertices[triangles].mean(axis=1)
    local_triangles = local_vertices[triangles]
    edge_a = local_triangles[:, 1] - local_triangles[:, 0]
    edge_b = local_triangles[:, 2] - local_triangles[:, 0]
    areas = 0.5 * np.abs(edge_a[:, 0] * edge_b[:, 1] - edge_a[:, 1] * edge_b[:, 0])
    depth = fields[0]
    velocity_local = fields[1:3].T
    speed = np.linalg.norm(velocity_local, axis=1)
    moving = speed > 1e-6
    ceiling = float(np.percentile(speed[moving], 95.0))

    water_manifest = json.loads((root / "data/onga_unified_water_manifest_r3.json").read_text(encoding="utf-8"))
    geographic = water_manifest["coordinateSystem"]["geographic"]
    projections: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for zoom in (16, 18):
        projected_vertices = project_vertices(image_vertices, geographic, zoom)
        projected_centres = projected_vertices[triangles].mean(axis=1)
        endpoint_image = image_centres + np.column_stack((velocity_local[:, 0], -velocity_local[:, 1]))
        endpoint_world = np.asarray([image_point_to_world(point, geographic, zoom) for point in endpoint_image])
        velocity_screen = endpoint_world - projected_centres
        velocity_screen *= np.divide(
            speed,
            np.maximum(np.linalg.norm(velocity_screen, axis=1), 1e-12),
        )[:, None]
        projections[zoom] = (projected_vertices, projected_centres, velocity_screen)

    internal_vertices = package["internal_face_vertices"].astype(np.int64)
    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    fishway_cells = package["fishway_cells"].astype(np.int64)
    confluence_image = np.asarray([1168.0, 441.0])
    tile_root = root / "data/external/gsi/seamlessphoto"
    output_dir = root / args.output_dir
    scenario_label = "メッシュv2合成応答パック／現在時刻（0時間）"
    disclaimer = "表示経路確認用の合成場／物理事前計算結果ではない"
    specs = [
        ("stage20-hybrid-v2-estuary.jpg", "1／4　河口全域", 16, (56553, 26201, 56558, 26204), None, None, 68, False, ("barrage", "confluence")),
        ("stage20-hybrid-v2-barrage.jpg", "2／4　河口堰付近", 18, (226224, 104808, 226231, 104816), "barrage", (1100, 580), 58, True, ("barrage",)),
        ("stage20-hybrid-v2-confluence.jpg", "3／4　曲川・遠賀川合流地点付近", 18, (226224, 104808, 226231, 104816), "confluence", (1180, 625), 58, True, ("confluence",)),
        ("stage20-hybrid-v2-fishway.jpg", "4／4　魚道付近", 18, (226224, 104808, 226231, 104816), "fishway", (1040, 550), 52, True, ("fishway", "barrage")),
    ]
    views = []
    for filename, title, zoom, tile_box, centre_kind, crop_size, bins, mesh_lines, marks in specs:
        projected_vertices, projected_centres, velocity_screen = projections[zoom]
        barrage_segments = projected_vertices[internal_vertices[barrage_ids]]
        fish_centres = projected_centres[fishway_cells]
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
            projected_vertices=projected_vertices,
            triangles=triangles,
            projected_centres=projected_centres,
            velocity_screen=velocity_screen,
            speed=speed,
            depth=depth,
            area=areas,
            ceiling=ceiling,
            barrage_segments=barrage_segments,
            fishway_centres=fish_centres,
            confluence_world=confluence_world,
            bin_pixels=bins,
            draw_mesh=mesh_lines,
            marks=marks,
            scenario_label=scenario_label,
            disclaimer_label=disclaimer,
        )
        view["path"] = str((output_dir / filename).relative_to(root))
        views.append(view)

    report = {
        "schema": "onga-stage20-hybrid-v2-visual-validation-v1",
        "status": "rendered_synthetic_response_path_only",
        "mesh": {
            "manifest": "public/data/onga/stage20/mesh-v2.json",
            "binarySha256": mesh_manifest["binary"]["sha256"],
            "cells": mesh_manifest["counts"]["cells"],
        },
        "responsePack": {
            "manifest": "public/data/onga/stage20/response-pack-synthetic-v2.json",
            "binarySha256": response_manifest["binary"]["sha256"],
            "snapshotHour": 0,
        },
        "diagnostics": {
            "minimumDepthM": float(depth.min()),
            "maximumDepthM": float(depth.max()),
            "maximumSpeedMPS": float(speed.max()),
            "speedP95MPS": ceiling,
            "nonFiniteValueCount": 0,
        },
        "views": views,
        "safeguards": {
            "syntheticResponsePackOnly": True,
            "physicalSolverExecuted": False,
            "publicSimulatorConnected": False,
            "mainMergeAuthorized": False,
        },
    }
    report_path = root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
