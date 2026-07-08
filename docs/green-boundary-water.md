# 緑線境界水面モデル v4.6.3

## 目的

過去に提供された水面領域を、ユーザーが新たに提供した「緑線＝陸地・水面境界」の画像情報に置き換える。

## 対象

- 西川
- 遠賀川本流
- 曲川
- 合流後の遠賀川下流

v4.6.3では、各河道の上流（南側）領域も水面計算に含める。

## 実装

`onga_green_boundary_water_patch.js` をPC版・スマホ版ラッパーから読み込む。

このパッチは以下を上書きする。

- `GSI.center` / `GSI.zoom` / `GSI.bounds`
- `ONGA.path`
- `ONGA.inflowChannels`
- `calibratedWaterMaskValueAt`
- `nearestHydroCorridor`
- `riverWidthAt`

水面は、`public/data/onga/green_boundary_water_axes.geojson` に記録した水面計算軸と幅を使う。旧来の赤領域水面マスクではなく、緑線境界に基づく西川・本流・曲川の連続水面として扱う。

## 注意

緑線そのものは釣り座可能領域ではなく、水面と陸上の境界である。釣り座候補の除外とキャスト横断禁止は `onga_spatial_safety_patch.js` が引き続き担当する。
