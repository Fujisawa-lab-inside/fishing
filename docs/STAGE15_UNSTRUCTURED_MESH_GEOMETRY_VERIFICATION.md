# Stage 15 unstructured-mesh geometry verification

## Scope

This stage provides a geometry and topology adapter for triangular finite-volume meshes．The implementation is independent of the public simulator and does not yet ingest the approved production mesh artifact．

## Geometry rules

- Triangle orientation is normalised to counter-clockwise order．
- Degenerate triangles and repeated vertex ids are rejected．
- Each undirected edge may have at most two incident cells．
- Interior face normals point from the declared left cell to the right cell．
- Boundary face normals point outward from their incident cell．
- Boundary markers are attached by undirected vertex-pair identity．
- Marked segments that are not true mesh boundaries are rejected．

## Exported solver view

The adapter exports cell areas，cell centroids，interior faces with left/right cell ids，unit normals and lengths，and boundary faces with outward normals and markers．A point-location routine returns the containing triangle and barycentric coordinates．

## Synthetic verification

A two-triangle square is used to verify total area，perimeter，face counts，orientation correction，normal direction，marker retention，point location，barycentric sums，and neighbour symmetry．Additional cases verify rejection of nonmanifold and degenerate meshes and invalid boundary markers．

## Safeguards

- The approved 679，791-cell water mask is not changed．
- The existing public flow model is not changed．
- No bathymetry，roughness，structure parameter，or physical boundary value is assigned．
- No visual fitting or geographic correction is performed．

The production mesh will be connected only after its serialized artifact and topology checks are available．
