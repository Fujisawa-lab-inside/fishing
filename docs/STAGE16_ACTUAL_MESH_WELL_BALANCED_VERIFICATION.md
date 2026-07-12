# Stage 16 actual-mesh well-balanced verification

## Scope

This stage applies hydrostatic reconstruction and semi-implicit Manning friction to the reproducibly generated 50,333-cell metric mesh．Only synthetic bathymetry，synthetic roughness，and reflective exterior boundaries are used．The public simulator and approved water geometry are unchanged．

## Synthetic bathymetry

A smooth nonuniform bed is defined from local metric cell-centroid coordinates．A constant free-surface elevation is then imposed through `h = eta - z`．The finite-volume hydrostatic reconstruction must preserve this lake-at-rest state on the irregular mesh．

## Verification cases

1．The variable-bed lake-at-rest residual must remain near machine precision．
2．Internal mass fluxes must cancel globally．
3．Reconstructed left and right water depths must remain nonnegative．
4．Adding a constant vertical datum shift to every bed elevation must not change the residual．
5．A flat-bed lake at rest must remain balanced．
6．A partially dry synthetic bed must yield finite residuals，nonnegative reconstructed depths，and zero global internal mass imbalance．
7．Semi-implicit Manning friction must not increase momentum magnitude．
8．Manning friction must preserve momentum direction while leaving water depth and total volume unchanged．

## Interpretation

Passing these cases demonstrates that the approved metric mesh，face orientation，hydrostatic reconstruction，and friction source treatment are algebraically compatible．The synthetic bed and roughness are not estimates of the real Onga River．

## Safeguards

- The bathymetry and roughness are synthetic only．
- The approved 679,791-pixel water geometry is unchanged．
- The approved fishway and barrage partition are unchanged．
- No tide，river discharge，fishway discharge，gate opening，or measured water level is assigned．
- The public PC and mobile simulators do not load this validator．
- The legacy flow calculation is unchanged．
- No visual fitting or physical calibration is performed．

This stage is numerical Verification on the actual approved mesh，not physical Validation of the real velocity field．
