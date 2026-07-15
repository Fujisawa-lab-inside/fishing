# Stage 20 reference-s01 canary result

更新日: 2026-07-16

一回限りで承認された`reference-s01`は、GitHub Actions run `29415527789`で正常完了した。model時刻`-24`から`-16`まで8物理時間を計算し、8個のhourly checkpointを保存した。

- 28,800.001230414004物理秒、2,979,347 step
- 数値wall time 13,695.202秒（3時間48分15秒）
- 最大CFL 0.12
- 最大相対質量誤差 `8.8017e-14`
- NaN 0、負水深0
- checkpoint 8/8、restart digest一致

予測4時間03分より約15分早く、5時間停止上限まで約1時間11分45秒の余裕があった。同じ速度を単純適用すると、6 segmentのreference 1基底は約22.83 runner-hours、66 segment全体は約251.08 runner-hoursとなる。ただし他の入力条件でも同じ速度になる保証はない。

各checkpointのfieldを検査し、最終restart stateから復元した水深・東西流速・南北流速が最終fieldと完全一致することを確認した。潮汐入力は時間変化しており、最後の1時間でもRMS流速変化は`0.04351 m/s`ある。このため、静的定常状態や助走完了を示す結果ではない。

最終fieldから物理計算を追加せず、model時刻-16時間の河口全域・河口堰・合流地点・魚道の4診断地図を作成した。全地図は同じ50,199セルの水深・流速値を参照する。地図は診断用であり、観測検証済みの釣況予測ではない。

次区間`reference-s02`のinactive contractを準備した。S01のdigest検証済みrestartからmodel時刻-16〜-8時間を継続し、要求表示範囲の最初の5 snapshot（-12〜-8時間）を保存する。新しい視覚承認がない限り実行されない。

この結果は推論入力1条件での数値安定性、8時間実行時間、checkpoint経路を確認するcanaryである。観測との一致、物理Validation、残り65 segment、公開接続、`main`反映を承認しない。一回限りのgateは消費済みで、自動retryと追加runは禁止されている。次の判断資料は`docs/visuals/stage20-reference-s01-result-decision.jpg`。
