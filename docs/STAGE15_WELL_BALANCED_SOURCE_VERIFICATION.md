# Stage 15 well-balanced bathymetry and friction verification

## Scope

This stage extends the isolated shallow-water candidate with hydrostatic reconstruction for discontinuous bed elevation and a semi-implicit Manning-friction update．Only synthetic bathymetry and roughness are used．The public simulator and accepted geometry remain unchanged．

## Hydrostatic reconstruction

For each face，the interface bed elevation is the maximum of the two cell bed elevations．The left and right depths are reconstructed from their free-surface elevations above that interface bed．Momentum is rescaled consistently with reconstructed depth．The Rusanov flux is then augmented by separate left and right hydrostatic pressure corrections．

This treatment permits a discrete lake-at-rest state over a bed step without creating artificial velocity．Mass flux remains conservative across every internal face．Momentum contains the intended bed-source balance through the two pressure corrections．

## Manning friction

The momentum damping coefficient follows the standard depth-averaged Manning form and is applied semi-implicitly．The update preserves water depth，does not rotate the momentum vector，leaves zero momentum unchanged，and monotonically reduces nonzero momentum for nonnegative roughness．

## Synthetic verification

1．A two-cell lake at rest over a bed step has zero residual with reflective outer walls．
2．Equal bed elevations reproduce the homogeneous shallow-water flux．
3．Adding a constant vertical datum to both bed elevations leaves the flux unchanged．
4．Internal mass flux remains globally conservative across variable bed elevation．
5．Dry reconstruction remains finite and nonnegative．
6．Manning friction reduces momentum magnitude without changing direction or volume．
7．Zero roughness leaves the state unchanged．
8．Time-dependent boundary state and bed elevation are evaluated at the requested time．

## Safeguards

- No real bathymetry is assigned．
- No real Manning coefficient is assigned．
- The module is not loaded by public PC or mobile pages．
- The approved 679,791-pixel water domain and georeference are unchanged．
- The legacy flow calculation is unchanged．
- No visual calibration is performed．

The result is numerical Verification only．Real bathymetry acquisition and physical Validation remain separate tasks．
