# 「領域一致の方法」からWORKへの引き継ぎ

更新日: 2026-07-14

冒頭の「Stage 18 v3完了後の最新状態」以外で、実行前後や移行時と明記した各節は履歴スナップショットであり、現行判断を示さない。旧v1手順は `docs/STAGE18_FULL64_RUN.md`、補正後v2の実行候補は `docs/STAGE18_FULL64_V2_EXECUTION_PLAN.md`、最新の実装状態はGit履歴を正本とする。

## 2026-07-14 Stage 18 v3完了後の最新状態

- Stage 19の現行取得方針は、遠賀川河川事務所へ連絡せず、公開データと明示した推論だけでシミュレータ開発を継続する経路へ変更された。正本は `config/stage17_physical_data_acquisition_decision_record_v3.json`、外部連絡の無効化記録は `config/stage17_external_contact_retirement_v1.json`、入力計画は `config/stage19_public_inference_input_plan_v1.json` である。旧公式照会案は履歴専用で送信不可である。

- one-time v3 workflow [run `29307047699`](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699) はexecution commit `c378fb3885484ea17b39143d294ca10e41cb59b6` 上で64 casesを完了し、数値評価に合格した。64/64完了、NaN 0、負水深0、最大CFL `0.12000000000000002`、最大絶対質量保存誤差 `3.0134486651120407e-16`、wall time `599.102227037`秒、peak RSS `168.59765625` MiB、最小水深 `1.26795059543982` mだった。
- 修正済みrasterは50,129/50,129セルを表現し、5/5枚の地図を完成した。numeric-evidence manifest SHA-256は`e60287e82d1837b978ecb1c939e9e4b5f2ac075bbaf5c4563df8972da8a350f8`、judgment SVG SHA-256は`47d3d36a257f4b086f707f97748d39782c50ff77ce40d55aed001233b3b11594`である。
- [results artifact `8300775754`](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699/artifacts/8300775754) と [numeric-evidence artifact `8300766356`](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699/artifacts/8300766356) のexpiryはともに`2026-10-12`である。
- authorization `stage18-v3-20260714t044734z-one-time` は消費済みで再利用不可。現行gateは`consumed`・無効で、authorizationファイルは履歴証拠としてのみ保持する。実行workflowはactive gateを要求するため、依存導入や数値入力読込みより前のcontrol planeで停止する。自動retry、追加run、物理Validation主張、公開シミュレータ接続は許可されない。
- 比較はstep-matchedであり同一物理時刻ではない。結果は暫定推論入力に対する実行時間・数値安定性の証拠に限定する。詳細は `docs/STAGE18_FULL64_V3_RESULT.md`、機械可読記録は `config/stage18_full64_v3_result_record.json` を正本とする。
- 利用者の地図レビューでは、水深中央値の分布は一般に実水深と異なり、理想化した局所横断面は正規分布のグラフを上下反転したような滑らかな谷形で、岸側ほど浅く河道中央が最深となる形が望ましいとの仮説が示された。これは公式横断測量で左右非対称、thalweg位置、複断面、局所洗掘を含めて検査する未検証仮説として引き継ぎ、地図の見た目からbathymetryを作成・承認しない。

## 2026-07-14 Stage 18 v2実行後・v3実行前の履歴スナップショット

以下はv3再実行の承認・完了より前の状態であり、現行判断ではない。

- one-time v2 workflow run `29300177716` は64 cases × 500 stepsを完了し、数値評価に合格した。64/64完了、NaN 0、負水深0、最大CFL 0.12、最大絶対質量保存誤差 `3.013e-16`、数値wall time約625.7秒、peak RSS約172.4 MiBだった。
- 地図化は、3,840 × 2,640のcenter-sampled rasterで境界セル320が1セル欠落したためSTOPした。欠落位置は画像上端近くの東側河岸で、承認済み橋下補正や河道形状の不具合ではない。
- v2 authorizationは消費済みで再利用不可。旧gateは再び無効化され、地図化より前にfull fieldsをartifactへ保存していなかったため、同runから5地図だけを再構成することもできない。
- 修正は画像寸法と中心を維持し、描画範囲のy方向だけを合計約8.356 m対称拡張して0.7147801171875 mの正方形pixelにする。exact meshのzero-case検証で50,129/50,129セル、最小1 pixel/cell、cell 320も1 pixelを確認済み。
- 次の正本は `docs/STAGE18_FULL64_V3_RECOVERY_PLAN.md`。新v3経路は新しい明示承認までgate無効・authorization不在とし、再実行が承認された場合も数値PASS直後にfull fieldsと評価をSHA-256 manifest付きartifactへ保存してから、別jobで地図を作る。

