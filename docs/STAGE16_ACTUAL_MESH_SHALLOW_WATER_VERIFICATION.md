# Stage 16 actual mesh shallow-water verification

## Scope

This stage applies a homogeneous two-dimensional depth-averaged shallow-water Rusanov flux to the reproducibly generated 50,333-cell metric mesh．It uses flat synthetic bathymetry，reflective external walls，synthetic states，and synthetic structure transfers only．It remains disconnected from the public simulator．

## Metric face geometry

Internal face normals are reconstructed from metric edge vectors and oriented from the stored left cell to the stored right cell．Boundary normals are oriented away from their adjacent cell centroid．For every triangular cell，the length-weighted outward face normals must close to zero．This is checked before any flow update．

## Synthetic verification

1．A uniform lake at rest on the irregular approved mesh produces a near-zero mass and momentum residual．
2．A smooth water-depth perturbation advanced under a conservative CFL step preserves global water volume，remains finite，and retains positive depth．
3．Removing all 68 barrage faces produces exactly two hydraulic graph components．Each component preserves its own water volume during a closed-wall step．
4．Opening only gate 4 produces nonzero exchange through that gate while the other seven gates retain zero applied flux．Global water volume remains conserved．
5．A synthetic fishway transfer applies equal and opposite mass and directional momentum sources to cells 17,144 and 38,289 while the barrage remains closed．Global volume remains conserved and each component receives the expected signed transfer．

## Important interpretation

The test demonstrates that the approved non-structured mesh，face orientation，barrage partition，fishway cell pair，and conservative flux assembly work together algebraically．It does not demonstrate that the synthetic depth field，flat bed，reflective external boundary，or selected fishway rate represents the real river．

## Safeguards

- The bathymetry is flat and synthetic．
- The initial states and structure rates are synthetic．
- The approved 679,791-pixel water geometry is unchanged．
- The approved fishway position and gate partition are not moved．
- The public PC and mobile simulators do not load this validator or generated mesh artifact．
- The legacy flow calculation is unchanged．
- No visual fitting or physical calibration is performed．

This stage is numerical Verification on the actual approved mesh，not physical Validation of the Onga River velocity field．
