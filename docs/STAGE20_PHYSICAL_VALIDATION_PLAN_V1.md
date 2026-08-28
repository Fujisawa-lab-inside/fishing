# Stage 20 物理Validation計画 v1

## 結論

現時点で実施できるのはValidation計画の固定までであり、物理Validationそのものではない。公開データと明示した推論で開発する現行方針では、数値Verificationと候補間比較は進められるが、観測に基づく予測精度を合格と主張してはならない。

物理Validationへ進む判断時期は、水面・陸地境界、production mesh、河床高と鉛直基準、境界時系列、門別水門則、魚道則、粗度zoneを固定した後、事前計算または公開接続を承認する前である。GUIの見た目や操作入力を確定した時点では判断しない。

## VerificationとValidationの分離

| 区分 | 問うこと | 現時点 |
|---|---|---|
| 数値Verification | 方程式と離散化を正しく解けているか | synthetic、保存則、収束性、正水深性を別途検査可能 |
| 補間holdout | 直接計算に対して事前計算・補間が十分近いか | 同一mesh・同一入力契約の直接計算が必要 |
| 物理Validation | 実河川の観測を独立期間・独立地点で再現できるか | 未実施、現行入力では主張不可 |

河口堰50%の「全閉＋全開の50:50補間」は、直接50%計算との補間holdoutに合格した場合だけ計算近似として採用候補になる。それでも観測との物理Validationにはならない。門別開放も同じで、個別門の直接計算とinteraction holdoutが必要である。

## 開始前に固定する入力

次をpath、SHA-256、単位、座標系、鉛直基準、適用期間とともに一つの入力manifestへ固定する。

1. 全域で閉合した水面・陸地境界と開境界M/N/O/G。
2. 採用済みproduction mesh、cell・face identity、境界tag。
3. 測量に基づく河床高、測量日、補間法、不確かさ、鉛直基準面。
4. M/N/O/Gの水位または流量時系列、観測所との空間対応、欠測・品質flag。
5. 1〜8番門それぞれの開度または状態時系列、敷高、有効幅、流量・運動量則。
6. 魚道の入口・出口、断面、敷高、流量・運動量則、運用状態。
7. 河床材料、護岸、植生、構造物に基づくManning粗度zoneと許容範囲。
8. 初期状態、助走期間、wet/dry、CFL、保存則、checkpoint条件。
9. 観測水位と独立した2成分流速の時刻、座標、測定法、精度、品質flag。

画像や水面maskから絶対水深を決めない。粗度を河床高、境界値、水門則の誤差を吸収する自由変数にしない。

## データ分割

較正用とValidation用を先に分離し、結果を見てから入れ替えない。

- 較正: 粗度zoneと、資料で不確かさ範囲が与えられた構造物係数だけを調整する。
- 時間holdout: 較正と異なる潮汐位相、流量帯、門操作を含む連続期間を使う。
- 空間holdout: 較正に使わない水位点とADCP・流速計断面を残す。
- 操作holdout: 全閉、全開、一様中間開度、単門変化、複数門interactionを分離する。
- 極端条件: 高流量、低流量、大きな上下流水位差は通常条件と別に判定する。

推奨する最小構成は、較正期間1組、時間holdout 2組以上、空間holdout 1地点以上、門操作holdout 5ケース以上である。ただし、観測の独立性と品質を満たさなければ件数だけで合格にしない。

## 段階と停止条件

### P0 入力・datum監査

座標系、鉛直基準、単位、時刻帯、観測所―境界対応、欠測処理を照合する。一つでも不明なら停止し、推定値で暗黙補完しない。

### P1 数値Verification

production meshでNaN/Inf、負水深、CFL超過、質量収支、checkpoint再開一致、mesh refinement感度を検査する。ここでの合格は数値実装の合格だけである。

初期hard gate候補:

- NaN/Inf: 0
- 許容外の負水深cell: 0
- CFL: 採用solver契約の上限以下
- 相対質量収支誤差: frozen契約値以下
- 同一checkpointからの再開結果: frozen決定性許容値以内

上限値はsolver・境界則・wet/dry契約と同時に固定し、本書だけで新しい値を発明しない。

### P2 較正

較正期間だけを用い、事前に許したparameter範囲内で調整する。parameter、探索範囲、目的関数、試行回数、棄却理由を全て保存する。bathymetryや境界時系列を結果合わせで変更した場合は、新しいmodel versionとしてP0からやり直す。

### P3 独立Validation

parameterを凍結し、時間・空間holdoutで次を計算する。

- 水位: bias、MAE、RMSE、位相差、振幅比
- 流速: 東西・南北成分bias/MAE/RMSE、速さ、流向差
- wet/dry: confusion matrix、境界位置誤差
- 河口堰・魚道: 上下流水位差、総流量、門別または経路別流量
- 保存則・安定性: P1と同じ数値指標

物理acceptance thresholdは観測精度、用途、空間・時間解像度を確認してから、結果を見る前に別recordで承認する。暫定図の見た目や単一RMSEだけで合格にしない。

### P4 操作・極端条件holdout

個別水門入力を公開する場合、少なくとも単門変化と複数門interactionの直接計算・観測対応を検査する。全閉・全開だけの2基底から個別門を推定して合格扱いにしない。魚道は水門とは別経路として存在・流量・運動量収支を確認する。

### P5 公開readiness

P0〜P4の全manifest、入力SHA、solver version、mesh identity、較正履歴、holdout結果、失敗例、適用範囲を固定する。公開GUIは、物理Validation済み範囲外の入力を選んだ場合に「未検証」または「計算不可」を表示し、最も近い検証済みcaseへ暗黙置換しない。

## 合否の単位

合否はmodel全体に一度だけ付けず、次の組で記録する。

`boundary version × mesh identity × bathymetry/datum × forcing period × gate/fishway law × parameter set × solver version × output quantity × validation domain`

この組の一要素を変更した場合、影響を受けるP0〜P4を再実施する。GUI表示だけの変更で物理再計算は不要だが、水面・陸地境界、mesh、河床高、水門・魚道の水理則、境界時系列、粗度を変更した場合は、既存結果とのcompatibility判定後に直接計算または事前計算が必要になる。

## 今後利用者が判断するもの

今すぐ数値thresholdや候補採用を判断する必要はない。次の順に、証拠が揃った時だけ判断する。

1. 全域境界を正本として凍結できるか。
2. その境界から作ったmeshをproductionに採用できるか。
3. 物理入力manifestに不足・datum不整合がないか。
4. 較正・Validation分割と用途別thresholdを、結果を見る前に採用できるか。
5. P1数値Verificationに合格した後、P2〜P4の物理実行を承認するか。
6. 全holdoutの証拠を見て、入力範囲ごとに公開可能か。

## 現在の禁止事項

本計画の作成は、solver実行、production mesh採用、事前計算、門別基底生成、魚道表現採用、物理Validation合格、response pack変更、public runtime接続を承認しない。
