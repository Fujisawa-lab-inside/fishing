# Stage 20 ハイブリッドGUI試作

## 位置づけ

`stage20-hybrid-gui.html` は、Stage 20 のブラウザ表示とローカル実験を確認するための独立したGUI試作です。既存の公開画面には接続していません。既定の合成・保存済みリプレイはsolverを実行せず、`local_r1c_experiment`だけが利用者の明示操作後に最大300秒のローカルR1C solverを実行します。

モード別の能力と禁止claimは `config/stage20_runtime_capabilities_v2.json` を正本候補とします。全モードが未較正・非予測で、釣果確率、釣行可否、安全判断、公開権限を持ちません。既定の `synthetic` は `response-pack-synthetic-v2` から生成した合成データです。

## ローカル起動

ローカルsolverとoffline forcingを使用する場合は、リポジトリのルートで専用serviceを起動します。

```sh
.venv-stage20/bin/python tools/serve_stage20_local_simulator_v1.py --bind 127.0.0.1 --port 4173
```

次のURLをブラウザで開きます。

```text
http://127.0.0.1:4173/stage20-hybrid-gui.html
```

serviceはloopback以外へのbindを拒否し、solver・forcingのPOSTには同一origin、JSON、プロセスごとのtokenを要求します。静的配信は検証済みGUI import closureと登録済みruntime assetのallowlistだけに限定し、リポジトリ一覧・`tools/`・checkpoint・未審査HTML/JavaScript・symlinkを配信しません。local solverのjob作成前には、表示用外部資産を含む17資産とsolverが同期読込するmesh、初期場、水域mask、潮位、魚道parameterをSHA-256とbyte lengthで検査します。forcingはPC内の保存済み潮位表だけを使い、ネットワーク取得を行いません。

local runnerはjob作成前のservice検査に加え、実行直前にも同じ17資産をhard-coded path・SHA-256・byte lengthとregistry/capabilityの両方へ照合します。共有するC2.2数値coreのreportはcontextを分け、local実験では標準4-stage cycleのplan・execution approval、24時以降の潮位延長を権限や入力として記録せず、JMA snapshotをruntimeで直接読んだとも記録しません。固定されたsource contract・source report・stage19 tide candidateだけをlocal provenanceとして記録し、24時以降の延長が必要になる条件は実行前に拒否します。

capabilityの `READY_FOR_EXPLICIT_LOCAL_RUN` は「明示requestを受け付けるためのrunnerと入力が検査済み」という意味だけです。まだsolver preflightや数値実行が完了した意味ではなく、応答は `physicalSolverConnected:false` と `solverExecutionPreflightPassed:false` を維持します。normal Gitへ入れない大容量assetはexact pathでignoreし、baseline validatorも未ignoreまたは誤追跡を拒否します。

`python3 -m http.server 4173 --bind 127.0.0.1` は合成・保存済みreplayの静的確認だけに使用できます。この場合、ローカルsolverとforcing APIは利用できません。`file://` から直接開くと、Workerとローカルデータの読み込みに失敗します。

## 操作

- 表示範囲: 河口全域、河口堰、合流部、魚道
- 地図の色: 流速、水深
- 補助表示: 流向矢印、地物ラベル
- 河口堰の開門表示: 「自動推定」と「現地目視入力」を切替。自動推定は固定順序 `5 → 4 → 6 → 3 → 7 → 2 → 8 → 1` の段階0〜8、現地入力は1〜8番の個別開閉に対応
- 現地観測JSON: 固定schemaでローカルファイルを検証・読込し、最終recordを画面内の8門表示へ反映。現地入力はcanonical JSONとして端末へDL可能
- forcing入力: 利用者が選んだ気象庁降水量CSVとPC内の保存済み潮位表だけを統合。ネットワーク取得はせず、対応する保存済み年がなければfail-closed。現在登録済みの潮位表で37時間窓を作れる日付は `2026-01-02`〜`2026-12-30`
- 事前計算準備: 11/11作業、22/22検証、境界影響、個別門basis、50:50補間、checkpoint、費用概算、結果provenanceをread-only表示
- 契約監査・復旧: error 0、warning 299、復旧bundle 588文書、物理Validation計画状態をread-only表示。監査JSON・復旧ZIP・計画書は操作時だけSHA検証してDL
- 水門位置表示: A1〜A8の番号参照アンカー点だけを表示。厳密な幾何中心や物理端面としては扱わない
- 写真可視端点: 承認済み16/16点を緑色の破線と端点でレビュー表示。物理メッシュ採用とは明確に分離
- 魚道状態: 主水門入力とは独立して「常時有効・操作不可」を固定表示。全主水門閉でも上流・下流接続の表示を維持
- 時刻: −12時間から+24時間までの37時点。前後移動、再生、0時間への復帰に対応
- 地点の値: 地図上の水域をクリックまたはタップすると、流速、水深、流向を表示
- キーボード: 左右キーで時刻移動、Spaceで再生・停止、地図上のEnterで中央地点を選択

