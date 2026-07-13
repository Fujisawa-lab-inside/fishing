#!/usr/bin/env python3
"""Generate and verify the Stage 13 r3 water authority.

The r3 authority is a deterministic, additive correction of the frozen r2
authority.  It restores water beneath the clipped Ashiya Bridge deck while
preserving every r2 water pixel and all rows outside 0..34.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


SOURCE_VERSION = "v4.8.0-candidate-r2"
TARGET_VERSION = "v4.8.0-candidate-r3"
SOURCE_PIXEL_COUNT = 679_791
ADDED_PIXEL_COUNT = 842
TARGET_PIXEL_COUNT = SOURCE_PIXEL_COUNT + ADDED_PIXEL_COUNT
SOURCE_MANIFEST = "data/onga_unified_water_manifest_r2.json"
TARGET_MANIFEST = "data/onga_unified_water_manifest_r3.json"
SOURCE_CHUNKS = [f"data/onga_water_rows_r2_{index}.json" for index in range(4)]
TARGET_CHUNKS = [f"data/onga_water_rows_r3_{index}.json" for index in range(4)]
SOURCE_SHA256 = {
    SOURCE_MANIFEST: "0561d46d31b3a0e47db66a203507fa41491e28507da340dbfd3a69b8c7c13537",
    SOURCE_CHUNKS[0]: "efc06d3b7c4b14798c5634919c12365c501dd48d6e94e52ed05b68a6e5e4a695",
    SOURCE_CHUNKS[1]: "ef373644c0b325d396ed8f03c1fcf6b4a34dfb8d4330e363e99118b5bdaa0ee8",
    SOURCE_CHUNKS[2]: "0bebd9f5b735bfc990f7d9e00b564e7d9a9aca64bb1b17006fe128bcd452f443",
    SOURCE_CHUNKS[3]: "9e55ca5fc0fddfbbfdd83d0dcea6b28ad41c91eb78adf5e39fc8eca1cf5ee48e",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def count_runs(runs: list[int]) -> int:
    require(len(runs) % 2 == 0, "run list length must be even")
    return sum(runs[index + 1] - runs[index] + 1 for index in range(0, len(runs), 2))


def pixels(runs: list[int]) -> set[int]:
    result: set[int] = set()
    for index in range(0, len(runs), 2):
        start, end = runs[index : index + 2]
        require(0 <= start <= end < 2048, f"invalid run [{start}, {end}]")
        require(not result.intersection(range(start, end + 1)), "overlapping runs")
        result.update(range(start, end + 1))
    return result


def load_sources(root: Path) -> tuple[dict, list[dict], list[bytes]]:
    source_paths = [SOURCE_MANIFEST, *SOURCE_CHUNKS]
    source_bytes = [(root / relative).read_bytes() for relative in source_paths]
    for relative, data in zip(source_paths, source_bytes, strict=True):
        require(sha256(data) == SOURCE_SHA256[relative], f"frozen r2 digest mismatch: {relative}")

    manifest = json.loads(source_bytes[0])
    chunks = [json.loads(data) for data in source_bytes[1:]]
    require(manifest.get("version") == SOURCE_VERSION, "unexpected r2 authority version")
    require(manifest.get("pixelCount") == SOURCE_PIXEL_COUNT, "unexpected r2 pixel count")
    require(
        manifest.get("chunks") == [f"./{relative}" for relative in SOURCE_CHUNKS],
        "unexpected r2 chunk list",
    )
    return manifest, chunks, source_bytes


def assemble_rows(manifest: dict, chunks: list[dict]) -> list[list[int]]:
    rows: list[list[int] | None] = [None] * int(manifest["height"])
    for chunk in chunks:
        start = int(chunk["startRow"])
        for offset, runs in enumerate(chunk["rows"]):
            row = start + offset
            require(0 <= row < len(rows), f"row {row} is outside the manifest")
            require(rows[row] is None, f"duplicate row {row}")
            rows[row] = list(map(int, runs))
    require(all(row is not None for row in rows), "one or more rows are missing")
    return [row for row in rows if row is not None]


def corrected_runs(row: int, source: list[int]) -> list[int]:
    if row == 0:
        require(source == [153, 160], "unexpected r2 row 0")
        return [57, 322]
    if row == 1:
        require(source == [151, 161], "unexpected r2 row 1")
        return [57, 323]
    if 2 <= row <= 34:
        require(len(source) >= 4, f"r2 row {row} lacks the two bridge-separated runs")
        # Merge only the first two runs.  Any later run, including the isolated
        # row-23 pixel at x=342, remains byte-for-byte equivalent semantically.
        return [source[0], source[3], *source[4:]]
    return list(source)


def build_expected(root: Path) -> tuple[dict[str, bytes], dict]:
    source_manifest, source_chunks, source_bytes = load_sources(root)
    source_rows = assemble_rows(source_manifest, source_chunks)
    target_rows = [corrected_runs(row, runs) for row, runs in enumerate(source_rows)]

    added = 0
    removed = 0
    changed_rows: list[int] = []
    for row, (before, after) in enumerate(zip(source_rows, target_rows, strict=True)):
        before_pixels = pixels(before)
        after_pixels = pixels(after)
        added += len(after_pixels - before_pixels)
        removed += len(before_pixels - after_pixels)
        if before != after:
            changed_rows.append(row)

    source_count = sum(count_runs(runs) for runs in source_rows)
    target_count = sum(count_runs(runs) for runs in target_rows)
    require(source_count == SOURCE_PIXEL_COUNT, "decoded r2 pixel count mismatch")
    require(added == ADDED_PIXEL_COUNT, f"expected 842 added pixels, got {added}")
    require(removed == 0, f"r3 unexpectedly removes {removed} r2 water pixels")
    require(target_count == TARGET_PIXEL_COUNT, "decoded r3 pixel count mismatch")
    require(changed_rows == list(range(35)), f"unexpected changed rows: {changed_rows}")
    require(count_runs(source_rows[0]) == 8, "unexpected r2 top-boundary wet count")
    require(count_runs(target_rows[0]) == 266, "unexpected r3 top-boundary wet count")

    target_chunks = copy.deepcopy(source_chunks)
    for chunk in target_chunks:
        start = int(chunk["startRow"])
        for offset in range(len(chunk["rows"])):
            chunk["rows"][offset] = target_rows[start + offset]

    target_manifest = copy.deepcopy(source_manifest)
    target_manifest["version"] = TARGET_VERSION
    target_manifest["pixelCount"] = TARGET_PIXEL_COUNT
    target_manifest["chunks"] = [f"./{relative}" for relative in TARGET_CHUNKS]
    target_manifest["geometryCorrection"] = {
        "id": "ashiya_bridge_underpass_water_restore_v1",
        "approvedDate": "2026-07-14",
        "sourceStatement": "進めてください",
        "sourceVersion": SOURCE_VERSION,
        "sourceManifest": f"./{SOURCE_MANIFEST}",
        "sourceManifestSha256": sha256(source_bytes[0]),
        "addedPixelCount": ADDED_PIXEL_COUNT,
        "removedPixelCount": 0,
        "changedRowRangeInclusive": [0, 34],
        "topBoundaryWetPixelsBefore": 8,
        "topBoundaryWetPixelsAfter": 266,
    }

    outputs = {TARGET_MANIFEST: compact_json(target_manifest)}
    for relative, chunk in zip(TARGET_CHUNKS, target_chunks, strict=True):
        outputs[relative] = compact_json(chunk)

    report = {
        "schema": "onga-stage13-ashiya-bridge-r3-generation-v1",
        "status": "passed",
        "sourceVersion": SOURCE_VERSION,
        "targetVersion": TARGET_VERSION,
        "sourcePixelCount": source_count,
        "addedPixelCount": added,
        "removedPixelCount": removed,
        "targetPixelCount": target_count,
        "changedRows": [changed_rows[0], changed_rows[-1]],
        "outputSha256": {relative: sha256(data) for relative, data in outputs.items()},
    }
    return outputs, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    outputs, report = build_expected(root)
    if args.write:
        for relative, data in outputs.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    else:
        for relative, expected in outputs.items():
            path = root / relative
            require(path.is_file(), f"generated r3 file is missing: {relative}")
            require(path.read_bytes() == expected, f"generated r3 file is stale: {relative}")

    report["mode"] = "write" if args.write else "check"
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
