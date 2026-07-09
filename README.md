# 遠賀川河口シミュレータ v4.7.3

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.7.3: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.7.3: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.7.3 の修正点

- 地形確認用の赤線・黄色線・緑線を通常表示から非表示にしました。
- `debugGeometry=1` をURLへ付けた場合だけ、GeoJSONの地形確認オーバーレイを表示できます。
- ホットスポット数が極端に減らないよう、座標GeoJSONで明示した範囲外では既存モデルへフォールバックします。
- 座標GeoJSONの水面ポリゴン周辺では、旧水面モデルの青点を抑制します。
- ズーム時にレーザービーム状に見える釣り座→水面標的のキャスト補助線を通常表示から停止しました。

## v4.7.2 の修正点

- `onga_geometry_authority_v472.js` を追加しました。
- v4.7.1で残っていた旧水面モデル由来の青点・ホットスポット生成を抑制しました。
- 座標GeoJSONで定義した水面ポリゴン周辺では、GeoJSON内だけを水面として扱います。
- ホットスポットの水面ターゲットは、座標GeoJSONの `water_polygon` 内に限定します。
- `onga_approved_water_flow_patch.js` をv4.7.2ラッパーから外しました。

## v4.7.1 の修正点

- 旧画像認識由来の緑点オーバーレイを停止しました。
- `onga_green_boundary_stands_patch.js` と `onga_approved_green_recognition_patch.js` をv4.7.1ラッパーから外しました。
- `onga_barrage_alignment_v469.js` もv4.7.1ラッパーから外し、座標ベースGeoJSONを正として表示・計算します。
- 水面・陸地境界の表示は `onga_geometry_engine_v470.js` が描くGeoJSON由来のポリゴン/ラインに統一しました。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
