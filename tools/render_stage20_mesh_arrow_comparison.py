#!/usr/bin/env python3
"""Compare screen-bin arrows with cell-referenced arrows on one mesh crop."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_stage17_station_boundary_compatibility import image_to_latlon  # noqa: E402
from render_stage20_barrage_satellite_comparison import lonlat_to_world_pixel  # noqa: E402


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc" if bold else "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def colour(value: float, alpha: int = 118) -> tuple[int, int, int, int]:
    stops = [
        (0.0, (30, 117, 179)),
        (0.35, (41, 178, 185)),
        (0.65, (246, 189, 69)),
        (1.0, (224, 80, 55)),
    ]
    x = min(1.0, max(0.0, value))
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0)
            return tuple(round(a + t * (b - a)) for a, b in zip(c0, c1)) + (alpha,)
    return stops[-1][1] + (alpha,)


def arrow(draw: ImageDraw.ImageDraw, start: np.ndarray, vector: np.ndarray, length: float, width: int, root: bool = False) -> None:
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        return
    unit = vector / norm
    end = start + unit * length
    draw.line([tuple(start), tuple(end)], fill=(19, 32, 39, 235), width=width + 3)
    draw.line([tuple(start), tuple(end)], fill=(255, 255, 255, 255), width=width)
    angle = math.atan2(unit[1], unit[0])
    wing_length = max(6.0, length * 0.32)
    for delta in (-2.55, 2.55):
        wing = end + wing_length * np.asarray([math.cos(angle + delta), math.sin(angle + delta)])
        draw.line([tuple(end), tuple(wing)], fill=(19, 32, 39, 240), width=width + 2)
        draw.line([tuple(end), tuple(wing)], fill=(255, 255, 255, 255), width=max(1, width - 1))
    if root:
        radius = max(3, width)
        draw.ellipse((start[0] - radius, start[1] - radius, start[0] + radius, start[1] + radius), fill=(255, 255, 255, 255), outline=(19, 32, 39, 255), width=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mesh-manifest", default="public/data/onga/stage20/mesh-v1.json")
    parser.add_argument("--water-manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--output", default="docs/visuals/stage20-mesh-arrow-comparison-v1.png")
    parser.add_argument("--html-output", default="docs/visuals/stage20-mesh-arrow-comparison-v1.html")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    manifest_path = root / args.mesh_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = (manifest_path.parent / manifest["binary"]["url"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["binary"]["sha256"]:
        raise RuntimeError("browser mesh digest mismatch")

    def mesh_array(name: str) -> np.ndarray:
        descriptor = manifest["arrays"][name]
        dtype = np.int32 if descriptor["dtype"] == "int32" else np.uint8
        return np.frombuffer(
            payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])

    vertices = mesh_array("vertex_image_millipixel").astype(np.float64) / 1000.0
    triangles = mesh_array("triangles").astype(np.int64)
    internal_vertices = mesh_array("internal_face_vertices").astype(np.int64)
    barrage_ids = mesh_array("barrage_face_ids").astype(np.int64)
    water_manifest = json.loads((root / args.water_manifest).read_text(encoding="utf-8"))
    geographic = water_manifest["coordinateSystem"]["geographic"]

    zoom, min_x, min_y, tile_size = 18, 226225, 104814, 256
    mosaic = Image.new("RGB", (6 * tile_size, 3 * tile_size))
    for tile_y in range(104814, 104817):
        for tile_x in range(226225, 226231):
            tile = Image.open(root / "data/external/gsi/seamlessphoto/z18" / f"{tile_x}-{tile_y}.jpg").convert("RGB")
            mosaic.paste(tile, ((tile_x - min_x) * tile_size, (tile_y - min_y) * tile_size))

    def project(point: np.ndarray) -> tuple[float, float]:
        lat, lon = image_to_latlon(float(point[0]), float(point[1]), geographic)
        wx, wy = lonlat_to_world_pixel(lon, lat, zoom)
        return wx - min_x * tile_size, wy - min_y * tile_size

    projected = np.asarray([project(point) for point in vertices])
    centroids = projected[triangles].mean(axis=1)
    barrage_segments = projected[internal_vertices[barrage_ids]]
    centre = barrage_segments.mean(axis=(0, 1)) + np.asarray([-15.0, -8.0])
    source_width, source_height = 100.0, 80.0
    crop_box = (
        int(round(centre[0] - source_width / 2)),
        int(round(centre[1] - source_height / 2)),
        int(round(centre[0] + source_width / 2)),
        int(round(centre[1] + source_height / 2)),
    )
    crop = mosaic.crop(crop_box)
    local_vertices = projected - np.asarray(crop_box[:2])
    local_centroids = centroids - np.asarray(crop_box[:2])
    visible = np.where(
        (local_centroids[:, 0] >= 0) & (local_centroids[:, 0] < source_width)
        & (local_centroids[:, 1] >= 0) & (local_centroids[:, 1] < source_height)
    )[0]

    speed = 0.22 + 0.7 * np.exp(-np.linalg.norm(centroids - barrage_segments.mean(axis=(0, 1)), axis=1) / 150.0)
    mouth = np.asarray(project(np.asarray([280.0, 90.0])))
    direction = mouth - centroids
    direction /= np.maximum(np.linalg.norm(direction, axis=1)[:, None], 1e-12)
    bend = 0.24 * np.sin((centroids[:, 1] - centre[1]) / 18.0)
    rotated = np.column_stack((
        direction[:, 0] * np.cos(bend) - direction[:, 1] * np.sin(bend),
        direction[:, 0] * np.sin(bend) + direction[:, 1] * np.cos(bend),
    ))

    panel_size = (650, 520)
    scale_x, scale_y = panel_size[0] / source_width, panel_size[1] / source_height
    scale = np.asarray([scale_x, scale_y])
    base = crop.resize(panel_size, Image.Resampling.LANCZOS).convert("RGBA")

    def render_panel(cell_mode: bool) -> tuple[Image.Image, int | None]:
        panel = base.copy()
        overlay = Image.new("RGBA", panel_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        for cell in visible:
            polygon = [tuple(point * scale) for point in local_vertices[triangles[cell]]]
            draw.polygon(polygon, fill=colour(float(speed[cell]), 120))
            if cell_mode:
                draw.line(polygon + [polygon[0]], fill=(255, 255, 255, 145), width=1)
        highlighted: int | None = None
        if cell_mode:
            for cell in visible:
                start = local_centroids[cell] * scale
                arrow(draw, start, rotated[cell], 11 + 8 * float(speed[cell]), 2, root=True)
            highlighted = int(visible[np.argmin(np.linalg.norm(local_centroids[visible] - np.asarray([50.0, 40.0]), axis=1))])
            polygon = [tuple(point * scale) for point in local_vertices[triangles[highlighted]]]
            draw.line(polygon + [polygon[0]], fill=(232, 78, 123, 255), width=5)
            start = local_centroids[highlighted] * scale
            radius = 7
            draw.ellipse((start[0] - radius, start[1] - radius, start[0] + radius, start[1] + radius), fill=(232, 78, 123, 255), outline=(255, 255, 255, 255), width=2)
        else:
            for x in (48.0, 96.0):
                xx = x * scale_x
                draw.line((xx, 0, xx, panel_size[1]), fill=(255, 255, 255, 180), width=3)
            draw.line((0, 48.0 * scale_y, panel_size[0], 48.0 * scale_y), fill=(255, 255, 255, 180), width=3)
            bins: dict[tuple[int, int], tuple[int, float]] = {}
            for cell in visible:
                key = (int(local_centroids[cell, 0] // 48), int(local_centroids[cell, 1] // 48))
                target = np.asarray([(key[0] + 0.5) * 48, (key[1] + 0.5) * 48])
                score = float(np.linalg.norm(local_centroids[cell] - target))
                if key not in bins or score < bins[key][1]:
                    bins[key] = (int(cell), score)
            for cell, _ in bins.values():
                arrow(draw, local_centroids[cell] * scale, rotated[cell], 115 + 45 * float(speed[cell]), 5)
        return Image.alpha_composite(panel, overlay).convert("RGB"), highlighted

    old_panel, _ = render_panel(False)
    new_panel, highlighted = render_panel(True)
    canvas = Image.new("RGB", (1600, 1260), (244, 247, 248))
    draw = ImageDraw.Draw(canvas)
    draw.text((50, 35), "流速表示　メッシュとの対応方法を比較", font=font(42, True), fill=(23, 49, 61))
    draw.text((50, 92), "同じ約50 m × 40 mの範囲・同じセル値を、二つの方法で表示", font=font(22), fill=(72, 98, 111))
    left_x, right_x, panel_y = 85, 865, 205
    draw.text((left_x, 145), "A　画面48 px区画の代表矢印", font=font(26, True), fill=(23, 49, 61))
    draw.text((right_x, 145), "B　各メッシュセルの値を参照（推奨）", font=font(26, True), fill=(23, 49, 61))
    canvas.paste(old_panel, (left_x, panel_y))
    canvas.paste(new_panel, (right_x, panel_y))
    draw.rectangle((left_x, panel_y, left_x + panel_size[0], panel_y + panel_size[1]), outline=(199, 211, 216), width=2)
    draw.rectangle((right_x, panel_y, right_x + panel_size[0], panel_y + panel_size[1]), outline=(199, 211, 216), width=2)

    draw.rounded_rectangle((85, 755, 735, 885), radius=18, fill=(255, 255, 255), outline=(199, 211, 216), width=2)
    draw.text((115, 780), "1区画に代表矢印1本", font=font(22, True), fill=(23, 49, 61))
    draw.text((115, 825), "矢印が複数セルを横断し、色との対応が不明", font=font(19), fill=(72, 98, 111))
    draw.rounded_rectangle((865, 755, 1515, 885), radius=18, fill=(255, 255, 255), outline=(7, 127, 186), width=3)
    draw.text((895, 780), "根元＝セル重心／色・向き・長さ＝同じセル値", font=font(21, True), fill=(23, 49, 61))
    draw.text((895, 825), f"桃色例：セル {highlighted:,} の色と矢印を一対一で表示", font=font(19), fill=(72, 98, 111))

    draw.rounded_rectangle((50, 930, 1550, 1115), radius=18, fill=(230, 242, 246), outline=(7, 127, 186), width=3)
    draw.text((82, 958), "判断すること：拡大表示でどちらの対応方法を採用するか", font=font(27, True), fill=(23, 49, 61))
    draw.text((82, 1015), "A　48 px区画の代表矢印を維持", font=font(23, True), fill=(23, 49, 61))
    draw.text((820, 1015), "B　メッシュセル値を直接参照（推奨）", font=font(23, True), fill=(23, 49, 61))
    draw.text((82, 1065), "Bでも全体表示時は同じセル群を水深・面積で集約し、拡大に応じてセル単位へ戻します。", font=font(19), fill=(72, 98, 111))
    draw.text((50, 1160), "値は表示比較用の合成セル値です。物理的な流速の妥当性ではなく、セルと矢印の対応方法だけを判断します。", font=font(18), fill=(72, 98, 111))
    draw.text((50, 1205), "背景：国土地理院「全国最新写真（シームレス）」　青線：承認済み河口堰", font=font(17), fill=(72, 98, 111))

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
    jpeg = output.with_suffix(".jpg")
    canvas.save(jpeg, format="JPEG", quality=89, optimize=True)
    encoded = base64.b64encode(jpeg.read_bytes()).decode("ascii")
    html = f'''<div id="stage20-mesh-arrow-comparison" style="display:grid;gap:0.75rem;color:var(--foreground);">
  <img src="data:image/jpeg;base64,{encoded}" alt="同じ拡大範囲を、48ピクセル区画の代表矢印と、各メッシュセルの値を直接参照する矢印で比較した二択判断画像" style="display:block;width:100%;height:auto;" />
</div>
'''
    (root / args.html_output).write_text(html, encoding="utf-8")
    print(json.dumps({
        "status": "awaiting_visual_decision",
        "output": args.output,
        "pngSha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "jpegSha256": hashlib.sha256(jpeg.read_bytes()).hexdigest(),
        "visibleCellCount": int(len(visible)),
        "highlightedCell": highlighted,
        "decision": {"A": "screen_bin_representative", "B": "cell_referenced_adaptive_lod_recommended"},
        "physicalFlowRun": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
