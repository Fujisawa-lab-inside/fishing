# Implementation scope

The draining-time limiter scales only excessive outward transport from a donor cell，preserves a single conservative internal-face flux，and normalises dry-cell momentum．The SSP-RK2 wrapper composes two limited forward-Euler stages．No bathymetric calibration，roughness calibration，geographic adjustment，or public runtime integration is included．
