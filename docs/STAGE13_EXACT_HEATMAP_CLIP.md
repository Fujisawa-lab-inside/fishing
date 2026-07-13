# Stage 13 exact heatmap clipping

## Purpose

Heatmap candidate centres were already restricted to the approved water authority. The legacy renderer，however，used a union of circles around sampled water points as its final clip mask. A radial-gradient tail could therefore remain outside the authoritative shoreline even when every heatmap centre was valid.

## Exact clip

`onga_stage13_heatmap_clip.js` performs a final alpha clip after the legacy heatmap has rendered to an offscreen canvas.

1. The approved 2048 x 1232，680,633-cell water mask is converted to a binary source alpha canvas.
2. The approved geographic control mesh maps its 12 source-image triangles to the current browser viewport.
3. Each triangle is rendered by an affine transform into a cached viewport mask.
4. Shared triangle edges use additive alpha composition to prevent seams.
5. The heatmap offscreen canvas is clipped with `destination-in` against the authoritative viewport mask.
6. Only the clipped result is composited into the visible canvas.

The mask is rebuilt only when the target-canvas dimensions or projected control-anchor coordinates change.

## Runtime diagnostics

The opt-in page reports:

- `data-onga-stage13-heatmap-clip="authority-mask"`
- `data-onga-stage13-heatmap-mask-triangles="12"`
- `data-onga-stage13-heatmap-mask-builds`
- `data-onga-stage13-heatmap-clip-calls`

Candidate-centre validation remains active and requires `data-onga-stage13-heatmap-mismatch="0"`.

## Compatibility

The module is loaded only for `?stage13=1`，after the authority bridge and before bootstrap. Normal URLs do not fetch it. A failure while loading optional Stage 13 assets preserves the legacy simulator.

## Scope

This change makes the final visible heatmap domain use the same authoritative water mask as water classification and fluid eligibility. It does not assign physical tide，river-discharge，fishway-discharge，or barrage-opening values.
