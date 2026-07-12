# Stage 16 governing-equation decision packet

## Purpose

This packet compares the scalar conservative skeleton and the two-dimensional depth-averaged shallow-water candidate without silently selecting either one．The comparison is based on declared modelling objectives，known capabilities，data requirements，and current evidence．A recommendation is not an approval．

## Scalar conservative skeleton

The scalar skeleton supplies conservative face exchange，flow-reversal sign handling，source and sink accounting，and structure transfer．It is valuable as a diagnostic baseline and regression model．It does not solve horizontal momentum，does not provide a physically complete two-component velocity vector，and cannot independently represent gravity-wave propagation or wetting and drying．

## Depth-averaged shallow-water candidate

The shallow-water candidate solves conservative water depth and two horizontal momentum components．It can represent tidal reversal，tributary momentum interaction，free-surface propagation，wetting and drying，friction，and hydraulic-structure transfer．It requires an audited production mesh，bathymetry，roughness，boundary series，initial state，and structure parameters，and it carries a substantially larger physical Validation burden．

## Current objective weights

The current packet gives extra weight to a two-component velocity vector，tributary-confluence interaction，bidirectional tidal flow，and water-level propagation．These weights describe the intended outputs and are not calibration coefficients．Under these objectives，the shallow-water candidate is recommended because the scalar skeleton has missing or indirect capabilities．

## Current evidence gaps

The approved water authority is ready．The scalar algebraic skeleton has passed its isolated synthetic tests．The production mesh artifact has not yet been committed and audited in CI，the integrated shallow-water benchmark registry has not yet been completed on that mesh，and no bathymetry，roughness，physical boundary series，fishway parameter，or barrage operating parameter has been approved．Therefore physical Validation is not ready．

## Decision options

1．Adopt the depth-averaged shallow-water equations for the physical-Validation track．This retains the scalar skeleton as a diagnostic baseline and proceeds to approved bathymetry，roughness，boundary，and structure data．
2．Retain only the scalar skeleton for conservative diagnostics and relative patterns．No complete physical velocity-field claim may be made．
3．Continue both tracks without selecting a production equation．Synthetic Verification may continue，but physical data acquisition and production integration remain deferred．

## Change control

A decision must identify the selected option，approver，time，and notes．The software does not infer approval from a recommendation，benchmark pass，or displayed flow pattern．Visual fitting is not a decision mechanism，and the approved water geometry cannot be changed to improve apparent agreement．