## 2026-07-14 Stage 18 v2実行前の履歴スナップショット

以下はv2実行承認より前の状態であり、現行判断ではない。

- 芦屋橋の橋桁を水面障害物にしない補正後水域（680,633 pixel）とLinux metric mesh v2（50,129 cell）は、比較画像に対する「この形でよい」で形状承認済み。
- この形状承認は数値実行許可ではない。実行ゲートは無効、v2 authorizationは未作成で、64-case数値計算は0 caseのまま。
- corrected-v2専用のimmutable contract、64-case ensemble、zero-case preflight、fail-closed runner、評価・5枚の地図・判定画像、one-time workflowを事前審査用ブランチで準備中。
- 旧v1 authorization、runner、pilot、workflowは補正後計算へ流用せず、拒否専用のままとする。
- 利用者に提示する実行判断は、補正後v2上で64 cases × 500 stepsを承認後24時間以内に一回だけ実行してよいかに限定する。範囲・上限・STOP条件・出力・非主張事項は1枚の画像に固定し、承認レコードとgateは別のactivation commitでのみ追加する。

## 引き継ぎ元と正本

- 引き継ぎ元: ChatGPTプロジェクト「シーバス釣行」のチャット「領域一致の方法」
- WORKの正本: `/Users/swarm/Documents/SeaBass`
- Gitリモート: `https://github.com/Fujisawa-lab-inside/fishing.git`
- 移行時ブランチ: `agent/stage18-full64-run`
- 基準コミット: `e22bc2e`（`main` / `origin/main` と同一、Stage 18 production-mesh pilotまで統合済み）

## 移行時点までに完了していた範囲

- ブラウザ版の遠賀川河口シミュレータ v4.7.8（PC版・スマホ版）
- 679,791 pixelの正解水面領域と、50,333 cellのproduction mesh
- Stage 13〜17の数値計算・実メッシュ・物理入力準備・公式データ取得方針
- Stage 18の決定的64-case inference ensemble（seed `20260713`）
- fail-closed runner、統計reducer、pilot evaluator
- production mesh上の1/4/16-case pilot
- 16/16 pilot合格（GitHub Actions run `29229011438`）

## 移行時に引き継いだ作業

Stage 18 full64実行基盤が、ブランチ上の未コミット変更として残っていた。

- 変更済み: `tools/run_stage18_production_mesh_pilot.py`
- 新規: `.github/workflows/stage18-full64-run.yml`
- 新規: `.github/workflows/stage18-full64-validation.yml`
- 新規: `config/stage18_full64_run_authorization_v1.json`
- 新規: `docs/STAGE18_FULL64_RUN.md`
- 新規: `onga_stage18_full64_evaluator.mjs`
- 新規: `tools/run_stage18_full64.py`
- 新規: `tools/aggregate_stage18_full64.py`
- 新規: `tools/validate_stage18_full64.mjs`
- 新規: `tools/validate_stage18_full64_artifacts.py`

このWORKでは、引き継いだ実装をレビューし、one-time実行ゲート、承認・mesh・ensembleの固定digest、途中progress、evaluation provenance、集約入力検証、workflow契約検証を追加した。

full64の実計算は、contract validationを通した変更がdefault branchへ統合されるまで実行しない。

## WORK移行時の検証結果

2026-07-13に現在の未コミット実装をローカル検証し、次を確認した。

