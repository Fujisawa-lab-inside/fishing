# Stage 8B scope

This branch connects the approved Stage 8A-r1 blue-water domain to water-detection APIs only.

## Connected

- `calibratedWaterMaskValueAt(lat, lng)`
- `isKnownWater(lat, lng)`

## Deliberately untouched

- heatmap generation / clipping
- fluid-grid water cells
- stand / hotspot generation
- long river-axis or fixed flow-direction fields

The Stage 8B adapter is loaded only by the branch PC/mobile wrappers. `main` remains unchanged pending user image approval.
