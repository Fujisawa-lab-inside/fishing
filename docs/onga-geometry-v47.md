# 座標ベース地形データ v4.7 候補

## 目的

画像認識・ラスタ補正・ランタイム座標補正に依存せず、ユーザー提供の緯度経度を正とする地形データへ移行する。

## 追加データ

`public/data/onga/onga_geometry.geojson` を追加した。

含まれる主なFeature:

- 曲川橋南側水面ポリゴン
- 曲川橋南側・東岸/西岸 shoreline
- 曲川橋南側流軸
- 曲川・遠賀川本流合流部の突き出た陸地ポリゴン
- 合流部突き出し陸地の曲川側/本流側 shoreline
- 曲川橋 line
- 西川橋 line
- 河口堰1〜8番ゲート中心
- 魚道中心
- 河口堰1〜8基準線

## 座標順

GeoJSONは `[longitude, latitude]`。
ユーザー入力はDMSから10進表記へ変換済み。

## 次の実装方針

v4.7では以下へ移行する。

- `water_polygon` 内を水面として扱う
- `land_polygon` 内を陸地として扱う
- `shoreline` を釣り座候補線として扱う
- `bridge_line` と `barrage_line` を no-stand / no-cross として扱う
- 水面判定、流況計算、釣り座生成、表示オーバーレイを同じGeoJSONから生成する
