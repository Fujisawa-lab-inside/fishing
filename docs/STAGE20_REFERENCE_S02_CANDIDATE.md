# Stage 20 reference-s02 continuation candidate

`reference-s01` completed its one-time numerical canary. The next prepared unit is only `reference-s02`, from model hour -16 to -8.

It starts from the retained, digest-verified S01 restart and writes eight hourly restart checkpoints plus five retained flow snapshots at model hours -12, -11, -10, -9, and -8. These are the first five hours in the requested past-12-hour display window.

The runner and GitHub Actions workflow are dormant. They require a new, visually reviewed, 24-hour one-time authorization. Preparing this candidate does not authorize or start a calculation.

The previous segment took 3 h 48 min of numerical wall time. S02 is capped at 5 h, but its runtime can differ because the flow state and tide forcing differ.

No automatic retry, later segment, full campaign, public simulator connection, main merge, paid resource, or physical-validation claim is authorized.