- JavaScriptの構文検査: 合格
- Python 4ファイルの構文検査: 合格
- full64 authorization/evaluatorのfail-closed検証: 合格
- 64 × 50,333 cellの圧縮artifact・統計集約検証: 合格

検証用に生成した一時成果物はリポジトリに残していない。

## full64の固定契約

- 64 cases × 最大500 steps
- ensemble seed: `20260713`
- 64/64完了必須
- NaN: 0
- 負水深: 0
- CFL: 0.95以下
- 最大絶対質量保存誤差: `1e-8`以下
- wall time: 3,600秒以下
- peak RSS: 8,192 MiB以下
- 手動workflow確認token: `RUN_STAGE18_FULL64_20260713`

比較は同一step数であり、同一物理時刻ではない。現段階の結果は暫定推論入力に対する実行時間・数値安定性の証拠に限定する。

## 継続して守る制約

- 物理Validation済みとは表現しない。
- 感度分析の結果とは表現しない。
- 暫定推論値を観測値として扱わない。
- 公開シミュレータへ接続しない。
- legacy flow calculationを変更しない。
- 失敗caseを補完しない。
- full64完了を追加runの自動承認とみなさない。

## 移行時に設定した作業順

1. 未コミットのfull64一式をレビューする。
2. contract validationを再実行する。
3. 変更をcommitし、PRでCIを通す。
4. CI合格後、明示token付きの手動workflowでfull64を1回実行する。
5. run reportとfield artifactをevaluatorで判定する。
6. 合格時のみstep-matched statisticsを生成する。
7. 結果と解釈上の制限を文書化する。

詳細な実行手順と解釈制限は `docs/STAGE18_FULL64_RUN.md` を参照する。
# Stage 19 public-data inference continuation (2026-07-14)

- The normalized smooth symmetric inverse-normal-like cross-section family has been approved and is digest-locked by `config/stage19_public_inference_shape_approval_v1.json`.
- The broad ranges and M/N/O/G candidate source roles are approved by `config/stage19_inferred_scenario_ranges_approval_v1.json`.
- Exactly 64 deterministic cases have been generated in `config/stage19_provisional_ensemble_cases_v1.json`; they are not assigned to a solver and do not authorize execution.
- `config/stage19_solver_parameter_coverage_audit_v1.json` prohibits reuse of the current Stage 18 kernel because only 1 of 16 approved inputs is applied with the intended meaning.
- The mean-removed 2026-02-15 JMA Hakata curve has been approved as the relative M-boundary reference and is fixed by `config/stage19_m_boundary_tide_approval_v1.json`; no absolute mouth level is assigned.
- `tools/stage19_solver_inputs.py` and `tools/stage19_shallow_water_kernel_v1.py` now apply all 16 approved dimensions. Synthetic tests and a noncanonical 50,113-cell Darwin zero-case probe passed; the exact 50,129-cell Linux preflight remains required before any numerical case.
- The immutable inactive run scope is `config/stage19_full64_execution_contract_v1.json`. The next requester decision is the two-way choice shown in `docs/visuals/stage19-full64-execution-decision.png`: one 64-case × 500-step run within 24 hours, or stop at the present state.
- No further production-mesh numerical case, physical Validation claim, external contact, public simulator connection, automatic retry, `main` merge, or additional run is currently enabled.
- The authorized one-time Stage 19 run completed in Actions run `29323240389`: 64/64 cases, NaN 0, negative depth 0, maximum CFL 0.12, maximum mass error `2.548e-15`, and five complete-cell maps. Evidence manifest SHA-256 is `c18e770052cb1365e77dd04d8aa73a9c6ef2d265a715b1e1d45de897a63b6961`.
- The 500 adaptive steps span only 3.25–6.09 simulated seconds, so the result is numerical-stability evidence, not a developed physical flow field. The one-time authorization is consumed; no rerun or additional run is authorized.

## Stage 20 browser mesh v2 connection (2026-07-15)

