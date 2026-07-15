#!/usr/bin/env python3
"""Render the full approved Stage 20 estuary domain on GSI imagery."""

from __future__ import annotations

import argparse
import base64
import hashlib
import heapq
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


def colour(value: float) -> tuple[int, int, int, int]:
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
            return tuple(round(a + t * (b - a)) for a, b in zip(c0, c1)) + (92,)
    return stops[-1][1] + (92,)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mesh-manifest", default="public/data/onga/stage20/mesh-v1.json")
    parser.add_argument("--water-manifest", default="data/onga_unified_water_manifest_r3.json")
    parser.add_argument("--output", default="docs/visuals/stage20-estuary-overview-v1.png")
    parser.add_argument("--html-output", default="docs/visuals/stage20-estuary-overview-v1.html")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    mesh_manifest_path = root / args.mesh_manifest
    mesh_manifest = json.loads(mesh_manifest_path.read_text(encoding="utf-8"))
    binary_path = mesh_manifest_path.parent / mesh_manifest["binary"]["url"]
    payload = binary_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != mesh_manifest["binary"]["sha256"]:
        raise RuntimeError("browser mesh digest mismatch")

    def mesh_array(name: str) -> np.ndarray:
        descriptor = mesh_manifest["arrays"][name]
        dtype = np.int32 if descriptor["dtype"] == "int32" else np.uint8
        return np.frombuffer(
            payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])

    image_vertices = mesh_array("vertex_image_millipixel").astype(np.float64) / 1000.0
    local_vertices = mesh_array("vertex_local_mm").astype(np.float64) / 1000.0
    triangles = mesh_array("triangles").astype(np.int64)
    internal_cells = mesh_array("internal_face_cells").astype(np.int64)
    internal_vertices = mesh_array("internal_face_vertices").astype(np.int64)
    boundary_vertices = mesh_array("boundary_face_vertices").astype(np.int64)
    boundary_cells = mesh_array("boundary_face_cell").astype(np.int64)
    boundary_tags = mesh_array("boundary_face_tag").astype(np.uint8)
    barrage_ids = mesh_array("barrage_face_ids").astype(np.int64)
    fishway_cells = mesh_array("fishway_cells").astype(np.int64)

    water_manifest = json.loads((root / args.water_manifest).read_text(encoding="utf-8"))
    geographic = water_manifest["coordinateSystem"]["geographic"]
    zoom = 16
    min_x, max_x = 56553, 56558
    min_y, max_y = 26201, 26204
    tile_size = 256
    mosaic = Image.new("RGB", ((max_x - min_x + 1) * tile_size, (max_y - min_y + 1) * tile_size))
    tile_hashes: list[str] = []
    for tile_y in range(min_y, max_y + 1):
        for tile_x in range(min_x, max_x + 1):
            path = root / "data/external/gsi/seamlessphoto/z16" / f"{tile_x}-{tile_y}.jpg"
            raw = path.read_bytes()
            tile_hashes.append(hashlib.sha256(raw).hexdigest())
            tile = Image.open(path).convert("RGB")
            mosaic.paste(tile, ((tile_x - min_x) * tile_size, (tile_y - min_y) * tile_size))

    def project(point: np.ndarray) -> tuple[float, float]:
        lat, lon = image_to_latlon(float(point[0]), float(point[1]), geographic)
        wx, wy = lonlat_to_world_pixel(lon, lat, zoom)
        return wx - min_x * tile_size, wy - min_y * tile_size

    projected = np.asarray([project(point) for point in image_vertices])
    centroids = projected[triangles].mean(axis=1)
    local_centroids = local_vertices[triangles].mean(axis=1)

    adjacency: list[list[tuple[int, float]]] = [[] for _ in range(len(triangles))]
    for left, right in internal_cells:
        weight = float(np.linalg.norm(local_centroids[right] - local_centroids[left]))
        adjacency[int(left)].append((int(right), weight))
        adjacency[int(right)].append((int(left), weight))
    m_seeds = np.unique(boundary_cells[boundary_tags == 1])
    distances = np.full(len(triangles), np.inf)
    queue: list[tuple[float, int]] = []
    for seed in m_seeds:
        distances[int(seed)] = 0.0
        heapq.heappush(queue, (0.0, int(seed)))
    while queue:
        distance, cell = heapq.heappop(queue)
        if distance != distances[cell]:
            continue
        for neighbour, weight in adjacency[cell]:
            candidate = distance + weight
            if candidate < distances[neighbour]:
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    maximum_distance = float(np.max(distances))
    speed_fraction = 0.12 + 0.88 * (1.0 - distances / maximum_distance)

    direction = np.zeros((len(triangles), 2), dtype=float)
    for cell, neighbours in enumerate(adjacency):
        for neighbour, _ in neighbours:
            drop = distances[cell] - distances[neighbour]
            if drop <= 0:
                continue
            vector = centroids[neighbour] - centroids[cell]
            length = float(np.linalg.norm(vector))
            if length > 0:
                direction[cell] += drop * vector / length
        norm = float(np.linalg.norm(direction[cell]))
        if norm > 0:
            direction[cell] /= norm

    padding = 24
    x0 = max(0, int(np.floor(projected[:, 0].min())) - padding)
    x1 = min(mosaic.width, int(np.ceil(projected[:, 0].max())) + padding)
    y0 = max(0, int(np.floor(projected[:, 1].min())) - padding)
    y1 = min(mosaic.height, int(np.ceil(projected[:, 1].max())) + padding)
    crop = mosaic.crop((x0, y0, x1, y1))
    crop_projected = projected - np.asarray([x0, y0])
    crop_centroids = centroids - np.asarray([x0, y0])
    overlay = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay, "RGBA")
    for cell in range(len(triangles)):
        polygon = [tuple(point) for point in crop_projected[triangles[cell]]]
        draw_overlay.polygon(polygon, fill=colour(float(speed_fraction[cell])))

    bins: dict[tuple[int, int], tuple[int, float]] = {}
    for cell, centre in enumerate(crop_centroids):
        key = (int(centre[0] // 48), int(centre[1] // 48))
        target = np.asarray([(key[0] + 0.5) * 48, (key[1] + 0.5) * 48])
        score = float(np.linalg.norm(centre - target))
        if key not in bins or score < bins[key][1]:
            bins[key] = (cell, score)
    for cell, _ in bins.values():
        if not np.any(direction[cell]):
            continue
        start = crop_centroids[cell]
        length = 12 + 14 * float(speed_fraction[cell])
        end = start + direction[cell] * length
        draw_overlay.line([tuple(start), tuple(end)], fill=(20, 33, 40, 215), width=5)
        draw_overlay.line([tuple(start), tuple(end)], fill=(255, 255, 255, 245), width=2)
        angle = math.atan2(direction[cell, 1], direction[cell, 0])
        for delta in (-2.55, 2.55):
            wing = end + 6 * np.asarray([math.cos(angle + delta), math.sin(angle + delta)])
            draw_overlay.line([tuple(end), tuple(wing)], fill=(20, 33, 40, 225), width=4)
            draw_overlay.line([tuple(end), tuple(wing)], fill=(255, 255, 255, 250), width=2)

    barrage_segments = crop_projected[internal_vertices[barrage_ids]]
    for segment in barrage_segments:
        draw_overlay.line([tuple(segment[0]), tuple(segment[1])], fill=(255, 255, 255, 245), width=9)
        draw_overlay.line([tuple(segment[0]), tuple(segment[1])], fill=(7, 112, 168, 255), width=5)
    for centre in crop_centroids[fishway_cells]:
        cx, cy = centre
        draw_overlay.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=(246, 189, 69, 255), outline=(255, 255, 255, 255), width=2)

    boundary_names = {1: "M 河口", 2: "N", 3: "O 上流", 4: "G"}
    boundary_positions: dict[int, np.ndarray] = {}
    face_midpoints = crop_projected[boundary_vertices].mean(axis=1)
    for tag, name in boundary_names.items():
        position = face_midpoints[boundary_tags == tag].mean(axis=0)
        boundary_positions[tag] = position
        x, y = position
        draw_overlay.ellipse((x - 11, y - 11, x + 11, y + 11), fill=(255, 255, 255, 245), outline=(20, 72, 95, 255), width=3)
        draw_overlay.text((x + 15, y - 16), name, font=font(20, True), fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(20, 72, 95, 255))
    barrage_midpoint = barrage_segments.mean(axis=(0, 1))
    draw_overlay.text(tuple(barrage_midpoint + np.asarray([12, -34])), "河口堰", font=font(20, True), fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(7, 80, 120, 255))
    map_image = Image.alpha_composite(crop.convert("RGBA"), overlay).convert("RGB")

    canvas = Image.new("RGB", (1600, 1260), (244, 247, 248))
    draw = ImageDraw.Draw(canvas)
    draw.text((50, 35), "遠賀川河口　計算領域の全体俯瞰", font=font(42, True), fill=(23, 49, 61))
    draw.text(
        (50, 91),
        f"承認済み{mesh_manifest['counts']['cells']:,}セル全域／M・N・O・G境界／河口堰・魚道",
        font=font(22),
        fill=(72, 98, 111),
    )
    map_width, map_height = 1500, 950
    fitted = map_image.copy()
    fitted.thumbnail((map_width, map_height), Image.Resampling.LANCZOS)
    map_x = 50 + (map_width - fitted.width) // 2
    map_y = 140 + (map_height - fitted.height) // 2
    canvas.paste(fitted, (map_x, map_y))
    draw.rectangle((map_x, map_y, map_x + fitted.width, map_y + fitted.height), outline=(199, 211, 216), width=2)
    north_x, north_y = map_x + fitted.width - 45, map_y + 55
    draw.polygon([(north_x, north_y - 30), (north_x - 10, north_y + 8), (north_x, north_y), (north_x + 10, north_y + 8)], fill=(255, 255, 255), outline=(23, 49, 61))
    draw.text((north_x - 8, north_y + 12), "北", font=font(17, True), fill=(255, 255, 255), stroke_width=3, stroke_fill=(23, 49, 61))

    draw.rounded_rectangle((50, 1110, 1550, 1210), radius=18, fill=(255, 255, 255), outline=(199, 211, 216), width=2)
    draw.text((80, 1130), "表示確認用の合成流速場", font=font(21, True), fill=(23, 49, 61))
    draw.text((80, 1170), "色＝速さ　白矢印＝河道に沿う向き　青線＝河口堰　黄点＝魚道両側", font=font(19), fill=(46, 73, 86))
    bar_x0, bar_y0, bar_w, bar_h = 1010, 1135, 460, 22
    for x in range(bar_w):
        draw.line((bar_x0 + x, bar_y0, bar_x0 + x, bar_y0 + bar_h), fill=colour(x / (bar_w - 1))[:3])
    draw.text((bar_x0, 1168), "遅い", font=font(17), fill=(72, 98, 111))
    draw.text((bar_x0 + bar_w - 45, 1168), "速い", font=font(17), fill=(72, 98, 111))
    draw.text((50, 1225), "流速値と向きは全域表示の確認用に作った合成場です。物理計算結果ではありません。背景：国土地理院", font=font(17), fill=(72, 98, 111))

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
    jpeg = output.with_suffix(".jpg")
    canvas.save(jpeg, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(jpeg.read_bytes()).decode("ascii")
    html = f'''<div id="stage20-estuary-overview" style="display:grid;gap:0.75rem;color:var(--foreground);">
  <img src="data:image/jpeg;base64,{encoded}" alt="遠賀川河口の承認済み計算領域全体を空中写真上に表示し、M・N・O・G境界、河口堰、魚道、合成流速の色と矢印を重ねた俯瞰画像" style="display:block;width:100%;height:auto;" />
</div>
'''
    (root / args.html_output).write_text(html, encoding="utf-8")
    print(json.dumps({
        "status": "rendered",
        "output": args.output,
        "pngSha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "jpegSha256": hashlib.sha256(jpeg.read_bytes()).hexdigest(),
        "tileCount": len(tile_hashes),
        "tileSetSha256": hashlib.sha256("".join(tile_hashes).encode("ascii")).hexdigest(),
        "meshBinarySha256": mesh_manifest["binary"]["sha256"],
        "physicalFlowRun": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
