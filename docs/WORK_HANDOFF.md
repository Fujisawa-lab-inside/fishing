# 「領域一致の方法」からWORKへの引き継ぎ

更新日: 2026-07-14

この文書の「移行時」各節は履歴スナップショットである。旧v1手順は `docs/STAGE18_FULL64_RUN.md`、補正後v2の実行候補は `docs/STAGE18_FULL64_V2_EXECUTION_PLAN.md`、最新の実装状態はGit履歴を正本とする。

## 2026-07-14時点の継続状態

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
