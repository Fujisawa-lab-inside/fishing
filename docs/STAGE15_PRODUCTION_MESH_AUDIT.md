# Stage 15 production mesh audit

## Purpose

This audit compares a loaded chunked production-mesh manifest with a topology independently reconstructed from its vertices and triangles．It is intended to detect serialization mistakes before the mesh is supplied to the Stage 15 solver．

## Checks

The audit reconstructs all triangle cells，interior faces，boundary faces，cell neighbours，face lengths，midpoints，centre distances，and boundary markers．It then compares these values against the exported Stage 12 connectivity tables．The cell adjacency graph must contain one connected component．

The audit rejects missing or duplicate edges，incorrect left/right cell pairs，length or midpoint disagreement，boundary-cell disagreement，marker disagreement，nonpositive area，and disconnected cell graphs．

## Command

```text
node tools/audit_stage15_production_mesh.mjs <manifest.json> <report.json>
```

## Safeguards

- The audit does not change the mesh．
- It does not change the approved water authority．
- It does not assign bathymetry，roughness，structure parameters，or physical boundary values．
- It is not loaded by the public simulator．

A production artifact is eligible for solver integration only after this audit reports `passed`．
