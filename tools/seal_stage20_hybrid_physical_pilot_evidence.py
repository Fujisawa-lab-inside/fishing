#!/usr/bin/env python3
"""Seal the complete one-time Stage 20 pilot artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED = [
    "execution-receipt.json",
    "pilot-progress.json",
    "pilot-report.json",
    "pilot-final-fields.npz",
    "pilot-visual-manifest.json",
    "maps/pilot-estuary.jpg",
    "maps/pilot-barrage.jpg",
    "maps/pilot-confluence.jpg",
    "maps/pilot-fishway.jpg",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    parser.add_argument("--expected-cell-count", type=int, default=50339)
    parser.add_argument("--manifest-schema", default="onga-stage20-hybrid-physical-pilot-evidence-v1")
    args = parser.parse_args()
    root = Path(args.work_dir)
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise RuntimeError(f"pilot evidence is incomplete: {missing}")
    report = json.loads((root / "pilot-report.json").read_text(encoding="utf-8"))
    progress = json.loads((root / "pilot-progress.json").read_text(encoding="utf-8"))
    visual = json.loads((root / "pilot-visual-manifest.json").read_text(encoding="utf-8"))
    if report["status"] != "passed_numerical_checks_not_physical_validation":
        raise RuntimeError("pilot numerical report did not pass")
    if progress["status"] != "complete" or progress["simulatedSeconds"] < 600:
        raise RuntimeError("pilot did not reach its physical-time target")
    if len(progress["checkpoints"]) != 10:
        raise RuntimeError("pilot checkpoint count is not ten")
    if visual["cellCount"] != args.expected_cell_count or len(visual["views"]) != 4:
        raise RuntimeError("pilot visual coverage is incomplete")
    files = []
    for relative in REQUIRED:
        path = root / relative
        files.append({"path": relative, "byteLength": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "schema": args.manifest_schema,
        "status": "sealed_complete_not_physical_validation",
        "authorizationId": report["authorizationId"],
        "simulatedSeconds": report["run"]["simulatedSeconds"],
        "stepsCompleted": report["run"]["stepsCompleted"],
        "checkpointCount": len(progress["checkpoints"]),
        "viewCount": len(visual["views"]),
        "files": files,
        "safeguards": {"physicalValidationClaimAllowed": False, "publicSimulatorConnected": False},
    }
    output = root / "pilot-evidence-manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
