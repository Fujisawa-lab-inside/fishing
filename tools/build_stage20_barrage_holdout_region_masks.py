#!/usr/bin/env python3
"""Build digest-locked cell masks for the approved Stage 20 four-view layout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from render_stage20_hypothetical_routing_preview import (
    image_point_to_world,
    load_mesh,
    project_vertices,
)
from stage19_solver_inputs import mesh_geometry


VIEW_SPECS = (
    ("estuary", "河口全域", 16, (56553, 26201, 56558, 26204), None, None),
    ("barrage", "河口堰付近", 18, (226225, 104811, 226231, 104816), "barrage", (1100, 580)),
    ("confluence", "曲川・遠賀川合流地点付近", 18, (226224, 104808, 226231, 104814), "confluence", (1180, 625)),
    ("fishway", "魚道付近", 18, (226224, 104812, 226231, 104816), "fishway", (1040, 550)),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crop_geometry(
    tile_box: tuple[int, int, int, int],
    centre: np.ndarray | None,
    crop_size: tuple[int, int] | None,
) -> tuple[np.ndarray, np.ndarray]:
    min_x, min_y, max_x, max_y = tile_box
    world_origin = np.asarray([min_x * 256, min_y * 256], dtype=np.float64)
    mosaic_size = np.asarray([(max_x - min_x + 1) * 256, (max_y - min_y + 1) * 256], dtype=np.float64)
    if centre is None:
        return world_origin, mosaic_size
    width, height = crop_size or tuple(int(value) for value in mosaic_size)
    left = int(round(float(centre[0] - world_origin[0] - width / 2)))
    top = int(round(float(centre[1] - world_origin[1] - height / 2)))
    return world_origin + np.asarray([left, top], dtype=np.float64), np.asarray([width, height], dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mesh-manifest", default="public/data/onga/stage20/mesh-v2.json")
    parser.add_argument("--binary-output", default="data/onga_stage20_barrage_holdout_region_masks_v1.bin")
    parser.add_argument("--manifest-output", default="config/stage20_barrage_holdout_region_masks_v1.json")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    mesh_path = root / args.mesh_manifest
    mesh_manifest, package = load_mesh(mesh_path)
    geometry = mesh_geometry(package)
    water_manifest = json.loads((root / "data/onga_unified_water_manifest_r3.json").read_text(encoding="utf-8"))
    geographic = water_manifest["coordinateSystem"]["geographic"]
    triangles = geometry["triangles"]
    image_vertices = geometry["imageVertices"]
    projected_centres = {}
    projected_vertices = {}
    for zoom in (16, 18):
        vertices = project_vertices(image_vertices, geographic, zoom)
        projected_vertices[zoom] = vertices
        projected_centres[zoom] = vertices[triangles].mean(axis=1)

    internal_vertices = package["internal_face_vertices"].astype(np.int64)
    barrage_ids = package["barrage_face_ids"].astype(np.int64)
    barrage_centre = projected_vertices[18][internal_vertices[barrage_ids]].mean(axis=(0, 1))
    fishway_cells = package["fishway_cells"].astype(np.int64)
    fishway_centre = projected_centres[18][fishway_cells].mean(axis=0)
    confluence_centre = image_point_to_world(np.asarray([1168.0, 441.0]), geographic, 18)
    centres = {
        "barrage": barrage_centre,
        "confluence": confluence_centre,
        "fishway": fishway_centre,
    }

    binary_path = root / args.binary_output
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = root / args.manifest_output
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    views = []
    for view_id, label, zoom, tile_box, centre_kind, crop_size in VIEW_SPECS:
        origin, size = crop_geometry(tile_box, centres.get(centre_kind), crop_size)
        points = projected_centres[zoom]
        scale = min(1400.0 / size[0], 740.0 / size[1])
        rendered_size = np.asarray(
            [round(float(size[0] * scale)), round(float(size[1] * scale))],
            dtype=np.float64,
        )
        local_points = (points - origin) * scale
        ids = np.where(
            (local_points[:, 0] >= 0.0)
            & (local_points[:, 0] <= rendered_size[0])
            & (local_points[:, 1] >= 0.0)
            & (local_points[:, 1] <= rendered_size[1])
        )[0].astype("<i4", copy=False)
        encoded = ids.tobytes(order="C")
        offset = len(payload)
        payload.extend(encoded)
        views.append(
            {
                "id": view_id,
                "legacyAlias": "full_estuary" if view_id == "estuary" else None,
                "labelJa": label,
                "zoom": zoom,
                "tileBox": list(tile_box),
                "cropCentreKind": centre_kind,
                "cropSizeWorldPixels": list(crop_size) if crop_size else None,
                "byteOffset": offset,
                "byteLength": len(encoded),
                "dtype": "int32-le",
                "cellCount": int(len(ids)),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )

    binary_path.write_bytes(bytes(payload))
    result = {
        "schema": "onga-stage20-barrage-holdout-region-masks-v1",
        "status": "digest_locked_before_recovery_execution",
        "sourceLayout": "approved_stage20_four_view_extents",
        "mesh": {
            "manifest": args.mesh_manifest,
            "binarySha256": mesh_manifest["binary"]["sha256"],
            "cellCount": mesh_manifest["counts"]["cells"],
        },
        "binary": {
            "path": args.binary_output,
            "byteLength": len(payload),
            "sha256": sha256(binary_path),
        },
        "views": views,
        "comparisonRule": "cell_centre_inside_approved_render_extent",
        "safeguards": {
            "resultFieldsRead": False,
            "physicalRunPerformed": False,
            "publicSimulatorConnected": False,
        },
    }
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
