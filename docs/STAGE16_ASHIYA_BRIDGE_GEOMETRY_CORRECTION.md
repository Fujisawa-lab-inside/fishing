# Stage 16 Ashiya bridge water-geometry correction

Updated: 2026-07-14

## Decision and scope

The upper-edge Ashiya bridge deck had been encoded as dry shoreline even though the river continues below the bridge. The user reviewed a before/after image and instructed the correction to proceed. This change corrects only the water geometry hidden by the bridge deck and the image-edge truncation immediately above it.

It does not authorize a 64-case run, physical-validation claims, connection to the public numerical runtime, or reuse of the earlier full64 authorization.

## Exact raster change

- authority: `v4.8.0-candidate-r2` to `v4.8.0-candidate-r3`
- water pixels: 679,791 to 680,633
- additions: 842 pixels
- removals: 0 pixels
- changed bounding box: image x 57–323, y 0–34 inclusive
- final top water run: x 57–322 inclusive
- four-neighbour water components: 1 before and 1 after
- N, O, and G outer boundary geometry: unchanged

Rows 0 and 1 restore the river to the image edge. Rows 2–34 fill only the dry gap between the two existing main wet runs. Existing outer banks are retained.

## Mesh handling

The corrected authority requires a new mesh version, `stage16-metric-fv-mesh-v2`. The previous mesh counts and every mesh digest are invalid for the corrected geometry.

Triangle output is platform-sensitive. A Darwin arm64 probe is retained only as a diagnostic and is not pinned as the canonical mesh. GitHub Actions Linux x86-64 probe run `29282420163` completed successfully, and its counts and hashes are now pinned in `data/onga_stage16_mesh_constraints_v2.json`. Canonical generation is accepted only on Linux x86-64. The mesh remains blocked from physical execution until its rendered comparison is visually approved.

Both the probe and final validation must verify:

- one connected water component;
- the complete top edge is tagged as boundary M;
- positive cell areas and valid face incidence;
- two components when the barrage is closed;
- fishway cells on opposite barrage components;
- conservative, shallow-water, and well-balanced algebra tests.

The pinned Linux candidate has:

- 28,411 vertices and 50,129 cells;
- 71,848 internal faces and 6,691 boundary faces;
- 67 barrage cut faces and two closed-barrage components;
- 36 M faces covering the complete 266-pixel top opening;
- fishway cells 16,903 and 37,535 on opposite components.

All three isolated algebra checks passed in probe run `29282420163`. These are mesh integrity checks, not a physical-flow run or physical validation.

## Authorization safety

`config/stage18_full64_run_authorization_v1.json` remains byte-for-byte historical evidence for the old 679,791-pixel / 50,333-cell geometry. It is not edited or translated to the new mesh. A separate execution gate blocks the full64 workflow until the corrected Linux mesh is visually reviewed and a new explicit authorization is created.

As an immediate pre-merge safeguard, GitHub Actions workflow ID `312347615` (`stage18-full64-run.yml`) was manually disabled on 2026-07-14. Its verified remote state is `disabled_manually`. It must remain disabled until a new authorization record and gate are explicitly approved.

The earlier Stage 16 and Stage 18 verification documents remain historical records for the superseded geometry; their old measured values are not rewritten as if they had been rerun.
