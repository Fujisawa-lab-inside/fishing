# Current flow calculation audit

## Scope

This document records the current public simulator behaviour before any new hydrodynamic solver is implemented．It is diagnostic only．It does not modify the approved water domain，georeference，heatmap，fluid grid，boundary values，or flow equations．

## Confirmed state

- The approved water authority contains 679,791 pixels and is frozen．
- Stage 13 connects the water predicate，heatmap admissible domain，and fluid admissible domain to the same authority．
- Stage 13 does not replace the existing public flow calculation．
- The public simulator still uses the legacy browser flow model contained in `pc_full.html` and `mobile_lite.html`．
- `closed_gate_patch.js` modifies the legacy model when the main barrage is fully closed．It forces the main-river contribution to zero，overrides selected boundary potential/classification behaviour，and changes hotspot scoring/water-mass attribution．
- The nonstructured finite-volume prototypes developed outside the public runtime have not yet been connected to the public simulator．

## Interpretation rule

A reported visual mismatch is an observation，not an instruction to alter geometry or tune the model．The approved water authority must not be changed merely to make a displayed flow field look plausible．Diagnosis shall proceed in the following order：

1．display and coordinate transformation；
2．input time series and sign conventions；
3．boundary-condition assignment；
4．physical model；
5．numerical discretisation；
6．approved geometry，only after explicit authorisation．

## Automated guard

`tools/audit_current_flow_model.mjs` records where the legacy flow symbols occur and fails CI if a Stage 13 module silently overwrites the principal legacy physics entry points．This ensures that domain integration and physics replacement remain separate changes．

## Next safe development step

The next solver work must begin as an opt-in diagnostic path，not by replacing the existing flow output．It shall first provide side-by-side fields and conservation diagnostics under synthetic boundary conditions．No calibration against visual expectations is permitted before independently defined physical inputs and validation criteria are available．
