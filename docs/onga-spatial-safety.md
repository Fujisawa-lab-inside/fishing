# 遠賀川河口 空間安全マスク v4.6.2

## 目的

v4.6.1では、河口堰に近い北側など、実際には川の中または構造物上で立てない場所に釣り座候補が出ることがある。v4.6.2では、釣り座生成後のスコアリング前後に空間安全マスクを適用し、非現実的な釣り座とキャスト軌道を除外する。

## 適用する制約

- 赤: 遠賀川河口堰。堰上に釣り座を置かない。堰を跨ぐキャスト・ルアー軌道を無効にする。
- 黄: 橋。橋上に釣り座を置かない。橋を跨ぐキャスト・ルアー軌道を無効にする。
- 青: 魚道。魚道上に釣り座を置かない。
- 緑: 陸地・水面境界。釣り座OK領域ではなく、水際境界の参考情報として扱う。

## 実装

`onga_spatial_safety_patch.js` をPC版・スマホ版ラッパーで `closed_gate_patch.js` の後に読み込む。

このパッチは既存の自己完結HTMLを直接編集せず、次の関数を上書きする。

- `landConfidenceAt`: no-standバッファ内の土地信頼度を0にする。
- `findLandCastPositionForWater`: 候補釣り座が河口堰・橋・魚道上に入る場合、および標的までの線が河口堰・橋を跨ぐ場合を除外する。
- `makeShoreCastingHotspots`: 最終候補にも同じ制約を再適用してランクを振り直す。
- `drawPins` / `renderHotspotList`: 既存状態に残る古い候補も表示前に除外する。

## データ

- `public/data/onga/no_stand_areas.geojson`
- `public/data/onga/no_lure_crossing_lines.geojson`

GeoJSONの座標順は `[longitude, latitude]`。
