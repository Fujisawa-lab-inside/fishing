# Stage 16 benchmark registry

## Purpose

The registry defines the minimum synthetic Verification evidence required for each solver-development track．It prevents an isolated successful test from being treated as readiness of the entire solver and prevents a synthetic result from being promoted to physical Validation or public production．

## Tracks

### Scalar conservative skeleton

This track requires production-mesh topology integrity，constant-field preservation，closed-domain mass conservation，boundary reversal symmetry，and complete interface closure．It remains a scalar potential or transport skeleton and does not establish a vector velocity field．

### Depth-averaged shallow-water candidate

This track requires all scalar-algebra safeguards plus lake-at-rest preservation over variable bed，dry-bed dam-break behaviour，linear standing-wave convergence，Manning uniform-flow consistency，and conservative structure-flow reversal．

## Criteria

Machine-precision algebraic checks use strict tolerances．PDE benchmarks use provisional numerical criteria tied to a declared synthetic scenario and resolution sequence．These criteria are Verification criteria only and are not observational calibration targets．Changing a threshold requires a versioned registry change rather than an ad-hoc adjustment to obtain a passing result．

## Result provenance

Every benchmark result must identify its synthetic scenario hash and code commit and must declare purpose `synthetic_verification`．A result labelled as physical prediction，or a result with missing provenance，is invalid．Missing，failed，and invalid benchmarks are reported separately．

## Readiness semantics

Passing all required benchmarks yields `syntheticTrackReady=true` for that development track only．The registry always reports `physicalValidationReady=false` and `publicProductionReady=false`．Those states require the separate Stage 16 experiment contract，traceable physical data，and explicit approvals．

## Safeguards

- The registry is not loaded by the public simulator．
- It changes no approved geometry，mesh，flow field，or physical input．
- It performs no calibration or visual fitting．
- A failed benchmark cannot be hidden by averaging it with successful benchmarks．