- The Linux x86-reproduced barrage-endpoint mesh is the approved canonical geometry. Browser mesh v2 contains 50,199 cells and 68 barrage faces; binary SHA-256 is `09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659`.
- Choice A connected `stage20-browser-reference.html` and `onga_stage20_reference_worker.mjs` to `public/data/onga/stage20/mesh-v2.json` on the work branch.
- A real WebKit page load and button click passed: zero clipped cells, zero non-finite values, zero depth drift, maximum velocity `2.551e-17 m/s`, and synthetic stable timestep `0.0033593783763900234 s`.
- This is a synthetic uniform still-water connection check only. It does not connect the public simulator, run physical flow, publish, or merge `main`.
- The machine-readable result is `config/stage20_browser_mesh_v2_connection_result_v1.json`; the screen evidence is `docs/visuals/stage20-browser-mesh-v2-connection.png`.
- The 36-hour hybrid browser path has also been ported to mesh v2 using a synthetic response pack. It produced 37 hourly snapshots from hour -12 to +24 for all 50,199 cells; a real WebKit run completed in 395 ms including first load. The visual in `docs/visuals/stage20-hybrid-v2-decision.jpg` was approved for the next code-only acceleration phase; that approval did not authorize a physical run.

## Stage 20 physical precompute acceleration (2026-07-15)

- The mesh-v2 hybrid browser path was visually approved. The next code-only phase ported the physical runner to mesh v2 and added kernel v2 without changing the numerical flux, hydrostatic reconstruction, boundary conditions, friction, or CFL rule.
- A deterministic 300-step nonphysical benchmark measured 16.25x from mesh v2, 1.22x from kernel v2, and 19.85x combined. The maximum relative state difference between kernels on mesh v2 was `6.41e-16`, within the sealed `1e-12` tolerance.
- Applying that synthetic multiplier to the prior failed physical checkpoint gives a planning estimate of 26.4 minutes for one 600-physical-second case. This is not a physical run result or guarantee; the candidate stops after 60 wall minutes and does not retry.
- The next user decision is the two-way choice in `docs/visuals/stage20-physical-pilot-v2-decision.jpg`: authorize one GitHub-hosted Linux x86 run within 24 hours, or keep execution disabled and continue code-only optimization.
- At the end of the code-only acceleration phase, no v2 authorization or gate existed. The later explicitly approved one-time result is recorded in the next section; that approval did not authorize a public connection, `main` merge, or paid resource.

## Stage 20 one-time physical pilot v2 result (2026-07-15)

- The explicitly approved mesh-v2/kernel-v2 run completed once in GitHub Actions run `29396657600` on execution commit `593e82c92c1b4111407e5fdaa213c4e89f3230eb`.
- It reached 600.0048579 physical seconds in 81,861 steps and 1,492.626 wall seconds. Maximum CFL was 0.12, maximum relative mass-balance error was `2.1974e-14`, and non-finite values and negative depths were both zero.
- Ten checkpoints and four maps were produced. Artifact evidence manifest SHA-256 is `f6bd88da4082dbbbfed035e996263b0e1ae9d193bea3e9e9c562356d1c404760`; artifact `8335924320` expires on `2026-10-13`.
- Missing Japanese glyphs in the Linux-rendered artifact maps were corrected by rerendering the exact retained final fields without another physical run. The retained fields SHA-256 is `a4421b659aabdcd7ead78b9244facfbe5d595666acf862f77f1958717ec6dca7`.
- The one-time gate is consumed. No retry, additional physical run, physical-validation claim, public connection, or `main` merge is authorized. The next user decision is whether the four flow-direction views should become the v2 reference display before planning the 36-hour response basis.

## Stage 20 36-hour response-basis planning (2026-07-15)

