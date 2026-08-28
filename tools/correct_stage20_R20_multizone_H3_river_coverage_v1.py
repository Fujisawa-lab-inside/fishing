#!/usr/bin/env python3
"""Correct the H3 scope audit: the 200 m Euclidean band includes side-river cells."""

from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

import generate_stage20_fishway_F3_review_mesh_v1 as old
import render_stage20_R20_multizone_mesh_v2_decision as common


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ONLY_ROOT = ROOT / ".stage20-local-only"
THREAD = (
    LOCAL_ONLY_ROOT
    / "visualizations"
    / "019f7538-8861-7831-b3d3-29723d9fb8c3"
)
RESULT = ROOT / "docs/results/stage20-R20-multizone-H3-river-coverage-correction-v1"
SUMMARY = RESULT / "correction-summary.json"
MESH = ROOT / "docs/results/stage20-R20-multizone-H3-local-patch-mesh-v1/review-mesh.npz"
MESH_SUMMARY = ROOT / "docs/results/stage20-R20-multizone-H3-local-patch-mesh-v1/mesh-summary.json"
CUT = ROOT / "config/stage20_barrage_bank_to_bank_cut_authority_v1.geojson"
PREVIOUS_AUDIT = (
    ROOT
    / "docs/results/stage20-R20-multizone-H3-confluence-scope-audit-v1/audit-summary.json"
)
PHOTO = common.PHOTO
OUTPUT = ROOT / "docs/visuals/stage20-R20-multizone-H3-river-coverage-correction-v1.jpg"
THREAD_IMAGE = THREAD / "h3-river-coverage-correction.webp"
THREAD_HTML = THREAD / "h3-river-coverage-correction.html"

EXPECTED = {
    MESH: "10f1a9bc6b5e66067faf7a87d65f2b2be8859958baaa9ae4884dc5fa8cf2137b",
    MESH_SUMMARY: "4ce08c3ebc20bd955992160933a3d50b142b40637038374648cc1a49e343f04b",
    CUT: "f8cc19aab4983b5f22b786021ae1b64550db49c3170a1bec3503bcfc8c26b132",
    PREVIOUS_AUDIT: "1b584a9d7d53e6396192df5dde1df8494af93f3ef1a6e834380e111c8f88e93c",
}

