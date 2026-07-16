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
- 時刻: −12時間から+24時間までの37時点。前後移動、再生、0時間への復帰に対応
- 地点の値: 地図上の水域をクリックまたはタップすると、流速、水深、流向を表示
- キーボード: 左右キーで時刻移動、Spaceで再生・停止、地図上のEnterで中央地点を選択

再生は+24時間で停止し、自動的に先頭へ戻りません。

## 固定したデータ契約

- メッシュ: `public/data/onga/stage20/mesh-v2.json`、50,199セル
- 応答パック: `public/data/onga/stage20/response-pack-synthetic-v2.json`
- 入力: `public/data/onga/stage20/hybrid-synthetic-input-v1.json`
- 背景: `data/external/gsi/seamlessphoto` のローカルタイルのみ
- フィールド: `[時刻][depthM, eastVelocityMPS, northVelocityMPS][セル]` のFloat32

メッシュ、応答パック、合成出力のSHA-256を読み込み時に固定値と照合します。

S02の5時点物理パック、物理runner、既存公開シミュレーター、外部タイルには接続していません。

## 検証

```sh
node tools/validate_stage20_hybrid_gui.mjs
node tools/validate_stage20_hybrid_browser.mjs
node tools/validate_stage20_hybrid_worker_runtime.mjs http://127.0.0.1:4173/
```

PCとスマホの操作確認には `tools/capture_stage20_hybrid_gui.swift` を使用できます。この試作を公開画面へ接続する場合は、データの位置づけと公開範囲を改めて承認してください。
