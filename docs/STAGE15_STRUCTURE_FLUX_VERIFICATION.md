# Stage 15 hydraulic-structure flux verification

## Scope

This stage defines generic，isolated hydraulic-transfer laws for future barrage and fishway coupling．It does not assign any Onga River structure dimensions，discharge coefficients，openings，or measured operating values．It is not loaded by the public simulator．

## Sign convention

A positive signed discharge travels from the left cell to the right cell．The corresponding conservative source pair is `left = -Q` and `right = +Q`，so the domain-total source is exactly zero．Head reversal must reverse the discharge sign without changing its magnitude for a symmetric law．

## Implemented candidate laws

- Closed interface，with exactly zero discharge．
- Fixed signed discharge，for a prescribed conservative transfer．
- Linear head-loss relation．
- Bidirectional orifice relation，using free-surface head difference，effective area，opening fraction，and discharge coefficient．
- Aggregation of independently configured gate units．
- Available-volume limiting that prevents a donor cell from transferring more water than it contains during one time step．

## Synthetic verification

The validator checks zero-head and closed-interface flow，head-reversal antisymmetry，monotonic head response，opening scaling，eight-gate aggregation，individual gate closure，source-pair conservation，donor-volume limiting，effective-area calculation，and rejection of invalid coefficients or opening fractions．

## Safeguards

- No real gate geometry is used．
- No fishway operating value is used．
- No approved water-domain pixel is changed．
- The existing public flow model is unchanged．
- No calibration or visual fitting is performed．

Selecting a real structure model and its parameters remains a later Validation decision．
