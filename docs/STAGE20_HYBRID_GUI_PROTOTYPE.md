# Stage 20 ハイブリッドGUI試作

## 位置づけ

`stage20-hybrid-gui.html` は、Stage 20 のブラウザ合成経路を地図と時系列で確認するための独立したGUI試作です。既存の公開画面には接続しておらず、物理ソルバーも実行しません。

画面が扱う値は `response-pack-synthetic-v2` から生成した合成データです。観測値、予報値、物理計算結果として利用しないでください。

## ローカル起動

リポジトリのルートでHTTPサーバーを起動します。

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

次のURLをブラウザで開きます。

```text
http://127.0.0.1:4173/stage20-hybrid-gui.html
```

`file://` から直接開くと、Workerとローカルデータの読み込みに失敗します。

## 操作

- 表示範囲: 河口全域、河口堰、合流部、魚道
- 地図の色: 流速、水深
- 補助表示: 流向矢印、地物ラベル
- 河口堰の開門表示: 「自動推定」と「現地目視入力」を切替。自動推定は固定順序 `5 → 4 → 6 → 3 → 7 → 2 → 8 → 1` の段階0〜8、現地入力は1〜8番の個別開閉に対応
- 時刻: −12時間から+24時間までの37時点。前後移動、再生、0時間への復帰に対応
- 地点の値: 地図上の水域をクリックまたはタップすると、流速、水深、流向を表示
- キーボード: 左右キーで時刻移動、Spaceで再生・停止、地図上のEnterで中央地点を選択

再生は+24時間で停止し、自動的に先頭へ戻りません。

### 河口堰の現地入力について

開門入力UIの固定順序、9状態、現地入力の上書き、入力元・観測時刻、自動との差、標準順序外警告、自動復帰、非接続境界は [Stage 20 河口堰開門入力UI候補](STAGE20_GATE_INPUT_UI_CANDIDATE.md) に固定します。

河口堰の番号は旧GUIと同じ現地基準（西から東へ1〜8番）です。番号中心は `public/data/onga/onga_geometry.geojson` のユーザー提供緯度経度を直接Web Mercatorへ投影します。メッシュ内の8等分IDは番号位置に使用しません。

入力した開門番号は地図上の対応区間と番号表示へ即時反映されます。`config/stage19_public_inference_input_plan_v1.json` に固定した国土交通省の公表諸元に従い、8本の色付き区間は各提供中心を基準に共通堰軸方向へ46.5mで描きます。魚道および微調節部は主水門1〜8の幅に含めません。

表示用の主水門区間は、魚道を含む全湿潤幅や凍結メッシュの `barrage_gate_id` を使用しません。凍結メッシュの門ID、魚道セル、計算領域、応答パックはこのGUI修正では変更しません。

凍結メッシュの門ID自体には全湿潤幅の8等分が残るため、将来、現地入力を物理計算へ接続する前に、主水門8門と魚道・微調節部を分離した別のメッシュ契約が必要です。

現地入力は現在の画面を開いている間だけ自動推定を上書きする表示メモで、再読み込みすると自動推定へ戻ります。Stage 20の応答パックには門別の流れを再計算する基底がないため、流速・水深・時刻には反映しません。誤認を避けるため、入力欄と地図の双方に「流れの図には未反映」と表示します。

## 固定したデータ契約

- メッシュ: `public/data/onga/stage20/mesh-v2.json`、50,199セル
- 応答パック: `public/data/onga/stage20/response-pack-synthetic-v2.json`
- 入力: `public/data/onga/stage20/hybrid-synthetic-input-v1.json`
- 水門番号中心: `public/data/onga/onga_geometry.geojson` の `gate_center` 8点
- 主水門幅: `config/stage19_public_inference_input_plan_v1.json` の公表値46.5m（表示契約として固定）
- 背景: `data/external/gsi/seamlessphoto` のローカルタイルのみ
- フィールド: `[時刻][depthM, eastVelocityMPS, northVelocityMPS][セル]` のFloat32

メッシュ、応答パック、合成出力、水門座標GeoJSONのSHA-256を読み込み時に固定値と照合します。

S02の5時点物理パック、物理runner、既存公開シミュレーター、外部タイルには接続していません。

## 検証

```sh
node tools/validate_stage20_hybrid_gui.mjs
node tools/validate_stage20_hybrid_browser.mjs
node tools/validate_stage20_hybrid_worker_runtime.mjs http://127.0.0.1:4173/
```

PCとスマホの操作確認には `tools/capture_stage20_hybrid_gui.swift` を使用できます。この試作を公開画面へ接続する場合は、データの位置づけと公開範囲を改めて承認してください。
