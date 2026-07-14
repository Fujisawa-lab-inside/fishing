# Stage 20 barrage-coordinate decision

The user-provided latitude/longitude coordinates for barrage gates 1 through 8 are the proposed positional authority. The comparison projects all eight gate centres through the approved `v4.8.0-candidate-r3` georeference, fits one orthogonal least-squares alignment, and extends that alignment across the contiguous water span for hydraulic closure.

The frozen Stage 19 numerical barrier remains unchanged until visual approval. Its image-space constraint is compared with the coordinate-derived alignment, but the completed Stage 19 evidence is not rewritten or reinterpreted.

The visual decision uses 18 zoom-level-18 tiles from the Geospatial Information Authority of Japan (GSI) `seamlessphoto` layer, retrieved on 2026-07-14. The photo is the dominant background; the blue coordinate-derived line, numbered gate centres, and red frozen Stage 19 line are overlaid in the same Web Mercator coordinate system. Source attribution and the fact that the overlay was added by this project are recorded in `data/external/gsi/seamlessphoto/README.md`.

The user approved choice A on 2026-07-14 with the exact statement `青線を採用します`. The blue coordinate-derived alignment is therefore the positional authority for the new Stage 20 candidate mesh.

This approval authorizes preparation of a new candidate mesh only. It does not authorize mesh acceptance, a numerical run, connection to the public simulator, or a merge to `main`.

## Local candidate-mesh diagnostic

The first local probe showed that stopping the hydraulic cut exactly at the last wet sample left a numerical endpoint path. The approved gate alignment itself was not moved. The cut test was extended by 2 image pixels into dry shoreline at both ends, after which the closed barrage produced exactly two hydraulic components and placed the two fishway transfer cells on opposite components.

The Darwin arm64 diagnostic candidate contains 50,327 cells and 78 barrage faces. The conservative geometry, shallow-water algebra, and well-balanced source checks all pass. This output is diagnostic rather than canonical because Triangle output is platform-sensitive. The next gated step is one Linux x86 probe in GitHub Actions; it requires a separate authorization and does not include a physical-flow or 64-condition run.
