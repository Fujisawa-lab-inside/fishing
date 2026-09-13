# 河口堰カメラの水滴低減 v1

## 目的

固定カメラの10分間隔画像から、レンズに付いた水滴の影響を低コストで弱める。原画像は変更せず、直近の奇数枚（標準7枚）の画素別時間中央値と時間分散画像を派生成果物として作る。

## 採用理由

- 同じ場所に水滴が残らない限り、過半数の画像に背景が写れば時間中央値で復元できる。
- 学習済み生成モデルを使わないため、未観測の水門輪郭をそれらしく生成する危険を抑えられる。
- CPUで短時間に処理でき、YODAのGPUを必要としない。

## 使用境界

- 時間中央値は人間の視認補助および将来モデルの補助入力候補である。
- 原画像、入力SHA、出力SHA、時間分散を必ず保持する。
- 対象窓の途中で水門状態が変化した可能性がある場合、時間中央値を開閉状態の証拠や教師ラベルにしない。
- 最終的な門別推論では、最新原画像、時間中央値、時間分散、画像品質、流量・水位・潮位の時系列を別入力として扱う。

## 実行例

```sh
python3 tools/stage20_yoda_gate_camera_temporal_derain_v1.py \
  --collection-root /home/swarm/work/seabass_observations/gate-multimodal-v1 \
  --count 7 \
  --output /home/swarm/work/seabass_observations/gate-multimodal-v1/derived/gate-camera-temporal-derain-v1/latest
```
