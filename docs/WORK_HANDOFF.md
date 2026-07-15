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
- No v2 authorization or gate exists. No physical solver, workflow, public connection, `main` merge, or paid resource has been started.
