# Stage 18 ensemble statistics

## Purpose

This module aggregates completed provisional shallow-water inference cases without treating inferred parameters as observations or validated truth.

## Inputs

Each case result uses schema `onga-stage18-case-result-v1` and contains a case ID，completion status，mass-balance error，and per-cell water depth，two-component velocity，and wet/dry state．Failed cases must carry an explicit failure reason and are never silently replaced by another case．

## Outputs

For every cell，the aggregator reports:

- velocity median
- first and third quartiles
- 2.5 and 97.5 percentiles
- median and interquartile range of water depth
- wet probability
- circular flow-direction agreement fraction
- circular mean direction
- active direction sample count

It also reports completed and failed case counts，completion fraction，failed-case reasons，and mass-balance error diagnostics．

## Direction agreement

Direction agreement is the magnitude of the mean unit velocity vector．It is 1 when all active cases point in the same direction and approaches 0 when directions cancel．Zero-speed cases are excluded from the circular direction statistic but remain in wet/dry and scalar statistics．

## Fail-closed rules

- Unknown or duplicate case IDs are rejected．
- Negative depth，NaN，Infinity，cell-count mismatch，or malformed status is rejected．
- An ensemble below the declared minimum completed fraction is rejected．
- Approved water geometry and metric mesh identities must remain unchanged．
- Physical-validation claims and public-simulator connection remain disabled．

## Interpretation

The statistics quantify numerical outcomes conditional on the declared prior ensemble．They do not establish that inferred bathymetry，roughness，tributary discharge，fishway flow，or barrage operation equals the historical physical state．Absolute velocity and water level therefore remain provisional．Robust direction agreement and sensitivity ranking may still identify conclusions that persist across the declared uncertainty range．
