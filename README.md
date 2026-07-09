# 遠賀川河口シミュレータ v4.7

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.7: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.7: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.7 の修正点

- `public/data/onga/onga_geometry.geojson` を追加しました。
- `onga_geometry_engine_v470.js` を追加しました。
- ユーザー提供の緯度経度を正とする座標ベース地形データを読み込みます。
- 曲川橋南側の水面ポリゴン、東岸/西岸shoreline、流軸を水面判定・水流計算・釣り座生成へ共通適用します。
- 曲川・遠賀川本流合流部の突き出た陸地を land_polygon として扱います。
- 曲川橋・西川橋・河口堰1〜8基準線を no-stand / no-cross 制約として扱います。
- 既存の水面マスクは、座標ベースGeoJSONで明示されていない範囲のフォールバックとしてのみ使います。

## v4.6.9 の修正点

- `onga_barrage_alignment_v469.js` を追加しました。
- 認識上の赤線両端を、河口堰1番・8番ゲート座標へ合わせる座標補正を追加しました。
- 水面マスクと緑線境界釣り座に同じ補正変換を適用します。
- 河口堰1〜8門の既存実測座標を補正基準として使います。

## v4.6.8 の修正点

- `onga_boundary_editor_patch.js` を追加しました。
- マップ上で水面・陸地境界を直接クリックして修正できる境界編集GUIを追加しました。
- 緑=閉じた陸地境界、黄=橋、赤=河口堰として描けます。
- 編集データはブラウザのlocalStorageに保存できます。
- 編集データを計算に適用できます。
- GeoJSONとして出力・読込できます。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
