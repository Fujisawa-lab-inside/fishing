# Stage 18 full64 numerical ensemble run

## 承認範囲

この実行は、seed `20260713`の決定的Stage 18 inference ensemble、679,791 pixelの凍結水面領域、50,333 cellのproduction mesh、1 caseあたり500 stepsを対象とする。目的はオフラインの実行時間・数値安定性確認だけである。

次の主張や変更は承認範囲に含まれない。

- 物理Validation済みという主張
- 感度分析結果という主張
- 暫定推論値の観測値扱い
- 公開シミュレータへの接続
- legacy flow calculationの変更
- 失敗caseの補完
- 追加runの自動承認

承認の正本は `config/stage18_full64_run_authorization_v1.json` である。runnerとevaluatorは、承認者・承認日・指示文、pilotのPR head／merge commit／workflow run、mesh summary、mesh source array、metric mesh NPZ内の全配列、64-case ensemble、受入閾値、active／inactive parameter、safeguardを固定値として検証する。

metric mesh NPZの配列digestは、Stage 16 workflow run `29191537971`のartifact `stage16-metric-fv-mesh`から固定した。このrun以降、full64基準commitまでmesh generator・入力data・固定依存関係に変更がないことを確認済みである。

## 一回限りの実行ゲート

`.github/workflows/stage18-full64-run.yml` は `workflow_dispatch` 以外では起動しない。承認済みrunは、workflowがdefault branchの`main`へ統合された後、次の条件をすべて満たす場合だけ開始する。

- repository: `Fujisawa-lab-inside/fishing`
- actor: `RyusukeFujisawa`
- ref: `refs/heads/main`
- run attempt: `1`
- confirmation: `RUN_STAGE18_FULL64_20260713`

confirmation文字列は秘密情報ではなく、誤操作防止用の明示確認である。実行権限はGitHubのrepository権限で決まる。

workflowは専用concurrency groupで直列化される。authorize jobは過去のworkflow jobsをGitHub Actions APIで調べ、`Consume one-time authorization` stepが一度でも成功していれば新しいrunを拒否する。full64 job自身も`run_attempt == 1`を検査するため、失敗jobだけを再実行してauthorize jobを飛び越えることはできない。誤ったconfirmationはjobをskipせず、明示的に失敗する。

authorize stepの成功後に数値計算や基盤障害で失敗した場合も、この承認は消費済みである。同じrunのre-runや同じ承認recordによる再dispatchは行わない。再実行が必要な場合は、失敗run IDと理由を記録し、別の明示承認recordを作成する。

## PR前のcontract validation

通常のfull64数値計算はPRでは実行しない。PRでは次を検証する。

```bash
node --check onga_stage18_full64_evaluator.mjs
node --check tools/evaluate_stage18_full64.mjs
node --check tools/validate_stage18_full64.mjs
node --check tools/validate_stage18_full64_workflow.mjs

node tools/validate_stage18_full64_workflow.mjs
node tools/validate_stage18_full64.mjs

python -m pip install -r tools/requirements-stage16-metric-mesh.txt
python tools/validate_stage18_full64_artifacts.py
```

この検証は、one-time workflow gate、承認とcanonical ensemble、evaluatorのfail-closed動作、64 × 50,333 field artifact、report／evaluation／authorizationのdigest binding、時間配列のshape・有限性、円方向統計の±π境界を含む。

## 承認runの処理順

workflowは以下を順番に実行する。

1. 一回限りのauthorizationを検証・消費する。
2. 固定依存関係を導入する。
3. authorizationとcanonical 64-case ensemble digestを検証する。
4. 凍結production meshを生成し、summary digestを検証する。
5. canonical ensembleを生成し、file digestを検証する。
6. 64 casesを各500 steps実行する。
7. reportを評価し、authorization／report／field／mesh／ensemble digestをevaluationへ結び付ける。
8. evaluation合格時だけstep-matched statisticsを集約する。
9. 必須成果物がすべて存在することを確認してからsuccess artifactを作成する。

runnerのworkflow内呼び出しは次である。

```bash
python tools/run_stage18_full64.py \
  stage18-full64/onga_stage16_metric_fv_mesh_v1.npz \
  stage18-full64/ensemble.json \
  config/stage18_full64_run_authorization_v1.json \
  --mesh-summary stage18-full64/stage16_metric_mesh_summary.json \
  --fields-output stage18-full64/full64-fields.npz \
  --report-output stage18-full64/full64-report.json \
  --progress-output stage18-full64/full64-progress.json \
  --repo-root .
```

このコマンドをworkflow外で実行して、承認済みの一回を迂回してはならない。

## 成果物

成功時のartifact名は `stage18-full64-results-<run_id>` であり、次をすべて含む。

- production mesh NPZとmesh summary
- canonical 64-case ensemble JSON
- caseごとに原子的更新されるprogress JSON
- 64-case run report JSON
- 64 × 50,333の最終水深・2成分流速field NPZ
- provenance付きevaluation JSON
- step-matched statistics NPZ
- statistics summary JSON

field artifactは64/64 casesが有限・非負fieldで完了した場合だけ作成する。evaluationは64/64完了、NaN 0、負水深 0、CFL 0.95以下、最大絶対質量保存誤差`1e-8`以下、wall time 3,600秒以下、peak RSS 8,192 MiB以下を要求する。

数値run stepには65分のwatchdogを置き、90分のjob上限より前に失敗として制御を戻す。失敗時は `stage18-full64-diagnostics-<run_id>` を作り、存在するprogress、report、field、evaluation等をsuccess artifactとは別名で保存する。数値step timeoutでは、最後に完了したcaseまでのprogress JSONを診断に使う。GitHub run自体を手動cancelした場合はartifact uploadが完了しない可能性がある。

## Step-matched statistics

`tools/aggregate_stage18_full64.py` は、evaluationが同じreportとauthorizationにdigestで結び付いている場合だけ集約する。field NPZ内のmesh／mesh summary／ensemble／authorization digestと、reportの集約診断も照合する。

出力は速度median・IQR・2.5／97.5 percentile、水深median・IQR・2.5／97.5 percentile、wet probability、circular direction agreement、circular mean directionを含む。

これらは**同一step数で比較した値であり、同一物理時刻の値ではない**。各caseはadaptive time stepを使うため、500 stepsが同じ物理時間を表すとは限らない。また、承認済みbed elevationがないため、water depthを絶対water-surface elevationへ読み替えてはならない。

## Parameter coverage

現kernelでactiveなのは、mainstem mean depth、uniform open-channel Manning roughness、mouth phaseの初期方向摂動、fishway mode／coefficient／area、barrageのclosed-versus-open状態である。

tributary depth、cross-section family、thalweg offset、smoothing length、roughness multiplier、mouth amplitude、N／O／G discharge、barrage coefficient、partial opening magnitudeはinactiveである。このため、full64結果をSobol、Morris、rank correlation等のparameter sensitivity evidenceとして扱ってはならない。
