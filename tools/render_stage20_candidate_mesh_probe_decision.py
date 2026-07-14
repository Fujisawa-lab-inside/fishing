#!/usr/bin/env python3
"""Render the local Stage 20 mesh probe and the next execution decision."""

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

from audit_stage17_station_boundary_compatibility import image_to_latlon  # noqa: E402
from render_stage20_barrage_satellite_comparison import (  # noqa: E402
    TILE_SIZE,
    lonlat_to_world_pixel,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mesh", default="stage20-mesh-probe/onga_stage20_metric_fv_mesh_v1_candidate.npz")
    parser.add_argument("--summary", default="stage20-mesh-probe/stage16_metric_mesh_summary.json")
    parser.add_argument("--metric-validation", default="stage20-mesh-probe/stage20_metric_solver_validation.json")
    parser.add_argument("--shallow-validation", default="stage20-mesh-probe/stage20_actual_mesh_shallow_water_validation.json")
    parser.add_argument("--well-balanced-validation", default="stage20-mesh-probe/stage20_actual_mesh_well_balanced_validation.json")
    parser.add_argument("--mode", choices=("probe", "result"), default="probe")
    parser.add_argument("--water-manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--tile-directory", default="data/external/gsi/seamlessphoto/z18")
    parser.add_argument("--svg-output", default="docs/visuals/stage20-candidate-mesh-probe-decision-v3.svg")
    parser.add_argument("--html-output", default="docs/visuals/stage20-candidate-mesh-probe-decision-v3.html")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    mesh_path = root / args.mesh
    summary_path = root / args.summary
    validation_paths = [
        root / args.metric_validation,
        root / args.shallow_validation,
        root / args.well_balanced_validation,
    ]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    validations = [json.loads(path.read_text(encoding="utf-8")) for path in validation_paths]
    if not all(item.get("status") == "passed" for item in validations):
        raise RuntimeError("all three local candidate-mesh validations must pass")
    manifest = json.loads((root / args.water_manifest).read_text(encoding="utf-8"))
    geographic = manifest["coordinateSystem"]["geographic"]

    with np.load(mesh_path) as package:
        vertices = package["vertex_image_millipixel"].astype(np.float64) / 1000.0
        internal_face_vertices = package["internal_face_vertices"].astype(np.int64)
        barrage_face_ids = package["barrage_face_ids"].astype(np.int64)
        fishway_cells = package["fishway_cells"].astype(np.int64)
        triangles = package["triangles"].astype(np.int64)

    zoom = 18
    min_x, max_x = 226225, 226230
    min_y, max_y = 104814, 104816
    mosaic_width = (max_x - min_x + 1) * TILE_SIZE
    mosaic_height = (max_y - min_y + 1) * TILE_SIZE
    map_left, map_top, map_width = 50.0, 155.0, 1500.0
    map_height = map_width * mosaic_height / mosaic_width
    map_scale = map_width / mosaic_width

    tile_images: list[str] = []
    for tile_y in range(min_y, max_y + 1):
        for tile_x in range(min_x, max_x + 1):
            tile_path = root / args.tile_directory / f"{tile_x}-{tile_y}.jpg"
            encoded = base64.b64encode(tile_path.read_bytes()).decode("ascii")
            local_x = (tile_x - min_x) * TILE_SIZE
            local_y = (tile_y - min_y) * TILE_SIZE
            tile_images.append(
                f'<image x="{local_x}" y="{local_y}" width="256.6" height="256.6" '
                f'href="data:image/jpeg;base64,{encoded}" preserveAspectRatio="none"/>'
            )

    screen_cache: dict[tuple[float, float], tuple[float, float]] = {}

    def screen_image(point: np.ndarray | list[float]) -> tuple[float, float]:
        key = (float(point[0]), float(point[1]))
        if key not in screen_cache:
            lat, lon = image_to_latlon(key[0], key[1], geographic)
            world_x, world_y = lonlat_to_world_pixel(lon, lat, zoom)
            screen_cache[key] = (
                map_left + (world_x - min_x * TILE_SIZE) * map_scale,
                map_top + (world_y - min_y * TILE_SIZE) * map_scale,
            )
        return screen_cache[key]

    wet_p0 = np.asarray(summary["barrageFullSpanImagePixel"][0], dtype=float)
    wet_p1 = np.asarray(summary["barrageFullSpanImagePixel"][1], dtype=float)
    line = wet_p1 - wet_p0
    line_length = float(np.linalg.norm(line))
    line_unit = line / line_length

    near_mesh: list[str] = []
    face_points = vertices[internal_face_vertices]
    midpoints = face_points.mean(axis=1)
    rel = midpoints - wet_p0
    along = rel @ line_unit
    orthogonal = np.abs(rel[:, 0] * line_unit[1] - rel[:, 1] * line_unit[0])
    selected = np.where((along >= -35.0) & (along <= line_length + 35.0) & (orthogonal <= 34.0))[0]
    for face_id in selected:
        a, b = face_points[face_id]
        x1, y1 = screen_image(a)
        x2, y2 = screen_image(b)
        near_mesh.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
        )

    barrage_lines: list[str] = []
    for face_id in barrage_face_ids:
        a, b = face_points[int(face_id)]
        x1, y1 = screen_image(a)
        x2, y2 = screen_image(b)
        barrage_lines.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
        )

    wet_screen = [screen_image(wet_p0), screen_image(wet_p1)]
    cut_span = [np.asarray(point, dtype=float) for point in summary["barrageCutSpanImagePixel"]]
    cut_screen = [screen_image(point) for point in cut_span]
    extension_lines = (
        f'<line x1="{cut_screen[0][0]:.2f}" y1="{cut_screen[0][1]:.2f}" '
        f'x2="{wet_screen[0][0]:.2f}" y2="{wet_screen[0][1]:.2f}"/>'
        f'<line x1="{cut_screen[1][0]:.2f}" y1="{cut_screen[1][1]:.2f}" '
        f'x2="{wet_screen[1][0]:.2f}" y2="{wet_screen[1][1]:.2f}"/>'
    )

    cell_centres = vertices[triangles].mean(axis=1)
    fishway_marks: list[str] = []
    fishway_labels = ["魚道・上流側", "魚道・河口側"]
    for label, cell_id in zip(fishway_labels, fishway_cells):
        x, y = screen_image(cell_centres[int(cell_id)])
        fishway_marks.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="10" fill="#f2b134" stroke="#ffffff" stroke-width="4"/>'
            f'<text x="{x + 15:.2f}" y="{y - 12:.2f}" class="maplabel">{label}</text>'
        )

    counts = summary["counts"]
    closed_components = int(validations[0]["diagnostics"]["closedComponents"])
    if args.mode == "result":
        title_text = "Linux x86候補メッシュ　確認結果"
        subtitle_text = "一回限りの確認は全工程合格。衛星・空中写真上で最終形状を判断"
        decision_text = "次の判断：このLinux候補メッシュ形状を採用するか"
        choice_a = "A　採用する（推奨）"
        choice_b = "B　再調整する"
        footer_text = "採用後は次の開発段階へ進む。物理流計算・64条件実行・公開・main反映は別判断。"
        run_text = "Linux run 29338332867"
    else:
        title_text = "承認済み青線による候補メッシュ"
        subtitle_text = "衛星・空中写真上のローカル診断。最終メッシュ同一性はLinux x86で未確定"
        decision_text = "次の判断：岸へ2 px接続した候補をLinux x86で一回だけ作成するか"
        choice_a = "A　この形で実行（推奨・目安5～10分）"
        choice_b = "B　実行せず停止"
        footer_text = "最大20分で停止。CI時間と30日保存の成果物を使う。物理流計算・64条件実行・公開・main反映は行わない。"
        run_text = "背景：国土地理院"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1260" viewBox="0 0 1600 1260" role="img" aria-labelledby="title desc">
