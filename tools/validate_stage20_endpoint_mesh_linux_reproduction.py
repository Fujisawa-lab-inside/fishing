#!/usr/bin/env python3
"""Verify that Linux reproduces the approved Stage 20 endpoint mesh candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path

import numpy as np


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_package(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name] for name in archive.files}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-directory", type=Path, required=True)
    parser.add_argument("--expected-artifact", type=Path, required=True)
    parser.add_argument("--expected-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require(platform.system() == "Linux", "reproduction must run on Linux")
    require(platform.machine() == "x86_64", "reproduction must run on x86_64")

    expected_summary = load_json(args.expected_summary)
    generated_summary_path = args.generated_directory / "stage20_barrage_endpoint_patch_mesh_summary.json"
    generated_summary = load_json(generated_summary_path)
    generated_artifact = args.generated_directory / generated_summary["artifact"]["path"]

    expected_sha = sha256(args.expected_artifact)
    generated_sha = sha256(generated_artifact)
    require(expected_sha == expected_summary["artifact"]["sha256"], "committed artifact digest mismatch")
    require(generated_sha == generated_summary["artifact"]["sha256"], "generated artifact digest mismatch")
    require(generated_sha == expected_sha, "Linux artifact is not a byte-for-byte reproduction")

    expected_package = load_package(args.expected_artifact)
    generated_package = load_package(generated_artifact)
    require(set(generated_package) == set(expected_package), "package array set mismatch")
    mismatched_arrays = [
        name for name in sorted(expected_package)
        if not np.array_equal(generated_package[name], expected_package[name])
    ]
    require(not mismatched_arrays, f"package arrays differ: {mismatched_arrays}")
    require(
        generated_summary["packageArrayHashes"] == expected_summary["packageArrayHashes"],
        "package array hashes differ",
    )
    for section in ("counts", "patch", "quality", "barrage", "fishway", "safeguards"):
        require(generated_summary[section] == expected_summary[section], f"summary section differs: {section}")

    evidence = {
        "schema": "onga-stage20-endpoint-mesh-linux-reproduction-evidence-v1",
        "status": "passed",
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "github": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "ref": os.environ.get("GITHUB_REF"),
            "commitSha": os.environ.get("GITHUB_SHA"),
            "runId": int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,
            "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"]) if os.environ.get("GITHUB_RUN_ATTEMPT") else None,
            "actor": os.environ.get("GITHUB_ACTOR"),
        },
        "candidate": {
            "artifactSha256": generated_sha,
            "arrayCount": len(generated_package),
            "arrayHashes": generated_summary["packageArrayHashes"],
            "counts": generated_summary["counts"],
            "patch": generated_summary["patch"],
            "quality": generated_summary["quality"],
        },
        "checks": {
            "exactArtifactByteMatch": True,
            "exactArraySetMatch": True,
            "exactArrayValueMatch": True,
            "exactArrayHashMatch": True,
            "exactGeometrySummaryMatch": True,
        },
        "safeguards": {
            "geometryOnly": True,
            "physicalFlowRun": False,
            "full64Run": False,
            "publicSimulatorConnected": False,
            "published": False,
            "mainMerged": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
