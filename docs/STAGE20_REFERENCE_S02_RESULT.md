# Stage 20 reference-s02 result

更新日: 2026-07-16

一回限りで承認された`reference-s02`は、GitHub Actions run `29434250546`で正常完了した。S01のdigest検証済みrestartからmodel時刻-16〜-8時間を継続し、要求表示範囲の最初の5 snapshot（-12、-11、-10、-9、-8時間）を保存した。

- 28,800.0067物理秒、3,187,689 segment step
- 数値wall time 14,366.265秒（3時間59分26秒）
- 最大CFL 0.12
- 最大相対質量誤差 `8.6385e-14`
- NaN 0、負水深0
- checkpoint 8/8、snapshot 5/5
- S01 input restart、最終restart、最終fieldのdigest一致

同じ0〜0.23 m/s表示尺度で、5時刻の河口全域地図を保存した。これらは直接solver snapshotであり、ブラウザ補間結果ではない。

この結果は、推論入力の基準条件でS01からS02へ連続計算できたことと、数値安定性を示す。実際の遠賀川との一致、当日の予報精度、ブラウザ補間精度は示さない。

一回限りのgateは消費済み。自動retry、追加run、残り64 segment、公開接続、`main`反映、物理Validationの主張は承認されていない。

比較検証の作成はA案として承認され、追加の物理計算なしで完了した。毎時snapshotの読み戻しは合格したが、欠落した1時間を前後2時間から直線補間する経路は高精度基準に不合格だった。次の判断は、この比較結果を採用して条件間補間のholdout試験計画だけを作るかである。判断資料は`docs/visuals/stage20-reference-s02-browser-comparison-decision.jpg`、詳細は`docs/STAGE20_REFERENCE_S02_BROWSER_COMPARISON.md`。
