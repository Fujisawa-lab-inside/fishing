# 遠賀川河口シミュレータ v4.7.4

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.7.4: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.7.4: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.7.4 の修正点

- 釣り座から水面標的へ伸びるキャスト方向線を復活させました。
- 現在認識している水面・陸地境界線を、通常表示で緑線として描画します。
- 赤線・黄色線・流軸などの地形確認用レイヤーは通常非表示のままです。
- `debugGeometry=1` をURLへ付けた場合だけ、赤線・黄色線・流軸などの確認用レイヤーを表示できます。

## v4.7.3 の修正点

- 地形確認用の赤線・黄色線・緑線を通常表示から非表示にしました。
- `debugGeometry=1` をURLへ付けた場合だけ、GeoJSONの地形確認オーバーレイを表示できます。
- ホットスポット数が極端に減らないよう、座標GeoJSONで明示した範囲外では既存モデルへフォールバックします。
- 座標GeoJSONの水面ポリゴン周辺では、旧水面モデルの青点を抑制します。
- ズーム時にレーザービーム状に見える釣り座→水面標的のキャスト補助線を通常表示から停止しました。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
