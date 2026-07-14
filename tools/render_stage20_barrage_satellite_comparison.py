#!/usr/bin/env python3
"""Render the Stage 20 barrage decision on official GSI aerial imagery."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_stage17_station_boundary_compatibility import image_to_latlon  # noqa: E402


TILE_SIZE = 256


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lonlat_to_world_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    latitude = max(-85.05112878, min(85.05112878, float(lat)))
    scale = TILE_SIZE * (2**zoom)
    x = (float(lon) + 180.0) / 360.0 * scale
    y = (
        1.0
        - math.asinh(math.tan(math.radians(latitude))) / math.pi
    ) / 2.0 * scale
    return x, y


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--geometry", default="public/data/onga/onga_geometry.geojson")
    parser.add_argument("--manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--constraints", default="data/onga_stage16_mesh_constraints_v2.json")
    parser.add_argument("--candidate", default="config/stage20_barrage_coordinate_candidate_v1.json")
    parser.add_argument("--tile-directory", default="data/external/gsi/seamlessphoto/z18")
    parser.add_argument("--zoom", type=int, default=18)
    parser.add_argument("--min-x", type=int, default=226225)
    parser.add_argument("--max-x", type=int, default=226230)
    parser.add_argument("--min-y", type=int, default=104814)
    parser.add_argument("--max-y", type=int, default=104816)
    parser.add_argument("--svg-output", default="docs/visuals/stage20-barrage-satellite-comparison-v2.svg")
    parser.add_argument("--html-output", default="docs/visuals/stage20-barrage-satellite-comparison-v2.html")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    geometry_path = root / args.geometry
    manifest_path = root / args.manifest
    constraints_path = root / args.constraints
    candidate_path = root / args.candidate
    tile_directory = root / args.tile_directory

    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    geographic = manifest["coordinateSystem"]["geographic"]

    gates: list[dict[str, float | int]] = []
    for feature in geometry["features"]:
        properties = feature.get("properties", {})
        if properties.get("kind") != "gate_center":
            continue
        longitude, latitude = feature["geometry"]["coordinates"]
        gates.append(
            {
                "gate": int(properties["gate_no"]),
                "longitude": float(longitude),
                "latitude": float(latitude),
            }
        )
    gates.sort(key=lambda item: int(item["gate"]))
    if [item["gate"] for item in gates] != list(range(1, 9)):
        raise RuntimeError("exactly gate centres 1 through 8 are required")

    tile_columns = args.max_x - args.min_x + 1
    tile_rows = args.max_y - args.min_y + 1
    mosaic_width = tile_columns * TILE_SIZE
    mosaic_height = tile_rows * TILE_SIZE

    tiles: list[dict[str, str | int]] = []
    tile_images: list[str] = []
    for tile_y in range(args.min_y, args.max_y + 1):
        for tile_x in range(args.min_x, args.max_x + 1):
            tile_path = tile_directory / f"{tile_x}-{tile_y}.jpg"
            if not tile_path.is_file():
                raise RuntimeError(f"missing GSI tile: {tile_path}")
            encoded = base64.b64encode(tile_path.read_bytes()).decode("ascii")
            local_x = (tile_x - args.min_x) * TILE_SIZE
            local_y = (tile_y - args.min_y) * TILE_SIZE
            tile_images.append(
                f'<image x="{local_x}" y="{local_y}" width="256.6" height="256.6" '
                f'href="data:image/jpeg;base64,{encoded}" preserveAspectRatio="none"/>'
            )
            tiles.append(
                {
                    "x": tile_x,
                    "y": tile_y,
                    "path": str(tile_path.relative_to(root)),
                    "sha256": sha256(tile_path),
                    "url": (
                        "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/"
                        f"{args.zoom}/{tile_x}/{tile_y}.jpg"
                    ),
                }
            )

    map_left = 50.0
    map_top = 155.0
    map_width = 1500.0
    map_height = map_width * mosaic_height / mosaic_width
    map_scale = map_width / mosaic_width

    def local_pixel(lon: float, lat: float) -> tuple[float, float]:
        world_x, world_y = lonlat_to_world_pixel(lon, lat, args.zoom)
        return (
            world_x - args.min_x * TILE_SIZE,
            world_y - args.min_y * TILE_SIZE,
        )

    def screen(lon: float, lat: float) -> tuple[float, float]:
        x, y = local_pixel(lon, lat)
        return map_left + x * map_scale, map_top + y * map_scale

    gate_screen = [
        screen(float(gate["longitude"]), float(gate["latitude"])) for gate in gates
    ]

    proposed_image = candidate["coordinateDerivedCandidate"]["fullWetSpanImagePixel"]
    proposed_latlon = [
        image_to_latlon(float(point[0]), float(point[1]), geographic)
        for point in proposed_image
    ]
    proposed_screen = [screen(lon, lat) for lat, lon in proposed_latlon]

    current_data = constraints["barrageHardConstraint"]
    current_image = [
        current_data["endpoint0Pixel"],
        current_data["endpoint1Pixel"],
    ]
    current_latlon = [
        image_to_latlon(float(point[0]), float(point[1]), geographic)
        for point in current_image
    ]
    current_screen = [screen(lon, lat) for lat, lon in current_latlon]

    gate_marks: list[str] = []
    for gate, (x, y) in zip(gates, gate_screen):
        gate_marks.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="10" fill="#0888c9" '
            'stroke="#ffffff" stroke-width="4"/>'
            f'<text x="{x:.2f}" y="{y - 18:.2f}" class="gate" '
            f'text-anchor="middle">{gate["gate"]}</text>'
        )

    average_offset = float(candidate["difference"]["averageOffsetM"])
    maximum_offset = float(candidate["difference"]["maximumOffsetM"])
    imagery_sha = hashlib.sha256(
        "".join(str(tile["sha256"]) for tile in tiles).encode("ascii")
    ).hexdigest()

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1260" viewBox="0 0 1600 1260" role="img" aria-labelledby="title desc">
<title id="title">遠賀川河口堰を国土地理院の空中写真上で比較</title>
<desc id="desc">青の実線は提供された1番から8番ゲート座標から作った河口堰位置、赤の破線は現在のStage19堰線。青線を採用するかを判断する画像。</desc>
<style>
text{{font-family:"Hiragino Sans","Yu Gothic","Noto Sans CJK JP",sans-serif;fill:#17313d}}
.title{{font-size:44px;font-weight:600}}.sub{{font-size:23px;fill:#48626f}}
.body{{font-size:22px}}.small{{font-size:18px;fill:#48626f}}.gate{{font-size:20px;font-weight:600;fill:#ffffff;stroke:#075b83;stroke-width:5px;paint-order:stroke fill}}
.decision{{font-size:27px;font-weight:600}}.choice{{font-size:24px;font-weight:600}}
</style>
<rect width="1600" height="1260" fill="#f4f7f8"/>
<text x="50" y="62" class="title">遠賀川河口堰　実際の空中写真との位置比較</text>
<text x="50" y="104" class="sub">提供済み1～8番ゲート座標と、現在のStage 19堰線を同じ緯度経度で重ね合わせ</text>
<rect x="{map_left:.0f}" y="{map_top:.0f}" width="{map_width:.0f}" height="{map_height:.0f}" rx="18" fill="#d7dcdf"/>
<clipPath id="mapClip"><rect x="{map_left:.0f}" y="{map_top:.0f}" width="{map_width:.0f}" height="{map_height:.0f}" rx="18"/></clipPath>
<g clip-path="url(#mapClip)">
  <g transform="translate({map_left:.3f} {map_top:.3f}) scale({map_scale:.9f})">{''.join(tile_images)}</g>
  <line x1="{current_screen[0][0]:.2f}" y1="{current_screen[0][1]:.2f}" x2="{current_screen[1][0]:.2f}" y2="{current_screen[1][1]:.2f}" stroke="#ffffff" stroke-width="16" opacity="0.88"/>
  <line x1="{current_screen[0][0]:.2f}" y1="{current_screen[0][1]:.2f}" x2="{current_screen[1][0]:.2f}" y2="{current_screen[1][1]:.2f}" stroke="#d9483b" stroke-width="9" stroke-dasharray="22 14"/>
  <line x1="{proposed_screen[0][0]:.2f}" y1="{proposed_screen[0][1]:.2f}" x2="{proposed_screen[1][0]:.2f}" y2="{proposed_screen[1][1]:.2f}" stroke="#ffffff" stroke-width="17" opacity="0.9"/>
  <line x1="{proposed_screen[0][0]:.2f}" y1="{proposed_screen[0][1]:.2f}" x2="{proposed_screen[1][0]:.2f}" y2="{proposed_screen[1][1]:.2f}" stroke="#0888c9" stroke-width="10"/>
  {''.join(gate_marks)}
</g>
<g transform="translate(1478 188)">
  <path d="M0 42 L0 0 L-11 18 L0 13 L11 18 Z" fill="#ffffff" stroke="#17313d" stroke-width="2"/>
  <text x="0" y="66" text-anchor="middle" class="small" style="fill:#ffffff;stroke:#17313d;stroke-width:4px;paint-order:stroke fill">北</text>
</g>
<rect x="50" y="930" width="1500" height="118" rx="18" fill="#ffffff" stroke="#c7d3d8" stroke-width="2"/>
<line x1="85" y1="975" x2="185" y2="975" stroke="#0888c9" stroke-width="10"/><text x="210" y="984" class="body">青実線・丸1～8：提供座標から作った候補</text>
<line x1="780" y1="975" x2="880" y2="975" stroke="#d9483b" stroke-width="9" stroke-dasharray="22 14"/><text x="905" y="984" class="body">赤破線：現在のStage 19堰線</text>
<text x="85" y="1025" class="small">現在線との差：平均 約{average_offset:.1f} m／最大 約{maximum_offset:.1f} m</text>
<text x="600" y="1025" class="small">背景：国土地理院「全国最新写真（シームレス）」Z18（2026-07-14取得）</text>
<rect x="50" y="1075" width="1500" height="135" rx="18" fill="#e6f2f6" stroke="#0888c9" stroke-width="3"/>
<text x="85" y="1120" class="decision">判断すること：河口堰位置をどちらにするか</text>
<text x="85" y="1170" class="choice">A　青線を採用（推奨）</text>
<text x="820" y="1170" class="choice">B　赤破線を維持</text>
<text x="85" y="1238" class="small">この判断では位置だけを確定します。新メッシュ作成・数値計算・main反映はまだ行いません。</text>
</svg>
'''

    svg_output = root / args.svg_output
    svg_output.parent.mkdir(parents=True, exist_ok=True)
    svg_output.write_text(svg, encoding="utf-8")

    encoded_svg = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    html = f'''<div id="stage20-barrage-satellite-comparison" style="display:grid;gap:0.75rem;color:var(--foreground);">
  <img src="data:image/svg+xml;base64,{encoded_svg}" alt="国土地理院の空中写真上で、提供座標の青線と現在の赤破線を比較した河口堰位置判断画像" style="display:block;width:100%;height:auto;" />
</div>
'''
    html_output = root / args.html_output
    html_output.write_text(html, encoding="utf-8")

    result = {
        "schema": "onga-stage20-barrage-satellite-comparison-v1",
        "status": "awaiting_visual_decision",
        "imagery": {
            "name": "GSI Maps seamlessphoto / 全国最新写真（シームレス）",
            "tileTemplate": "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg",
            "zoom": args.zoom,
            "retrievedDate": "2026-07-14",
            "tileCount": len(tiles),
            "tileSetSha256": imagery_sha,
            "tiles": tiles,
            "attribution": "背景：国土地理院『全国最新写真（シームレス）』を加工して作成",
        },
        "providedGateCoordinates": {
            "path": args.geometry,
            "sha256": sha256(geometry_path),
            "gateCount": len(gates),
        },
        "candidateLine": {
            "source": args.candidate,
            "fullWetSpanLatLon": proposed_latlon,
        },
        "currentStage19Line": {
            "source": args.constraints,
            "sha256": sha256(constraints_path),
            "endpointsLatLon": current_latlon,
        },
        "difference": {
            "averageOffsetM": average_offset,
            "maximumOffsetM": maximum_offset,
        },
        "outputs": {
            "svg": args.svg_output,
            "html": args.html_output,
        },
        "decision": {
            "A": "adopt_blue_coordinate_derived_line_recommended",
            "B": "keep_red_stage19_line",
            "approvalDoesNotAuthorize": ["mesh_generation", "numerical_run", "main_merge"],
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
