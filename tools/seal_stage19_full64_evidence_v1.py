#!/usr/bin/env python3
"""Seal Stage 19 numerical and visual evidence with SHA-256 identities."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.work_dir).resolve()
    output = Path(args.output).resolve()
    required = [
        "onga_stage16_metric_fv_mesh_v2.npz",
        "stage16_metric_mesh_summary.json",
        "canonical-zero-case-preflight.json",
        "full64-progress.json",
        "full64-report.json",
        "full64-fields.npz",
        "full64-statistics.npz",
        "full64-statistics-summary.json",
        "maps/full64-depth-median.png",
        "maps/full64-velocity-median.png",
        "maps/full64-wet-probability.png",
        "maps/full64-direction-agreement.png",
        "maps/full64-direction-support.png",
        "maps/full64-map-manifest.json",
    ]
    files = []
    for relative in required:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"missing required evidence: {relative}")
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    report = json.loads((root / "full64-report.json").read_text(encoding="utf-8"))
    maps = json.loads((root / "maps/full64-map-manifest.json").read_text(encoding="utf-8"))
    if report["status"] != "passed" or report["completedCaseCount"] != 64:
        raise RuntimeError("numerical report is not complete")
    if maps["status"] != "passed" or maps["mapCount"] != 5:
        raise RuntimeError("map package is not complete")
    payload = {
        "schema": "onga-stage19-full64-evidence-manifest-v1",
        "status": "sealed",
        "authorizationId": report["authorizationId"],
        "numericalCases": 64,
        "stepsPerCase": 500,
        "mapCount": 5,
        "files": files,
        "interpretationLimits": report["interpretationLimits"],
        "automaticRetryAllowed": False,
        "additionalRunAuthorized": False,
    }
    if output.exists():
        raise RuntimeError(f"output already exists: {output}")
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "sealed", "fileCount": len(files), "sha256": sha256(output)}))


if __name__ == "__main__":
    main()
