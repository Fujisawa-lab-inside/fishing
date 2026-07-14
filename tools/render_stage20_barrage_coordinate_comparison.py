#!/usr/bin/env python3
"""Compare the frozen Stage 19 barrage constraint with user-provided gate coordinates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_stage17_station_boundary_compatibility import (  # noqa: E402
    haversine_m,
    image_to_latlon,
    latlon_to_image,
    load_water,
    row_contains,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dot(left: tuple[float, float], right: tuple[float, float]) -> float:
    return left[0] * right[0] + left[1] * right[1]


def fit_line(points: list[tuple[float, float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    centre = (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )
    sxx = sum((point[0] - centre[0]) ** 2 for point in points)
    syy = sum((point[1] - centre[1]) ** 2 for point in points)
    sxy = sum((point[0] - centre[0]) * (point[1] - centre[1]) for point in points)
    angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    direction = (math.cos(angle), math.sin(angle))
    if direction[0] < 0:
        direction = (-direction[0], -direction[1])
    return centre, direction


def project_to_line(
    point: tuple[float, float],
    origin: tuple[float, float],
    direction: tuple[float, float],
) -> tuple[float, float]:
    distance = dot((point[0] - origin[0], point[1] - origin[1]), direction)
    return origin[0] + distance * direction[0], origin[1] + distance * direction[1]


def wet_span(
    rows: list[list[int]],
    width: int,
    height: int,
    origin: tuple[float, float],
    direction: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    step = 0.05
    count = int(2000.0 / step) + 1
    values: list[bool] = []
    for index in range(count):
        t = -1000.0 + index * step
        x = origin[0] + t * direction[0]
        y = origin[1] + t * direction[1]
        ix, iy = math.floor(x), math.floor(y)
        values.append(0 <= ix < width and 0 <= iy < height and row_contains(rows[iy], ix))
    middle = int(round(1000.0 / step))
    if not values[middle]:
        candidates = [index for index, value in enumerate(values) if value]
        if not candidates:
            raise RuntimeError("coordinate-derived barrage line does not intersect the water domain")
        middle = min(candidates, key=lambda index: abs(index - middle))
    low = high = middle
    while low > 0 and values[low - 1]:
        low -= 1
    while high + 1 < len(values) and values[high + 1]:
        high += 1
    low_t = -1000.0 + low * step
    high_t = -1000.0 + high * step
    return (
        (origin[0] + low_t * direction[0], origin[1] + low_t * direction[1]),
        (origin[0] + high_t * direction[0], origin[1] + high_t * direction[1]),
    )


def water_rectangles(
    rows: list[list[int]], crop: tuple[float, float, float, float]
) -> str:
    x0, y0, x1, y1 = crop
    rectangles: list[str] = []
    for y in range(max(0, math.floor(y0)), min(len(rows), math.ceil(y1))):
        row = rows[y]
        for start, end in zip(row[0::2], row[1::2]):
            left, right = max(float(start), x0), min(float(end + 1), x1)
            if right > left:
                rectangles.append(
                    f'<rect x="{left - x0:.3f}" y="{y - y0:.3f}" '
                    f'width="{right - left:.3f}" height="1.06"/>'
                )
    return "".join(rectangles)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--geometry", default="public/data/onga/onga_geometry.geojson")
    parser.add_argument("--manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--constraints", default="data/onga_stage16_mesh_constraints_v2.json")
    parser.add_argument("--svg-output", default="docs/visuals/stage20-barrage-coordinate-comparison.svg")
    parser.add_argument("--html-output", default="docs/visuals/stage20-barrage-coordinate-comparison.html")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    geometry_path = root / args.geometry
    manifest_path = root / args.manifest
    constraints_path = root / args.constraints
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
    manifest, rows = load_water(manifest_path)
    geographic = manifest["coordinateSystem"]["geographic"]

    gates: list[dict] = []
    for feature in geometry["features"]:
        properties = feature.get("properties", {})
        if properties.get("kind") != "gate_center":
            continue
        longitude, latitude = feature["geometry"]["coordinates"]
        image_x, image_y = latlon_to_image(latitude, longitude, geographic)
        gates.append(
            {
                "gate": int(properties["gate_no"]),
                "longitude": float(longitude),
                "latitude": float(latitude),
                "image": (float(image_x), float(image_y)),
            }
        )
    gates.sort(key=lambda item: item["gate"])
    if [item["gate"] for item in gates] != list(range(1, 9)):
        raise RuntimeError("exactly gate centres 1 through 8 are required")

    centre, direction = fit_line([item["image"] for item in gates])
    proposed_span = wet_span(rows, int(manifest["width"]), int(manifest["height"]), centre, direction)
    current = constraints["barrageHardConstraint"]
    current_endpoints = [
        tuple(float(value) for value in current["endpoint0Pixel"]),
        tuple(float(value) for value in current["endpoint1Pixel"]),
    ]
    current_origin = current_endpoints[0]
    current_vector = (
        current_endpoints[1][0] - current_endpoints[0][0],
        current_endpoints[1][1] - current_endpoints[0][1],
    )
    current_length = math.hypot(*current_vector)
    current_direction = (current_vector[0] / current_length, current_vector[1] / current_length)
    offsets_m: list[float] = []
    for gate in gates:
        projected = project_to_line(gate["image"], current_origin, current_direction)
        gate_latlon = [gate["latitude"], gate["longitude"]]
        projected_latlon = image_to_latlon(projected[0], projected[1], geographic)
        offsets_m.append(haversine_m(gate_latlon, projected_latlon))

    all_points = current_endpoints + list(proposed_span) + [item["image"] for item in gates]
    crop = (
        min(point[0] for point in all_points) - 70.0,
        min(point[1] for point in all_points) - 90.0,
        max(point[0] for point in all_points) + 70.0,
        max(point[1] for point in all_points) + 90.0,
    )
    crop_width, crop_height = crop[2] - crop[0], crop[3] - crop[1]
    map_left, map_top, map_width, map_height = 70.0, 210.0, 1050.0, 960.0
    scale = min(map_width / crop_width, map_height / crop_height)
    draw_width, draw_height = crop_width * scale, crop_height * scale
    offset_x = map_left + (map_width - draw_width) / 2.0
    offset_y = map_top + (map_height - draw_height) / 2.0

    def screen(point: tuple[float, float]) -> tuple[float, float]:
        return (
            offset_x + (point[0] - crop[0]) * scale,
            offset_y + (point[1] - crop[1]) * scale,
        )

    current_screen = [screen(point) for point in current_endpoints]
    proposed_screen = [screen(point) for point in proposed_span]
    gate_marks = []
    for gate in gates:
        x, y = screen(gate["image"])
        gate_marks.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="9" fill="#0b6f91" stroke="#ffffff" stroke-width="3"/>'
            f'<text x="{x:.2f}" y="{y - 15:.2f}" class="gate" text-anchor="middle">{gate["gate"]}</text>'
        )

    water = water_rectangles(rows, crop)
    average_offset = sum(offsets_m) / len(offsets_m)
    max_offset = max(offsets_m)
    proposed_angle = math.degrees(math.atan2(direction[1], direction[0]))
    result = {
        "schema": "onga-stage20-barrage-coordinate-comparison-v1",
        "status": "awaiting_visual_decision",
        "authoritativeGeometry": {
            "path": args.geometry,
            "sha256": sha256(geometry_path),
            "gateCount": 8,
            "coordinateOrder": "[longitude, latitude]",
        },
        "frozenStage19Constraint": {
            "path": args.constraints,
            "sha256": sha256(constraints_path),
            "endpointsImagePixel": [list(point) for point in current_endpoints],
        },
        "coordinateDerivedCandidate": {
            "fitMethod": "orthogonal_least_squares_through_all_eight_projected_gate_centres",
            "lineAngleImageDegrees": proposed_angle,
            "fullWetSpanImagePixel": [list(point) for point in proposed_span],
            "gateResidualPixels": [
                abs(
                    (gate["image"][0] - centre[0]) * direction[1]
                    - (gate["image"][1] - centre[1]) * direction[0]
                )
                for gate in gates
            ],
        },
        "difference": {
            "gateToCurrentLineOffsetM": offsets_m,
            "averageOffsetM": average_offset,
            "maximumOffsetM": max_offset,
        },
        "decision": {
            "question": "青線を今後の数値メッシュ・表示・釣り制約に共通する河口堰位置として採用するか",
            "approvalDoesNotAuthorize": ["mesh_generation", "numerical_run", "main_merge"],
        },
    }

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1600" viewBox="0 0 1600 1600" role="img" aria-labelledby="title desc">
<title id="title">河口堰位置の比較</title>
<desc id="desc">現在の数値メッシュの堰線と、ユーザー提供の1番から8番ゲートの緯度経度から作った堰線を水面上で比較する。青線を採用するか判断する資料。</desc>
<style>
text{{font-family:"Hiragino Sans","Yu Gothic","Noto Sans CJK JP",sans-serif;fill:#17313d}}
.title{{font-size:48px;font-weight:600}}.sub{{font-size:25px;fill:#526d79}}.section{{font-size:28px;font-weight:600}}
.body{{font-size:22px}}.small{{font-size:18px;fill:#526d79}}.metric{{font-size:34px;font-weight:600}}
.gate{{font-size:18px;font-weight:600;fill:#0b6f91}}.decision{{font-size:29px;font-weight:600}}
</style>
<rect width="1600" height="1600" fill="#f4f7f8"/>
<text x="70" y="78" class="title">遠賀川河口堰　位置の比較</text>
<text x="70" y="125" class="sub">提供済み1～8番ゲート座標を正本として再構成</text>
<rect x="70" y="165" width="1050" height="1050" rx="20" fill="#e8e2d7" stroke="#c7d3d8" stroke-width="2"/>
<clipPath id="mapClip"><rect x="70" y="165" width="1050" height="1050" rx="20"/></clipPath>
<g clip-path="url(#mapClip)">
  <g transform="translate({offset_x:.3f} {offset_y:.3f}) scale({scale:.6f})" fill="#b9dfeb">{water}</g>
  <line x1="{current_screen[0][0]:.2f}" y1="{current_screen[0][1]:.2f}" x2="{current_screen[1][0]:.2f}" y2="{current_screen[1][1]:.2f}" stroke="#b34b37" stroke-width="9" stroke-dasharray="18 12"/>
  <line x1="{proposed_screen[0][0]:.2f}" y1="{proposed_screen[0][1]:.2f}" x2="{proposed_screen[1][0]:.2f}" y2="{proposed_screen[1][1]:.2f}" stroke="#0b6f91" stroke-width="9"/>
  {''.join(gate_marks)}
</g>
<text x="90" y="205" class="small">上：河口側</text><text x="90" y="1180" class="small">下：上流側</text>

<rect x="1160" y="165" width="370" height="1050" rx="20" fill="#ffffff" stroke="#c7d3d8" stroke-width="2"/>
<text x="1200" y="220" class="section">線の意味</text>
<line x1="1200" y1="270" x2="1290" y2="270" stroke="#0b6f91" stroke-width="9"/><text x="1310" y="278" class="body">提供座標</text>
<line x1="1200" y1="325" x2="1290" y2="325" stroke="#b34b37" stroke-width="9" stroke-dasharray="18 12"/><text x="1310" y="333" class="body">現在の堰線</text>
<circle cx="1215" cy="380" r="9" fill="#0b6f91" stroke="#ffffff" stroke-width="3"/><text x="1240" y="388" class="body">ゲート中心</text>
<text x="1200" y="470" class="small">現在線までの平均ずれ</text>
<text x="1200" y="515" class="metric">約{average_offset:.1f} m</text>
<text x="1200" y="580" class="small">最大ずれ</text>
<text x="1200" y="625" class="metric">約{max_offset:.1f} m</text>
<text x="1200" y="700" class="small">青線の作り方</text>
<text x="1200" y="740" class="body">8座標すべてで</text>
<text x="1200" y="777" class="body">向きを決定</text>
<text x="1200" y="814" class="body">水面の両岸まで延長</text>
<text x="1200" y="875" class="small">旧Stage 19結果は変更しない</text>
<text x="1200" y="960" class="small">採用後の処理</text>
<text x="1200" y="1000" class="body">青線を正本として</text>
<text x="1200" y="1037" class="body">新メッシュを作成</text>
<text x="1200" y="1095" class="small">数値計算は別承認</text>

<rect x="70" y="1270" width="1460" height="150" rx="20" fill="#e6f2f6" stroke="#0b6f91" stroke-width="3"/>
<text x="105" y="1330" class="decision">判断すること：青線を新しい河口堰位置として採用するか</text>
<text x="105" y="1380" class="small">採用後に新メッシュを作成する。追加の数値計算・main反映は含まない。</text>
</svg>
'''
    svg_output = root / args.svg_output
    svg_output.parent.mkdir(parents=True, exist_ok=True)
    svg_output.write_text(svg, encoding="utf-8")

    html = f'''<div id="stage20-barrage-coordinate-comparison" style="display:grid;gap:1rem;color:var(--foreground);">
  <div class="viz-grid">
    <div class="card viz-stat"><span class="text-muted">使用座標</span><span class="viz-stat-value">1～8番ゲート</span><span class="text-small text-muted">過去の提供値</span></div>
    <div class="card viz-stat"><span class="text-muted">現在線との平均差</span><span class="viz-stat-value">約{average_offset:.1f} m</span><span class="text-small text-muted">現行ジオリファレンス上</span></div>
  </div>
  <svg viewBox="0 0 720 300" role="img" aria-label="現在の河口堰線と提供座標から作った堰線の比較" style="width:100%;height:auto;display:block;">
    <rect x="15" y="15" width="690" height="230" rx="12" fill="var(--muted)"/>
    <path d="M20 85 C180 45 320 70 700 45 L700 215 C470 175 250 230 20 190 Z" fill="var(--viz-series-3)" opacity="0.28"/>
    <line x1="115" y1="170" x2="620" y2="115" stroke="var(--viz-series-2)" stroke-width="6" stroke-dasharray="12 8"/>
    <line x1="115" y1="135" x2="620" y2="75" stroke="var(--viz-series-1)" stroke-width="6"/>
    <g fill="var(--viz-series-1)">{''.join(f'<circle cx="{150 + index * 65}" cy="{131 - index * 7.7}" r="6"/>' for index in range(8))}</g>
    <text x="25" y="275" fill="var(--foreground)">実線：提供座標　　破線：現在の数値メッシュ</text>
  </svg>
  <div class="card"><strong>判断：</strong>提供座標から作った線を新しい河口堰位置として採用するか</div>
</div>
'''
    html_output = root / args.html_output
    html_output.write_text(html, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
