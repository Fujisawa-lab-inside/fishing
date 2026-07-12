# Stage 16 metric finite-volume mesh package

## Purpose

This package connects the already approved 679,791-pixel water authority to the isolated shallow-water solver work without changing the accepted shoreline．It is a deterministic export of the verified 50,333-cell constrained Delaunay mesh，expressed in metres for finite-volume calculations．

## Deterministic generation

The generation source is fixed by `data/onga_stage16_mesh_source_v1.json`．The workflow decodes the authenticated generator，installs pinned versions of NumPy，Rasterio，Shapely，and Triangle，then reconstructs the mesh from the approved RLE water rows．

The accepted meshing procedure is:

1．Decode the 2048 × 1232 approved water mask．
2．Extract the four-neighbour water polygon．
3．Apply the previously verified topology-preserving 0.5-pixel simplification，which has raster difference 0．
4．Add the shoreline and barrage marker as the only hard PSLG constraints．
5．Run Triangle with `pq30a30`．
6．Reconstruct internal and boundary finite-volume faces．
7．Assign M，N，O，G，shoreline，barrage，eight-gate，fishway，and reference-section metadata．
8．Map image vertices to a local east/north metric coordinate system through the approved piecewise-affine georeference．
9．Quantise local vertices to millimetres and image vertices to millipixels．
10．Store the package as deterministic gzip plus base64 chunks．

## Fixed counts

- Vertices：28,560
- Cells：50,333
- Internal faces：72,107
- Boundary faces：6,785
- Barrage faces：68
- Closed-barrage graph components：2
- Fishway transfer cells：17,144 and 38,289

## Validation

The package validator checks SHA-256 hashes，array dimensions，positive cell areas，positive face lengths，left-to-right internal normals，outward boundary normals，boundary-tag counts，gate-face counts，closed-barrage connectivity，fishway component separation，and reference-section mappings．

## Safeguards

- The approved water geometry is not modified．
- No cell is fitted to a displayed velocity field．
- No bathymetry，Manning roughness，tide，river discharge，fishway discharge，or gate opening is assigned．
- The package is not loaded by the public PC or mobile simulator．
- The legacy flow calculation is unchanged．

This stage is geometry and numerical-data Verification only．Physical Validation begins after a separate decision on bathymetry，roughness，and boundary-data sources．
