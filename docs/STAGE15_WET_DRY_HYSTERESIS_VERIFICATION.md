# Stage 15 wet-dry hysteresis verification

## Scope

This stage adds isolated state classification and regularisation for wetting and drying．It does not alter the approved shoreline，does not activate or deactivate geometric cells，and is not connected to the public simulator．

## Hysteresis

A dry cell becomes wet only when depth reaches the wet threshold．A wet cell remains wet through the hysteresis band and becomes dry only when depth reaches the lower dry threshold．This prevents repeated state switching when depth oscillates near a single threshold．

## State regularisation

- Dry cells are assigned zero depth and zero momentum．
- Wet cells retain their water depth．
- Momentum in shallow wet cells is interpreted with a configurable reference depth．
- Velocity magnitude is capped without rotating the momentum direction．
- Any removed sub-threshold volume is reported explicitly and bounded by the configured threshold and affected cell areas．

## Synthetic verification

1．Initial wet activation follows the wet threshold．
2．Prior wet and dry states are retained inside the hysteresis band．
3．The dry threshold deactivates a previously wet cell．
4．Oscillation inside the hysteresis band produces no chatter．
5．One threshold crossing in each direction produces exactly one activation and one deactivation．
6．Dry cells have zero depth and momentum．
7．Velocity capping preserves direction．
8．Removed sub-threshold volume is diagnosed and bounded．
9．Invalid thresholds and negative depth are rejected．

## Safeguards

No real bathymetry，roughness，tide，river discharge，fishway discharge，or gate opening is used．The approved 679,791-pixel water domain and the legacy flow calculation remain unchanged．
