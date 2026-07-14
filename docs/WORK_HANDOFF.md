# 「領域一致の方法」からWORKへの引き継ぎ

更新日: 2026-07-14

冒頭の「Stage 18 v3完了後の最新状態」以外で、実行前後や移行時と明記した各節は履歴スナップショットであり、現行判断を示さない。旧v1手順は `docs/STAGE18_FULL64_RUN.md`、補正後v2の実行候補は `docs/STAGE18_FULL64_V2_EXECUTION_PLAN.md`、最新の実装状態はGit履歴を正本とする。

## 2026-07-14 Stage 18 v3完了後の最新状態

- one-time v3 workflow [run `29307047699`](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699) はexecution commit `c378fb3885484ea17b39143d294ca10e41cb59b6` 上で64 casesを完了し、数値評価に合格した。64/64完了、NaN 0、負水深0、最大CFL `0.12000000000000002`、最大絶対質量保存誤差 `3.0134486651120407e-16`、wall time `599.102227037`秒、peak RSS `168.59765625` MiB、最小水深 `1.26795059543982` mだった。
- 修正済みrasterは50,129/50,129セルを表現し、5/5枚の地図を完成した。numeric-evidence manifest SHA-256は`e60287e82d1837b978ecb1c939e9e4b5f2ac075bbaf5c4563df8972da8a350f8`、judgment SVG SHA-256は`47d3d36a257f4b086f707f97748d39782c50ff77ce40d55aed001233b3b11594`である。
- [results artifact `8300775754`](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699/artifacts/8300775754) と [numeric-evidence artifact `8300766356`](https://github.com/Fujisawa-lab-inside/fishing/actions/runs/29307047699/artifacts/8300766356) のexpiryはともに`2026-10-12`である。
- authorization `stage18-v3-20260714t044734z-one-time` は消費済みで再利用不可。現行gateは`consumed`・無効で、authorizationファイルは履歴証拠としてのみ保持する。実行workflowはactive gateを要求するため、依存導入や数値入力読込みより前のcontrol planeで停止する。自動retry、追加run、物理Validation主張、公開シミュレータ接続は許可されない。
- 比較はstep-matchedであり同一物理時刻ではない。結果は暫定推論入力に対する実行時間・数値安定性の証拠に限定する。詳細は `docs/STAGE18_FULL64_V3_RESULT.md`、機械可読記録は `config/stage18_full64_v3_result_record.json` を正本とする。
- 利用者の地図レビューでは、水深中央値の分布は一般に実水深と異なり、河道中央ほど深く岸へ近づくほど浅いのではないかとの仮説が示された。これは公式横断測量で検査する未検証仮説として引き継ぎ、地図の見た目からbathymetryを作成・承認しない。

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
