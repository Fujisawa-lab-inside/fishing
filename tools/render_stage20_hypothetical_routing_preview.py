#!/usr/bin/env python3
"""Render four cell-referenced maps for one explicitly hypothetical flow case.

This is a quasi-steady graph-routing preview.  It is intentionally separate
from the shallow-water solver and must not be presented as a physical result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_stage17_station_boundary_compatibility import image_to_latlon  # noqa: E402
from render_stage20_barrage_satellite_comparison import lonlat_to_world_pixel  # noqa: E402


TAG_NAME = {1: "M", 2: "N", 3: "O", 4: "G"}
SCENARIO_JA = "3日間降雨後相当・河口堰全開・大潮相当・下げ三分"
DISCLAIMER_JA = "準定常経路プレビュー／浅水方程式の物理計算結果ではない"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    mac_hiragino = sorted(Path("/System/Library/Fonts").glob("*W6.ttc" if bold else "*W3.ttc"))
    candidates = [
        *map(str, mac_hiragino),
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
        if bold
        else "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_mesh(manifest_path: Path) -> tuple[dict, dict[str, np.ndarray]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = manifest_path.parent / manifest["binary"]["url"]
    payload = payload_path.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == manifest["binary"]["sha256"], "mesh digest mismatch")
    arrays: dict[str, np.ndarray] = {}
    for name, descriptor in manifest["arrays"].items():
        dtype = np.int32 if descriptor["dtype"] == "int32" else np.uint8
        arrays[name] = np.frombuffer(
            payload,
            dtype=dtype,
            count=math.prod(descriptor["shape"]),
            offset=descriptor["byteOffset"],
        ).reshape(descriptor["shape"])
    return manifest, arrays


def boundary_face_lengths(package: dict[str, np.ndarray], local_vertices: np.ndarray) -> np.ndarray:
    endpoints = local_vertices[package["boundary_face_vertices"].astype(np.int64)]
    return np.linalg.norm(endpoints[:, 1] - endpoints[:, 0], axis=1)


def tide_state(candidate: dict) -> dict[str, float]:
    """Return spring-tide proxy at 30% of the 21:00-to-03:00 ebb."""
    hour = 21.0 + 0.3 * 6.0
    values = np.asarray(
        candidate["candidateCurve"]["relativeAnomalyM"]
        + [candidate["candidateCurve"]["nextDayZeroHourRelativeAnomalyM"]],
        dtype=np.float64,
    )
    reference = float(np.interp(hour, np.arange(25, dtype=np.float64), values))
    left = int(math.floor(hour))
    slope_reference = float(values[left + 1] - values[left]) / 3600.0
    multiplier = 1.4
    return {
        "ebbFraction": 0.3,
        "curveHour": hour,
        "amplitudeMultiplier": multiplier,
        "relativeAnomalyM": reference * multiplier,
        "levelSlopeMPerS": slope_reference * multiplier,
        "levelSlopeMPerHour": slope_reference * multiplier * 3600.0,
    }


def build_case() -> dict:
    return {
        "bathymetry": {
            "sigma": 0.36,
            "mainstemMeanDepthM": 4.0,
            "tributaryMeanDepthM": 1.8,
        },
        "roughness": {
            "manningOpenChannel": 0.03,
            "shallowMarginMultiplier": 1.25,
            "structureVicinityMultiplier": 1.15,
        },
        "barrage": {
            "scenario": "uniform_100_percent",
            "effectiveDischargeCoefficient": 0.65,
        },
        "fishway": {
            "mode": "head_difference_relation_ensemble",
            "effectiveDischargeCoefficient": 0.6,
            "effectiveAreaM2": 1.0,
        },
        "boundaries": {
            "M": {"phaseShiftMinutes": 0.0, "amplitudeMultiplier": 1.4, "meanOffsetM": None},
            "N": {"dischargeM3S": 12.0},
            "O": {"dischargeM3S": 180.0},
            "G": {"dischargeM3S": 8.0},
        },
    }


def solve_routing_proxy(
    package: dict[str, np.ndarray], fields: dict, tide: dict[str, float]
) -> dict[str, np.ndarray | float | dict]:
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve

    geometry = fields["geometry"]
    centres = geometry["localCentroids"]
    vertices = geometry["localVertices"]
    depth = fields["initialWaterDepthM"]
    manning = fields["manningN"]
    areas = geometry["areas"]
    face_vertices = package["internal_face_vertices"].astype(np.int64)
    face_cells = package["internal_face_cells"].astype(np.int64)
    left, right = face_cells.T
    face_length = np.linalg.norm(vertices[face_vertices[:, 1]] - vertices[face_vertices[:, 0]], axis=1)
    distance = np.linalg.norm(centres[right] - centres[left], axis=1)
    h = 0.5 * (depth[left] + depth[right])
    n = 0.5 * (manning[left] + manning[right])
    conductance = (h ** (5.0 / 3.0) / n) * face_length / np.maximum(distance, 1e-9)
    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    conductance[barrage_ids] *= float(fields["barrageTransmissivity"])
    require(np.all(np.isfinite(conductance)) and np.all(conductance > 0), "invalid conductance")

    ncell = len(centres)
    source = np.zeros(ncell, dtype=np.float64)
    tags = package["boundary_face_tag"].astype(np.uint8)
    boundary_cells = package["boundary_face_cell"].astype(np.int64)
    b_length = boundary_face_lengths(package, vertices)
    discharge_by_boundary = fields["boundaryDischargeM3S"]
    for tag, name in ((2, "N"), (3, "O"), (4, "G")):
        selected = np.where(tags == tag)[0]
        weights = b_length[selected] / float(b_length[selected].sum())
        np.add.at(source, boundary_cells[selected], float(discharge_by_boundary[name]) * weights)

    mouth_cells = np.unique(boundary_cells[tags == 1])
    free = np.ones(ncell, dtype=bool)
    free[mouth_cells] = False
    storage_release = max(-float(tide["levelSlopeMPerS"]), 0.0) * areas
    storage_release[~free] = 0.0
    source += storage_release

    row = np.concatenate([left, right, left, right])
    col = np.concatenate([left, right, right, left])
    val = np.concatenate([conductance, conductance, -conductance, -conductance])
    laplacian = coo_matrix((val, (row, col)), shape=(ncell, ncell)).tocsr()
    free_ids = np.where(free)[0]
    potential = np.zeros(ncell, dtype=np.float64)
    potential[free_ids] = spsolve(laplacian[free_ids][:, free_ids], source[free_ids])
    require(np.all(np.isfinite(potential)), "routing solve produced non-finite potential")

    discharge = conductance * (potential[left] - potential[right])
    divergence = np.asarray(laplacian @ potential).ravel()
    residual = divergence[free] - source[free]
    total_source = float(source.sum())
    mouth_sink = float(divergence[mouth_cells].sum())
    require(abs(mouth_sink + total_source) < max(1e-7, total_source * 1e-9), "mass balance failed")

    # Reconstruct a direction from the same signed face fluxes used by the graph solve.
    direction_sum = np.zeros((ncell, 2), dtype=np.float64)
    throughput = np.zeros(ncell, dtype=np.float64)
    width_sum = np.zeros(ncell, dtype=np.float64)
    unit = (centres[right] - centres[left]) / np.maximum(distance[:, None], 1e-12)
    vector_flux = discharge[:, None] * unit
    np.add.at(direction_sum, left, vector_flux)
    np.add.at(direction_sum, right, vector_flux)
    np.add.at(throughput, left, 0.5 * np.abs(discharge))
    np.add.at(throughput, right, 0.5 * np.abs(discharge))
    np.add.at(width_sum, left, 0.5 * face_length)
    np.add.at(width_sum, right, 0.5 * face_length)
    speed = throughput / np.maximum(depth * width_sum, 1e-9)
    norm = np.linalg.norm(direction_sum, axis=1)
    velocity_local = np.zeros_like(direction_sum)
    moving = norm > 1e-12
    velocity_local[moving] = direction_sum[moving] / norm[moving, None] * speed[moving, None]
    require(np.all(np.isfinite(velocity_local)), "invalid reconstructed velocity")
    return {
        "potential": potential,
        "faceDischargeM3S": discharge,
        "velocityLocalMPS": velocity_local,
        "speedMPS": speed,
        "sourceM3S": source,
        "storageReleaseM3S": storage_release,
        "massBalance": {
            "riverInflowM3S": float(sum(discharge_by_boundary.values())),
            "fallingTideStorageReleaseM3S": float(storage_release.sum()),
            "totalSourceM3S": total_source,
            "mouthSinkM3S": mouth_sink,
            "maxFreeCellResidualM3S": float(np.max(np.abs(residual))),
        },
    }


def colour(value: float, ceiling: float, alpha: int = 112) -> tuple[int, int, int, int]:
    stops = [
        (0.0, (27, 107, 174)),
        (0.32, (37, 167, 184)),
        (0.63, (246, 188, 65)),
        (1.0, (218, 69, 55)),
    ]
    x = float(np.clip(value / max(ceiling, 1e-12), 0.0, 1.0))
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0)
            return tuple(round(a + t * (b - a)) for a, b in zip(c0, c1)) + (alpha,)
    return stops[-1][1] + (alpha,)


def stitch_tiles(tile_root: Path, zoom: int, box: tuple[int, int, int, int]) -> tuple[Image.Image, np.ndarray]:
    x0, y0, x1, y1 = box
    mosaic = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            path = tile_root / f"z{zoom}" / f"{tx}-{ty}.jpg"
            require(path.exists(), f"missing GSI tile: {path}")
            tile = Image.open(path).convert("RGB")
            mosaic.paste(tile, ((tx - x0) * 256, (ty - y0) * 256))
    return mosaic, np.asarray([x0 * 256.0, y0 * 256.0])


def arrow(draw: ImageDraw.ImageDraw, start: np.ndarray, vector: np.ndarray, length: float, width: int) -> None:
    magnitude = float(np.linalg.norm(vector))
    if magnitude <= 1e-12:
        return
    unit = vector / magnitude
    end = start + unit * length
    outline = (16, 29, 35, 245)
    inside = (255, 255, 255, 255)
    draw.line([tuple(start), tuple(end)], fill=outline, width=width + 3)
    draw.line([tuple(start), tuple(end)], fill=inside, width=width)
    angle = math.atan2(unit[1], unit[0])
    wing = max(6.0, length * 0.27)
    for delta in (-2.55, 2.55):
        point = end + wing * np.asarray([math.cos(angle + delta), math.sin(angle + delta)])
        draw.line([tuple(end), tuple(point)], fill=outline, width=width + 2)
        draw.line([tuple(end), tuple(point)], fill=inside, width=max(1, width - 1))


def project_vertices(
    image_vertices: np.ndarray, geographic: dict, zoom: int
) -> np.ndarray:
    projected = []
    for x, y in image_vertices:
        lat, lon = image_to_latlon(float(x), float(y), geographic)
        projected.append(lonlat_to_world_pixel(lon, lat, zoom))
    return np.asarray(projected, dtype=np.float64)


def image_point_to_world(point: np.ndarray, geographic: dict, zoom: int) -> np.ndarray:
    lat, lon = image_to_latlon(float(point[0]), float(point[1]), geographic)
    return np.asarray(lonlat_to_world_pixel(lon, lat, zoom), dtype=np.float64)


def render_view(
    *,
    output: Path,
    title: str,
    zoom: int,
    tile_box: tuple[int, int, int, int],
    crop_center_world: np.ndarray | None,
    crop_size_world: tuple[int, int] | None,
    tile_root: Path,
    projected_vertices: np.ndarray,
    triangles: np.ndarray,
    projected_centres: np.ndarray,
    velocity_screen: np.ndarray,
    speed: np.ndarray,
    depth: np.ndarray,
    area: np.ndarray,
    ceiling: float,
    barrage_segments: np.ndarray,
    fishway_centres: np.ndarray,
    confluence_world: np.ndarray,
    bin_pixels: int,
    draw_mesh: bool,
    marks: tuple[str, ...],
    scenario_label: str = SCENARIO_JA,
    disclaimer_label: str = DISCLAIMER_JA,
) -> dict:
    mosaic, world_origin = stitch_tiles(tile_root, zoom, tile_box)
    if crop_center_world is None:
        crop = mosaic
        crop_origin = world_origin
    else:
        width, height = crop_size_world or mosaic.size
        left = int(round(crop_center_world[0] - world_origin[0] - width / 2))
        top = int(round(crop_center_world[1] - world_origin[1] - height / 2))
        crop = mosaic.crop((left, top, left + width, top + height))
        crop_origin = world_origin + np.asarray([left, top], dtype=np.float64)

    map_size = (1400, 740)
    scale = min(map_size[0] / crop.width, map_size[1] / crop.height)
    resized = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1500, 1080), (242, 246, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((50, 28), title, font=font(38, True), fill=(22, 47, 59))
    draw.text((50, 80), scenario_label, font=font(22), fill=(62, 87, 99))
    map_xy = np.asarray([50.0, 130.0])
    canvas.paste(resized, tuple(map_xy.astype(int)))
    map_wh = np.asarray(resized.size, dtype=np.float64)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay, "RGBA")
    local_vertices = (projected_vertices - crop_origin) * scale + map_xy
    local_centres = (projected_centres - crop_origin) * scale + map_xy
    visible = np.where(
        (local_centres[:, 0] >= map_xy[0])
        & (local_centres[:, 0] <= map_xy[0] + map_wh[0])
        & (local_centres[:, 1] >= map_xy[1])
        & (local_centres[:, 1] <= map_xy[1] + map_wh[1])
    )[0]
    for cell in visible:
        polygon = [tuple(p) for p in local_vertices[triangles[cell]]]
        odraw.polygon(polygon, fill=colour(float(speed[cell]), ceiling, 76 if zoom == 16 else 92))
        if draw_mesh:
            odraw.line(polygon + [polygon[0]], fill=(255, 255, 255, 65), width=1)

    # Every display arrow is a depth-area weighted aggregation of the cells in its bin.
    bins: dict[tuple[int, int], list[int]] = {}
    for cell in visible:
        key = (
            int((local_centres[cell, 0] - map_xy[0]) // bin_pixels),
            int((local_centres[cell, 1] - map_xy[1]) // bin_pixels),
        )
        bins.setdefault(key, []).append(int(cell))
    arrow_count = 0
    for ids in bins.values():
        cells = np.asarray(ids, dtype=np.int64)
        weights = depth[cells] * area[cells]
        vector = np.average(velocity_screen[cells], axis=0, weights=weights)
        magnitude = float(np.linalg.norm(vector))
        if magnitude < max(0.004, ceiling * 0.012):
            continue
        start = np.average(local_centres[cells], axis=0, weights=weights)
        length = 13.0 + 34.0 * min(magnitude / ceiling, 1.0)
        arrow(odraw, start, vector, length, 2 if zoom == 16 else 3)
        arrow_count += 1

    if "barrage" in marks:
        segments = (barrage_segments - crop_origin) * scale + map_xy
        for segment in segments:
            odraw.line([tuple(segment[0]), tuple(segment[1])], fill=(17, 102, 196, 255), width=5)
        centre = segments.mean(axis=(0, 1))
        odraw.rounded_rectangle((centre[0] + 10, centre[1] - 38, centre[0] + 190, centre[1] - 5), 8, fill=(17, 102, 196, 230))
        odraw.text((centre[0] + 20, centre[1] - 34), "河口堰（全開）", font=font(18, True), fill=(255, 255, 255, 255))
    if "fishway" in marks:
        points = (fishway_centres - crop_origin) * scale + map_xy
        labels = ("魚道・上流側セル", "魚道・河口側セル")
        for point, label in zip(points, labels):
            odraw.ellipse((point[0] - 8, point[1] - 8, point[0] + 8, point[1] + 8), fill=(232, 67, 127, 255), outline=(255, 255, 255, 255), width=3)
            odraw.text((point[0] + 12, point[1] - 13), label, font=font(17, True), fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(21, 34, 40, 220))
        odraw.line([tuple(points[0]), tuple(points[1])], fill=(232, 67, 127, 230), width=3)
    if "confluence" in marks:
        point = (confluence_world - crop_origin) * scale + map_xy
        odraw.ellipse((point[0] - 8, point[1] - 8, point[0] + 8, point[1] + 8), fill=(232, 67, 127, 255), outline=(255, 255, 255, 255), width=3)
        odraw.text((point[0] + 14, point[1] - 16), "曲川・遠賀川合流部先端", font=font(18, True), fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(21, 34, 40, 230))

    # Keep edge-cell polygons and arrows inside the map; they must not cover the title or footer.
    clip = Image.new("L", canvas.size, 0)
    cdraw = ImageDraw.Draw(clip)
    cdraw.rectangle(
        (
            int(map_xy[0]),
            int(map_xy[1]),
            int(map_xy[0] + map_wh[0]),
            int(map_xy[1] + map_wh[1]),
        ),
        fill=255,
    )
    overlay.putalpha(ImageChops.multiply(overlay.getchannel("A"), clip))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    legend_x, legend_y = 1080, 914
    draw.rounded_rectangle((1040, 890, 1450, 1000), radius=14, fill=(255, 255, 255), outline=(190, 204, 210), width=2)
    for index in range(240):
        value = ceiling * index / 239.0
        draw.line((legend_x + index, legend_y, legend_x + index, legend_y + 22), fill=colour(value, ceiling, 255)[:3])
    draw.text((1058, 952), "0", font=font(15), fill=(38, 61, 71))
    draw.text((1288, 952), f"{ceiling:.2f} m/s（表示上限）", font=font(15), fill=(38, 61, 71))
    draw.text((50, 894), "色・矢印は同じメッシュセル値を参照。矢印は水深×面積で集約。", font=font(18), fill=(52, 78, 90))
    draw.text((50, 938), disclaimer_label, font=font(21, True), fill=(155, 51, 42))
    draw.text((50, 992), "背景：国土地理院「全国最新写真（シームレス）」", font=font(16), fill=(73, 95, 105))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
    return {
        "path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "visibleCells": int(len(visible)),
        "displayArrows": int(arrow_count),
        "zoom": zoom,
    }


def main() -> None:
    from stage19_solver_inputs import (
        build_case_fields,
        classify_branch_ownership,
        load_water_mask,
        mesh_geometry,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default="docs/visuals")
    parser.add_argument("--report", default="config/stage20_hypothetical_rain3d_spring_ebb3_v1.json")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    manifest, package = load_mesh(root / "public/data/onga/stage20/mesh-v1.json")
    water_manifest, water_mask = load_water_mask(root / "data/onga_unified_water_manifest_r3.json")
    geometry = mesh_geometry(package)
    owner = classify_branch_ownership(package, geometry)
    case = build_case()
    fields = build_case_fields(case, package, water_mask, geometry=geometry, owner=owner)
    tide_candidate = json.loads((root / "config/stage19_m_boundary_tide_candidate_v1.json").read_text(encoding="utf-8"))
    tide = tide_state(tide_candidate)
    solution = solve_routing_proxy(package, fields, tide)

    geographic = water_manifest["coordinateSystem"]["geographic"]
    image_vertices = geometry["imageVertices"]
    triangles = geometry["triangles"]
    image_centres = geometry["imageCentroids"]
    local_velocity = solution["velocityLocalMPS"]
    speed = solution["speedMPS"]
    moving = speed > 1e-6
    ceiling = float(np.percentile(speed[moving], 95.0))

    projections: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for zoom in (16, 18):
        p_vertices = project_vertices(image_vertices, geographic, zoom)
        p_centres = p_vertices[triangles].mean(axis=1)
        # Convert local velocity direction into the same screen basis by projecting a short endpoint.
        endpoint_image = image_centres + np.column_stack((local_velocity[:, 0], -local_velocity[:, 1]))
        endpoint_world = np.asarray([
            image_point_to_world(point, geographic, zoom) for point in endpoint_image
        ])
        velocity_screen = endpoint_world - p_centres
        velocity_screen *= np.divide(
            speed,
            np.maximum(np.linalg.norm(velocity_screen, axis=1), 1e-12),
        )[:, None]
        projections[zoom] = (p_vertices, p_centres, velocity_screen)

    internal_vertices = package["internal_face_vertices"].astype(np.int64)
    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    fishway_cells = package["fishway_cells"].astype(np.int64)
    confluence_image = np.asarray([1168.0, 441.0])
    tile_root = root / "data/external/gsi/seamlessphoto"
    output_dir = root / args.output_dir
    views = []
    specs = [
        ("stage20-rain3d-ebb3-estuary-v1.jpg", "1／4　河口全域", 16, (56553, 26201, 56558, 26204), None, None, 68, False, ("barrage", "confluence")),
        ("stage20-rain3d-ebb3-barrage-v1.jpg", "2／4　河口堰付近", 18, (226225, 104811, 226231, 104816), "barrage", (1100, 580), 58, True, ("barrage",)),
        ("stage20-rain3d-ebb3-confluence-v1.jpg", "3／4　曲川・遠賀川合流地点付近", 18, (226224, 104808, 226231, 104814), "confluence", (1180, 625), 58, True, ("confluence",)),
        ("stage20-rain3d-ebb3-fishway-v1.jpg", "4／4　魚道付近", 18, (226224, 104812, 226231, 104816), "fishway", (1040, 550), 52, True, ("fishway", "barrage")),
    ]
    for filename, title, zoom, tile_box, centre_kind, crop_size, bins, mesh_lines, marks in specs:
        p_vertices, p_centres, velocity_screen = projections[zoom]
        barrage_segments = p_vertices[internal_vertices[barrage_ids]]
        fish_centres = p_centres[fishway_cells]
        confluence_world = image_point_to_world(confluence_image, geographic, zoom)
        centre = None
        if centre_kind == "barrage":
            centre = barrage_segments.mean(axis=(0, 1))
        elif centre_kind == "confluence":
            centre = confluence_world
        elif centre_kind == "fishway":
            centre = fish_centres.mean(axis=0)
        views.append(render_view(
            output=output_dir / filename,
            title=title,
            zoom=zoom,
            tile_box=tile_box,
            crop_center_world=centre,
            crop_size_world=crop_size,
            tile_root=tile_root,
            projected_vertices=p_vertices,
            triangles=triangles,
            projected_centres=p_centres,
            velocity_screen=velocity_screen,
            speed=speed,
            depth=fields["initialWaterDepthM"],
            area=geometry["areas"],
            ceiling=ceiling,
            barrage_segments=barrage_segments,
            fishway_centres=fish_centres,
            confluence_world=confluence_world,
            bin_pixels=bins,
            draw_mesh=mesh_lines,
            marks=marks,
        ))
        views[-1]["path"] = str((output_dir / filename).relative_to(root))

    report = {
        "schema": "onga-stage20-hypothetical-routing-preview-v1",
        "status": "approved_scenario_output_layout_not_physical_run",
        "scenario": {
            "labelJa": SCENARIO_JA,
            "rainInterpretation": "three_day_rainfall_aftermath_represented_by_approved_upper_inferred_N_O_G_discharges",
            "boundaryDischargeM3S": case["boundaries"],
            "barrage": case["barrage"],
            "fishway": case["fishway"],
            "tide": tide,
            "bathymetry": case["bathymetry"],
            "roughness": case["roughness"],
        },
        "modelClass": "quasi_steady_graph_routing_proxy",
        "mesh": {
            "manifest": "public/data/onga/stage20/mesh-v1.json",
            "binarySha256": manifest["binary"]["sha256"],
            "cells": manifest["counts"]["cells"],
        },
        "diagnostics": {
            "speedMPS": {
                "min": float(speed.min()),
                "median": float(np.median(speed)),
                "p95": ceiling,
                "max": float(speed.max()),
            },
            **solution["massBalance"],
        },
        "views": views,
        "visualDecision": {
            "question": "May these four extents and the mesh-referenced adaptive display be adopted as the scenario-output layout?",
            "approve": "adopt_view_extents_and_mesh_referenced_display_only",
            "revise": "revise_extents_or_display_before_physical_solver_output",
        },
        "layoutApproval": {
            "approved": True,
            "approvedDate": "2026-07-15",
            "sourceStatement": "採用します。作業を進めてください。",
            "approvedScope": [
                "four_view_extents_for_estuary_barrage_confluence_and_fishway",
                "mesh_referenced_speed_colour",
                "depth_area_weighted_adaptive_arrow_display",
                "shared_display_legend",
            ],
            "doesNotApprove": [
                "physical_correctness_of_preview_velocity",
                "rainfall_runoff_calibration",
                "numerical_execution",
                "public_simulator_connection",
                "main_merge",
            ],
        },
        "safeguards": {
            "shallowWaterSolverExecuted": False,
            "rainfallRunoffModelExecuted": False,
            "observedOngaMouthLevelAssigned": False,
            "physicalValidationClaimAllowed": False,
            "fishingOrSafetyPredictionAllowed": False,
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