<title id="title">{title_text}</title>
<desc id="desc">国土地理院の空中写真上に候補メッシュ、河口堰閉鎖面、2ピクセルの岸接続補正、魚道の上流側と河口側セルを表示する判断画像。</desc>
<style>
text{{font-family:"Hiragino Sans","Yu Gothic","Noto Sans CJK JP",sans-serif;fill:#17313d}}
.title{{font-size:43px;font-weight:600}}.sub{{font-size:22px;fill:#48626f}}.body{{font-size:21px}}.small{{font-size:17px;fill:#48626f}}.decision{{font-size:26px;font-weight:600}}.choice{{font-size:23px;font-weight:600}}.maplabel{{font-size:18px;font-weight:600;fill:#ffffff;stroke:#70500d;stroke-width:5px;paint-order:stroke fill}}
</style>
<rect width="1600" height="1260" fill="#f4f7f8"/>
<text x="50" y="62" class="title">{title_text}</text>
<text x="50" y="104" class="sub">{subtitle_text}</text>
<rect x="{map_left:.0f}" y="{map_top:.0f}" width="{map_width:.0f}" height="{map_height:.0f}" rx="18" fill="#d7dcdf"/>
<clipPath id="mapClip"><rect x="{map_left:.0f}" y="{map_top:.0f}" width="{map_width:.0f}" height="{map_height:.0f}" rx="18"/></clipPath>
<g clip-path="url(#mapClip)">
  <g transform="translate({map_left:.3f} {map_top:.3f}) scale({map_scale:.9f})">{''.join(tile_images)}</g>
  <g stroke="#64d7ee" stroke-width="1.4" opacity="0.62">{''.join(near_mesh)}</g>
  <line x1="{wet_screen[0][0]:.2f}" y1="{wet_screen[0][1]:.2f}" x2="{wet_screen[1][0]:.2f}" y2="{wet_screen[1][1]:.2f}" stroke="#ffffff" stroke-width="16" opacity="0.86"/>
  <g stroke="#087fba" stroke-width="8" stroke-linecap="round">{''.join(barrage_lines)}</g>
  <g stroke="#f28e2b" stroke-width="12" stroke-linecap="round">{extension_lines}</g>
  {''.join(fishway_marks)}
</g>
<rect x="50" y="930" width="1500" height="118" rx="18" fill="#ffffff" stroke="#c7d3d8" stroke-width="2"/>
<line x1="80" y1="971" x2="150" y2="971" stroke="#64d7ee" stroke-width="3"/><text x="168" y="979" class="body">候補メッシュ</text>
<line x1="390" y1="971" x2="460" y2="971" stroke="#087fba" stroke-width="8"/><text x="478" y="979" class="body">閉鎖面 {counts['barrageFaces']}本</text>
<line x1="730" y1="971" x2="770" y2="971" stroke="#f28e2b" stroke-width="11"/><text x="788" y="979" class="body">岸へ2 px接続</text>
<circle cx="1068" cy="971" r="9" fill="#f2b134"/><text x="1087" y="979" class="body">魚道の両側セル</text>
<text x="80" y="1025" class="small">{counts['cells']:,}セル／閉鎖時 {closed_components}領域／形状・保存・浅水・水深勾配検査 3/3合格</text>
<text x="1030" y="1025" class="small">{run_text}</text>
<rect x="50" y="1075" width="1500" height="135" rx="18" fill="#e6f2f6" stroke="#087fba" stroke-width="3"/>
<text x="85" y="1120" class="decision">{decision_text}</text>
<text x="85" y="1168" class="choice">{choice_a}</text>
<text x="845" y="1168" class="choice">{choice_b}</text>
<text x="85" y="1238" class="small">{footer_text}</text>
</svg>
'''
    svg_output = root / args.svg_output
    svg_output.parent.mkdir(parents=True, exist_ok=True)
    svg_output.write_text(svg, encoding="utf-8")

    encoded_svg = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    html = f'''<div id="stage20-candidate-mesh-probe-decision" style="display:grid;gap:0.75rem;color:var(--foreground);">
  <img src="data:image/svg+xml;base64,{encoded_svg}" alt="空中写真上の候補メッシュと、一回限りのLinux x86プローブを実行するかの判断画像" style="display:block;width:100%;height:auto;" />
</div>
'''
    html_output = root / args.html_output
    html_output.write_text(html, encoding="utf-8")

    result = {
        "schema": "onga-stage20-linux-mesh-result-decision-v1" if args.mode == "result" else "onga-stage20-candidate-mesh-probe-decision-v1",
        "status": "awaiting_linux_candidate_visual_approval" if args.mode == "result" else "awaiting_linux_probe_authorization",
        "localProbe": {
            "platform": summary["platform"],
            "mesh": args.mesh,
            "meshSha256": sha256(mesh_path),
            "summary": args.summary,
            "summarySha256": sha256(summary_path),
            "counts": counts,
            "closedComponents": closed_components,
            "fishwayComponents": counts["fishwayComponents"],
            "barrageCutExtensionPixel": summary["barrageCutExtensionPixel"],
            "validationStatuses": [item["status"] for item in validations],
        },
        "nextDecision": (
            {
                "A": "approve_linux_candidate_mesh_geometry_recommended",
                "B": "return_to_mesh_adjustment",
                "doesNotAuthorize": ["physical_flow_run", "full64", "publish", "main_merge"],
            }
            if args.mode == "result"
            else {
                "A": "push_candidate_branch_and_run_one_linux_x86_probe_recommended",
                "B": "stop_without_external_execution",
                "expectedMinutes": [5, 10],
                "timeoutMinutes": 20,
                "doesNotAuthorize": ["physical_flow_run", "full64", "publish", "main_merge"],
            }
        ),
        "outputs": {"svg": args.svg_output, "html": args.html_output},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
