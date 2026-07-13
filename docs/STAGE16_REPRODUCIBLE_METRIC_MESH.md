# Stage 16 reproducible metric finite-volume mesh

> Historical record: this document describes the superseded 679,791-pixel / 50,333-cell v1 geometry. The Ashiya bridge correction and v2 regeneration status are recorded in `STAGE16_ASHIYA_BRIDGE_GEOMETRY_CORRECTION.md`.

## Purpose

This stage reproduces the approved non-structured triangular mesh directly from the frozen 679,791-pixel water authority．It converts the image-space mesh to a local metric coordinate system and emits an isolated solver artifact．The public simulator is not changed and no physical flow values are assigned．

## Deterministic inputs

- `data/onga_unified_water_manifest_r2.json` and its four approved water-row chunks
- the frozen barrage hard-constraint endpoints
- the user-approved fishway image pixel
- the approved M，N，O，G open-boundary runs
- pinned Python geometry and triangulation dependencies

The user-approved fishway image pixel is retained explicitly．It is not moved to force agreement with a later coordinate transform．Any difference between that approved image point and a transformed latitude／longitude is a diagnostic，not an instruction to alter the geometry．

## Mesh generation

1．Decode the approved raster water mask．
2．Extract its single 4-neighbour water polygon．
3．Apply the previously verified topology-preserving 0.5-pixel simplification．
4．Insert only the shoreline and barrage as hard constrained segments．
5．Run the pinned Triangle constrained Delaunay generation with `pq30a30`．
6．Require exact SHA-256 equality for vertices，triangles，segments，and segment markers．
7．Build finite-volume internal and boundary face incidence．
8．Assign M，N，O，G boundary tags without overlap．
9．Extend the barrage closure across the approved wetted span and partition 68 cut faces into eight gates．
10．Assign the approved fishway cells on opposite barrage components．

## Metric coordinates

Image vertices are mapped through the approved piecewise-affine georeference to Web Mercator coordinates．The exported local axes are east and north in metres．Vertices are quantised to integer millimetres only in the generated NPZ artifact．The generator reports cell-area diagnostics and keeps the original image vertex coordinates in integer milli-pixels for traceability．

## Exact acceptance values

- vertices：28,560
- cells：50,333
- internal faces：72,107
- boundary faces：6,785
- barrage cut faces：68
- boundary faces：shoreline 6,678，M 5，N 21，O 57，G 24
- fishway cells：17,144 and 38,289
- all source mesh array hashes must equal their frozen values

## Safeguards

- The approved water geometry is not modified．
- The public PC and mobile simulators do not load the generated artifact．
- The legacy flow calculation is unchanged．
- No tide，river discharge，fishway discharge，gate opening，bathymetry，or roughness is assigned．
- No visual calibration or force-fitting is performed．

This stage is reproducibility and numerical-domain Verification only．It does not validate the real Onga River velocity field．
