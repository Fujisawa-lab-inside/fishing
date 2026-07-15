#!/usr/bin/env python3
"""Export the approved Stage 20 Linux mesh as one browser-native binary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from generate_stage16_metric_mesh import load_constraints


ARRAY_DTYPES = {
    "vertex_local_mm": "<i4",
    "vertex_image_millipixel": "<i4",
    "triangles": "<i4",
    "internal_face_vertices": "<i4",
    "internal_face_cells": "<i4",
    "boundary_face_vertices": "<i4",
    "boundary_face_cell": "<i4",
    "boundary_face_tag": "u1",
    "barrage_face_ids": "<i4",
    "barrage_gate_id": "u1",
    "fishway_cells": "<i4",
    "fishway_components": "<i4",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--constraints", type=Path, default=Path("data/onga_stage20_mesh_constraints_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/onga/stage20"))
    parser.add_argument("--browser-version", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()

    constraints = load_constraints(args.constraints)
    expected_package = constraints["expected"]["packageArrayHashes"]
    expected_source = constraints["visualApproval"]["reviewedPackageSha256"]
    actual_source = sha256_file(args.mesh)
    if constraints["candidateStatus"] != "approved_canonical":
        raise RuntimeError("Stage 20 mesh is not approved canonical")
    if actual_source != expected_source:
        raise RuntimeError("source mesh does not match the visually approved Linux package")
    if set(ARRAY_DTYPES) != set(expected_package):
        raise RuntimeError("browser array list differs from the approved package")

    args.output.mkdir(parents=True, exist_ok=True)
    binary_path = args.output / f"mesh-{args.browser_version}.bin"
    arrays: dict[str, dict[str, object]] = {}
    payload = bytearray()
    with np.load(args.mesh, allow_pickle=False) as package:
        if set(package.files) != set(ARRAY_DTYPES):
            raise RuntimeError("source package array set mismatch")
        for name, dtype in ARRAY_DTYPES.items():
            array = np.ascontiguousarray(package[name], dtype=np.dtype(dtype))
            raw = array.tobytes(order="C")
            digest = sha256_bytes(raw)
            if digest != expected_package[name]:
                raise RuntimeError(f"approved array digest mismatch: {name}")
            padding = (-len(payload)) % max(1, array.dtype.itemsize)
            payload.extend(b"\0" * padding)
            offset = len(payload)
            payload.extend(raw)
            arrays[name] = {
                "dtype": "int32" if array.dtype.itemsize == 4 else "uint8",
                "shape": list(array.shape),
                "byteOffset": offset,
                "byteLength": len(raw),
                "sha256": digest,
            }

    binary_path.write_bytes(payload)
    source = {
        "linuxPackageSha256": actual_source,
        "constraints": str(args.constraints),
        "workflowRunId": constraints["canonicalProbe"]["workflowRunId"],
    }
    if args.browser_version == "v2":
        source.update({
            "workflowRunAttempt": constraints["canonicalProbe"]["workflowRunAttempt"],
            "evidenceSha256": constraints["canonicalProbe"]["evidenceSha256"],
        })
    manifest = {
        "schema": f"onga-stage20-browser-mesh-{args.browser_version}",
        "version": constraints["version"],
        "status": "approved_canonical_geometry_only",
        "binary": {
            "url": f"./mesh-{args.browser_version}.bin",
            "byteLength": len(payload),
            "sha256": sha256_bytes(payload),
        },
        "source": source,
        "counts": {
            "vertices": constraints["expected"]["vertices"],
            "cells": constraints["expected"]["cells"],
            "internalFaces": constraints["expected"]["internalFaces"],
            "boundaryFaces": constraints["expected"]["boundaryFaces"],
            "barrageFaces": constraints["expected"]["barrageFaces"],
        },
        "arrays": arrays,
        "safeguards": {
            "physicalValuesAssigned": False,
            "numericalExecutionAuthorizedByExport": False,
            "publicSimulatorConnected": False,
        },
    }
    (args.output / f"mesh-{args.browser_version}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "passed", "binary": str(binary_path), "sha256": manifest["binary"]["sha256"], "bytes": len(payload)}))


if __name__ == "__main__":
    main()
