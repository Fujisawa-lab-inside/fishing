# Stage 14 matrix-free PCG verification

## Scope

This stage adds an isolated matrix-free preconditioned conjugate-gradient solver for the symmetric finite-volume operator．It remains disconnected from the public PC and mobile simulator．The approved water geometry，legacy flow calculation，and physical inputs are unchanged．

## Steady equation

The algebraic system follows the conservative sign convention used by the transient core．Internal face conductance contributes equal and opposite fluxes to adjacent cells．A Dirichlet face contributes `g * (phi_cell - phi_boundary)` as outward flux．A prescribed-flux boundary is positive outward．The steady equation is therefore assembled as `A * phi = source - prescribed outward flux + Dirichlet forcing`．

## Solver

- Matrix-free symmetric operator application
- Jacobi diagonal preconditioner
- Relative and absolute residual tolerances
- Explicit rejection of non-unique pure-Neumann systems unless an anchor is supplied
- Nonnegative edge multipliers for closed or partially open interfaces

## Synthetic verification

The automated test checks the following．

1．A one-dimensional chain reproduces the analytical linear profile between two Dirichlet boundaries．
2．The matrix-free residual is below tolerance．
3．Reversing field and boundary values reverses the solution consistently．
4．A prescribed outward flux and a balanced source satisfy the steady residual．
5．An interface multiplier of zero produces exactly zero cross-interface flux and permits a discontinuity．
6．A pure-Neumann system without an anchor is rejected．
7．A two-cell system agrees with an independently derived dense analytical solution．

## Safeguards

- The module is not loaded by public simulator wrappers．
- No tide，river discharge，fishway discharge，or barrage opening value is assigned．
- No geographic or visual calibration is performed．
- The purpose is numerical Verification only．
