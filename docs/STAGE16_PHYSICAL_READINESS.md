# Stage 16 physical readiness gate

## Purpose

The numerical solver，wetting/drying logic，structure laws，and accepted metric mesh can be verified without assigning the Onga estuary's real physical inputs．A physical simulation must not begin by silently inventing bathymetry，roughness，boundary values，fishway discharge，or gate coefficients．This readiness gate records every unresolved input and requires explicit provenance and approval before execution．

## Current frozen identity and v1 history

The default readiness contract is `config/onga_stage16_physical_readiness_v2.json`．It is bound to the visually approved corrected identity:

- water authority `v4.8.0-candidate-r3`，680，633 pixels，manifest SHA-256 `964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7`;
- Linux canonical metric mesh `stage16-metric-fv-mesh-v2`，50，129 cells，package SHA-256 `f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2`;
- mesh constraints SHA-256 `44c629ba6b7eb7bf0c43a1863de0c4835d8d331c0d230e50d891a0b23043fb33`．

The v2 loader also verifies all four r3 row-chunk files referenced by the water manifest. Historical v1 can still be read for audit, but the combined physical-execution gate rejects it as a downgrade. Before a future physical run can pass, the canonical mesh NPZ must be supplied as a runtime resource and its bytes must match package SHA-256 `f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2`.

This identity update records only the approved water and mesh geometry．Every physical input remains `null` or `unassigned`，and `physicalRunEnabled` remains `false`．It does not authorize numerical execution or physical-Validation claims．

`config/onga_stage16_physical_readiness_v1.json` remains unchanged as historical evidence for the superseded 679，791-pixel，50，333-cell identity．The runtime validator accepts v1 only with that exact historical identity for reading，but every v1 readiness report carries a permanent non-executable blocker and both execution assertions reject it．The validator accepts v2 only with the corrected identity and fixed digests above; new callers load v2 by default．

## Governing equation selected

Option A was explicitly approved on 2026-07-13 00:43:58 JST．The physical-Validation development track therefore uses the two-dimensional depth-averaged shallow-water equations．The scalar conservative skeleton remains available as a diagnostic and regression baseline．The selection is recorded in `config/stage16_governing_equation_decision_record_v1.json` and is cross-checked against the physical-readiness configuration by `onga_stage16_physical_validation_gate.mjs`．

This governing-equation decision does not approve any physical input，does not enable a physical run，and does not connect the candidate solver to the public simulator．

## Remaining blocking categories

A physical run remains disabled until all of the following are complete:

1．The exact canonical v2 mesh package supplied at runtime and verified byte-for-byte against its approved SHA-256．
2．Bathymetry source，mapping mode，vertical datum，uncertainty，and approved cell field．
3．Manning roughness representation，source，and approved value or field．
4．Initial water-surface datum，water level，and velocity state．
5．Approved M，N，O，and G boundary resources．
6．Fishway mode and the corresponding approved operation or hydraulic data．
7．Barrage operation mode，opening data，effective geometry，and discharge coefficient when applicable．
8．An explicit physical-configuration approval record describing who approved which data，modes，values，and scope．
9．A separate explicit enable flag for physical execution．

Water-level values cannot be combined with bathymetry unless their vertical datums match．

## No silent defaults

The committed v2 template deliberately contains `null` and `unassigned` values for physical inputs．The validator must reject physical execution with this template．A synthetic metadata fixture resolves the ordinary physical-input fields only to exercise their validation rules; it still cannot become ready because no runtime mesh bytes were securely loaded and verified．That fixture is not committed as a model input and is not approved for real simulation．Its per-cell resources derive their expected length from the selected readiness contract rather than from a historical hard-coded cell count．

The combined gate independently verifies that the option-A decision record，the readiness configuration，and the selected equation agree．A missing record，a scalar-equation substitution，an approver or timestamp mismatch，or removal of the scalar diagnostic baseline causes fail-closed rejection．

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

- The approved corrected 680，633-pixel r3 water geometry remains unchanged．
- The public PC and mobile simulator remain disconnected from the candidate physical solver．
- The legacy flow calculation remains unchanged．
- Calibration remains disabled．
- The secure readiness loader validates the r3 manifest，all four row-chunk byte digests，the constraints digest，and any supplied runtime mesh package before deeply freezing the configuration．
- Execution assertions accept only the exact deeply frozen object graph issued by the secure readiness and combined-gate loaders; copied or hand-built objects remain diagnostic-only．
- Historical v1 remains readable for audit but is rejected by both execution assertions．
- `assertPhysicalSimulationReady` fails until every physical-input blocker is resolved．
- `assertStage16PhysicalValidationReady` additionally requires the recorded shallow-water selection to agree with the readiness contract．

This gate marks the boundary between numerical Verification，governing-equation selection，and physical model configuration．
