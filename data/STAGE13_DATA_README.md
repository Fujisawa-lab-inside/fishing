# Stage 13 authoritative water data

このディレクトリには，承認済みの唯一の正解水面を格納する．

## 必須ファイル

`onga_unified_spec_v480_candidate_r2.json`

## 必須条件

- `version` は `v4.8.0-candidate-r2`
- `waterDomain.width` は画像幅と一致する
- `waterDomain.height` は画像高と一致する
- `waterDomain.rows` は行単位run-length encodingである
- 水面画素数は `679791`
- `acceptanceCriteria.runtimeDomainDifferenceCells` は `0`
- `acceptanceCriteria.controlPointSemanticMismatchCount` は `0`
- 魚道座標は水面内である

## 検証

```bash
node tools/validate_stage13_data.mjs data/onga_unified_spec_v480_candidate_r2.json
```

検証に合格しないデータをruntimeへ接続してはならない．

## runtime接続

`onga_stage13_runtime.js` が本ファイルを取得し，`OngaUnifiedAuthority.water.contains(x, y)` を生成する．

PC版・スマホ版は通常URLでは従来実装を維持し，`?stage13=1` を付けた場合だけStage 13統合経路を有効化する．この方式により，mainへ統合する前に既存公開版への影響なしで検証できる．