- The four flow-direction views from the completed pilot were approved as the Stage 20 v2 reference display. The approval is recorded in `config/stage20_physical_pilot_v2_result_adoption_approval_v1.json` and authorizes planning only.
- Extrapolating the measured pilot ratio gives about 89.6 runner-hours for one 36-hour trajectory and 985 runner-hours for all 11 bases. With 5-hour safe segments under the GitHub-hosted 6-hour job ceiling, this becomes 18 segments per basis and 198 segments in total.
- The 600-second state was still changing, so it cannot be treated as a static steady response. The physical plan must retain dynamic trajectories or use a separately validated reduced-order time-response model.
- Cell-local timestep analysis gives only a 3.28x ideal upper-bound speedup before synchronization and conservation overhead, so local time stepping alone is not the recommended first optimization.
- The next binary decision is the compute route shown in `docs/visuals/stage20-36h-precompute-strategy-decision.jpg`: A develops a compiled/fused kernel v3 using code-only equivalence and speed tests first; B accepts the current kernel v2 and a 198-segment campaign plan. Neither choice by itself authorizes a physical run.

## Stage 20 compiled kernel v3 code-only result (2026-07-15)

- Route A was approved. A fused Numba kernel v3 was implemented without changing mesh v2, numerical flux, hydrostatic reconstruction, boundary conditions, friction, CFL, or float64 state.
- The one-time code-only Linux x86 run `29410611389` passed. Across five 300-step repetitions per kernel, the median kernel-v3 speedup was 7.9227x, maximum relative state difference was `6.2681e-16`, simulated-time difference was zero, and non-finite and negative-depth counts were zero.
- The fixture exercised synthetic nonzero M/N/O/G, barrage, and fishway paths but did not use physical boundary inputs or advance a physical campaign.
- Applying the synthetic speedup to the completed kernel-v2 physical pilot gives an unverified estimate of about 3.14 minutes for a kernel-v3 physical 10-minute run and about 124.3 runner-hours / 33 five-hour segments for all 11 bases. These are projections, not guarantees.
- The next binary decision is whether to authorize one kernel-v3 physical 10-minute benchmark within 24 hours. No physical run, retry, 11-basis campaign, public connection, or `main` merge is currently authorized.

## Stage 20 one-time kernel v3 physical pilot result (2026-07-15)

- The explicitly approved mesh-v2/kernel-v3 run completed once in GitHub Actions run `29411976467` on execution commit `00852a870e8551e6ae59483bc0f24d0a19a065b4`.
- It reached 600.0048579 physical seconds in 81,861 steps and 304.202 wall seconds. Maximum CFL was 0.12, maximum relative mass-balance error was `2.1974e-14`, and non-finite values and negative depths were both zero.
- Against the completed kernel-v2 run, maximum relative field difference was `3.2708e-15`; the four corrected map JPEGs were byte-identical. Physical-pilot speedup was 4.9067x and wall time fell 79.62%.
- The updated planning projection is about 18.25 runner-hours per 36-hour basis and 200.77 runner-hours for 11 bases. With 5-hour wall segments this is 4 segments per basis and 44 total, excluding queue/setup/transfer/restart/failure overhead.
- The one-time gate is consumed. No retry, additional physical run, 11-basis campaign, physical-validation claim, public connection, or `main` merge is authorized. The next decision is whether to adopt kernel v3 for detailed segmented-plan preparation; that decision will not itself start the campaign.

## Stage 20 kernel v3 detailed segmented plan (2026-07-15)

- Kernel v3 was approved for detailed planning only. No physical segment or campaign was authorized.
- Detailed planning found that the original 44-segment estimate would cold-start at the beginning of the requested past-12-hour display. A 12-hour warmup was therefore added before the retained window.
- The execution-disabled candidate now models hour -24 through +24 as six 8-physical-hour segments per basis: 66 segments for 11 bases, with 37 retained hourly snapshots from -12 through +24.
- Measured-pilot extrapolation gives about 4.06 wall hours per segment, a 5-hour stop cap, and about 267.70 runner-hours total, excluding queue/setup/transfer/restart/failure overhead.
- Missing or corrupt predecessor checkpoints stop before a numerical step; cross-basis restart, automatic retry/resume, partial publication, and downstream execution after failure are forbidden.
- The next visual decision is limited to one `reference-s01` warmup canary from model hour -24 to -16. Even a successful canary will not authorize the remaining 65 segments, public connection, or `main` merge.

