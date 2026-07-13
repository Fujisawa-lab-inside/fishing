# Stage 18 ensemble runner

## Purpose

This module executes inferred-parameter scenarios through an injected solver callback and reduces successful fields into uncertainty statistics．It is an orchestration and audit layer．It does not itself choose bathymetry，roughness，boundary values，fishway discharge，or barrage operation．

## Fail-closed safeguards

- At least two distinct scenario cases are required．
- Every case must carry bathymetry，roughness，M／N／O／G，fishway，and barrage data．
- `physicalRunEnabled=true` is rejected．
- Public-simulator connection is rejected．
- A solver result must be converged，finite，non-negative in water depth，and dimensionally consistent．
- Failed cases are recorded explicitly rather than silently replaced．
- Physical Validation claims and visual fitting remain forbidden．

## Statistics

For every cell，the reducer emits speed median，first and third quartiles，median depth，wet probability，and flow-direction agreement fraction．Run-level diagnostics include maximum absolute mass-balance error and maximum CFL value．

These statistics quantify numerical and scenario consistency only．They do not prove that inferred bathymetry，Manning roughness，Magarigawa discharge，fishway flow，or barrage operation equal historical reality．

## Next integration step

The next step is to bind the callback to the verified shallow-water kernel and the 50，333-cell production mesh in an opt-in offline workflow．That integration must retain case-level convergence，mass-balance，CFL，and positivity checks before any statistical field is accepted．The legacy public flow calculation and approved 679，791-pixel water geometry remain unchanged．
