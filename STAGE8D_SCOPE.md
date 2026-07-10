# Stage 8D scope

This branch extends the approved Stage 8C integration to fluid-grid water eligibility only.

## Connected

- Stage 8B water detection
- Stage 8C visible heatmap domain
- `buildFluidGrid(env)` water-cell eligibility
  - a finite-difference cell is water exactly when the Stage 8B water API returns `true` at that cell centre
  - the former additional `nearestHydroCorridor().corridor > 0.01` gate is neutralized only while the static fluid base grid is built
  - the temporary corridor wrapper is restored immediately after the synchronous grid build

## Resolution distinction

- Logical authoritative domain: the exact approved `water.rows` raster, 680,236 source pixels
- Numerical solver discretization: the existing 54 × 54 finite-difference grid
- Stage 8D acceptance is evaluated at all solver-cell centres: expected water flag equals actual solver water flag, difference count 0

## Deliberately untouched

- hydraulic-head formulas and boundary-condition classification
- approved M/N/O/G boundary-section integration, which remains a later stage
- depth and mobility formulas
- potential-flow iterations and velocity calculation
- heatmap scoring source generation
- stand / hotspot generation
- turbulence overlay
- long river-axis or fixed flow-direction fields

The Stage 8D adapter is loaded only by the branch PC/mobile wrappers. `main` remains unchanged pending user image approval.
