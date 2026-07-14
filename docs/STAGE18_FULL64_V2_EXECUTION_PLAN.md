# Stage 18 corrected-geometry full64 execution plan

## Current state

The corrected water authority and Linux metric mesh are visually approved, but numerical execution is not authorized. The active execution gate must remain disabled until a separate user decision is recorded after review of the decision image.

This plan is a new v2 path. It does not reactivate, rename, or reinterpret the retired v1 authorization, workflow, runner, evaluator, or artifacts.

## Proposed one-time scope

- Water authority: `v4.8.0-candidate-r3`, 680,633 approved pixels.
- Metric mesh: `stage16-metric-fv-mesh-v2`, 50,129 cells, exact Linux package SHA-256 `f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2`.
- Cases: exactly 64 deterministic provisional-inference cases, seed `20260713`.
- Work per case: exactly 500 adaptive steps; comparisons are step-matched, not time-matched.
- Purpose: offline runtime and numerical-stability evidence only.
- Authorization validity: no more than 24 hours after the UTC issue time.
- Checkpoints inside the same authorized run: case 1, case 4, case 16, and case 64. A checkpoint is not a separate pilot or an additional authorized run.

The parameter case set preserves the historical deterministic sampling ranges, but is rebound to the corrected v2 geometry under a new ensemble schema and digest. The parameters are not observations.

## Bounds and immediate STOP policy

The runner must reject before loading the mesh, ensemble, numerical dependencies, or output paths unless the gate, v2 contract, and a separate one-time v2 authorization all match exactly.

After numerical work starts, the run stops immediately on the first of:

- a failed case or incomplete 500-step case;
- a non-finite value or negative water depth;
- CFL greater than 0.95;
- absolute mass-balance error greater than `1e-8`;
- elapsed numerical time greater than 3,600 seconds;
- peak resident memory greater than 8,192 MiB;
- a changed protected public or legacy file;
- a termination signal or an output collision.

The workflow adds a 65-minute hard watchdog around the runner and a 90-minute numerical-job ceiling. The sequential preflight, authorization, and numerical-job ceilings total 130 minutes; GitHub queue time is additional. These are ceilings, not a runtime prediction. No reliable corrected-v2 runtime measurement exists yet.

There is no automatic retry, failed-case imputation, automatic additional run, or reuse of a consumed authorization. The authorization expires no more than 24 hours after issuance. An unconsumed expiration requires a new decision image and explicit authorization. Once the consumption step succeeds, any stopped or failed run additionally requires a new reviewed execution path.

## Parameter coverage

The current numerical kernel responds to seven parameter groups:

- mainstem mean depth;
- uniform open-channel Manning roughness;
- mouth phase shift;
- fishway enabled or disabled;
- fishway effective discharge coefficient;
- fishway effective area;
- barrage fully closed versus open.

The 25%, 50%, and 100% barrage labels currently collapse to the same open-state kernel behavior. Cross-section family, tributary depth and discharge, thalweg offset, longitudinal smoothing, roughness multipliers, mouth amplitude, barrage coefficient, and partial-opening magnitude do not currently affect the kernel. Therefore the run cannot support a parameter-sensitivity claim.

## Success and diagnostic outputs

A success artifact is created only after 64 of 64 cases finish within every bound. It contains the exact contract, authorization and consumption receipt, v2 mesh and summary, v2 ensemble, atomic progress record, report, `64 x 50129` final depth and two-component velocity fields, evaluation, step-matched statistics, five maps, judgment image, and a digest manifest.

The five maps are median depth, median speed, wet probability, flow-direction agreement, and flow-direction sample support.

After authorization consumption, the workflow makes a best-effort attempt to publish a separately named diagnostic artifact containing whichever receipt, atomic progress record, sanitized details, and red STOP image are available. Checkout, setup, infrastructure cancellation, or the job ceiling can prevent some or all diagnostic files from being created; missing diagnostics can never be interpreted as success. Partial fields can never be presented as a successful result.

## Claims that remain forbidden

Even a numerical PASS does not establish:

- agreement with observed water level, discharge, velocity, bathymetry, or barrage operation;
- physical validation or predictive accuracy;
- equal physical-time comparison across cases;
- parameter sensitivity;
- fishing success or fish location;
- permission to connect the result to the public simulator;
- permission to change the legacy flow calculation;
- permission for another run.

## Authorization boundary

The visual statement `この形でよい` approves corrected geometry only. The later execution decision must expressly authorize this exact one-time `64 x 500` v2 plan within a validity window of no more than 24 hours. Until that statement is recorded in a new authorization file and the gate is activated against its exact digest, zero numerical cases may start.
