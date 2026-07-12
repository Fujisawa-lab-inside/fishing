# Stage 16 benchmark metrics

## Purpose

This module standardises numerical error，conservation，convergence，wetting-front，and standing-wave diagnostics used by later shallow-water solver Verification．It contains no Onga River physical data and does not select a production governing equation．

## Error norms

`weightedErrorNorms` evaluates area- or length-weighted mean absolute error，root-mean-square error，and maximum absolute error．The weights must be positive，which prevents zero-area or sign-changing quadrature weights from silently entering an acceptance result．

## Conservation metric

`relativeConservationError` compares the final conserved quantity with the initial quantity plus the expected source and boundary contribution．The reported residual is signed，while the relative error uses an explicit positive scale．

## Convergence order

`observedConvergenceOrders` calculates pairwise observed orders from strictly decreasing characteristic cell sizes and positive errors．A benchmark report must preserve the complete resolution sequence rather than quoting only its finest-grid error．

## Wetting-front and standing-wave diagnostics

`detectWettingFront` returns the extreme coordinate whose depth exceeds a declared threshold．`standingWaveProjection` projects a numerical free-surface perturbation onto a cosine basin mode，returning modal amplitude and weighted mean．These diagnostics separate phase or front-position error from a general field norm．

## Benchmark assessment

`assessBenchmark` aggregates named pass or fail checks without changing their values or criteria．A failed check remains failed and cannot be hidden by averaging it with successful checks．

## Safeguards

- The module is not loaded by the public simulator．
- It changes no approved geometry，mesh，flow field，or physical input．
- It performs no calibration or visual fitting．
- It does not turn a synthetic Verification result into a physical Validation result．

The metrics are intended to be consumed by a separately versioned benchmark registry and run manifest．