再生は+24時間で停止し、自動的に先頭へ戻りません。

### 河口堰の現地入力について

開門入力UIの固定順序、9状態、現地入力の上書き、入力元・観測時刻、自動との差、標準順序外警告、自動復帰、非接続境界は [Stage 20 河口堰開門入力UI候補](STAGE20_GATE_INPUT_UI_CANDIDATE.md) に固定します。

河口堰の番号は旧GUIと同じ現地基準（西から東へ1〜8番）です。番号位置は `docs/results/stage20-barrage-pink-structure-alignment-candidate-v2/gate-reference-anchor-authority-v2.geojson` のA1〜A8を直接Web Mercatorへ投影します。A1〜A8は番号対応の参照アンカーであり、厳密な幾何中心ではありません。メッシュ内の8等分IDは番号位置に使用しません。

入力した開門番号は地図上のA1〜A8状態バッジへ即時反映されます。`stage20_gui_integration_status_manifest_v1.json` に固定した写真可視端点16点は、緑色の破線と端点によるレビューoverlayとして表示します。A1〜A8と写真可視端点は別authorityであり、どちらも物理メッシュ採用を意味しません。H2の46.5mは8門共通のモデル開口幅契約として保持しますが、地理的な実位置線、写真上の端面間距離、または厳密中心を示す線としては使いません。魚道は主水門1〜8に含めません。

写真可視端点は16/16承認済みですが、GUIには同時に「物理メッシュ採用未承認」と表示します。A1〜A8から端点を導出せず、写真可視端点を凍結メッシュへ適用しません。凍結メッシュの門ID、魚道セル、計算領域、応答パックはこのGUI統合では変更しません。

凍結メッシュの門ID自体には全湿潤幅の8等分が残るため、将来、現地入力を物理計算へ接続する前に、主水門8門と魚道・微調節部を分離した別のメッシュ契約が必要です。

現地入力は現在の画面を開いている間だけ自動推定を上書きし、再読み込みすると自動推定へ戻ります。必要な場合は「現在入力をJSONでDL」で端末へ保存し、次回「観測JSONを読込」で復元できます。読込とDLはブラウザ内だけで処理し、サーバーへの自動保存・外部送信は行いません。`synthetic`と保存済みreplayではStage 20の応答パックを再計算しないため、入力は流速・水深・時刻へ反映しません。`local_r1c_experiment`だけは、利用者が実行ボタンを押した時点の8門入力を固定し、最大300秒のローカル未較正solverへ反映します。

魚道は承認済みトポロジー方針に従い、主水門1〜8とは別の常時有効な接続として表示します。`synthetic`では表示専用、保存済みR1Cと`local_r1c_experiment`では未較正の集約C2.1 storage表現です。いずれも操作不可で、現地魚道の再現・較正済み流量を意味しません。

## 固定したデータ契約

