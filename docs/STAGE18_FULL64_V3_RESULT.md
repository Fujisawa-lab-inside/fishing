# Stage 18 corrected v3 full64 result

## Outcome

The one-time corrected-v3 recovery workflow completed successfully in [GitHub Actions run 29307047699](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699). The execution commit was `c378fb3885484ea17b39143d294ca10e41cb59b6`, and the consumed authorization was `stage18-v3-20260714t044734z-one-time`.

The authorization is consumed and cannot be reused. This result does not authorize an automatic retry or an additional numerical run.

## Numerical result

- Completed cases: 64 of 64; failed cases: 0.
- Steps: 500 per case under the fixed full64 contract.
- NaN count: 0.
- Negative-depth count: 0.
- Maximum CFL: `0.12000000000000002`.
- Maximum absolute mass-balance error: `3.0134486651120407e-16`.
- Numerical wall time: `599.102227037` seconds.
- Peak resident memory: `168.59765625` MiB.
- Minimum depth reported by the numerical evidence: `1.26795059543982` m.

These values passed the fixed numerical acceptance checks. They are evidence of completion, numerical stability, conservation, and resource use for this run; they are not evidence of physical predictive accuracy.

The user review recorded a hypothesis that the displayed median-depth distribution differs from actual bathymetry and that real cross-channel depth may be greater near the channel centre and shallower toward land. This is retained only as an unverified hypothesis for checking authoritative surveyed cross sections. It is not an approved bathymetry field and must not be used for visual fitting.

## Map and evidence package

- Raster coverage: 50,129 of 50,129 mesh cells.
- Completed maps: 5 of 5.
- Numeric-evidence manifest SHA-256: `e60287e82d1837b978ecb1c939e9e4b5f2ac075bbaf5c4563df8972da8a350f8`.
- Judgment SVG SHA-256: `47d3d36a257f4b086f707f97748d39782c50ff77ce40d55aed001233b3b11594`.

The numerical evidence was sealed before map packaging. The result package and the numerical checkpoint are separate artifacts:

- [Results artifact 8300775754](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699/artifacts/8300775754) — `stage18-full64-v3-results-29307047699`.
- [Numeric-evidence artifact 8300766356](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699/artifacts/8300766356) — `stage18-full64-v3-numeric-evidence-29307047699`.

Both artifacts record an expiry date of `2026-10-12`.

## Interpretation limits

The 64 cases are compared at an equal step count, not at an equal simulated physical time. The outputs remain provisional runtime and numerical-stability evidence conditional on inferred physical inputs.

This result does not:

- establish physical Validation or predictive accuracy;
- establish a sensitivity-analysis result;
- turn inferred parameters into observations;
- authorize connection to the public simulator;
- change the legacy flow calculation; or
- authorize another numerical run.

The machine-readable record is `config/stage18_full64_v3_result_record.json`.
