# Stage 19 one-time full64 result

The authorized Stage 19 run completed successfully on 2026-07-14 in GitHub Actions run `29323240389`. The exact 50,129-cell canonical Linux mesh passed the zero-step preflight before any numerical case. All 16 approved input dimensions reached their intended Stage 19 fields or equations.

Exactly 64 cases × 500 steps completed once. NaN count and negative-depth count were both zero. Maximum CFL was `0.12000000000000002`, maximum absolute mass-balance error was `2.547909753044614e-15`, numerical wall time was `805.3850622509999` seconds, and peak resident memory was `396.94921875` MiB. The sealed evidence manifest SHA-256 is `c18e770052cb1365e77dd04d8aa73a9c6ef2d265a715b1e1d45de897a63b6961`.

Five maps were created at 3,840 × 2,640 pixels and represent all 50,129 cells. The compact review sheet is `docs/visuals/stage19-full64-result-judgment.png`; the five source maps are in `docs/visuals/stage19-full64-results/`.

## Interpretation limit

The 500 adaptive steps represented only `3.2479783289253414` to `6.090228051765682` seconds across the 64 cases. The run therefore establishes numerical stability for the approved provisional inputs, not a developed estuarine flow field. Velocity and direction evidence is concentrated near open boundaries, and the maps must not be treated as physical validation or as a common-physical-time comparison.

The one-time authorization is consumed and cannot be reused. No retry, additional run, public simulator connection, `main` merge, or physical-validation claim is authorized by this result.
