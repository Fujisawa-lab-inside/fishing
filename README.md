# 遠賀川河口シミュレータ v4.6.5

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- Webサービス: `https://fujisawa-lab-inside.github.io/fishing/`
- 選択画面: `index.html`
- PC版 v4.6.5: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.6.5: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## 釣行判断カード

- `prime_window_patch.js` を追加しました。
- 今から24時間内を30分刻みで走査し，本命90分・次点90分・避ける時間を表示します。
- 本命カードの `この時間に合わせる` を押すと，時間スライダーを該当時間の中央へ移動します。
- 評価理由は最大3項目に絞り，全閉・潮の動き・夜間・潮汐流などを短く表示します。

## v4.6.5 の修正点

- `onga_approved_green_recognition_patch.js` を追加しました。
- 確認済みの認識画像に基づき、水面・陸地境界の緑線をマップ上に表示します。
- 釣り座を承認済みの緑線境界上に固定します。
- 河口堰，橋，魚道の釣り座除外と、河口堰/橋を跨ぐキャスト禁止は継続します。

## v4.6.4 の修正点

- `onga_green_boundary_stands_patch.js` を追加しました。
- 釣り座を、提供画像の緑線で示された水面・陸地境界線上に配置します。
- 水面標的は従来の水面スコアから選び、釣り座だけを最寄りの緑線境界へスナップします。
- 河口堰，橋，魚道の釣り座除外と、河口堰/橋を跨ぐキャスト禁止は継続します。

## v4.6.2 の修正点

- `onga_spatial_safety_patch.js` を追加しました。
- 遠賀川河口堰，橋，魚道を釣り座候補から除外します。
- 河口堰または橋を跨ぐキャスト・ルアー軌道を無効化します。
- `public/data/onga/no_stand_areas.geojson` と `public/data/onga/no_lure_crossing_lines.geojson` を追加しました。
- GitHub Pagesへ静的サイトとしてデプロイするワークフローを追加しました。

## v4.6.1 の修正点

- 現地ゲート入力で8門すべて全閉の場合，遠賀川本流ゲート流を0として扱います。
- 全閉時に残る流れ成分は，魚道・西川・曲川・潮汐です。
- 水面はv4.6の連続水域として維持し，遠賀川・西川・曲川は水塊寄与率トレーサーで扱います。
- 魚道は本流ゲート流に混ぜず，魚道出口を起点とする局所流として扱います。

## 注意

このシミュレータは釣行判断用の簡易モデルです。安全確認の代替ではありません。増水，濁流，流木，足場冠水，強風時は釣行しないでください。
