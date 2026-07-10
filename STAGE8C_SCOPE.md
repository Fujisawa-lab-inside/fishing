# Stage 8C scope

This branch extends the approved Stage 8B water-detection integration to the visible heatmap only.

## Connected

- `calibratedWaterMaskValueAt(lat, lng)`
- `isKnownWater(lat, lng)`
- `drawHeatmap(ctx)`
  - filters source heat points through the Stage 8B authoritative water API
  - clips the final heat raster with the exact same `water.rows` object

## Deliberately untouched

- `samplePhotoWaterCandidates()` and fishing-score generation
- `buildFluidBaseGrid()` and all fluid-grid water cells
- stand / hotspot generation
- `nearestHydroCorridor()`
- turbulence overlay
- long river-axis or fixed flow-direction fields

The Stage 8C adapter is loaded only by the branch PC/mobile wrappers. `main` remains unchanged pending user image approval.
