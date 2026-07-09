# 遠賀川河口シミュレータ v4.7.7

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.7.7: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.7.7: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.7.7 の修正点

- `onga_pointcloud_water_region_v477.js` を追加しました。
- スコア計算用の水面評価点群から水面領域を生成します。
- 評価点群から生成した水面領域の外縁を、通常表示で青点線として描画します。
- `water_polygon` 外縁は補助扱いとし、主表示は評価点群外縁へ移行します。
- ホットスポットの水面ターゲットは、これまで通り評価点を使います。
- 釣り座候補は、評価点群外縁のサンプルを優先します。
- 橋・河口堰・画面端・開境界に近い外縁サンプルは釣り座候補から除外します。
- legacy_shoreline は通常表示から外し、評価点群外縁とGeoJSON水面判定を優先します。

## v4.7.6 の修正点

- 表示用のshorelineを、荒い個別shorelineではなく `water_polygon` の外縁へ切り替えました。
- 釣り座候補も `water_polygon` 外縁サンプルを優先します。
- `water_polygon` 外縁は通常表示で青点線として描画します。
- 既存の座標ベースshorelineとlegacy_shorelineは通常表示から外し、`debugGeometry=1` の確認表示に下げました。
- 水面判定と青点は、引き続き `water_polygon` / `land_polygon` を優先します。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
