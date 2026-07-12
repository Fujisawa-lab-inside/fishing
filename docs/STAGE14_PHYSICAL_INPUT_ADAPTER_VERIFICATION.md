# Stage 14 physical-input adapter verification

## Scope

This stage converts the already selected provisional input modes into the isolated Stage 14 solver conventions．It does not assign actual tide，river-discharge，fishway-discharge，or barrage-opening values．It remains disconnected from the public simulator．

## Selected provisional modes

- M：water-level time series．
- N，O，G：normal discharge with outward-positive sign convention．
- Fishway：fixed conservative transfer from the upstream cell to the downstream cell．
- Barrage：uniform opening，with eight-gate input accepted for future extension．

## Mapping rules

- M water level is linearly interpolated in time and applied as a Dirichlet value to all mapped M faces．
- N，O，G total outward discharge is distributed across mapped faces in proportion to face length．Negative discharge denotes inflow into the domain．
- Fishway transfer is represented by `-Q` in the upstream cell and `+Q` in the downstream cell，so the domain-integrated source is zero．
- Barrage opening multiplies only the mapped barrage edges．All non-barrage edge multipliers remain one．
- A uniform opening is copied to all eight gates．A gate-wise input requires exactly eight values in the range zero to one．

## Input validation

- ISO-8601 timestamps must include a timezone．
- Time-series timestamps must be strictly increasing．
- All values must be finite．
- Fishway fixed discharge must be present and nonnegative．
- Barrage opening must be present and lie in the range zero to one．
- Boundary and interface mappings are range-checked before use．

## Synthetic verification

The automated test checks interpolation，hold extrapolation，timestamp rejection，outward-flux sums，fishway conservation，uniform and gate-wise barrage multipliers，unchanged non-barrage edges，rejection of unassigned values，and use of detached adapter functions．

## Safeguards

- Synthetic values only．
- No public PC or mobile runtime connection．
- No approved-water or geographic modification．
- No actual physical values assigned．
- No calibration or visual fitting．

This adapter prepares a validated input contract．Selecting data sources and approving actual values remains a separate future decision．
