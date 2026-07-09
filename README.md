# 遠賀川河口シミュレータ v4.6.9

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.6.9: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.6.9: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

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

## v4.6.7 の修正点

- 計算用の水面・陸地境界を高解像度の承認済み水面マスクへ差し替えました。
- 河口堰の北側・南側は、河口堰の開閉に応じた境界として扱います。
- 西川は画面外から遠賀川本流との合流までの流れとして扱います。
- 曲川は画面外から遠賀川本流との合流までの流れとして扱います。
- 釣り座は承認済み緑線境界上に固定します。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