- GUI統合状態: `config/stage20_gui_integration_status_manifest_v1.json`（read-only、SHA-256固定、runtime binding 6件）
- 事前計算準備GUI統合: `config/stage20_parallel_readiness_gui_integration_v1.json`（read-only、SHA-256固定、runtime binding 5件）
- 契約監査・復旧GUI統合: `config/stage20_contract_recovery_gui_integration_v1.json`（起動時は5.4 KBのsidecarだけを読込、4 bindingをoffline検証、3成果物をDL時検証）
- 契約監査report: `docs/results/stage20-contract-lint-and-recovery-v1/report.json`（585 JSON、error 0、warning 299）
- 復旧ZIP: `docs/results/stage20-contract-lint-and-recovery-v1/stage20-json-contract-recovery-v1.zip`（588文書・589 entry検証済み）
- 物理Validation計画: `docs/STAGE20_PHYSICAL_VALIDATION_PLAN_V1.md`（計画のみ、未実施）
- 事前計算準備package: `config/stage20_parallel_readiness_package_v1.json`（11項目完了、22/22 PASS、復旧binding 30件）
- 境界影響: `docs/results/stage20-boundary-mesh-impact-v1/report.json`（旧境界から116,403画素、旧mesh 14,859セル重心の所属が変化）
- 現地観測schema: `config/stage20_field_gate_observation_schema_v1.json`
- 結果provenance schema: `config/stage20_result_provenance_schema_v1.json`
- メッシュ: `public/data/onga/stage20/mesh-v2.json`、50,199セル
- 応答パック: `public/data/onga/stage20/response-pack-synthetic-v2.json`
- 入力: `public/data/onga/stage20/hybrid-synthetic-input-v1.json`
- offline forcing: 気象庁降水量CSVは利用者選択ファイル、潮位はasset registryでSHA-256・byte lengthを固定した `data/jma_hakata_2026_hourly_tide_QF.txt` だけを使用。API provenanceのlocatorはrepository-relativeで、端末の絶対pathを返さない
- 水門番号参照アンカー: `gate-reference-anchor-authority-v2.geojson` の `gate_reference_anchor` 8点（A1〜A8、厳密中心ではない）
- 写真可視端点: `config/stage20_barrage_gate_photo_visible_faces_authority_v1.geojson` の8線分・16端点（レビュー表示のみ、物理メッシュ採用未承認）
- 主水門幅: H2の46.5m（モデル開口幅の静的契約として保持し、地理的線分は描画しない）
- 魚道位置: `public/data/onga/onga_geometry.geojson` の `fishway_center` 1点
- 背景: `data/external/gsi/seamlessphoto` のローカルタイルのみ
- フィールド: `[時刻][depthM, eastVelocityMPS, northVelocityMPS][セル]` のFloat32

GUI統合manifest、事前計算準備GUI統合manifest、その5 binding、契約監査・復旧sidecar、メッシュ、応答パック、合成出力、A1〜A8参照アンカーGeoJSON、写真可視端点GeoJSON、魚道座標GeoJSONのSHA-256を読み込み時に固定値と照合します。監査JSON、復旧ZIP、物理Validation計画は起動時には読み込まず、DL操作時だけ固定SHAとbyte lengthを照合します。44,880セルのR20レビュー用メッシュと50,199セルの現行synthetic応答packは非互換として表示し、混用しません。

事前計算準備パネルは「v3境界を採用する場合はmesh再生成後に事前計算」「formal R20は既存計算の再計算ではなく初回事前計算」「個別門はbinary 9 basis＋5 holdoutまたはcontinuous 17 basis＋5 holdout」「全閉＋全開50:50補間は未採用」を表示します。費用はplanning estimateであり、実行承認やproduction mesh選択を意味しません。

S02の5時点物理パック、production物理runner、既存公開シミュレーター、外部タイルには接続していません。接続するsolverは明示操作後のbounded local R1Cだけです。

M0.1で追跡対象に含める過去のvalidation/reportには、作成時の端末絶対pathを「当時取得できなかった外部証拠」として記録したものがあります。実行時に参照・解決するpathではありませんが、公開配布前には履歴証拠を保持するかsanitized copyへ分離するかを別途決定する必要があります。魚道coupling candidateの `judgmentVisual.inlinePath` も同じ性質ですが、承認済みartifactのwhole-file SHAを壊さないため原本を保持し、M0.1 validatorでは値・JSON pointer・SHAを固定した非runtime例外1件としてのみ許可します。

## 検証

### M0.1 人手による視覚・操作確認（2026-08-26）

ローカルGUIを実ブラウザで確認し、次の4項目を人手確認PASSとした。

