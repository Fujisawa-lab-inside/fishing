# Stage 20 barrage holdout recovery result

GitHub Actions run `29511898671` completed successfully on execution commit `92fd709ba4b8760c35b203649e5a0bf00904cdc5`. The five authorized recovery jobs ran once on standard public GitHub-hosted Linux runners. The monitoring automation was deleted after the terminal result was confirmed.

The downloaded recovery evidence is complete. All five artifact inventories, every declared file length and SHA-256, all float64 arrays, the five-link input-restart chain, nine new endpoint snapshots, and the retained open-barrage model-hour `-12` snapshot were verified. The resulting endpoint inventory is exactly ten snapshots: closed and open barrage states at model hours `-12`, `-11`, `-10`, `-9`, and `-8`.

All five recovery segments passed the numerical-stability checks. Maximum CFL was `0.12000000000000001`, maximum relative mass-balance error was `5.390327755611793e-13`, and non-finite and negative-depth counts were zero. These checks establish numerical integrity of the retained calculation; they do not validate the model against observations.

The cross-condition holdout was fully evaluable. For each of five model hours, the component-wise float64 midpoint of the closed and open fields was compared with the existing direct 50%-open reference S02 in four fixed regions. Of the resulting 20 hour-region comparisons, 5 passed every threshold and 15 failed at least one threshold.

The five passing comparisons were all in the 曲川・遠賀川 confluence region. The full estuary, barrage, and fishway regions failed at every evaluated hour. The worst velocity-vector RMSE was `0.02766268977037687 m/s` at model hour `-9` for the full estuary, against a `0.01 m/s` threshold. The worst direction p95 error was `162.19096100669907°` at model hour `-8` near the barrage. The worst depth RMSE was `3.5213067614156484 m` at model hour `-8` near the barrage, and the maximum absolute depth error reached `5.060152317037159 m`.

The result is therefore `evaluated_failed_thresholds`, not an evidence failure or numerical instability. A single global 0%/100% component-wise average is not accurate enough to represent the 50% barrage condition across the estuary. It must not be connected to the public simulator.

The comparison overview uses the model hour selected by the largest velocity-vector RMSE (`-9 h`) and shows direct 50%, endpoint-average 50%, and endpoint-average-minus-direct velocity for the four fixed regions. It is an interpolation-consistency comparison, not validation of observed or forecast accuracy.

The recommended next design is to retain the direct 50% S02 trajectory as a middle anchor and prepare a code-only piecewise interpolation candidate for 0–50% and 50–100%. This recommendation does not authorize another physical run, retry, reference S03, public connection, or `main` merge. The alternative is to stop cross-condition interpolation and keep only directly calculated barrage settings.

The machine-readable analysis is `config/stage20_barrage_holdout_recovery_analysis_v1.json`. The result record is `config/stage20_barrage_holdout_recovery_result_v1.json`. Downloaded artifacts and derived comparison fields are under `docs/results/stage20-barrage-holdout-recovery-29511898671`, and the judgment image is `docs/results/stage20-barrage-holdout-recovery-29511898671/postrun/maps/comparison-overview.jpg`.
