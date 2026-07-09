# 遠賀川河口シミュレータ v4.7.8

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.7.8: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.7.8: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.7.8 の修正点

- 評価点群から作る水面領域を連結成分へ分割します。
- 主要水域または高信頼 `water_polygon` に接続しない孤立水面候補を除外します。
- 陸地内で孤立して見える誤認識水面を、主要水域外として除外しやすくしました。
- 除外後の主要水域外縁だけを青点線で表示します。
- 釣り座候補も、除外後の主要水域外縁サンプルを優先します。
- `state.photoSampleStatus` に孤立除外セル数を表示します。

## v4.7.7 の修正点

- `onga_pointcloud_water_region_v477.js` を追加しました。
- スコア計算用の水面評価点群から水面領域を生成します。
- 評価点群から生成した水面領域の外縁を、通常表示で青点線として描画します。
- `water_polygon` 外縁は補助扱いとし、主表示は評価点群外縁へ移行します。
- ホットスポットの水面ターゲットは、これまで通り評価点を使います。
- 釣り座候補は、評価点群外縁のサンプルを優先します。
- 橋・河口堰・画面端・開境界に近い外縁サンプルは釣り座候補から除外します。
- legacy_shoreline は通常表示から外し、評価点群外縁とGeoJSON水面判定を優先します。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
