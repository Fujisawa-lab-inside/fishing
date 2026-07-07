# 遠賀川河口シミュレータ v4.6.1

GitHub Pagesで動作するブラウザ版シミュレータです。

## 公開URL

- 選択画面: `index.html`
- PC版 v4.6.1: `OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html`
- スマホ版 v4.6.1: `OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html`
- 元の自己完結HTML: `pc_full.html`, `mobile_lite.html`

## v4.6.1 の修正点

- 現地ゲート入力で8門すべて全閉の場合、遠賀川本流ゲート流を0として扱います。
- 全閉時に残る流れ成分は、魚道・西川・曲川・潮汐です。
- 水面はv4.6の連続水域として維持し、遠賀川・西川・曲川は水塊寄与率トレーサーで扱います。
- 魚道は本流ゲート流に混ぜず、魚道出口を起点とする局所流として扱います。
