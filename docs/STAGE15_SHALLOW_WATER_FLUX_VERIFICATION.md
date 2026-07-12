# Stage 15 homogeneous shallow-water flux verification

## Scope

This stage introduces an isolated candidate flux for the two-dimensional depth-averaged shallow-water equations on arbitrary finite-volume faces．It is not connected to the public simulator，does not use bathymetry or friction，and does not assign real tide or river inputs．

## Conserved variables

The state is `U = [h，h u，h v]`，where `h` is water depth and `u，v` are depth-averaged velocities．The homogeneous normal flux contains advective momentum and hydrostatic pressure．A local Lax-Friedrichs／Rusanov numerical flux is used for robustness．

## Geometry convention

- Every internal face normal points from the left cell to the right cell．
- Every boundary normal points outward from the computational domain．
- Internal integrated flux is added to the left-cell outward residual and subtracted from the right-cell residual．
- Reflective walls reverse only the normal momentum component．

## Verification cases

1．Equal left and right states reproduce the physical normal flux．
2．All internal mass and momentum fluxes cancel globally．
3．A square one-cell lake at rest has zero net wall residual．
4．A reflective wall has zero mass flux for a moving state．
5．The numerical flux is rotationally invariant．
6．Velocity reversal reverses mass flux while preserving the corresponding momentum flux．
7．A periodic two-face pair preserves a uniform state．
8．Dry-state regularisation produces finite fluxes．
9．A CFL-limited dam-break Euler step preserves positive depth and total mass．
10．A time-dependent boundary state is evaluated at the requested time．

## Deliberate omissions

- Bathymetry and well-balanced source treatment．
- Bed friction and turbulence closure．
- Coriolis force．
- Wetting and drying beyond a minimum-depth regularisation．
- Barrage and fishway constitutive laws．
- Actual boundary values．

## Safeguards

The approved 679,791-pixel water domain，georeference，legacy flow calculation，and public display are unchanged．This stage is numerical Verification of a candidate governing-equation flux only．It is not a calibration or physical Validation result．
