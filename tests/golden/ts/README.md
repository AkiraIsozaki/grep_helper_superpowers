# TypeScript / JavaScript ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件を含む。間接追跡（クロスファイル）も B-1 で対応。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| const定数定義 | sample.ts | 1 | 1 |
| デコレータ | sample.ts | 3 | 1 |
| 変数代入(let/var) | sample.ts | 6 | 1 |
| 条件判定 | sample.ts | 7 | 1 |
| 関数引数 | sample.ts | 10 | 1 |
| return文 | sample.ts | 15 | 1 |
| その他 | sample.ts | 18 | 1 |
| 合計（直接） | 1 ファイル | | 7 |

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 7 | sample.ts の各行 |
| 間接 | 3 | service.ts / worker.ts の各行 |

## 間接参照サンプル

- `src/service.ts` / `src/worker.ts`: `sample.ts` の `STATUS_CODE` を別ファイルから参照する。
  クロスファイル間接追跡（B-1）の検証用。
- 期待行: `expected/777.tsv` に間接行 3 件あり（service.ts の import 行 / if 行、worker.ts の logValue 行）。

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全7件（直接のみ） |

## ファイル一覧（src/ 配下、1 ファイル）
- sample.ts — 7使用タイプを単一クラスに集約

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_ts.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの TypeScript / JavaScript ファイル（`.ts` / `.tsx` / `.js` / `.jsx`）を追加
2. ```bash
   ( cd tests/golden/ts/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/ts/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_ts.py \
     --source-dir tests/golden/ts/src \
     --input-dir tests/golden/ts/inputs \
     --output-dir /tmp/kpi_bootstrap_ts
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_ts/<文言>.tsv tests/golden/ts/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang ts` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に ts が追加された後)
