# SeaBass local development instructions

このリポジトリでは `docs/project/SIMULATOR_EXPLORATION_POLICY.md` を開発段階の正本方針とする。

## Default behavior

- 実装要求は、原則として探索 A（水理）、B（地形・入力）、C（釣り機能・表示）のどれか一つへ割り当てる。
- 探索中は短い `edit -> run -> inspect` を優先し、対象 smoke test と診断出力まで自律的に完了する。
- 通常の局所実装・局所試験・表示確認では、ユーザー操作を求めない。
- 探索案ごとに新しい authority、activation、provenance chain、SHA 固定 package、全回帰試験を作らない。
- 既存の未関連変更と未追跡ファイルを保持し、探索に必要なファイルだけを変更する。
- Mac では短時間 canary と少数比較を行い、長時間・大量 sweep・Monte Carlo・高解像度処理だけを YODA 候補にする。

## Safety and claims

- 負水深、非有限値、重大な質量収支違反、許可していない逆流などの hard safety condition は探索中も fail closed とする。
- 合成、診断、未較正、物理候補、予測、公開版を明確に区別する。
- 実観測不足は探索を止めないが、physical validation、mesh adoption、forecast、fishing decision、GUI promotion、release を許可しない。
- YODA 実行は既存 runbook と明示承認に従い、prepared / submitted / running / fetched / validated を区別する。

## Integration trigger

同一 scenario と seed で比較し、有利で、hard safety violation がなく、反例条件でも利点が残る候補だけを統合系列へ送る。統合候補が選ばれた後に限り、詳細回帰、ADR、SHA 固定、YODA 長時間試験、来歴監査、公開判定を追加する。
