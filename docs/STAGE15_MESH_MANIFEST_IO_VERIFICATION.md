# Stage 15 mesh manifest I/O verification

## Purpose

The production unstructured mesh contains tens of thousands of vertices，cells，and faces．This stage defines a chunked JSON transport format so that the mesh can be versioned and loaded without embedding one very large JavaScript object．The production artifact itself is not added in this stage．

## Manifest contract

The manifest records exact counts for vertices，triangles，interior faces，and boundary faces．Each chunk declares its kind，start index，row count，relative URL，and FNV-1a checksum of the JavaScript-canonical JSON row array．Chunks for each kind must cover `[0，count)` exactly，without gaps or overlaps．

## Loader checks

The loader verifies schema，coverage，checksum，row dimensions，finite values，vertex references，cell references，positive face lengths，and unique loaded indices．The output preserves boundary markers and separates interior and boundary faces．

## Export utility

`tools/export_stage15_mesh_manifest.py` converts the Stage 11 mesh NPZ and Stage 12 finite-volume connectivity NPZ into chunk files and a manifest．It invokes Node.js for the canonical JSON representation so that the Python exporter and JavaScript loader compute identical checksums．

## Synthetic verification

An in-memory two-triangle mesh verifies multi-chunk ordering，counts，markers，and successful loading．Corrupted checksums，coverage gaps，overlapping chunks，and out-of-range references are rejected．The Python exporter is syntax-checked in CI．

## Safeguards

- The production mesh artifact is not yet committed．
- The approved water authority is not modified．
- The public simulator does not load this module．
- No physical values or calibration parameters are introduced．

The next data step is to export and audit the approved production mesh artifact before any solver connection．
