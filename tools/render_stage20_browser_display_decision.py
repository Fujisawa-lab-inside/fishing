#!/usr/bin/env python3
"""Render the Stage 20 browser flow-map display decision."""

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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def colour(speed: float) -> tuple[int, int, int, int]:
    stops = [
        (0.0, (30, 117, 179)),
        (0.35, (41, 178, 185)),
        (0.65, (246, 189, 69)),
        (1.0, (224, 80, 55)),
    ]
    value = min(1.0, max(0.0, speed))
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if value <= x1:
            t = (value - x0) / (x1 - x0)
            return tuple(round(a + t * (b - a)) for a, b in zip(c0, c1)) + (105,)
    return stops[-1][1] + (105,)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mesh-manifest", default="public/data/onga/stage20/mesh-v1.json")
    parser.add_argument("--manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--validation", default="config/stage20_browser_reference_validation_v1.json")
    parser.add_argument("--output", default="docs/visuals/stage20-browser-display-decision-v1.png")
    parser.add_argument("--html-output", default="docs/visuals/stage20-browser-display-decision-v1.html")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    mesh_manifest_path = root / args.mesh_manifest
    manifest = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    validation = json.loads((root / args.validation).read_text(encoding="utf-8"))
    if not validation["status"].startswith("passed"):
        raise RuntimeError("browser reference validation must pass before rendering")
    geographic = manifest["coordinateSystem"]["geographic"]
    mesh_manifest = json.loads(mesh_manifest_path.read_text(encoding="utf-8"))
    mesh_binary_path = mesh_manifest_path.parent / mesh_manifest["binary"]["url"]
    mesh_payload = mesh_binary_path.read_bytes()
    if hashlib.sha256(mesh_payload).hexdigest() != mesh_manifest["binary"]["sha256"]:
        raise RuntimeError("browser mesh digest mismatch")

    def mesh_array(name: str) -> np.ndarray:
        descriptor = mesh_manifest["arrays"][name]
        dtype = np.int32 if descriptor["dtype"] == "int32" else np.uint8
        return np.frombuffer(
            mesh_payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])

    vertices = mesh_array("vertex_image_millipixel").astype(np.float64) / 1000.0
    triangles = mesh_array("triangles").astype(np.int64)
    internal_face_vertices = mesh_array("internal_face_vertices").astype(np.int64)
    barrage_face_ids = mesh_array("barrage_face_ids").astype(np.int64)
    fishway_cells = mesh_array("fishway_cells").astype(np.int64)

    zoom = 18
    min_x, max_x = 226225, 226230
    min_y, max_y = 104814, 104816
    tile_size = 256
    mosaic = Image.new("RGB", ((max_x - min_x + 1) * tile_size, (max_y - min_y + 1) * tile_size))
    for tile_y in range(min_y, max_y + 1):
        for tile_x in range(min_x, max_x + 1):
            tile = Image.open(root / "data/external/gsi/seamlessphoto/z18" / f"{tile_x}-{tile_y}.jpg").convert("RGB")
            mosaic.paste(tile, ((tile_x - min_x) * tile_size, (tile_y - min_y) * tile_size))

    def mosaic_point(point: np.ndarray) -> tuple[float, float]:
        lat, lon = image_to_latlon(float(point[0]), float(point[1]), geographic)
        wx, wy = lonlat_to_world_pixel(lon, lat, zoom)
        return wx - min_x * tile_size, wy - min_y * tile_size

    projected = np.asarray([mosaic_point(point) for point in vertices])
    centroids = projected[triangles].mean(axis=1)
    barrage_points = projected[internal_face_vertices[barrage_face_ids]]
    barrage_mid = barrage_points.mean(axis=(0, 1))
    mouth = np.asarray(mosaic_point(np.asarray([280.0, 90.0])))
    distance = np.linalg.norm(centroids - barrage_mid, axis=1)
    synthetic_speed = 0.16 + 0.84 * np.exp(-((distance / 250.0) ** 2))

    overlay = Image.new("RGBA", mosaic.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay, "RGBA")
    inside = (
        (centroids[:, 0] >= 0) & (centroids[:, 0] < mosaic.width)
        & (centroids[:, 1] >= 0) & (centroids[:, 1] < mosaic.height)
    )
    for cell in np.where(inside)[0]:
        polygon = [tuple(point) for point in projected[triangles[cell]]]
        od.polygon(polygon, fill=colour(float(synthetic_speed[cell])))

    bins: dict[tuple[int, int], tuple[int, float]] = {}
    for cell in np.where(inside)[0]:
        x, y = centroids[cell]
        key = (int(x // 58), int(y // 58))
        centre = np.asarray([(key[0] + 0.5) * 58, (key[1] + 0.5) * 58])
        score = float(np.linalg.norm(centroids[cell] - centre))
        if key not in bins or score < bins[key][1]:
            bins[key] = (int(cell), score)
    for cell, _ in bins.values():
        start = centroids[cell]
        direction = mouth - start
        magnitude = float(np.linalg.norm(direction))
        if magnitude < 1:
            continue
        direction /= magnitude
        length = 15 + 19 * float(synthetic_speed[cell])
        end = start + direction * length
        od.line([tuple(start), tuple(end)], fill=(20, 33, 40, 210), width=6)
        od.line([tuple(start), tuple(end)], fill=(255, 255, 255, 245), width=3)
        angle = math.atan2(direction[1], direction[0])
        for delta in (-2.55, 2.55):
            wing = end + 8 * np.asarray([math.cos(angle + delta), math.sin(angle + delta)])
            od.line([tuple(end), tuple(wing)], fill=(20, 33, 40, 220), width=5)
            od.line([tuple(end), tuple(wing)], fill=(255, 255, 255, 250), width=2)

    for segment in barrage_points:
        od.line([tuple(segment[0]), tuple(segment[1])], fill=(255, 255, 255, 235), width=10)
        od.line([tuple(segment[0]), tuple(segment[1])], fill=(7, 112, 168, 255), width=6)
    fish_centres = centroids[fishway_cells]
    for centre in fish_centres:
        x, y = centre
        od.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(246, 189, 69, 255), outline=(255, 255, 255, 255), width=3)
    map_image = Image.alpha_composite(mosaic.convert("RGBA"), overlay).convert("RGB")

    canvas = Image.new("RGB", (1600, 1260), (244, 247, 248))
    draw = ImageDraw.Draw(canvas)
    draw.text((50, 38), "Stage 20　流速地図の表示確認", font=font(42, True), fill=(23, 49, 61))
    draw.text((50, 94), "承認済み50,339セル＋ブラウザWorker＋WASM更新核", font=font(23), fill=(72, 98, 111))
    resized = map_image.resize((1500, 750), Image.Resampling.LANCZOS)
    canvas.paste(resized, (50, 145))

    draw.rounded_rectangle((50, 915, 1550, 1045), radius=18, fill=(255, 255, 255), outline=(199, 211, 216), width=2)
    draw.text((78, 936), "表示確認用の合成流速場", font=font(23, True), fill=(23, 49, 61))
    draw.text((78, 980), "色＝速さ　白矢印＝向き　青線＝承認済み河口堰　黄点＝魚道両側", font=font(21), fill=(46, 73, 86))
    bar_x0, bar_y0, bar_w, bar_h = 985, 943, 500, 24
    for x in range(bar_w):
        c = colour(x / (bar_w - 1))[:3]
        draw.line((bar_x0 + x, bar_y0, bar_x0 + x, bar_y0 + bar_h), fill=c)
    draw.text((bar_x0, 977), "0", font=font(17), fill=(72, 98, 111))
    draw.text((bar_x0 + bar_w - 58, 977), "1.0 m/s", font=font(17), fill=(72, 98, 111))
    maximum_velocity = validation["syntheticStillWaterValidation"]["maximumVelocityMPerS"]
    draw.text((985, 1012), f"静水保存試験：最大疑似流速 {maximum_velocity:.2e} m/s　合格", font=font(17), fill=(72, 98, 111))

    draw.rounded_rectangle((50, 1065, 1550, 1210), radius=18, fill=(230, 242, 246), outline=(7, 127, 186), width=3)
    draw.text((82, 1090), "判断すること：この流速地図の表示方法を採用するか", font=font(27, True), fill=(23, 49, 61))
    draw.text((82, 1145), "A　採用する（推奨）", font=font(24, True), fill=(23, 49, 61))
    draw.text((820, 1145), "B　色・矢印・重ね方を調整する", font=font(24, True), fill=(23, 49, 61))
    draw.text((50, 1225), "この画像の流速値と向きは表示確認用の合成場です。流れの物理的妥当性は今回の判断対象ではありません。背景：国土地理院", font=font(17), fill=(72, 98, 111))

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
    jpeg = output.with_suffix(".jpg")
    canvas.save(jpeg, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(jpeg.read_bytes()).decode("ascii")
    html = f'''<div id="stage20-browser-display-decision" style="display:grid;gap:0.75rem;color:var(--foreground);">
  <img src="data:image/jpeg;base64,{encoded}" alt="衛星画像上に合成流速の色と矢印、承認済み河口堰、魚道を重ねた表示方法の二択判断画像" style="display:block;width:100%;height:auto;" />
</div>
'''
    (root / args.html_output).write_text(html, encoding="utf-8")
    print(json.dumps({
        "status": "awaiting_display_decision",
        "output": args.output,
        "pngSha256": sha256(output),
        "jpegSha256": sha256(jpeg),
        "html": args.html_output,
        "question": "adopt_or_adjust_flow_map_display_encoding",
        "physicalFlowRun": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
