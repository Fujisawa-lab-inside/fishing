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
- 河口堰の現地入力: 西から東へ1〜8番の各門を開・閉で記録。全閉、西1-2、中央4-5、東7-8、全開のプリセットに対応
- 時刻: −12時間から+24時間までの37時点。前後移動、再生、0時間への復帰に対応
- 地点の値: 地図上の水域をクリックまたはタップすると、流速、水深、流向を表示
- キーボード: 左右キーで時刻移動、Spaceで再生・停止、地図上のEnterで中央地点を選択

再生は+24時間で停止し、自動的に先頭へ戻りません。

### 河口堰の現地入力について

河口堰の番号は旧GUIと同じ現地基準（西から東へ1〜8番）です。番号中心は `public/data/onga/onga_geometry.geojson` のユーザー提供緯度経度を直接Web Mercatorへ投影します。メッシュ内の8等分IDは番号位置に使用しません。

入力した開門番号は地図上の対応区間と番号表示へ即時反映されます。色付き区間には実門幅の資料がないため、各堰辺を最も近い提供中心へ割り当てた表示上の推定です。凍結メッシュの門IDや計算領域は変更しません。

この入力は現在の画面を開いている間だけの表示メモで、再読み込みすると未入力に戻ります。Stage 20の応答パックには門別の流れを再計算する基底がないため、流速・水深・時刻には反映しません。誤認を避けるため、入力欄と地図の双方に「流れの図には未反映」と表示します。

## 固定したデータ契約

- メッシュ: `public/data/onga/stage20/mesh-v2.json`、50,199セル
- 応答パック: `public/data/onga/stage20/response-pack-synthetic-v2.json`
- 入力: `public/data/onga/stage20/hybrid-synthetic-input-v1.json`
- 水門番号中心: `public/data/onga/onga_geometry.geojson` の `gate_center` 8点
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
