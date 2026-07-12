# Stage 16 analytical shallow-water reference benchmarks

## Purpose

This library supplies analytical or closed-form reference states for solver Verification before any Onga River physical input is used．The references are independent of the approved geometry and public simulator．

## Dry-bed dam break

The Ritter self-similar solution is implemented for a reservoir of depth `h0` released onto a dry horizontal bed．The reference includes the undisturbed reservoir，rarefaction fan，dry region，and wetting-front speed `2 sqrt(g h0)`．It is suitable for checking wetting-front position，depth positivity，and mass conservation．

## Linear standing wave

A small-amplitude standing-wave solution in a closed one-dimensional basin is provided．It satisfies the linearised continuity and momentum equations and has zero velocity at both walls．It is suitable for checking phase error，amplitude error，boundary reflection，and temporal convergence．

## Lake at rest

A constant free-surface elevation over arbitrary bed elevation is converted to nonnegative depth with zero momentum．It is suitable for well-balanced source-term tests．

## Manning uniform flow

The wide-channel Manning discharge-per-width relation and its inverse normal-depth relation are provided for consistency checks of friction and steady uniform-flow calculations．

## Characteristic speeds

The one-dimensional shallow-water characteristic speeds `u-c` and `u+c` and spectral radius are provided for CFL and flux diagnostics．

## Safeguards

These references use synthetic parameters only．They neither select the governing equation for production use nor assign Onga River bathymetry，roughness，boundary values，or structure parameters．
