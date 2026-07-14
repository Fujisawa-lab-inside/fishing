# Stage 19 public-data and declared-inference route

## Current decision

The requester explicitly decided on 2026-07-14 that the project will not contact the Onga River Office. The current route uses only public data and explicitly declared inference to continue simulator development. The governing record is `config/stage17_physical_data_acquisition_decision_record_v3.json`.

Every email, web form, telephone, postal, and in-person contact route is disabled by `config/stage17_external_contact_retirement_v1.json`. The older request draft and submission configuration are retained only as historical evidence and must not be sent or reactivated by reusing their prior digests.

## Public facts available for the next input packet

- The MLIT hydrology database identifies Gion Bridge on Nishikawa, Nakama on the Onga main stem, and Karakuma on the Onga main stem as water-level/discharge stations and publishes their locations and T.P. zero-height metadata.
- The JMA Hakata tide table provides an hourly astronomical-tide prediction and a published tide-table datum. It remains a secondary timing and shape reference, not an observed Onga-mouth water level.
- The Onga River Office publicly describes the barrage as eight main gates, one fine-adjustment gate, and one fishway gate, and publishes gate dimensions in the 2025 training release. These are structure-inventory facts, not effective hydraulic parameters.
- Public fishway material identifies shallow gentle, deeper, and step-pool passage concepts, but does not publish a validated head-discharge relation or operation time series.

The exact URLs, extracted facts, and use restrictions are recorded in `config/stage19_public_inference_input_plan_v1.json`.

## Inputs that remain inferred

The public audit does not resolve domain-wide surveyed bathymetry and vertical datum, a direct Magarigawa discharge series, period-matched gate-by-gate openings, fishway hydraulic coefficients, or independent two-component velocity observations. These items therefore remain ensemble variables and must never be labelled as observations.

The existing Stage 17 numerical ranges are retained for continuity with the completed Stage 18 stability evidence. The old parabolic, trapezoidal, and asymmetric section categories are replaced in the proposed preview by the user-requested smooth symmetric inverse-normal-like trough family. Only its normalized spatial shape is shown for the next decision; no absolute depth is assigned.

## Approved shape boundary

The requester approved the normalized inverse-normal-like cross-channel distribution on 2026-07-14 with the statement `この形でよい．作業を進めてください．`. The exact plan and visual digests, the three retained sigma candidates, and the limited approval scope are fixed in `config/stage19_public_inference_shape_approval_v1.json`. This approval covers the normalized shore-shallow/channel-centre-deep shape family only.

## Approved ranges and generated cases

The requester approved the broad candidate ranges and public-source-to-boundary roles on 2026-07-14 with the statement `この範囲と対応でよい．作業を進めてください．`. The exact approval is fixed in `config/stage19_inferred_scenario_ranges_approval_v1.json`.

`config/stage19_provisional_ensemble_cases_v1.json` now contains exactly 64 deterministic cases with seed `20260714`. Thirteen continuous dimensions span their lowest and highest stratified bins; the three sigma values occur 21, 22, and 21 times; all four barrage scenarios occur 16 times each; and the two fishway modes occur 32 times each. The package remains unassigned to the solver and provides no execution authorization.

The approved candidate roles remain:

- M: JMA Hakata astronomical tide as a secondary shape and timing reference only, with no absolute offset.
- N: MLIT Gion Bridge metadata as a same-river candidate.
- O: MLIT Nakama and Karakuma metadata as upstream main-stem candidates.
- G: no direct public station; the entire discharge range remains declared inference.

## Solver coverage audit

The current Stage 18 kernel cannot be reused for a Stage 19 run. The audit in `config/stage19_solver_parameter_coverage_audit_v1.json` shows that only open-channel Manning roughness is applied with the intended meaning. Six inputs are only partially applied or use the wrong meaning, and nine inputs are unused. In particular, the approved inverse-normal-like bed shape is absent, all open boundaries are reflected walls, barrage opening magnitude and coefficient are ignored, and the fishway has no head-difference relation. A Stage 19 numerical run on that kernel is prohibited.

## Approved M boundary and solver integration

The public JMA 2026 Hakata hourly tide table was snapshotted without external contact. The proposed deterministic selection rule chooses the earliest day whose daily hourly range is closest to the 2026 annual median. This produces 2026-02-15, whose range is exactly 1.37 m. `config/stage19_m_boundary_tide_candidate_v1.json` removes that day's mean, assigns no absolute water-level offset, and proposes the resulting curve as the relative M-boundary reference with the already approved phase and amplitude ranges.

The requester approved that exact relative curve on 2026-07-14 with the statement `この相対潮位曲線をM境界に使用してよい`. The digest-bound record is `config/stage19_m_boundary_tide_approval_v1.json`. This approval allows solver integration and zero-case verification only; it does not authorize a production-mesh numerical case.

The Stage 19 input builder and well-balanced shallow-water kernel now apply all 16 approved input dimensions with their intended Stage 19 meanings. The bed is generated from the approved shore-shallow/channel-centre-deep family, with a 0.05 m numerical wet-depth floor; this floor is not an observation. Main-stem and tributary ownership is assigned by geodesic proximity to M/O and N/G open-boundary cells, respectively. N/O/G use case-constant inflow, barrage transport uses scenario opening fraction times effective coefficient, and fishway transfer uses the approved head-difference relation.

Synthetic two-cell tests passed for lake-at-rest preservation, all three inflow boundaries, barrage transport, relative M phase/amplitude, rejection of an absolute M offset, and fishway direction/scaling. A noncanonical Darwin mesh probe also prepared all 64 input fields, confirmed all 16 counterfactual paths, and called zero numerical time steps. The exact 50,129-cell canonical Linux zero-case preflight remains mandatory before any numerical case.

## Current decision boundary

`config/stage19_full64_execution_contract_v1.json` and `docs/visuals/stage19-full64-execution-decision.png` define the next single decision: whether to run exactly 64 cases × 500 steps once within 24 hours of explicit approval. The planning estimate is 15–30 minutes with a 60-minute hard stop. Automatic retry and additional runs are prohibited. Success requires complete numerical evidence and five maps; failure of any acceptance threshold stops the path.

This execution remains inactive. No production-mesh numerical case has started. The decision does not authorize a physical-validation claim, public simulator connection, external contact, `main` merge, or automatic retry.
