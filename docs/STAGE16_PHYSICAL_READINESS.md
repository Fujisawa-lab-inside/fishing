# Stage 16 physical readiness gate

## Purpose

The numerical solver，wetting/drying logic，structure laws，and accepted metric mesh can be verified without assigning the Onga estuary's real physical inputs．A physical simulation must not begin by silently inventing bathymetry，roughness，boundary values，fishway discharge，or gate coefficients．This readiness gate records every unresolved input and requires explicit provenance and approval before execution．

## Blocking categories

A physical run remains disabled until all of the following are complete:

1．Bathymetry source，mapping mode，vertical datum，uncertainty，and approved cell field．
2．Manning roughness representation，source，and approved value or field．
3．Initial water-surface datum，water level，and velocity state．
4．Approved M，N，O，and G boundary resources．
5．Fishway mode and the corresponding approved operation or hydraulic data．
6．Barrage operation mode，opening data，effective geometry，and discharge coefficient when applicable．
7．An explicit approval record describing who approved which data，modes，values，and scope．
8．A separate explicit enable flag for physical execution．

Water-level values cannot be combined with bathymetry unless their vertical datums match．

## No silent defaults

The committed template deliberately contains `null` and `unassigned` values．The validator must reject physical execution with this template．A complete synthetic fixture is constructed only inside the validation program to test the positive readiness path; that fixture is not committed as a model input and is not approved for real simulation．

## Deferred options

The configuration retains the alternatives previously promised for later presentation:

- bathymetry source and representation
- uniform，zonal，per-cell，or observation-calibrated Manning roughness
- M water-level，discharge，radiation，or external coupling
- N，O，G discharge，water-level，time-series，or estimated input
- fixed，time-series，head-difference，or disabled fishway
- uniform，eight-gate，measured time-series，or fully closed barrage operation

No option is selected merely to make a computed field resemble a desired visual pattern．

## Safeguards

- The approved 679,791-pixel water geometry remains unchanged．
- The public PC and mobile simulator remain disconnected from the candidate physical solver．
- The legacy flow calculation remains unchanged．
- Calibration remains disabled．
- `assertPhysicalSimulationReady` fails until every blocker is resolved and explicit approval is recorded．

This gate marks the boundary between numerical Verification and physical model configuration．