## Stage 20 reference-s01 warmup canary result (2026-07-16)

- The explicitly approved one-time `reference-s01` run completed in GitHub Actions run `29415527789` on execution commit `a4f21d210c4aed36f3ae9cc81de9f4df77d50070`.
- It reached 28,800.0012 physical seconds in 2,979,347 steps and 13,695.202 numerical wall seconds (3h48m15s), under the 5-hour stop.
- Maximum CFL was 0.12, maximum relative mass-balance error was `8.8017e-14`, and non-finite and negative-depth counts were zero. All eight hourly checkpoints and 13 evidence-file digests passed.
- Simple extrapolation updates the planning estimate to about 22.83 runner-hours per six-segment reference basis and 251.08 runner-hours for 66 segments, but other basis conditions may run at different speeds.
- The final-hour RMS velocity change was `0.04351 m/s` under time-varying tide, so this is not evidence of a static steady state or sufficient warmup.
- The one-time gate is consumed. No retry, additional segment, remaining 65-segment execution, public connection, physical-validation claim, or `main` merge is authorized.
- Four diagnostic maps were rendered from the exact retained final fields without another numerical run. They show model hour -16 for the full estuary, barrage, confluence, and fishway.
- A dormant `reference-s02` continuation contract is prepared. It is bound to the verified S01 restart and would retain the first five requested hourly snapshots at model hours -12 through -8.
- The next visual decision is A: authorize only S02 once, or B: retain S01 and stop. No S02 authorization, gate, or activation exists yet.

## Stage 20 reference-s02 continuation result (2026-07-16)

- The explicitly approved one-time `reference-s02` run completed in GitHub Actions run `29434250546` on execution commit `83aa9abc9d8de07552bcd37b996556506fe393df`.
- It continued the digest-verified S01 restart from model hour -16 to -8, reaching 28,800.0067 physical seconds in 3,187,689 segment steps and 14,366.265 numerical wall seconds (3h59m26s).
- Maximum CFL was 0.12, maximum relative mass-balance error was `8.6385e-14`, and non-finite and negative-depth counts were zero. All eight checkpoints and 18 evidence-file digests passed.
- Five direct-solver snapshots at model hours -12, -11, -10, -9, and -8 were retained and rendered on one common 0–0.23 m/s scale.
- This verifies the S01→S02 numerical chain and the first five requested display snapshots. It does not verify observed flow, daily forecast accuracy, or browser interpolation accuracy.
- The one-time gate is consumed. No retry, S03, remaining 64-segment execution, public connection, `main` merge, or physical-validation claim is authorized.
- The browser comparison was approved as route A and completed without another physical run. Exact hourly snapshot loading passed with a maximum float32 velocity-vector RMSE of `2.3343e-9 m/s`.
- A deliberately omitted hour reconstructed by linear time interpolation failed the high-accuracy thresholds at model hours -11 and -10. The worst -11-hour vector RMSE was `0.01626 m/s` and speed MAE was `0.009742 m/s`.
- The candidate architecture therefore retains every displayed hourly snapshot and forbids a missing-hour linear fallback. Cross-condition interpolation remains unvalidated.
- This comparison result was adopted as route A. A cross-condition holdout plan now uses the existing 50%-open reference S02 as an unused direct-solver target and proposes interpolation from new 0%-closed and 100%-open barrage bases.
- The recommended staged scope covers five hours and four views with the same velocity thresholds. It would require two 16-hour basis trajectories split into eight four-hour jobs, projected at about 15.6 runner-hours from the reference timings.
- The next visual decision is A: prepare an inactive barrage-first eight-job contract, or B: prepare an inactive five-input forty-job contract. Either choice still requires separate execution authorization. No physical run, S03, public connection, or `main` merge is authorized.
- Route A was selected. The sealed barrage holdout contract now contains two parallel four-job chains for barrage-body opening 0% and 100%, each modeling hour -24 through -8 and retaining five hourly snapshots. Fully closed keeps the approved fishway head-difference relation active.
- A stage barrier requires both conditions to pass before either proceeds. Every job stops after five numerical wall hours; workflow reruns, automatic retries, cross-basis restarts, and continuation after a failed stage are forbidden.
- The runner and activation-only workflow pass inactive contract validation. Authorization, gate, and activation files are absent, so no numerical step has run.
- The next visual decision is whether to authorize exactly this eight-job run once within 24 hours. Expected elapsed time is about 8–10 hours and total resource about 15.6 runner-hours, neither guaranteed.

