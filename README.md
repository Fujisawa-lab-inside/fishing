# 遠賀川河口シミュレータ v4.6.3

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- 選択画面: `index.html`
- PC版 v4.6.3: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.6.3: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.6.3 の修正点

- 水面マスクを格子化する軽量2D CFDソルバー `cfd_patch.js` を追加しました。
- 速度場は、水面セル上のポテンシャル場を反復緩和で解き、勾配から `u,v` を計算します。
- 境界・流入源は、ゲート・魚道・西川・曲川・潮汐です。
- 全閉時はゲート由来流量を0にし、魚道・西川・曲川・潮汐だけで速度場を解きます。
- 粒子流 `flow_particles_patch.js` は、CFDがONの場合はCFD速度場に沿って移動します。
- 地図右上に `CFD ON/OFF` と `粒子流 ON/OFF` のパネルを表示します。

## v4.6.2 の修正点

- 水の流れを粒子の移動で表示する `flow_particles_patch.js` を追加しました。
- 粒子の発生源は、ゲート・魚道・西川・曲川・潮汐です。
- 全閉時はゲート由来粒子を停止し、魚道・西川・曲川・潮汐由来の粒子のみを表示します。
- 粒子表示は地図上の右上パネルからON/OFFできます。

## v4.6.1 の修正点

- 現地ゲート入力で8門すべて全閉の場合、遠賀川本流ゲート流を0として扱います。
- 全閉時に残る流れ成分は、魚道・西川・曲川・潮汐です。
- 水面はv4.6の連続水域として維持し、遠賀川・西川・曲川は水塊寄与率トレーサーで扱います。
- 魚道は本流ゲート流に混ぜず、魚道出口を起点とする局所流として扱います。
