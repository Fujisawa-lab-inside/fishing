# Stage 14 transient and boundary verification

## Scope

This stage extends the isolated conservative flux algebra with a semi-discrete transient operator and boundary-condition skeleton．It remains disconnected from the public simulator and does not use the approved water geometry or any real physical values．

## Sign convention

- Internal face flux is positive from the left cell to the right cell．
- Boundary flux is positive outward from the computational domain．
- Source is positive into the computational domain．
- The conservative cell equation is `capacity * d(field)/dt = source - net outward flux`．

## Supported synthetic boundary forms

- Dirichlet value with nonnegative face conductance．
- Prescribed outward flux．
- Time-dependent boundary values supplied by a function．
- Time-dependent nonnegative edge multipliers for closed or partially open interfaces．

## Time integration

- Forward Euler is provided as a first-order reference method．
- Explicit Heun integration is provided as a second-order verification method．
- A conservative explicit time-step estimate is computed from cell capacity and the sum of connected conductances．

## Verification cases

The automated test checks the following properties．

1．A constant field remains constant when all Dirichlet values are equal to that field．
2．A closed domain conserves total capacity-weighted mass over repeated Heun steps．
3．Prescribed outward flux and internal source produce the exact expected one-step mass change．
4．The Heun method exhibits second-order convergence for a one-cell relaxation problem with an analytical solution．
5．Reversing the field and boundary value reverses the boundary-flux sign．
6．An interface multiplier of zero produces exactly zero interface flux．
7．An open interface remains active．
8．The explicit stability estimate matches the analytical diagonal bound for a two-cell test．
9．A time-dependent prescribed flux is evaluated at the requested simulation time．

## Safeguards

- The module is not loaded by the PC or mobile public simulator．
- The approved 679,791-cell water authority is not modified or used for calibration．
- Tide，river discharge，fishway discharge，and barrage opening are not assigned．
- The legacy flow calculation is unchanged．
- No visual fitting or geographic adjustment is performed．

The purpose of this stage is numerical Verification only．Physical Validation begins only after a separate decision on the governing equations and approved input data．
