# Stage 20 barrage holdout recovery post-run analysis

GitHub Actions run `29511898671` completed successfully and its five recovery artifacts were downloaded. The offline analyzer verified the evidence and returned `evaluated_failed_thresholds`: numerical integrity passed, but the simple 0%/100% midpoint failed 15 of 20 interpolation comparisons. The analyzer neither monitored nor changed the live run and did not invoke another physical calculation.

## Tools and scope

- `tools/stage20_barrage_holdout_postrun.py` is the offline validation and comparison library. It checks digest-locked inputs, complete artifact inventories, recovery-segment diagnostics, restart continuity, endpoint snapshots, regional masks, and holdout metrics.
- `tools/analyze_stage20_barrage_holdout_recovery_result.py` is the command-line entry point. It writes a diagnostic analysis JSON even when the evidence is incomplete or invalid. An unsafe output location that would overwrite sealed input is refused without writing and is reported on standard output.
- `tools/validate_stage20_barrage_holdout_recovery_result.py` exercises the analyzer with synthetic fixtures. It does not use the physical solver or live recovery artifacts.

The analyzer reads only local files. It does not invoke the shallow-water solver, access the network, download artifacts, mutate GitHub Actions, retry the run, or start another physical job. Artifact collection and rendered map production are separate operations.

## Local result directory

The five recovery artifacts were extracted without flattening or renaming their internal files. The retained layout is:

```text
docs/results/stage20-barrage-holdout-recovery-29511898671/
├── artifact-inventory.json
├── run-metadata.json
├── barrage-closed-m16-m14-29511898671/
├── barrage-closed-m14-m12-29511898671/
├── barrage-closed-m12-m10-29511898671/
├── barrage-closed-m10-m08-29511898671/
├── barrage-open-m12-m08-29511898671/
└── postrun/
```

Each artifact directory must remain an exact evidence bundle: its evidence manifest, reports, receipt, progress record, final restart, final fields, checkpoints, and declared snapshots must agree in filename, byte length, and SHA-256. Missing files, extra files, path traversal, symlinks, digest mismatches, numerical-diagnostic failures, or broken restart links make the result not evaluable.

The retained open-barrage model-hour `-12` snapshot, the five direct held-out reference snapshots, and the four regional masks are read from their existing digest-pinned repository paths. They are not copied into this recovery result directory.

## Normalized run metadata

`run-metadata.json` has schema `onga-stage20-barrage-holdout-recovery-run-metadata-v1`. The retained first-attempt record is:

```json
{
  "schema": "onga-stage20-barrage-holdout-recovery-run-metadata-v1",
  "runId": 29511898671,
  "runAttempt": 1,
  "status": "completed",
  "conclusion": "success",
  "headSha": "92fd709ba4b8760c35b203649e5a0bf00904cdc5",
  "url": "https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29511898671",
  "createdAtUtc": "2026-07-16T15:36:16Z",
  "completedAtUtc": "2026-07-17T05:07:35Z",
  "jobConclusions": {
    "preflight": "success",
    "authorize": "success",
    "closed_m16_m14": "success",
    "open_m12_m08": "success",
    "closed_m14_m12": "success",
    "closed_m12_m10": "success",
    "closed_m10_m08": "success"
  }
}
```

The analyzer requires the exact job-key set shown above, a first attempt, a completed successful run, and `success` for every job. A running, cancelled, failed, or rerun record is reported as not evaluable; it is not treated as a failed interpolation result.

## Endpoint inventory and comparisons

The accepted endpoint set is exactly ten snapshots:

| Basis | Model hours | Source |
|---|---|---|
| `barrage-closed` | `-12`, `-11`, `-10`, `-9`, `-8` | Recovery artifacts |
| `barrage-open` | `-12` | Retained sealed pre-recovery artifact |
| `barrage-open` | `-11`, `-10`, `-9`, `-8` | Recovery artifact |

For each model hour from `-12` through `-8`, the predicted 50% field is the component-wise float64 midpoint of the closed and open endpoint fields. It is compared with the digest-pinned direct 50% reference in four masks: `estuary`, `barrage`, `confluence`, and `fishway`. This produces exactly `5 hours × 4 regions = 20` comparison rows. All 20 rows must pass the velocity-vector RMSE, speed MAE, p95 direction error, depth RMSE, and maximum absolute depth-error limits sealed in the recovery contract.

## Invocation

Run from the repository root after the terminal run metadata and all five extracted artifacts are present:

```sh
.venv-stage20/bin/python tools/analyze_stage20_barrage_holdout_recovery_result.py \
  --run-id 29511898671
```

The default analysis record is `config/stage20_barrage_holdout_recovery_analysis_v1.json`. The default derived-field directory is `docs/results/stage20-barrage-holdout-recovery-29511898671/postrun/`. Use `--no-derived-fields` to perform validation and comparison without writing map-ready NPZ files.

The process exit code and top-level analysis status have distinct meanings. This result returned exit code `1`, meaning fully valid evidence with threshold failures:

| Exit code | Analysis status | Meaning |
|---:|---|---|
| `0` | `evaluated_passed_thresholds` | All evidence is valid, all 20 comparisons were evaluated, and every threshold passed. |
| `1` | `evaluated_failed_thresholds` | All evidence is valid and all 20 comparisons were evaluated, but one or more thresholds failed. |
| `2` | `not_evaluable_invalid_or_incomplete_evidence` | Evidence or run metadata is missing, incomplete, invalid, unsuccessful, or internally inconsistent; this is not an interpolation failure. |

Map-ready direct, interpolated, velocity-error, and depth-error fields were generated only after the full evidence chain was valid and all 20 comparisons were evaluable. This applies to both evaluated pass and evaluated threshold-failure outcomes. No derived fields are generated for a not-evaluable result. The NPZ files are inputs for a separate deterministic rendering step; the analyzer does not render or publish maps itself.

## Comparison-map rendering

The comparison renderer was validated independently with synthetic fixtures. Rendering the run-specific result requires an evaluable analysis record and its map-ready fields, but accepts either an evaluated threshold pass or an evaluated threshold failure; it rejects a not-evaluable analysis.

```sh
.venv-stage20/bin/python tools/validate_stage20_barrage_holdout_comparison_maps.py
```

```sh
.venv-stage20/bin/python tools/render_stage20_barrage_holdout_comparison_maps.py \
  --repo-root . \
  --analysis config/stage20_barrage_holdout_recovery_analysis_v1.json \
  --output-dir docs/results/stage20-barrage-holdout-recovery-29511898671/postrun/maps \
  --manifest-output docs/results/stage20-barrage-holdout-recovery-29511898671/postrun/comparison-map-manifest.json \
  --html-output docs/results/stage20-barrage-holdout-recovery-29511898671/postrun/maps/comparison.html
```

For the worst evaluated model hour, the renderer produces one three-panel comparison for each of `estuary`, `barrage`, `confluence`, and `fishway`: direct 50%, endpoint-average 50%, and velocity difference (endpoint average minus direct). It also writes a combined overview, a local comparison index, and a digest-bearing manifest under the post-run directory. These maps assess **endpoint-interpolation consistency only**. They are not validation against observations, and must not be described as physical accuracy, forecast accuracy, or operational prediction.
