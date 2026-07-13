# Stage 18 provisional inference ensemble

## Purpose

This stage operationalises the approved policy for quantities that cannot be obtained from public or official records．Missing bathymetry，roughness，tributary discharge，fishway flow，mouth-water-level transfer，and barrage operation are represented by an explicit ensemble rather than a single hidden best guess．

## What remains rigorous

The following properties remain directly verifiable even when physical inputs are inferred．

- The approved 679，791-pixel water geometry and 50，333-cell mesh remain unchanged．
- Every scenario uses the same governing equations，finite-volume conservation laws，boundary orientation，wetting／drying protection，and structure-transfer implementation．
- Each numeric input remains inside its declared prior range．
- Required categorical alternatives are represented，including all barrage scenarios and a disabled fishway case．
- The generator is deterministic for a declared seed，so an ensemble can be reproduced exactly．
- Mass-balance error，solver convergence，positivity，and numerical failure can be audited per scenario．

## What is not rigorous as a physical claim

The following cannot be treated as measured truth without independent data．

- Absolute river-bed elevation and vertical datum．
- Exact cross-section shape and thalweg position．
- Historical gate-by-gate barrage operation．
- Actual fishway discharge．
- Actual Magarigawa discharge．
- Exact Manning roughness．
- Absolute mouth-water-level offset，amplitude transfer，and phase transfer．

Results from this stage are therefore uncertainty and sensitivity results，not physical Validation．

## Sampling contract

The generator applies deterministic stratified marginal sampling to all continuous prior ranges and categorical rotation to cross-section families，barrage scenarios，and fishway modes．The committed default uses 64 cases and seed `20260713`．A different seed produces a different but reproducible ensemble．

The ensemble must preserve the following output obligations．

- Median velocity．
- Velocity interquartile range．
- Flow-direction agreement fraction．
- Water-level range．
- Wet／dry probability．
- Mass-balance error．
- Parameter-sensitivity ranking．

## Safeguards

- No single case may be labelled the true or calibrated case．
- No visual fitting is permitted．
- No inferred case may be described as an observation．
- Physical Validation claims remain disabled．
- Public-simulator connection and physical-run enablement remain disabled．
- Authoritative data，if later obtained，must replace the corresponding prior only after provenance，datum，quality，and applicability review．