- 「河口全域」「河口堰」「曲川・遠賀川合流部」「魚道」の切替で、地図範囲とラベルが変わる
- 時間スライダー、前後1時間、再生の操作で、時刻・色・流向矢印が更新される
- 「流速」と「水深」の切替で、白抜け・黒塗り・極端なちらつきがない
- 河口堰画面でA1〜A8の並びが自然に見え、魚道が主水門とは別に表示される

一方、旧画面の小さな「合成データ／非予測」表示は利用者が認知できず、表示自体の存在ではなく情報の優先度を不合格とした。M0.1では、表示範囲タブと地図の間に全幅の「現在表示」bannerを置き、合成・保存済みreplay・local計算の別と「予測ではない」境界を平文で常時表示する。760px以下では重複する小型source badgeを隠し、bannerを優先する。

また、service起動前に開いたタブが初回接続失敗を保持し続ける問題に対し、local計算serviceとforcing serviceを明示的に再確認する操作を追加した。画面はHTMLとJavaScriptの契約版が一致するまで初期状態から操作不能とし、moduleの読込・評価失敗または版不一致が確定した場合だけ、操作停止を維持したまま警告と再読込操作を表示する。Safariの正常なcold loadを固定秒数で版不一致と誤判定しない。再確認と再読込はcapability GETだけを行い、solverやforcing作成を開始しない。

このPASSはGUIの視認性、画面切替、時間操作、描画破綻の有無、番号表示と魚道の表示分離だけを対象とする。メッシュの物理的正しさ、A1〜A8の厳密位置、魚道の水理表現、stage4運用の実世界妥当性、較正、予測性能、釣行安全、canary、公開可否は未確認である。

### M0.2 runtime truth・失敗復帰（2026-08-26）

地図の直前にローカル計算状態を常時表示し、`未実行`、`接続確認中`、`計算中`、`結果検証中`、`結果表示中`、`入力変更済み・再計算が必要`、`安全停止`、`サービス未接続`を区別する。水門入力を計算後に変更した場合は、表示中または保存済みの結果が変更前の8門入力であることを地図の近くにも示す。

同じbannerの「水門入力と計算へ」はローカル計算カードへ移動するだけで、計算を開始しない。local計算が`failed`、forcing入力作成が`error`となった場合も再確認ボタンを表示する。再確認はcapability GETだけを実行し、solver job、forcing作成、subprocess、自動retryを開始しない。異常時も合成または保存済み表示を継続し、停止範囲がローカル計算だけであることを明示する。

HTMLとJavaScriptのbrowser contractは`m0.2-ui-20260826-01`へ更新し、追跡対象のWebKit確認toolでPC・スマホ双方の初期状態、source区分、計算未実行表示、計算カードへの導線、画面操作を検証する。この段階はGUIの状態表示と復旧導線だけを対象とし、solverの実行前検証、数値計算、物理妥当性、較正、予測、YODA、公開・昇格を承認しない。

```sh
python3 tools/validate_stage20_runtime_baseline_v2.py --workspace-candidate
node tools/validate_stage20_runtime_capabilities_v2.mjs
python3 -m unittest tests/test_stage20_local_service_m0.py tests/test_stage20_parallel_forcing_integration_v1.py -v
node --test tests/stage20_local_simulator_input_lock_20260806_test_v1.test.mjs
python3 tools/validate_stage20_gui_integration_status_manifest_v1.py
python3 tools/validate_stage20_contract_recovery_gui_integration_v1.py
node tools/validate_stage20_gui_integration_runtime_v1.mjs
node tools/validate_stage20_hybrid_browser.mjs
node tools/validate_stage20_hybrid_worker_runtime.mjs http://127.0.0.1:4173/
```

`tools/validate_stage20_gui_integration_runtime_v1.mjs`を含む旧display-only validatorと各旧validation結果は履歴として保持し、local solverを含む現行GUIの正本判定には使用しません。追跡後のCIではbaseline validatorを`--release`で実行します。

PCとスマホの操作確認には `tools/capture_stage20_hybrid_gui.swift` を使用できます。この試作を公開画面へ接続する場合は、データの位置づけと公開範囲を改めて承認してください。
