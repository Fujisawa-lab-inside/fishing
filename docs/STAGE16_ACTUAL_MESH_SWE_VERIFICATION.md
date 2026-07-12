# Stage 16 actual-mesh shallow-water verification

## Purpose

This stage applies the isolated Stage 15 numerical kernels to the deterministic 50,333-cell metric finite-volume mesh derived from the approved water authority．It verifies the interaction between real accepted mesh geometry and the candidate shallow-water discretisation without assigning real bathymetry，roughness，tide，river discharge，fishway discharge，or barrage opening．

## Adapter

`onga_stage16_actual_mesh_adapter.mjs` decodes the compact Stage 16 package and constructs:

- metric vertex coordinates in metres
- triangle areas and centroids
- internal faces with unit normals oriented from left cell to right cell
- boundary faces with outward unit normals
- shoreline and M，N，O，G boundary groups
- barrage face and eight-gate metadata
- fishway upstream and downstream cells
- reference-section metadata

The adapter does not add，remove，move，or fit any geometry cell．

## Full-mesh verification

`tools/validate_stage16_actual_mesh_solver.mjs` runs the following tests on all 50,333 cells and 72,107 internal faces:

1．Flat-bed lake-at-rest with reflective external boundaries．
2．Synthetic variable-bed lake-at-rest with a constant free surface．
3．Global mass and momentum conservation of all internal numerical fluxes．
4．Finite positive CFL time-step estimation using actual metric areas and face lengths．
5．One SSP-RK2 step with nonnegative depth and global volume conservation．
6．One connected component when the barrage is open．
7．Two connected components when all 68 barrage faces are closed．
8．Fishway cells on opposite closed-barrage components．
9．Conservative fishway source pair with global source sum zero．
10．M，N，O，G，shoreline，gate，and reference-section metadata consistency．

The variable bed and hydraulic state are synthetic and are not an estimate of the Onga estuary．

## Safeguards

- The approved 679,791-pixel water geometry is unchanged．
- No visible flow field is used as a calibration target．
- No real bathymetry or Manning coefficient is assigned．
- No real boundary or structure value is assigned．
- The public PC and mobile simulator do not load this adapter．
- The legacy flow calculation remains unchanged．

This stage is numerical Verification on accepted geometry only．Physical Validation requires a later explicit decision on data sources and model inputs．
