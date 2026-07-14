# Stage 18 full64 map-recovery plan

## Current state

The first corrected-geometry v2 workflow run (`29300177716`) completed and passed all 64 numerical cases, but the result package stopped before publishing the maps because one boundary cell was omitted during rasterization. Its one-time authorization is consumed and cannot be reused. The full field archive was not uploaded before the packaging failure, so the five maps cannot be reconstructed from that run.

The v3 recovery path is a new, inactive control plane. It reuses the approved geometry, exact mesh, deterministic 64-case ensemble, numerical kernel, limits, and field formats without changing them. Until a new visual decision is recorded, the v3 gate remains disabled, the v3 authorization file is absent, and zero numerical cases may start.

## Fixed defect and required preflight

The original 3,840 × 2,640 map used slightly different horizontal and vertical pixel sizes. Center-sampled rasterization therefore gave boundary cell 320 no pixel. The fixed renderer keeps the same image dimensions and center, expands only the vertical local bounds symmetrically by about 8.356 m in total, and uses square 0.7147801171875 m pixels.

Before any new authorization can be consumed, the exact canonical Linux mesh must pass a zero-case raster preflight proving:

- 50,129 of 50,129 cells are represented;
- every cell occupies at least one pixel;
- boundary cell 320 occupies at least one pixel;
- the image remains 3,840 × 2,640 with square pixels;
- no numerical case was started.

This changes only map projection bounds. It does not change the water geometry, bridge correction, mesh, physical inputs, numerical kernel, or acceptance limits.

## One-time recovery scope

- Exactly 64 deterministic corrected-v2 cases, seed `20260713`.
- Exactly 500 adaptive steps per case.
- Same step-matched, non-physical-validation classification as v2.
- Same STOP limits: 64/64 completion, zero NaN, zero negative depth, CFL at most 0.95, absolute mass-balance error at most `1e-8`, numerical wall time at most 3,600 seconds, and peak RSS at most 8,192 MiB.
- No automatic retry, additional run, failed-case imputation, public-simulator connection, legacy-flow change, physical-validation claim, or sensitivity claim.
- A new authorization is valid for at most 24 hours and is consumed once.

The measured numerical portion of the failed packaging run was about 626 seconds. Queue, setup, mesh generation, artifact transfer, and map generation add variable time, so this is evidence rather than a completion guarantee.

## Numeric-evidence checkpoint before maps

After the 64-case evaluation passes, the workflow must seal and upload the complete numerical evidence before starting map generation. The checkpoint includes the receipt, exact mesh and summary, ensemble, progress, run report, full fields, evaluation, raster-preflight report, and a SHA-256 manifest.

Map generation runs in a separate job that can only read a reverified checkpoint. It has no numerical-runner invocation. Therefore a later map-packaging failure cannot erase the numerical fields or silently start another numerical run.

If that map-only job fails, a human may retry only the map job against the same workflow run and sealed checkpoint. Every preflight, authorization-consumption, and numerical job remains restricted to the first attempt.

## Authorization boundary

The earlier statements approving the corrected geometry and the v2 run do not authorize v3. A new decision image must show the prior result, the exact map fix, the unchanged numerical scope, the checkpoint-first sequence, expected duration, risks, and STOP guards. Only an explicit approval of the exact statement bound to that reviewed image and commit may activate the v3 gate.

The reviewed decision image is `docs/visuals/stage18-v3-execution-decision.svg`. The only activation statement it offers is: `承認済み橋下補正v2と修正済み地図化経路v3上で、この判断資料に示された64条件×500ステップを、承認後24時間以内に一回限り、完全な数値証拠と5枚の地図を作成するため再実行してよい。` Choosing not to send that exact statement leaves the path inactive.
