# Stage 18 production-mesh pilot gate

本段階は，50,333セルのproduction meshへ浅水方程式kernelを接続する前後の計算量，数値安定性，保存性を，小規模な段階試験で測定するための契約である．

## 段階

1．smoke：1 case，最大20 step
2．screening：4 case，最大100 step
3．pilot：16 case，最大500 step

各段階で，NaN，負水深，CFL，質量保存誤差，wall time，peak memory，失敗caseを記録する．上位段階への移行は自動ではない．

## 厳密に担保する事項

- 正解水面679,791画素と50,333-cell meshを変更しない
- NaNおよび負水深を許容しない
- 失敗caseを補間または成功値で置換しない
- 完了率95％未満を合格としない
- full 64-case runを自動開始しない
- public simulatorとlegacy流れ計算を変更しない

## 担保しない事項

- 推論された河床，粗度，境界流量，魚道，河口堰操作の実測真値性
- pilot結果の物理Validation
- 絶対流速および絶対水位の正確性

16-case pilotが合格した後にのみ，64-case本計算の実施可否を明示的に判断する．
