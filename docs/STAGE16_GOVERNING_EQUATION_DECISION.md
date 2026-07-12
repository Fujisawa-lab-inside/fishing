# Stage 16 governing-equation decision packet

## Purpose

This packet compares the scalar conservative skeleton and the two-dimensional depth-averaged shallow-water candidate without silently selecting either one．The comparison is based on declared modelling objectives，known capabilities，data requirements，and current evidence．A recommendation is not an approval．

## Scalar conservative skeleton

The scalar skeleton supplies conservative face exchange，flow-reversal sign handling，source and sink accounting，and structure transfer．It remains valuable as a diagnostic baseline and regression model．It does not solve horizontal momentum，does not provide a physically complete two-component velocity vector，and cannot independently represent gravity-wave propagation or wetting and drying．

## Depth-averaged shallow-water candidate

The shallow-water candidate solves conservative water depth and two horizontal momentum components．It can represent tidal reversal，tributary momentum interaction，free-surface propagation，wetting and drying，friction，and hydraulic-structure transfer．It requires an audited production mesh，bathymetry，roughness，boundary series，initial state，and structure parameters，and it carries a substantially larger physical Validation burden．

## Current objective weights

The current packet gives extra weight to a two-component velocity vector，tributary-confluence interaction，bidirectional tidal flow，and water-level propagation．These weights describe the intended outputs and are not calibration coefficients．Under these objectives，the shallow-water candidate is recommended because the scalar skeleton has missing or indirect capabilities．

## Current evidence

The approved water authority is ready and remains frozen at 679，791 pixels．The 50，333-cell metric finite-volume mesh has been reproducibly generated and audited，including boundary tags，the 68-face barrage cut，the eight-gate partition，and the fishway transfer cells．The scalar and depth-averaged shallow-water candidates have passed their current synthetic and actual-mesh numerical Verification suites，including conservation，flow reversal，wetting and drying，well-balanced bathymetry tests，Manning friction，and structure-transfer tests．

## Recorded decision

The professor explicitly selected option A on 2026-07-13 00:43:58 JST（2026-07-12T15:43:58.000Z）．The physical-Validation development track therefore uses the two-dimensional depth-averaged shallow-water equations．The scalar conservative skeleton is retained as a diagnostic，regression，and conservation baseline．The machine-readable record is `config/stage16_governing_equation_decision_record_v1.json`．

This decision approves only the governing-equation track．It does not approve bathymetry，vertical datum，Manning roughness，initial state，M／N／O／G physical series，fishway hydraulic parameters，barrage parameters，physical execution，or public release．

## Remaining readiness blockers

Physical Validation is not yet ready because no bathymetry，roughness，physical M／N／O／G boundary series，initial state，fishway parameter，or barrage operating parameter has been approved．These remaining items are physical-input decisions rather than numerical defects．`physicalRunEnabled` remains false and the public simulator continues to use the legacy flow calculation．

## Change control

The recorded selection must identify the selected option，approver，time，and scope．The software does not infer approval from a recommendation，benchmark pass，or displayed flow pattern．Visual fitting is not a decision mechanism，and the approved water geometry cannot be changed to improve apparent agreement．Any future change of governing equation requires a new explicit decision record rather than editing the accepted geometry or fitting the result visually．
