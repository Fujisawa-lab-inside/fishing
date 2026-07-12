# Stage 16 actual metric mesh solver verification

## Scope

This stage runs conservative finite-volume algebra on the reproducibly generated 50,333-cell metric mesh．It uses synthetic dimensionless boundary values only．The test does not assign actual tide，river discharge，fishway discharge，gate opening，bathymetry，or roughness，and it is not connected to the public simulator．

## Reconstructed geometry

The validator reconstructs cell centroids，cell areas，internal face lengths，boundary face lengths，and centroid distances from the millimetre-quantised metric vertices．A unit-mobility transmissibility is formed as face length divided by centre distance．This scalar problem verifies topology and conservation on the actual mesh without claiming to be the final shallow-water momentum model．

## Synthetic cases

1．All M，N，O，G boundaries are assigned the same value，which must reproduce a constant field．
2．M=0 with N，O，G=1 is compared with the reversed boundary assignment．The two fields must sum to one and every boundary flux must reverse sign．
3．Boundary outward fluxes must sum to zero in both reversal cases．
4．All 68 barrage faces are assigned zero transmissibility．The interface flux must be exactly zero and the graph must split into two components，with O isolated from M，N，G．
5．A conservative fishway transfer of `-Q` in cell 17,144 and `+Q` in cell 38,289 is applied while the barrage remains closed．The global source and boundary balances must remain zero．
6．Only one synthetic gate is opened．All nonselected gates must retain exactly zero interface flux while the selected gate remains active．
7．Every sparse linear solve must satisfy the residual threshold．

## Acceptance examples

The current deterministic test produces constant-field and reversal errors near machine precision，zero closed-barrage flux，two closed-barrage graph components，and a nonzero selected-gate flux．Solve timings are reported for diagnostics but are not treated as physical performance calibration．

## Safeguards

- Only synthetic dimensionless values are used．
- The approved 679,791-pixel water geometry is unchanged．
- The approved fishway cells and eight-gate partition are used without relocation．
- The public PC and mobile simulators do not load this validator or generated NPZ artifact．
- The legacy flow calculation is unchanged．
- No visual fitting or physical calibration is performed．

This stage is topology，conservation，and linear-algebra Verification on the actual approved mesh．It is not Validation of the real velocity field．
