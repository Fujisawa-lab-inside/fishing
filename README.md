# 遠賀川河口シミュレータ v4.7.6

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.7.6: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.7.6: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.7.6 の修正点

- 表示用のshorelineを、荒い個別shorelineではなく `water_polygon` の外縁へ切り替えました。
- 釣り座候補も `water_polygon` 外縁サンプルを優先します。
- `water_polygon` 外縁は通常表示で青点線として描画します。
- 既存の座標ベースshorelineとlegacy_shorelineは通常表示から外し、`debugGeometry=1` の確認表示に下げました。
- 水面判定と青点は、引き続き `water_polygon` / `land_polygon` を優先します。

## v4.7.5 の修正点

- `onga_legacy_shoreline_v475.js` を追加しました。
- 過去画像由来の緑線を、`legacy_shoreline` 相当の補助境界として統合します。
- 現在の座標ベース shoreline と重なる場所では、座標ベース shoreline を優先します。
- legacy_shoreline は通常表示で薄い緑の点線として表示します。
- 釣り座候補としては、座標ベース shoreline が近くにない場合だけ legacy_shoreline を補助的に使います。
- 水面判定と青点は、引き続き water_polygon / land_polygon を優先します。legacy_shoreline は水面ポリゴンとしては使いません。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
