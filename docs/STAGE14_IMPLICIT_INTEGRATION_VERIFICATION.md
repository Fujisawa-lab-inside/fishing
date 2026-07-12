# Stage 14 implicit integration verification

## Scope

This stage adds isolated implicit time integration to the verified matrix-free finite-volume operator．It remains disconnected from the public simulator and does not use approved physical boundary values．

## Theta method

The semi-discrete conservative equation is advanced with the theta method．

- `theta = 1` gives backward Euler．
- `theta = 0.5` gives Crank-Nicolson．
- The mass matrix is diagonal and uses positive cell capacities．
- Each implicit step is solved by the verified matrix-free PCG solver．

The method accepts time-dependent source values，Dirichlet values，boundary conductance，and nonnegative interface multipliers．A pure-Neumann diffusion operator is permitted inside the transient system because the positive mass term makes the step matrix nonsingular．

## Synthetic verification

The automated test checks the following．

1．Backward Euler exhibits first-order convergence for a one-cell analytical relaxation problem．
2．Crank-Nicolson exhibits second-order convergence for the same problem．
3．A closed multi-cell domain preserves capacity-weighted total mass over large implicit time steps．
4．The field amplitude does not grow under a large Crank-Nicolson step sequence for the symmetric diffusion operator．
5．Complementary initial and boundary values preserve reversal symmetry．
6．An interface multiplier of zero prevents any exchange even for a very large time step．
7．A time-dependent Dirichlet value is evaluated at the correct implicit time．
8．The internal PCG solve converges to the requested tolerance．

## Safeguards

- The module is not loaded by public PC or mobile wrappers．
- The approved 679,791-cell water authority is unchanged．
- The legacy flow calculation is unchanged．
- No tide，river discharge，fishway discharge，or barrage opening value is assigned．
- No visual or geographic calibration is performed．

This stage is numerical Verification only．It does not yet select or validate a physical governing equation for the estuary．
