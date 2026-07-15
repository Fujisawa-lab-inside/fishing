# Stage 20 kernel v3 コード限定結果

GitHub-hosted Linux x86_64で、物理時間campaignではない決定的300-step比較を5回ずつ実行した。run `29410611389` は成功し、kernel v3はkernel v2に対して中央値で7.9227倍だった。

## 数値一致

- 最大相対状態差: `6.2681e-16`（許容`1e-12`以下）
- 模擬時間差: `0.0 s`
- NaN: `0`
- 負水深: `0`
- mesh: v2、50,199セル、68 barrage faces

M/N/O/G境界、河口堰、魚道を通る合成入力を使用した。これは観測入力による物理計算ではなく、数値経路の同値性と速度だけを検査するfixtureである。

## 速度

- kernel v2中央値: `8.4873 s / 300 steps`
- kernel v3中央値: `1.0713 s / 300 steps`
- speedup: `7.9227x`
- compile＋初回1 step: `1.5134 s`（steady-state測定から除外）

## 物理runへの見積り

完了済みkernel v2物理10分パイロットの`1,492.626 s`へ合成fixtureの7.9227倍を単純適用すると、kernel v3は約`188.4 s`（3分08.4秒）となる。11本×36時間は約124.3 runner時間、5時間区切りなら33区間という計画値になる。

この換算は物理run結果でも保証値でもない。入力分布、step数、I/O、checkpointにより変わるため、36時間campaignを計画する前に同じ1条件×物理10分をkernel v3で一回だけ確認する判断が必要である。

## 現在の禁止事項

追加物理run、automatic retry、11基底campaign、公開シミュレータ接続、`main`反映は許可されていない。
