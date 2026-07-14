# Stage 17 inferred physical prior

> Historical parameter-prior record: `config/stage17_inferred_physical_prior_v1.json` retains the superseded 679,791-pixel / 50,333-cell identity because its digest is part of completed Stage 18 provenance. The corrected Stage 18 v2 ensemble reuses only the parameter cases and binds them separately to the approved 680,633-pixel / 50,129-cell geometry. This prior is not a physical bathymetry source.

## Purpose

When authoritative physical data are unavailable，the model may proceed with an explicitly provisional inference ensemble．The objective is sensitivity analysis，algorithm development，and identification of robust flow features．It is not physical Validation and must not be represented as measured reality．

## Core rule

No single inferred parameter set is treated as truth．Bathymetry，roughness，boundary forcing，fishway transfer，and barrage coefficients are varied over declared prior ranges．Outputs must report both central tendency and uncertainty．

## Bathymetry inference

The approved shoreline and water connectivity constrain the horizontal domain only．They do not determine submerged elevation．The provisional bed therefore uses families of smooth cross-sections and longitudinal profiles，with separate main-stem and tributary depth ranges，thalweg-offset alternatives，and multiple section shapes．The vertical datum is relative and cannot be combined with observed water levels until a datum transformation is approved．

## Boundary inference

The mouth boundary may use an observed or astronomical water-level shape only after separating unknown offset，amplitude，and phase．Tributary and main-stem discharges remain ensembles rather than fixed values．A public water-level station is not automatically converted to discharge and is not automatically assigned to M，N，O，or G．

## Structures

The fishway and eight barrage gates are represented by scenario ensembles．Closed，partially open，and fully open barrage scenarios are mandatory．No gate coefficient，fishway area，or discharge relation is treated as an observed parameter．

## Required reporting

Every inferred run must report velocity median，velocity interquartile range，flow-direction agreement，water-level range，wet／dry probability，mass-balance error，and parameter-sensitivity ranking．A flow feature is considered robust only when it persists across a substantial fraction of the ensemble．

## Safeguards

- The approved 679,791-pixel water geometry and 50,333-cell mesh remain unchanged．
- Visual fitting to a desired flow pattern is forbidden．
- The legacy public simulator remains unchanged．
- The candidate physical solver remains disconnected from the public simulator．
- Authoritative data supersede the inferred prior after provenance，datum，quality，and applicability review．
