# 河口堰・門別候補推定 v1

## 目的

公式の河口堰流入量・総放流量・上下流水位と、任意の画像証拠・直前状態を使い、A1〜A8の説明可能な開放組合せを上位3件まで順位付けする。

## 出力の意味

- `topConfigurations`: 256組合せ中の相対的な上位候補。
- `gateOpenSupportByGateId`: 全256候補の相対重みから求めた門別支持度。
- `equivalentDischargeCoefficientTimesAreaM2`: 総放流量と水頭差が要求する `Cd × 総開口面積`。門番号は決めない。
- `relativeCandidateWeight`: 候補間の比較値。較正済み確率ではない。

流入量は国土交通省の公開操作帯を選ぶために使う。総放流量は集約水理制約にだけ使い、特定の門へ割り当てない。微調整ゲート、魚道、貯留・時刻差が未分離なので、出力は診断候補である。

## 画像証拠

`--image-evidence` は門別に次を任意指定できる。

```json
{
  "byGateId": {
    "A5": {
      "pairedOrangeLampsVisible": true,
      "gateLeafOpeningSupport0To1": null,
      "downstreamPlumeSupport0To1": 0.8
    }
  }
}
```

両端のオレンジ回転灯が見えた場合だけ開放の正証拠とする。見えない、または画像にない場合は不明であり、閉鎖証拠にしない。

## 実行例

```sh
python tools/stage20_gate_configuration_candidate_estimator_v1.py \
  --observation /path/to/observation.json \
  --image-evidence /path/to/image-evidence.json \
  --previous-report /path/to/previous-candidate.json \
  --output /path/to/gate-candidate.json
```

## 限界

これは門別開度、実門状態、教師ラベルを生成しない。既存の開門順序は弱い順位補助に限り、実運用順序の正解として扱わない。物理採用には門別開度記録または十分な人手確認イベントによる較正・独立検証が必要である。
