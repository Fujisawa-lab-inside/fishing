#!/usr/bin/env python3
"""Render the photo-overlay review figure for the R20 multizone v2 mesh."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

import generate_stage20_fishway_F3_review_mesh_v1 as old


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ONLY_ROOT = ROOT / ".stage20-local-only"
THREAD = (
    LOCAL_ONLY_ROOT
    / "visualizations"
    / "019f7538-8861-7831-b3d3-29723d9fb8c3"
)
PHOTO = LOCAL_ONLY_ROOT / "gsi-z16-mouth-mosaic.jpg"
RESULT = ROOT / "docs/results/stage20-R20-multizone-mesh-v2"
MESH = RESULT / "review-mesh.npz"
SUMMARY = RESULT / "mesh-summary.json"
VALIDATION = RESULT / "static-validation.json"
ZONE_DEFINITION = RESULT / "zone-definition.geojson"
INTEGRATED = ROOT / "config/stage20_estuary_confirmed_integration_v3.geojson"
P2 = ROOT / "config/stage20_fishway_constant_weak_flow_coupling_candidate_v1.json"
OUTPUT = ROOT / "docs/visuals/stage20-R20-multizone-mesh-v2-decision.jpg"
THREAD_IMAGE = THREAD / "r20-multizone-mesh-v2-decision.webp"
THREAD_HTML = THREAD / "r20-multizone-mesh-v2-decision.html"
VISUAL_MANIFEST = RESULT / "visual-manifest.json"

EXPECTED = {
    MESH: "e7de2e31085412a3a66bd42b70587d9eceed94e2d69a42f336f2a2f710711505",
    SUMMARY: "1a2fee7bf3b61aca17a8826d5ad68c0f01f5182626bf3c55cb1654e99d3f1bad",
    VALIDATION: "10904060dff680187b6afed921c7c0d077111ee963662432835b9c713f63e781",
    ZONE_DEFINITION: "897d3dd7f85e1779f3379d51c715ae6472884a916ebaaeb9647a084b41babcfc",
    INTEGRATED: "2868cf998e9b8886d0306db7d774b2de6c0591474ef6755506ce76a18ad4233e",
    P2: "7afe958520537b4f0ca2c1bf493160919b85a897cabb63639b83b07104be5313",
}

FONT_REGULAR = os.environ.get("STAGE20_FONT_REGULAR")
FONT_BOLD = os.environ.get("STAGE20_FONT_BOLD", FONT_REGULAR)
ZOOM = 16
ORIGIN_X = 56553
ORIGIN_Y = 26201
FULL_CROP = (330.0, 150.0, 1380.0, 920.0)
ZONE_COLORS = {
    3: (209, 115, 255, 170),
    30: (20, 218, 211, 125),
    45: (103, 220, 137, 115),
    60: (255, 190, 65, 105),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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
    return {"path": label, "sha256": sha256(path), "byteLength": path.stat().st_size}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    configured = FONT_BOLD if bold else FONT_REGULAR
    if configured:
        return ImageFont.truetype(configured, size)
    return ImageFont.load_default(size=size)


def tile_pixel(coordinate: list[float] | tuple[float, float] | np.ndarray) -> tuple[float, float]:
    lon, lat = float(coordinate[0]), float(coordinate[1])
    scale = 2**ZOOM
    x = (((lon + 180.0) / 360.0) * scale - ORIGIN_X) * 256.0
    y = (
        (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi)
        / 2.0
        * scale
        - ORIGIN_Y
    ) * 256.0
    return x, y


def map_point(
    point: tuple[float, float] | np.ndarray,
    crop: tuple[float, float, float, float],
    box: tuple[int, int, int, int],
) -> tuple[float, float]:
    return (
        box[0] + (float(point[0]) - crop[0]) / (crop[2] - crop[0]) * (box[2] - box[0]),
        box[1] + (float(point[1]) - crop[1]) / (crop[3] - crop[1]) * (box[3] - box[1]),
    )


def rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str = "#101b2b",
    outline: str = "#30445e",
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=width)


def paste_photo(
    canvas: Image.Image,
    photo: Image.Image,
    box: tuple[int, int, int, int],
    crop: tuple[float, float, float, float],
    brightness: float,
) -> None:
    source = photo.crop(tuple(int(round(value)) for value in crop)).convert("RGB")
    source = ImageEnhance.Brightness(source).enhance(brightness)
    source = source.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
    canvas.paste(source, (box[0], box[1]))


def clip_overlay(
    canvas: Image.Image,
    overlay: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    clipped = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    clipped.paste(overlay.crop(box), (box[0], box[1]))
    canvas.alpha_composite(clipped)


def draw_constraints(
    draw: ImageDraw.ImageDraw,
    mesh: dict[str, np.ndarray],
    vertices_tile: np.ndarray,
    crop: tuple[float, float, float, float],
    box: tuple[int, int, int, int],
    *,
    width_scale: float,
) -> None:
    for edge, marker_value in zip(
        mesh["segments"], mesh["segment_markers"], strict=True
    ):
        marker = int(marker_value)
        a = vertices_tile[int(edge[0])]
        b = vertices_tile[int(edge[1])]
        if (
            max(a[0], b[0]) < crop[0]
            or min(a[0], b[0]) > crop[2]
            or max(a[1], b[1]) < crop[1]
            or min(a[1], b[1]) > crop[3]
        ):
            continue
        points = [map_point(a, crop, box), map_point(b, crop, box)]
        if 101 <= marker <= 108:
            draw.line(points, fill=(35, 145, 255, 255), width=max(3, round(5 * width_scale)))
        elif marker == 200:
            draw.line(points, fill=(255, 58, 76, 255), width=max(3, round(5 * width_scale)))
        elif 11 <= marker <= 14:
            draw.line(points, fill=(255, 67, 215, 255), width=max(3, round(5 * width_scale)))
        elif marker in (301, 302):
            draw.line(points, fill=(209, 115, 255, 240), width=max(2, round(4 * width_scale)))
        elif marker == 10:
            draw.line(points, fill=(246, 250, 255, 235), width=max(1, round(2 * width_scale)))


def draw_full_map(
    canvas: Image.Image,
    photo: Image.Image,
    mesh: dict[str, np.ndarray],
    vertices_tile: np.ndarray,
    open_centres: dict[str, np.ndarray],
    box: tuple[int, int, int, int],
) -> None:
    paste_photo(canvas, photo, box, FULL_CROP, 0.72)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    triangles = mesh["triangles"].astype(np.int32)
    targets = np.rint(mesh["triangle_maximum_area_m2"]).astype(np.int32)
    for triangle, target in zip(triangles, targets, strict=True):
        points = [map_point(vertices_tile[index], FULL_CROP, box) for index in triangle]
        draw.polygon(points, fill=ZONE_COLORS[int(target)])
    draw_constraints(
        draw, mesh, vertices_tile, FULL_CROP, box, width_scale=1.0
    )
    for name, centre in open_centres.items():
        x, y = map_point(centre, FULL_CROP, box)
        draw.ellipse((x - 19, y - 19, x + 19, y + 19), fill=(255, 67, 215, 245))
        draw.text((x - 9, y - 16), name, font=font(22, True), fill="#ffffff")
    clip_overlay(canvas, overlay, box)


def draw_zoom(
    canvas: Image.Image,
    photo: Image.Image,
    mesh: dict[str, np.ndarray],
    vertices_tile: np.ndarray,
    center: np.ndarray,
    half_size: tuple[float, float],
    box: tuple[int, int, int, int],
    *,
    label_gates: bool = False,
) -> None:
    crop = (
        float(center[0] - half_size[0]),
        float(center[1] - half_size[1]),
        float(center[0] + half_size[0]),
        float(center[1] + half_size[1]),
    )
    paste_photo(canvas, photo, box, crop, 0.70)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    triangles = mesh["triangles"].astype(np.int32)
    targets = np.rint(mesh["triangle_maximum_area_m2"]).astype(np.int32)
    centres = vertices_tile[triangles].mean(axis=1)
    selected = np.where(
        (centres[:, 0] >= crop[0])
        & (centres[:, 0] <= crop[2])
        & (centres[:, 1] >= crop[1])
        & (centres[:, 1] <= crop[3])
    )[0]
    for cell in selected:
        points = [map_point(vertices_tile[index], crop, box) for index in triangles[cell]]
        fill = tuple(list(ZONE_COLORS[int(targets[cell])][:3]) + [70])
        draw.polygon(points, fill=fill)
        draw.line(points + [points[0]], fill=(255, 255, 255, 150), width=1)
    draw_constraints(draw, mesh, vertices_tile, crop, box, width_scale=1.25)
    if label_gates:
        for gate in range(1, 9):
            gate_segments = mesh["segments"][mesh["segment_markers"] == 100 + gate]
            gate_points = vertices_tile[gate_segments.reshape(-1)]
            gate_centre = gate_points.mean(axis=0)
            x, y = map_point(gate_centre, crop, box)
            draw.ellipse((x - 15, y - 15, x + 15, y + 15), fill=(14, 71, 142, 245))
            draw.text((x - 7, y - 13), str(gate), font=font(18, True), fill="#ffffff")
    clip_overlay(canvas, overlay, box)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    width: int,
    *,
    size: int,
    fill: str,
    bold: bool = False,
    line_gap: int = 7,
) -> int:
    fnt = font(size, bold)
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and draw.textlength(candidate, font=fnt) > width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    y = xy[1]
    for line in lines:
        draw.text((xy[0], y), line, font=fnt, fill=fill)
        y += size + line_gap
    return y


def main() -> None:
    for path, expected in EXPECTED.items():
        require(path.is_file() and sha256(path) == expected, f"pinned input changed: {path}")
    require(PHOTO.is_file(), "GSI z16 photo mosaic is missing")
    summary = read_json(SUMMARY)
    validation = read_json(VALIDATION)
    require(validation["status"] == "PASS", "static validation must pass before rendering")
    integrated = read_json(INTEGRATED)
    by_id = {feature["id"]: feature for feature in integrated["features"]}
    with np.load(MESH, allow_pickle=False) as archive:
        mesh = {key: np.asarray(archive[key]).copy() for key in archive.files}

    vertices_lonlat = old.unproject_many(mesh["vertices_m"])
    vertices_tile = np.asarray([tile_pixel(point) for point in vertices_lonlat], dtype=np.float64)
    open_lines_tile = {
        name: np.asarray(
            [
                tile_pixel(point)
                for point in by_id[f"open_boundary_{name}_authority_v2"]["geometry"]["coordinates"]
            ],
            dtype=np.float64,
        )
        for name in ("M", "N", "O", "G")
    }
    open_centres = {name: points.mean(axis=0) for name, points in open_lines_tile.items()}
    cut_mask = np.isin(mesh["segment_markers"], np.arange(101, 109))
    cut_vertices = vertices_tile[mesh["segments"][cut_mask].reshape(-1)]
    barrage_center = cut_vertices.mean(axis=0)
    nishikawa_center = np.asarray(tile_pixel([130.67325, 33.891666666666666]))
    magarigawa_center = np.asarray(tile_pixel([130.6752222222222, 33.894888888888886]))
    no_center = np.vstack([open_lines_tile["N"], open_lines_tile["O"]]).mean(axis=0)
    photo = Image.open(PHOTO).convert("RGB")

    canvas = Image.new("RGBA", (3000, 2860), "#07111f")
    draw = ImageDraw.Draw(canvas)
    draw.text((55, 28), "判断図｜R20制約固定・3 / 30 / 45 / 60m² 可変メッシュ", font=font(43, True), fill="#f8fafc")
    draw.text(
        (58, 88),
        "前候補を再利用せず、R20の全制約線から内部セルだけを再生成",
        font=font(23),
        fill="#cbd5e1",
    )
    draw.rounded_rectangle((2490, 30, 2940, 112), radius=16, fill="#164e3a", outline="#62e89a", width=3)
    draw.text(
        (2535, 53),
        f"静的検査 {validation['passedCount']}/{validation['checkCount']} PASS",
        font=font(23, True),
        fill="#8ff0b6",
    )

    full_outer = (45, 145, 1870, 1450)
    rounded_panel(draw, full_outer)
    draw.text((70, 160), "A｜河口全域：写真と細分化帯の位置", font=font(27, True), fill="#f8fafc")
    full_box = (60, 210, 1855, 1345)
    draw_full_map(canvas, photo, mesh, vertices_tile, open_centres, full_box)
    draw = ImageDraw.Draw(canvas)
    legend = [
        ("3m² 魚道P2", "#d173ff"),
        ("30m² M・河口堰・開境界・合流部", "#14dad3"),
        ("45m² 遷移帯", "#67dc89"),
        ("60m² 広い内部", "#ffbe41"),
    ]
    x = 75
    for label, colour in legend:
        draw.rounded_rectangle((x, 1370, x + 26, 1396), radius=5, fill=colour)
        draw.text((x + 36, 1367), label, font=font(18, True), fill="#f1f5f9")
        x += 425
    draw.text(
        (75, 1410),
        "青＝水門1〜8　赤＝固定部　桃＝M/N/O/G　白＝確定R20外周　紫線＝魚道P2",
        font=font(17),
        fill="#dbe6f3",
    )

    metrics_outer = (1905, 145, 2955, 1450)
    rounded_panel(draw, metrics_outer)
    draw.text((1940, 170), "B｜判断基準", font=font(29, True), fill="#f8fafc")
    draw.rounded_rectangle((1940, 225, 2920, 390), radius=18, fill="#103322", outline="#4bd58b", width=3)
    draw.text((1970, 245), "制約位置は完全固定", font=font(31, True), fill="#75eba6")
    draw.text((1970, 302), "全1,939制約辺｜座標移動 0.000m", font=font(24, True), fill="#eef8f2")
    draw.text((1970, 345), "水門・固定部・M/N/O/G・P2を含む", font=font(19), fill="#cce7d6")

    comparison = summary["comparisonToFormalR20"]
    rows = [
        ("セル数", f"{comparison['referenceCellCount']:,} → {comparison['candidateCellCount']:,}", f"−{comparison['cellCountReductionPercent']:.1f}%"),
        ("最小辺", f"{summary['mesh']['minimumCellEdgeM']:.3f}m", "R20と同じ"),
        ("最小角", f"{summary['mesh']['minimumAngleDegree']:.3f}°", "30°以上"),
        ("閉門時", "河口堰で2領域", "PASS"),
        ("1門以上開", "主流域が1領域", "PASS"),
        ("魚道P2", "全256門状態で接続", "PASS"),
    ]
    y = 440
    for label, value, result in rows:
        draw.text((1960, y), label, font=font(20, True), fill="#cbd5e1")
        draw.text((2180, y), value, font=font(21, True), fill="#f8fafc")
        draw.text((2740, y), result, font=font(20, True), fill="#75eba6")
        draw.line((1960, y + 38, 2900, y + 38), fill="#263b53", width=1)
        y += 68

    draw.text((1955, 865), "セル内訳", font=font(24, True), fill="#f8fafc")
    zone_labels = {3: "魚道P2", 30: "重要部", 45: "遷移帯", 60: "広い内部"}
    y = 915
    for zone in (3, 30, 45, 60):
        item = summary["mesh"]["zoneCounts"][str(zone)]
        colour = "#%02x%02x%02x" % ZONE_COLORS[zone][:3]
        draw.rounded_rectangle((1960, y + 3, 1985, y + 28), radius=5, fill=colour)
        draw.text((2000, y), f"{zone}m² {zone_labels[zone]}", font=font(19, True), fill="#eaf1f8")
        draw.text((2690, y), f"{item['cellCount']:,}セル", font=font(19, True), fill=colour)
        y += 48

    draw.line((1955, 1120, 2905, 1120), fill="#30445e", width=2)
    draw.text((1955, 1145), "図で確認する3点", font=font(24, True), fill="#f8fafc")
    items = [
        "① M河口部が水色30m²で十分に覆われているか",
        "② 河口堰・魚道・西川/曲川合流部のセルが細かいか",
        "③ 緑45m²から黄60m²への移行に不自然な穴がないか",
    ]
    y = 1195
    for item in items:
        y = wrap_text(draw, item, (1970, y), 900, size=19, fill="#e7eef7", bold=True) + 10
    draw.text((1970, 1385), "問題なければ次は同条件60秒H2比較", font=font(20, True), fill="#ffd36d")

    zooms = [
        ("C｜M河口部（前回誤差集中域）", open_centres["M"], (220.0, 145.0), False),
        ("D｜河口堰・水門1〜8・魚道P2", barrage_center, (170.0, 105.0), True),
        ("E｜N・O開境界", no_center, (230.0, 155.0), False),
        ("F｜G開境界", open_centres["G"], (185.0, 125.0), False),
        ("G｜西川・遠賀川合流部", nishikawa_center, (180.0, 130.0), False),
        ("H｜曲川・遠賀川合流部", magarigawa_center, (180.0, 130.0), False),
    ]
    panel_positions = [
        (45, 1495, 1010, 2100),
        (1020, 1495, 1985, 2100),
        (1995, 1495, 2960, 2100),
        (45, 2120, 1010, 2725),
        (1020, 2120, 1985, 2725),
        (1995, 2120, 2960, 2725),
    ]
    for (title, center, half_size, label_gates), outer in zip(
        zooms, panel_positions, strict=True
    ):
        rounded_panel(draw, outer)
        draw.text((outer[0] + 24, outer[1] + 15), title, font=font(22, True), fill="#f8fafc")
        box = (outer[0] + 15, outer[1] + 60, outer[2] - 15, outer[3] - 15)
        draw_zoom(
            canvas,
            photo,
            mesh,
            vertices_tile,
            center,
            half_size,
            box,
            label_gates=label_gates,
        )
        draw = ImageDraw.Draw(canvas)

    draw.text(
        (55, 2780),
        "背景：国土地理院「全国最新写真（seamlessphoto）」を加工。候補はレビュー専用で、H2再計算・正式メッシュ・事前計算・公開データ・mainは未変更。",
        font=font(17),
        fill="#8fa3b9",
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    THREAD.mkdir(parents=True, exist_ok=True)
    rgb = canvas.convert("RGB")
    rgb.save(OUTPUT, quality=90, optimize=True, progressive=True)
    rgb.save(THREAD_IMAGE, format="WEBP", quality=83, method=6)
    encoded = base64.b64encode(THREAD_IMAGE.read_bytes()).decode("ascii")
    fragment = f"""<div id="r20-multizone-v2-review-root" style="font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',sans-serif;background:#07111f;color:#f8fafc;padding:12px;border-radius:18px;max-width:100%;box-sizing:border-box">
  <style>
    #r20-multizone-v2-review-root .note{{display:flex;gap:12px;align-items:center;justify-content:space-between;margin:0 0 10px;padding:10px 14px;background:#10281f;border:1px solid #3f9f72;border-radius:12px;font-weight:700}}
    #r20-multizone-v2-review-root button{{appearance:none;border:1px solid #5f7896;background:#14243a;color:#f8fafc;border-radius:9px;padding:7px 12px;font-weight:700;cursor:pointer}}
    #r20-multizone-v2-review-root .viewport{{overflow:auto;border-radius:12px;border:1px solid #30445e;background:#07111f}}
    #r20-multizone-v2-review-root img{{display:block;width:100%;height:auto;max-width:none}}
    #r20-multizone-v2-review-root.native img{{width:3000px}}
  </style>
  <div class="note"><span>確認：M・河口堰・N/O/G・両合流部の色分けと実セル</span><button type="button" onclick="this.closest('#r20-multizone-v2-review-root').classList.toggle('native');this.textContent=this.textContent==='原寸で見る'?'全体表示':'原寸で見る'">原寸で見る</button></div>
  <div class="viewport"><img alt="{html.escape('R20制約を固定した3/30/45/60平方メートル可変メッシュ候補。河口全域の写真重畳、M、河口堰、水門1から8、魚道、N、O、G、西川合流部、曲川合流部の拡大図。')}" src="data:image/webp;base64,{encoded}"></div>
</div>"""
    THREAD_HTML.write_text(fragment, encoding="utf-8")
    require(THREAD_HTML.stat().st_size < 2_000_000, "inline visualization exceeds 2 MB")
    manifest = {
        "schema": "onga-stage20-R20-multizone-mesh-v2-decision-visual-v1",
        "version": 1,
        "status": "rendered_pending_user_H2_60s_diagnostic_decision",
        "artifact": binding(OUTPUT),
        "inlineImage": binding(THREAD_IMAGE),
        "inlineHtml": binding(THREAD_HTML),
        "inputs": {
            "mesh": binding(MESH),
            "summary": binding(SUMMARY),
            "staticValidation": binding(VALIDATION),
            "zoneDefinition": binding(ZONE_DEFINITION),
            "photo": binding(PHOTO),
        },
        "decision": {
            "id": "authorize_same_condition_60s_H2_comparison_for_multizone_v2",
            "requiredVisualChecks": [
                "M_30m2_coverage",
                "barrage_fishway_and_confluence_refinement",
                "45_to_60m2_transition_continuity",
            ],
        },
        "safeguards": summary["safeguards"],
    }
    write_json(VISUAL_MANIFEST, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
