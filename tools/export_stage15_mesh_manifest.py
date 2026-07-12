#!/usr/bin/env python3
"""Export Stage 11/12 NPZ mesh products to the Stage 15 chunked JSON schema."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

MANIFEST_SCHEMA = "onga-stage15-unstructured-mesh-manifest-v1"
CHUNK_SCHEMA = "onga-stage15-unstructured-mesh-chunk-v1"


def fnv1a32(text: str) -> str:
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def javascript_canonical_json(values: Sequence[object]) -> str:
    """Return exactly the string produced by JavaScript JSON.stringify after parsing."""
    python_json = json.dumps(values, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    script = (
        "const fs=require('node:fs');"
        "const value=JSON.parse(fs.readFileSync(0,'utf8'));"
        "process.stdout.write(JSON.stringify(value));"
    )
    result = subprocess.run(
        ["node", "-e", script],
        input=python_json,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def rows_from_array(array: np.ndarray, *, integer: bool = False) -> list[list[object]]:
    result: list[list[object]] = []
    for row in np.asarray(array):
        values: list[object] = []
        for value in np.asarray(row).tolist():
            if integer:
                values.append(int(value))
            elif isinstance(value, (int, np.integer)):
                values.append(int(value))
            else:
                numeric = float(value)
                if not np.isfinite(numeric):
                    raise ValueError("mesh data contains NaN or infinity")
                values.append(numeric)
        result.append(values)
    return result


def write_chunk(
    output_directory: Path,
    kind: str,
    start: int,
    values: Sequence[object],
    chunk_index: int,
) -> dict[str, object]:
    canonical = javascript_canonical_json(values)
    filename = f"{kind}_{chunk_index:04d}.json"
    payload = (
        "{"
        f'"schema":{json.dumps(CHUNK_SCHEMA)},'
        f'"kind":{json.dumps(kind)},'
        f'"start":{start},'
        f'"values":{canonical}'
        "}\n"
    )
    (output_directory / filename).write_text(payload, encoding="utf-8")
    return {
        "kind": kind,
        "start": start,
        "count": len(values),
        "url": f"./{filename}",
        "checksum": fnv1a32(canonical),
    }


def write_chunks(
    output_directory: Path,
    kind: str,
    rows: Sequence[object],
    chunk_size: int,
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    for chunk_index, start in enumerate(range(0, len(rows), chunk_size)):
        values = rows[start : start + chunk_size]
        chunks.append(write_chunk(output_directory, kind, start, values, chunk_index))
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True, type=Path, help="Stage 11 mesh NPZ")
    parser.add_argument("--connectivity", required=True, type=Path, help="Stage 12 FV connectivity NPZ")
    parser.add_argument("--output", required=True, type=Path, help="Output directory")
    parser.add_argument("--chunk-size", type=int, default=10000)
    parser.add_argument("--version", default="stage15-production-mesh-candidate1")
    args = parser.parse_args()

    if args.chunk_size <= 0:
        raise ValueError("chunk size must be positive")
    args.output.mkdir(parents=True, exist_ok=True)

    with np.load(args.mesh) as mesh, np.load(args.connectivity) as connectivity:
        vertices = rows_from_array(mesh["vertices"])
        triangles = rows_from_array(mesh["triangles"], integer=True)
        interior_faces = rows_from_array(connectivity["interior_edges"])
        boundary_raw = np.asarray(connectivity["boundary_edges"])
        markers = np.asarray(connectivity["boundary_markers"]).reshape(-1)
        if len(boundary_raw) != len(markers):
            raise ValueError("boundary edge and marker counts do not match")
        boundary_faces = []
        for row, marker in zip(boundary_raw, markers, strict=True):
            values = np.asarray(row).tolist()
            boundary_faces.append([
                int(values[0]),
                int(values[1]),
                int(values[2]),
                float(values[3]),
                float(values[4]),
                float(values[5]),
                int(marker),
            ])

    datasets = {
        "vertices": vertices,
        "triangles": triangles,
        "interiorFaces": interior_faces,
        "boundaryFaces": boundary_faces,
    }
    chunks: list[dict[str, object]] = []
    for kind, rows in datasets.items():
        chunks.extend(write_chunks(args.output, kind, rows, args.chunk_size))

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "version": args.version,
        "counts": {kind: len(rows) for kind, rows in datasets.items()},
        "chunks": chunks,
        "source": {
            "mesh": args.mesh.name,
            "connectivity": args.connectivity.name,
        },
        "physicalValuesAssigned": False,
        "publicRuntimeConnected": False,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "output": str(args.output), "counts": manifest["counts"], "chunks": len(chunks)}))


if __name__ == "__main__":
    main()
