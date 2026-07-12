# Stage 15 positivity limiter and SSP-RK2 verification

## Scope

This stage adds a draining-time positivity limiter and a second-order SSP-RK2 integrator to the isolated homogeneous shallow-water candidate．It remains disconnected from the public simulator and uses synthetic states only．

## Positivity strategy

For every cell，the available water volume during one step is computed from the current depth，cell area，and positive mass source．The requested outward volume includes all outward internal-face fluxes，outward boundary fluxes，and negative mass sources．A cell-wise factor

`alpha = min(1，available volume / requested outward volume)`

limits only the outward contributions that would otherwise drain more water than is available．Each internal face uses the factor of its donor cell，so the same limited flux is added to one cell and subtracted from the other．Internal mass and momentum exchange therefore remain conservative．

## Time integration

- Positivity-preserving Forward Euler is the elementary step．
- SSP-RK2 applies two positivity-preserving Euler stages followed by the convex combination `0.5 * U^n + 0.5 * U^(2)`．
- Dry cells have zero momentum．
- The limiter is inactive when the unmodified CFL-limited update is already positive．

## Synthetic verification

The automated test checks the following properties．

1．Below the CFL limit，the limiter remains inactive and reproduces the original Euler result．
2．An intentionally excessive time step does not create negative depth．
3．Closed-domain water volume remains conserved under the limited Euler step．
4．SSP-RK2 preserves nonnegative depth and closed-domain volume．
5．A fully dry state remains unchanged．
6．Boundary outflow cannot remove more than the available cell volume．
7．An excessive negative source is limited at zero depth．
8．Limited internal mass and momentum fluxes still cancel globally．
9．Left-right reflection symmetry is retained．

## Safeguards

- The module is not loaded by the public PC or mobile simulator．
- The approved 679,791-pixel water authority is not modified．
- The legacy flow calculation is not modified．
- No real tide，river discharge，fishway discharge，gate opening，bathymetry，or roughness is assigned．
- No visual calibration is performed．

This stage is numerical Verification only．It is not physical Validation of the Onga River flow．
