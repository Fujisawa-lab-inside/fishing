# 遠賀川河口シミュレータ v4.6

GitHub Pagesで動作するブラウザ版シミュレータである。

## 公開URL

- 選択画面: https://fujisawa-lab-inside.github.io/fishing/
- PC版: https://fujisawa-lab-inside.github.io/fishing/pc_full.html
- スマホ版: https://fujisawa-lab-inside.github.io/fishing/mobile_lite.html
- PC版 v4.6 ConfluenceTracer: https://fujisawa-lab-inside.github.io/fishing/OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html
- スマホ版 v4.6 ConfluenceTracer: https://fujisawa-lab-inside.github.io/fishing/OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html

## v4.6 の要点

v4.6では、v4.5の強制分離帯を削除し、水面を1つの連続水域として扱う。遠賀川・西川・曲川は流入源トレーサーとして扱い、水塊境界・混合・せん断をシーバス可能性スコアへ弱く反映する。

## 主要仕様

- 国土地理院写真タイルを背景に表示する。
- 遠賀川河口堰の8門ゲートを西側から1〜8番として扱う。
- 河口堰全閉時は本流ゲート放流を0とし，遠賀川側は魚道流のみを有効にする。
- 魚道は 33.88913889, 130.67458333 に配置し，北東方向の流れ出しとして扱う。
- 日付・時間範囲は現在時刻から -24h〜+72h である。
- PC版は詳細確認用，スマホ版は現地操作用である。