COMPONENTS = {
    0: {
        "id": "main_channel",
        "label": "遠賀川主流側",
        "colour": (24, 224, 219, 140),
    },
    1: {
        "id": "nishikawa_side_channel",
        "label": "西川側水路",
        "colour": (255, 74, 188, 180),
    },
    2: {
        "id": "magarigawa_side_channel",
        "label": "曲川側水路",
        "colour": (255, 154, 48, 180),
    },
}


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
    try:
        label = str(path.relative_to(ROOT))
    except ValueError:
        label = str(path)
    return {
        "path": label,
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def metric_to_tile(coordinates: np.ndarray) -> np.ndarray:
    return np.asarray(
        [common.tile_pixel(point) for point in old.unproject_many(coordinates)],
        dtype=np.float64,
    )


def fixed_component_assignment(
    vertices: np.ndarray,
    triangles: np.ndarray,
    fixed: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    fixed_ids = np.flatnonzero(fixed)
    fixed_polygons = [Polygon(vertices[triangles[index]]) for index in fixed_ids]
    union = unary_union(fixed_polygons)
    if union.geom_type != "MultiPolygon" or len(union.geoms) != 3:
        raise ValueError(f"expected three fixed water components, got {union.geom_type}")
    components = sorted(union.geoms, key=lambda geometry: geometry.area, reverse=True)
    assignment = np.full(len(triangles), -1, dtype=np.int8)
    records: list[dict[str, Any]] = []
    for component_id, geometry in enumerate(components):
        members = [
            int(cell_id)
            for cell_id, polygon in zip(fixed_ids, fixed_polygons, strict=True)
            if geometry.covers(polygon.representative_point())
        ]
        assignment[members] = component_id
        centroid_m = np.asarray([[geometry.centroid.x, geometry.centroid.y]])
        records.append(
            {
                "componentIndex": component_id,
                "id": COMPONENTS[component_id]["id"],
                "label": COMPONENTS[component_id]["label"],
                "cellCount": len(members),
                "areaM2": float(geometry.area),
                "centroidLonLat": old.unproject_many(centroid_m)[0],
                "boundsM": [float(value) for value in geometry.bounds],
            }
        )
    if np.any(fixed & (assignment < 0)):
        raise ValueError("one or more fixed cells were not assigned to a component")
    return assignment, records


def draw_dashed_path(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    *,
    fill: tuple[int, int, int, int],
    width: int,
) -> None:
    for index, (left, right) in enumerate(zip(points[:-1], points[1:], strict=True)):
        if index % 3 != 2:
            draw.line([left, right], fill=fill, width=width)


def main() -> None:
    for path, expected in EXPECTED.items():
        common.require(path.is_file() and sha256(path) == expected, f"pinned input changed: {path}")
    common.require(PHOTO.is_file(), "GSI photo mosaic is missing")
    mesh_summary = read_json(MESH_SUMMARY)
    with np.load(MESH, allow_pickle=False) as archive:
        mesh = {key: np.asarray(archive[key]).copy() for key in archive.files}
    vertices = mesh["vertices_m"]
    triangles = mesh["triangles"]
    fixed = mesh["fixed_R20_cell_mask"].astype(bool)
    assignment, component_records = fixed_component_assignment(
        vertices, triangles, fixed
    )
    total_fixed_cells = int(fixed.sum())
    total_fixed_area = float(sum(record["areaM2"] for record in component_records))
    side_cells = int(sum(record["cellCount"] for record in component_records[1:]))
    side_area = float(sum(record["areaM2"] for record in component_records[1:]))

    cut_features = read_json(CUT)["features"]
    cut_lonlat = [cut_features[0]["geometry"]["coordinates"][0]] + [
        feature["geometry"]["coordinates"][1] for feature in cut_features
    ]
    cut_line = LineString(old.project_many(cut_lonlat))
    distance_band = cut_line.buffer(200.0, resolution=128)
    candidate_tile = metric_to_tile(vertices)
    buffer_tile = metric_to_tile(np.asarray(distance_band.exterior.coords))

    checks = [
        {
            "id": "current_H3_fixed_patch_has_three_disconnected_water_components",
            "pass": len(component_records) == 3,
            "evidence": len(component_records),
        },
        {
            "id": "nishikawa_side_channel_contains_fixed_R20_cells",
            "pass": component_records[1]["cellCount"] > 0,
            "evidence": component_records[1],
        },
        {
            "id": "magarigawa_side_channel_contains_fixed_R20_cells",
            "pass": component_records[2]["cellCount"] > 0,
            "evidence": component_records[2],
        },
        {
            "id": "all_10617_fixed_cells_are_component_assigned",
            "pass": sum(record["cellCount"] for record in component_records)
            == total_fixed_cells
            == 10617,
            "evidence": {
                "componentSum": sum(record["cellCount"] for record in component_records),
                "fixedCellCount": total_fixed_cells,
            },
        },
    ]
    failed = [item["id"] for item in checks if not item["pass"]]
    summary = {
        "schema": "onga-stage20-R20-multizone-H3-river-coverage-correction-v1",
        "version": 1,
        "status": "CORRECTED_CURRENT_H3_INCLUDES_NISHIKAWA_AND_MAGARIGAWA_SIDE_CHANNELS"
        if not failed
        else "FAIL",
        "erratum": {
            "supersedesConclusionFrom": binding(PREVIOUS_AUDIT),
            "incorrectConclusion": "R20完全固定を西川・曲川へ適用していない",
            "cause": (
                "The previous audit tested only whether the two confluence point coordinates "
                "were covered. It did not test river/channel portions inside the 200m band."
            ),
            "correctConclusion": (
                "The current H3 Euclidean 200m selection includes fixed R20 cells in both "
                "the Nishikawa-side and Magarigawa-side channels."
            ),
        },
        "selectionRule": mesh_summary["construction"]["fixedSelection"],
        "components": component_records,
        "sideChannelTotals": {
            "cellCount": side_cells,
            "percentOfFixedCells": side_cells / total_fixed_cells * 100.0,
            "areaM2": side_area,
            "percentOfFixedArea": side_area / total_fixed_area * 100.0,
        },
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failed),
        "failedCount": len(failed),
        "checks": checks,
        "safeguards": {
            "H3MeshChanged": False,
            "H2Run": False,
            "productionPrecomputeRun": False,
            "publicChanged": False,
            "mainMerged": False,
        },
        "bindings": {
            "H3Mesh": binding(MESH),
            "H3MeshSummary": binding(MESH_SUMMARY),
            "completeBarrageCut": binding(CUT),
        },
    }
    write_json(SUMMARY, summary)
    common.require(not failed, f"river coverage correction failed: {failed}")

    photo = Image.open(PHOTO).convert("RGB")
    canvas = Image.new("RGBA", (2700, 1760), "#07111f")
    draw = ImageDraw.Draw(canvas)
    draw.text((55, 30), "訂正図｜現在のH3は西川・曲川側の水路もR20固定している", font=common.font(38, True), fill="#f8fafc")
    draw.text((58, 88), "前回は合流点座標だけを検査しており、河道区間の包含を見落とした", font=common.font(22), fill="#cbd5e1")
    draw.rounded_rectangle((2240, 28, 2645, 110), radius=16, fill="#5b241d", outline="#ff8b72", width=3)
    draw.text((2290, 52), "前回答を訂正", font=common.font(24, True), fill="#ffd1c7")

    map_outer = (45, 145, 1965, 1660)
    common.rounded_panel(draw, map_outer)
    draw.text((70, 164), "A｜河口堰200m帯に入った固定R20セルを河道別に分離", font=common.font(26, True), fill="#f8fafc")
    map_box = (60, 220, 1950, 1570)
    map_crop = (620.0, 470.0, 1425.0, 910.0)
    common.paste_photo(canvas, photo, map_box, map_crop, 0.70)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    centres = candidate_tile[triangles].mean(axis=1)
    visible = np.flatnonzero(
        (centres[:, 0] >= map_crop[0])
        & (centres[:, 0] <= map_crop[2])
        & (centres[:, 1] >= map_crop[1])
        & (centres[:, 1] <= map_crop[3])
    )
    for cell in visible:
        points = [
            common.map_point(candidate_tile[index], map_crop, map_box)
            for index in triangles[cell]
        ]
        component_id = int(assignment[cell])
        if component_id >= 0:
            fill = COMPONENTS[component_id]["colour"]
            overlay_draw.polygon(points, fill=fill)
            overlay_draw.line(points + [points[0]], fill=(255, 255, 255, 95), width=1)
        else:
            overlay_draw.polygon(points, fill=(103, 220, 137, 42))
    band_points = [
        common.map_point(point, map_crop, map_box) for point in buffer_tile
    ]
    draw_dashed_path(
        overlay_draw,
        band_points,
        fill=(255, 255, 255, 245),
        width=4,
    )
    common.draw_constraints(
        overlay_draw,
        mesh,
        candidate_tile,
        map_crop,
        map_box,
        width_scale=1.35,
    )
    for record in component_records:
        component_id = int(record["componentIndex"])
        centre_tile = np.asarray(common.tile_pixel(record["centroidLonLat"]))
        x, y = common.map_point(centre_tile, map_crop, map_box)
        colour = COMPONENTS[component_id]["colour"][:3] + (255,)
        label = (
            f"{record['label']}  {record['cellCount']:,}セル"
            f"／{record['areaM2']:,.0f}m²"
        )
        overlay_draw.ellipse(
            (x - 14, y - 14, x + 14, y + 14),
            fill=colour,
            outline=(255, 255, 255, 255),
            width=3,
        )
        overlay_draw.text(
            (x + 18, y - 18),
            label,
            font=common.font(21, True),
            fill="#ffffff",
            stroke_width=4,
            stroke_fill="#07111f",
        )
    common.clip_overlay(canvas, overlay, map_box)
    draw = ImageDraw.Draw(canvas)
    legend = [
        ("水色：遠賀川主流側", "#18e0db"),
        ("桃：西川側水路", "#ff4abc"),
        ("橙：曲川側水路", "#ff9a30"),
        ("白点線：河口堰完全切断線の200m帯", "#ffffff"),
    ]
    x = 80
    for label, colour in legend:
        draw.rounded_rectangle((x, 1600, x + 24, 1624), radius=5, fill=colour)
        draw.text((x + 32, 1597), label, font=common.font(17, True), fill="#f1f5f9")
        x += 450

    result_outer = (1995, 145, 2655, 1660)
    common.rounded_panel(draw, result_outer)
    draw.text((2025, 170), "B｜訂正結果", font=common.font(28, True), fill="#f8fafc")
    draw.rounded_rectangle((2025, 225, 2625, 440), radius=18, fill="#4a251b", outline="#ff9a73", width=3)
    draw.text((2055, 245), "ユーザーの指摘が正しい", font=common.font(27, True), fill="#ffb39f")
    draw.text((2055, 303), "西川・曲川側も固定対象", font=common.font(23, True), fill="#fff0ea")
    draw.text((2055, 350), f"合計 {side_cells:,}セル", font=common.font(22, True), fill="#ffd1c7")
    draw.text((2055, 392), f"全固定セルの {side_cells / total_fixed_cells * 100.0:.2f}%", font=common.font(19), fill="#ffd1c7")

    rows = [
        (
            component_records[0]["label"],
            f"{component_records[0]['cellCount']:,}セル",
            f"{component_records[0]['areaM2']:,.0f}m²",
        ),
        (
            component_records[1]["label"],
            f"{component_records[1]['cellCount']:,}セル",
            f"{component_records[1]['areaM2']:,.0f}m²",
        ),
        (
            component_records[2]["label"],
            f"{component_records[2]['cellCount']:,}セル",
            f"{component_records[2]['areaM2']:,.0f}m²",
        ),
    ]
    y = 500
    for label, cells, area in rows:
        draw.text((2040, y), label, font=common.font(21, True), fill="#f8fafc")
        draw.text((2040, y + 42), cells, font=common.font(19), fill="#cbd5e1")
        draw.text((2350, y + 42), area, font=common.font(19, True), fill="#75eba6")
        draw.line((2040, y + 82, 2610, y + 82), fill="#30445e", width=2)
        y += 120

    draw.text((2040, 890), "原因", font=common.font(23, True), fill="#ffd36d")
    cause = (
        "固定判定が河道名や流路接続ではなく、完全切断線からの平面直線距離だけだからです。"
        "200m帯に入る水面セルは、西川・曲川側でも固定されます。"
    )
    y = common.wrap_text(draw, cause, (2045, 940), 550, size=19, fill="#e7eef7", bold=True) + 25
    draw.text((2040, y), "現時点の扱い", font=common.font(23, True), fill="#f8fafc")
    notes = [
        "現在のH3メッシュは変更していません。",
        "前回の「適用していない」は撤回します。",
        "河口堰主流だけを固定するなら、選択条件の修正が必要です。",
        "修正案は主流側9,261セルのみを固定し、側水路1,356セルを45m²へ戻す方法です。",
    ]
    y += 50
    for note in notes:
        y = common.wrap_text(draw, "・" + note, (2050, y), 540, size=18, fill="#e7eef7", bold=True) + 12
    draw.text((2040, 1560), "H2再計算は未実施", font=common.font(20, True), fill="#75eba6")
    draw.text((55, 1705), "訂正監査のみ。H3候補、承認済みR20、水面正本、事前計算、公開データ、mainは変更していません。", font=common.font(17), fill="#8fa3b9")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    THREAD.mkdir(parents=True, exist_ok=True)
    rgb = canvas.convert("RGB")
    rgb.save(OUTPUT, quality=91, optimize=True, progressive=True)
    rgb.save(THREAD_IMAGE, format="WEBP", quality=84, method=6)
    encoded = base64.b64encode(THREAD_IMAGE.read_bytes()).decode("ascii")
    fragment = f"""<div id="h3-river-coverage-correction-root">
  <style>
    #h3-river-coverage-correction-root .coverage-image {{ display:block; width:100%; height:auto; max-width:none; }}
    #h3-river-coverage-correction-root.coverage-native .coverage-image {{ width:2700px; }}
    #h3-river-coverage-correction-root .coverage-viewport {{ overflow:auto; }}
  </style>
  <div class="viz-controls">
    <span class="viz-badge">訂正：西川・曲川側1,356セルもR20固定</span>
    <button type="button" class="btn" id="h3-river-coverage-size-button">原寸で見る</button>
  </div>
  <div class="coverage-viewport">
    <img class="coverage-image" alt="{html.escape('訂正図。河口堰完全切断線から200メートル以内に接する固定R20セルを、遠賀川主流側、西川側水路、曲川側水路の3群に色分けし、現在のH3が西川・曲川側も合計1356セル固定していることを示す。')}" src="data:image/webp;base64,{encoded}">
  </div>
  <script>
    (() => {{
      const root = document.getElementById('h3-river-coverage-correction-root');
      const button = document.getElementById('h3-river-coverage-size-button');
      button.addEventListener('click', () => {{
        const native = root.classList.toggle('coverage-native');
        button.textContent = native ? '全体表示' : '原寸で見る';
      }});
    }})();
  </script>
</div>"""
    THREAD_HTML.write_text(fragment, encoding="utf-8")
    common.require(THREAD_HTML.stat().st_size < 2_000_000, "inline visualization exceeds 2 MB")
    common.require('\\"' not in fragment and "\\n" not in fragment, "escaped markup found")
    summary["visuals"] = {
        "artifact": binding(OUTPUT),
        "inlineImage": binding(THREAD_IMAGE),
        "inlineHtml": binding(THREAD_HTML),
    }
    write_json(SUMMARY, summary)
    print(
        json.dumps(
            {
                "result": summary["status"],
                "components": component_records,
                "sideChannelTotals": summary["sideChannelTotals"],
                "summary": binding(SUMMARY),
                "visual": binding(OUTPUT),
                "inlineHtml": binding(THREAD_HTML),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