## Stage 20 barrage holdout stopped result (2026-07-16)

- The explicitly authorized one-time barrage holdout was consumed by GitHub Actions run `29464186133` on execution commit `3b2cba242b2da1205121d9dbf2e231f0b081b49a`.
- Five of eight numerical jobs completed and passed the available numerical checks. The maximum CFL was `0.12`, maximum relative mass-balance error was `2.4024e-13`, and non-finite and negative-depth counts were zero.
- `barrage-closed-s03` was externally terminated with exit code `124` at the fixed five-hour wall limit. Its last retained checkpoint reached three of four physical hours with no numerical-threshold failure; it did not produce a sealed final restart or the required model-hour `-12` snapshot.
- The stage barrier worked: both S04 jobs were skipped. Automatic retry and additional execution remain forbidden, and the one-time gate is consumed.
- Only one of ten required endpoint snapshots is sealed, so the 50:50 interpolation, five-hour metric comparison, and four-region direct/interpolated/error maps are not evaluable. This is `not_evaluable`, not an interpolation failure.
- The five complete artifacts and one partial diagnostic artifact are retained under `docs/results/stage20-barrage-holdout-29464186133`. All complete evidence manifests, file digests, arrays, final restarts, final fields, and the available snapshot were verified.
- The audit also found that the plan required regional-mask digests before execution but no literal mask file/digest was recorded, and no water-depth acceptance threshold was defined. The pre-existing approved view definitions remain reproducible, but these limitations must be corrected before a strict recovery comparison.
- The next visual decision is A: adopt the stopped result and prepare code-only acceleration plus an inactive recovery plan, or B: retain the evidence and end this holdout path. A does not authorize another physical run.

## Stage 20 barrage holdout inactive recovery candidate (2026-07-17)

- The user chose to continue under the free public-standard-runner condition. This was interpreted as authorization to prepare the recovery path, not as authorization to start another physical run.
- The five sealed successful jobs from run `29464186133` are retained. The unsealed partial closed-S03 checkpoints remain diagnostic-only and are not used as restart inputs.
- The remaining scope is five physical jobs: four sequential two-hour closed-barrage jobs from model hour `-16` to `-8`, plus one four-hour open-barrage job from `-12` to `-8`. The first closed job and the open job may start in parallel.
- The numerical mesh, kernel, inferred bathymetry, roughness, boundary inputs, barrage endpoints, and fishway relation are unchanged. Splitting changes only recovery checkpoint boundaries.
- The recovery contract fixes the public `ubuntu-latest` standard runner, verifies public visibility immediately before authorization consumption, forbids larger or paid runners, and estimates 14–17 total runner-hours and 12–16 elapsed hours. The prior closed two-hour checkpoint took about 2h54m, leaving about 2h06m below the five-hour stop, but later intervals may differ. GitHub artifacts remain for 30 days; required evidence and records will be retained on the work branch. The cost expectation is 0 USD under the current public-standard-runner policy, not a future guarantee.
- The four approved regional masks are now stored and digest-locked before execution. Recovery reports and receipts record the exact input restart and input evidence-manifest SHA-256. Water-depth interpolation consistency thresholds are RMSE `0.10 m` and maximum absolute error `0.25 m`; they do not assert actual bathymetric accuracy.
- The contract, runner, workflow, masks, and decision image pass inactive validation. Authorization, gate, and activation files are absent, and no numerical step has been called.
- The next visual decision is A: authorize exactly these five recovery jobs once within 24 hours, or B: retain the stopped result without recovery. Retry, other physical runs, reference S03, public connection, and `main` merge remain outside scope.
