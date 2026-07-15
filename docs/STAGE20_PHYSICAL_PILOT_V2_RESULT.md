# Stage 20 physical pilot v2 result

更新日: 2026-07-15

承認された一回限りのmesh-v2＋kernel-v2パイロットは、GitHub Actions run `29396657600` で完了した。

- 50,199セル、1条件、物理時間600秒
- 600.0048578949198秒到達、81,861ステップ
- 数値wall time 1,492.625987149秒（24分52.6秒）
- 最大CFL 0.12、最大相対質量誤差 `2.1974e-14`
- NaN 0、負水深0、checkpoint 10/10、4地点画像4/4

artifactの9証拠ファイルと10 checkpointのdigest、最終field配列を取得直後に再検査し、すべて合格した。artifact IDは`8335924320`、expiryは`2026-10-13T07:13:46Z`、evidence manifest SHA-256は`f6bd88da4082dbbbfed035e996263b0e1ae9d193bea3e9e9c562356d1c404760`である。

GitHub runnerには日本語glyph fontがなく、sealed artifact内の地図文字が欠落記号になった。数値計算は再実行せず、同一の最終field（SHA-256 `a4421b659aabdcd7ead78b9244facfbe5d595666acf862f77f1958717ec6dca7`）を日本語fontで再描画した。数値・流向・色は変更していない。

この結果は推論入力に対する数値安定性、実行時間、4地点の表示を確認する一回限りのパイロットである。観測との一致、物理Validation、36時間応答基底の妥当性を証明しない。gateは消費済みで、自動再試行・追加run・公開シミュレータ接続・`main`反映は許可されていない。
