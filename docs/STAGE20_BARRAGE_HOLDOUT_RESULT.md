# Stage 20 barrage holdout result

GitHub Actions run `29464186133` consumed the approved one-time barrage holdout authorization and stopped at the fixed five-hour external limit in `barrage-closed-s03`. The failure was exit code `124`, not a CFL, mass-balance, non-finite, or negative-depth threshold failure.

Five of eight numerical jobs completed with sealed evidence. One closed-barrage job retained three hourly checkpoints before external termination, and both S04 jobs were skipped by the stage barrier. The one-time authorization is consumed; automatic retry and additional execution are not allowed.

Across the five completed segments, maximum CFL was `0.12000000000000002`, maximum relative mass-balance error was `2.4024123051501584e-13`, and non-finite and negative-depth counts were zero. The partial closed S03 artifact retained 10,800.0027 of 14,400 required physical seconds. Its three retained checkpoints also passed the available numerical checks, but no sealed final restart or model-hour `-12` snapshot exists.

Only one of ten required endpoint snapshots is sealed. Therefore the 50:50 interpolation, comparison against the held-out direct 50% reference, five-hour metric acceptance, and four-region direct/interpolated/error maps are not evaluable. The correct conclusion is `not_evaluable`, not an interpolation failure.

The audit found two additional contract limitations: no literal regional-mask file/digest had been recorded before execution, despite the planning requirement, and no water-depth acceptance threshold was defined. The approved four-view geometry existed before execution and remains reproducible, but a strict recovery contract must record the masks and add the missing threshold before any new authorization.

The machine-readable audit is `config/stage20_barrage_holdout_analysis_v1.json`; the result record is `config/stage20_barrage_holdout_result_v1.json`; the retained artifacts are under `docs/results/stage20-barrage-holdout-29464186133`. The decision image is `docs/visuals/stage20-barrage-holdout-stop-decision.jpg`.

The next choice is limited to planning. Option A adopts the stopped result and prepares code-only acceleration plus an inactive recovery plan. Option B retains the evidence and ends the holdout path. Option A does not authorize another physical run, retry, reference S03, public connection, or main merge.
