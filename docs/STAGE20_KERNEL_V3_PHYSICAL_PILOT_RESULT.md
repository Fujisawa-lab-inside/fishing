# Stage 20 kernel v3 physical pilot result

更新日: 2026-07-15

承認された一回限りのmesh-v2＋kernel-v3パイロットは、GitHub Actions run `29411976467` で正常完了した。

- 50,199セル、1条件、物理時間600秒
- 600.0048578949198秒到達、81,861ステップ
- 数値wall time 304.202253369秒（5分04.2秒）
- 最大CFL 0.12、最大相対質量誤差 `2.1974e-14`
- NaN 0、負水深0、checkpoint 10/10、4地点画像4/4

同じ入力を使ったkernel v2との最大相対差は全fieldで`3.2708e-15`だった。補正済みの4地点JPEGはbyte単位で同一であり、表示される流向・流速分布は変わっていない。実測wall timeは24分52.6秒から5分04.2秒へ短縮され、4.9067倍、79.62%削減となった。

この実測比で36時間×11基底を単純外挿すると、1基底約18.25 runner-hours、全11基底約200.77 runner-hoursである。5時間wallの安全区間では1基底4 segment、合計44 segmentになる。これは実行済み36時間結果ではなく、queue、setup、artifact転送、checkpoint再開、失敗segmentを含まない計画値である。

GitHub runnerで欠落した日本語glyphだけを、同一の最終field（SHA-256 `3e8fed6ee564a34761081728aa2c1d244cdccfee8a78e9203641f2c985613c3b`）から再描画した。数値計算は再実行していない。元artifact画像も証拠digest検証用に保持している。

この結果は、推論入力1条件でのkernel v2/v3の等価性、数値安定性、実行時間を示す。観測との一致、物理Validation、36時間応答基底の妥当性は示さない。一回限りのgateは消費済みで、再試行、追加物理run、11基底campaign、公開接続、`main`反映は許可されていない。
