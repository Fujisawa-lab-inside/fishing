# Stage 16 actual-mesh wet-dry verification

## Scope

This stage applies hysteretic wet／dry state classification and shallow-cell momentum regularisation to all 50,333 cells of the reproducibly generated metric mesh．Only a synthetic bed and a synthetic free-surface sequence are used．No geometric cell is added or removed，and the public simulator is unchanged．

## Hysteresis rule

- A previously dry cell becomes wet only when depth reaches the wet threshold．
- A previously wet cell remains wet through the hysteresis band and becomes dry only at the lower dry threshold．
- Re-evaluating the same state is idempotent．

The fixed computational geometry remains the approved water domain．The wet／dry flag is a dynamic numerical state inside that fixed domain，not a modification of the approved shoreline．

## State regularisation

- Dry cells receive zero depth and zero momentum．
- Wet-cell depth is unchanged．
- Shallow-cell velocity uses a reference depth for regularisation．
- Velocity magnitude is capped without changing momentum direction．
- Any removed sub-threshold water volume is reported explicitly and checked against a threshold-area bound．

## Synthetic verification

1．Every metric cell has positive area and receives exactly one wet／dry state．
2．Cells inside the hysteresis band retain their previous state．
3．Newly wet and newly dry cells satisfy the corresponding thresholds．
4．Repeated classification is idempotent．
5．A deliberately mixed mask remains unchanged at a depth inside the hysteresis band．
6．Regularised depth remains nonnegative and dry momentum becomes zero．
7．Velocity magnitude is bounded and direction is preserved．
8．Wet-cell depth is unchanged．
9．Raw volume equals retained volume plus diagnosed removed volume．
10．The synthetic rising and falling surface sequence produces actual wetting and drying transitions．

## Safeguards

- The bed and free-surface sequence are synthetic．
- The approved 679,791-pixel water geometry is unchanged．
- No mesh cell is deleted or introduced．
- No real tide，river discharge，fishway discharge，gate opening，bathymetry，or roughness is assigned．
- The public PC and mobile simulators do not load this validator．
- The legacy flow calculation is unchanged．
- No visual fitting or physical calibration is performed．

This stage is numerical state-management Verification on the actual approved mesh，not physical Validation of shoreline motion in the Onga River．
