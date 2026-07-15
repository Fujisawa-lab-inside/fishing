#!/usr/bin/env python3
"""Render old/new barrage endpoint mesh patches on GSI aerial imagery."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_stage17_station_boundary_compatibility import image_to_latlon
from run_stage20_hybrid_physical_pilot import load_mesh


TILE_SIZE = 256


def lonlat_to_world_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    latitude = max(-85.05112878, min(85.05112878, float(lat)))
    scale = TILE_SIZE * (2**zoom)
    x = (float(lon) + 180.0) / 360.0 * scale
    y = (1.0 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2.0 * scale
    return x, y


def triangle_key(vertices: np.ndarray, triangle: np.ndarray) -> tuple:
    return tuple(sorted((round(float(vertices[index, 0]), 6), round(float(vertices[index, 1]), 6)) for index in triangle))


def cell_areas(package: dict[str, np.ndarray]) -> np.ndarray:
    vertices = package["vertex_local_mm"].astype(np.float64) * 1e-3
    points = vertices[package["triangles"].astype(np.int64)]
    return np.abs(
        (points[:, 1, 0] - points[:, 0, 0]) * (points[:, 2, 1] - points[:, 0, 1])
        - (points[:, 1, 1] - points[:, 0, 1]) * (points[:, 2, 0] - points[:, 0, 0])
    ) / 2.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--candidate",
        default="docs/results/stage20-barrage-endpoint-mesh-v2-candidate/onga_stage20_metric_fv_mesh_v2_boundary_snap_candidate.npz",
    )
    parser.add_argument(
        "--summary",
        default="docs/results/stage20-barrage-endpoint-mesh-v2-candidate/stage20_barrage_endpoint_patch_mesh_summary.json",
    )
    parser.add_argument("--manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--tile-directory", default="data/external/gsi/seamlessphoto/z18")
    parser.add_argument("--zoom", type=int, default=18)
    parser.add_argument("--min-x", type=int, default=226225)
    parser.add_argument("--max-x", type=int, default=226230)
    parser.add_argument("--min-y", type=int, default=104814)
    parser.add_argument("--max-y", type=int, default=104816)
    parser.add_argument(
        "--svg-output", default="docs/visuals/stage20-barrage-endpoint-mesh-decision-v1.svg"
    )
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    summary = json.loads((root / args.summary).read_text(encoding="utf-8"))
    old_manifest, old = load_mesh(root)
    with np.load(root / args.candidate, allow_pickle=False) as archive:
        new = {name: archive[name] for name in archive.files}

    tile_images = []
    tile_hashes = []
    tile_directory = root / args.tile_directory
    for tile_y in range(args.min_y, args.max_y + 1):
        for tile_x in range(args.min_x, args.max_x + 1):
            tile = tile_directory / f"{tile_x}-{tile_y}.jpg"
            payload = tile.read_bytes()
            tile_hashes.append(hashlib.sha256(payload).hexdigest())
            encoded = base64.b64encode(payload).decode("ascii")
            tile_images.append(
                f'<image x="{(tile_x - args.min_x) * TILE_SIZE}" '
                f'y="{(tile_y - args.min_y) * TILE_SIZE}" width="256.5" height="256.5" '
                f'href="data:image/jpeg;base64,{encoded}" preserveAspectRatio="none"/>'
            )
    imagery = "".join(tile_images)
    geographic = manifest["coordinateSystem"]["geographic"]

    def mosaic_point(image_point: np.ndarray) -> tuple[float, float]:
        latitude, longitude = image_to_latlon(
            float(image_point[0]), float(image_point[1]), geographic
        )
        world_x, world_y = lonlat_to_world_pixel(longitude, latitude, args.zoom)
        return world_x - args.min_x * TILE_SIZE, world_y - args.min_y * TILE_SIZE

    old_image = old["vertex_image_millipixel"].astype(np.float64) * 1e-3
    new_image = new["vertex_image_millipixel"].astype(np.float64) * 1e-3
    old_triangles = old["triangles"].astype(np.int64)
    new_triangles = new["triangles"].astype(np.int64)
    old_areas = cell_areas(old)
    new_areas = cell_areas(new)
    old_keys = {triangle_key(old_image, triangle) for triangle in old_triangles}
    new_keys = {triangle_key(new_image, triangle) for triangle in new_triangles}
    old_changed = old_keys - new_keys
    new_changed = new_keys - old_keys

    endpoints = [
        np.asarray(summary["patch"]["approvedEndpointsPixel"][1], dtype=np.float64),
        np.asarray(summary["patch"]["approvedEndpointsPixel"][0], dtype=np.float64),
    ]
    effective = [
        np.asarray(summary["patch"]["effectiveEndpointsPixel"][1], dtype=np.float64),
        np.asarray(summary["patch"]["effectiveEndpointsPixel"][0], dtype=np.float64),
    ]

    panels = [
        ("現行・左端", old_image, old_triangles, old_areas, old_changed, endpoints[0], 50, 235, "old-left"),
        ("現行・右端", old_image, old_triangles, old_areas, old_changed, endpoints[1], 825, 235, "old-right"),
        ("候補・左端", new_image, new_triangles, new_areas, new_changed, endpoints[0], 50, 625, "new-left"),
        ("候補・右端", new_image, new_triangles, new_areas, new_changed, endpoints[1], 825, 625, "new-right"),
    ]
    panel_width = 725
    panel_height = 330
    half_world_pixel = 25.0
    panel_scale = panel_width / (2 * half_world_pixel)
    panel_markup = []
    approved_line = [mosaic_point(point) for point in endpoints[::-1]]
    for label, vertices, triangles, areas, changed, center_image, left, top, clip_id in panels:
        center = mosaic_point(center_image)
        centroids = vertices[triangles].mean(axis=1)
        selected = np.linalg.norm(centroids - center_image, axis=1) < 6.0
        polygons = []
        for triangle, area in zip(triangles[selected], areas[selected]):
            points = [mosaic_point(vertices[index]) for index in triangle]
            point_text = " ".join(f"{x:.3f},{y:.3f}" for x, y in points)
            key = triangle_key(vertices, triangle)
            if key in changed:
                fill = "#f04438" if label.startswith("現行") else "#00a6a6"
                fill_opacity = "0.56"
                stroke = fill
                stroke_width = "0.75"
            elif label.startswith("現行") and area < 0.25:
                fill = "#f04438"
                fill_opacity = "0.62"
                stroke = "#f04438"
                stroke_width = "0.75"
            else:
                fill = "none"
                fill_opacity = "0"
                stroke = "#ffffff"
                stroke_width = "0.32"
            polygons.append(
                f'<polygon points="{point_text}" fill="{fill}" fill-opacity="{fill_opacity}" '
                f'stroke="{stroke}" stroke-width="{stroke_width}" vector-effect="non-scaling-stroke"/>'
            )
        transform_x = left + panel_width / 2 - center[0] * panel_scale
        transform_y = top + panel_height / 2 - center[1] * panel_scale
        line_color = "#f04438" if label.startswith("現行") else "#0089d0"
        marker = effective[0] if "左端" in label else effective[1]
        marker_world = mosaic_point(marker)
        panel_markup.append(f'''
<clipPath id="{clip_id}"><rect x="{left}" y="{top}" width="{panel_width}" height="{panel_height}" rx="14"/></clipPath>
<rect x="{left}" y="{top}" width="{panel_width}" height="{panel_height}" rx="14" fill="#cad3d6"/>
<g clip-path="url(#{clip_id})">
  <g transform="translate({transform_x:.5f} {transform_y:.5f}) scale({panel_scale:.8f})">{imagery}</g>
  <g transform="translate({transform_x:.5f} {transform_y:.5f}) scale({panel_scale:.8f})">
    {''.join(polygons)}
    <line x1="{approved_line[0][0]:.3f}" y1="{approved_line[0][1]:.3f}" x2="{approved_line[1][0]:.3f}" y2="{approved_line[1][1]:.3f}" stroke="#ffffff" stroke-width="1.1" vector-effect="non-scaling-stroke"/>
    <line x1="{approved_line[0][0]:.3f}" y1="{approved_line[0][1]:.3f}" x2="{approved_line[1][0]:.3f}" y2="{approved_line[1][1]:.3f}" stroke="#0089d0" stroke-width="0.55" vector-effect="non-scaling-stroke"/>
    <circle cx="{marker_world[0]:.3f}" cy="{marker_world[1]:.3f}" r="0.58" fill="{line_color}" stroke="#ffffff" stroke-width="0.22" vector-effect="non-scaling-stroke"/>
  </g>
</g>
<rect x="{left}" y="{top}" width="{panel_width}" height="{panel_height}" rx="14" fill="none" stroke="#ffffff" stroke-width="3"/>
<text x="{left + 20}" y="{top + 34}" class="panel" style="fill:#ffffff;stroke:#17313d;stroke-width:5px;paint-order:stroke fill">{label}</text>
''')

    old_min = float(old_areas.min())
    new_min = float(new_areas.min())
    changed_count = int(summary["patch"]["changedOldTriangleCount"])
    changed_percent = float(summary["patch"]["changedOldTriangleFraction"]) * 100
    endpoint_shift = summary["patch"]["endpointShiftPixel"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1135" viewBox="0 0 1600 1135" role="img" aria-labelledby="title desc">
<title id="title">河口堰両端の局所再メッシュ候補</title>
<desc id="desc">国土地理院の空中写真上で現行と候補の左右端メッシュを比較。候補は両端164セルだけを変更し、微小セルを解消する。</desc>
<style>
text{{font-family:"Hiragino Sans","Yu Gothic","Noto Sans CJK JP",sans-serif;fill:#17313d}}
.title{{font-size:42px;font-weight:600}}.sub{{font-size:22px;fill:#48626f}}.panel{{font-size:25px;font-weight:600}}
.metric{{font-size:24px;font-weight:600}}.small{{font-size:17px;fill:#48626f}}.decision{{font-size:25px;font-weight:600}}.choice{{font-size:23px;font-weight:600}}
</style>
<rect width="1600" height="1135" fill="#f4f7f8"/>
<text x="50" y="58" class="title">河口堰両端だけを修正した候補メッシュ</text>
<text x="50" y="98" class="sub">青い堰軸・8ゲート・魚道位置・河道外形を固定し、時間刻みを制限した端部パッチだけを置換</text>
<rect x="50" y="125" width="1500" height="82" rx="16" fill="#ffffff" stroke="#c7d3d8" stroke-width="2"/>
<text x="80" y="175" class="metric">変更 {changed_count} / 50,339セル（{changed_percent:.3f}%）</text>
<text x="575" y="175" class="metric">最小面積 {old_min:.4f} → {new_min:.3f} m²</text>
<text x="1110" y="175" class="metric">端点補正 {endpoint_shift[0]:.3f} / {endpoint_shift[1]:.3f} px</text>
{''.join(panel_markup)}
<rect x="50" y="985" width="1500" height="112" rx="16" fill="#e6f2f6" stroke="#0089d0" stroke-width="3"/>
<text x="80" y="1027" class="decision">判断すること：この局所候補をLinux確認へ進めるか</text>
<text x="80" y="1073" class="choice">A　この候補を採用（推奨）</text>
<text x="850" y="1073" class="choice">B　候補を修正する</text>
<text x="80" y="1123" class="small">赤：現行で置換される端部セル　青緑：候補の新しい端部セル　背景：国土地理院「全国最新写真（シームレス）」を加工</text>
</svg>
'''
    output = root / args.svg_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    result = {
        "schema": "onga-stage20-barrage-endpoint-mesh-decision-visual-v1",
        "status": "awaiting_visual_decision",
        "svg": str(output.relative_to(root)),
        "svgSha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "candidateArtifactSha256": summary["artifact"]["sha256"],
        "approvedBrowserMeshSha256": old_manifest["binary"]["sha256"],
        "imageryTileSetSha256": hashlib.sha256("".join(tile_hashes).encode("ascii")).hexdigest(),
        "changedOldTriangleCount": changed_count,
        "minimumCellAreaOldM2": old_min,
        "minimumCellAreaCandidateM2": new_min,
    }
    output.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
