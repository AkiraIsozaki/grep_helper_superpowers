# Oracle SQL ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件、間接参照（同一ファイル内 PL/SQL 変数経由）を1件以上含む。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| 定数・変数定義 | sample.sql | 2, 3, 12 | 3 |
| SELECT/INTO | sample.sql | 9 | 1 |
| その他 | sample.sql | 6, 21 | 2 |
| INSERT/UPDATE値 | sample.sql | 7, 8 | 2 |
| 比較・DECODE | sample.sql | 11 | 1 |
| WHERE条件 | sample.sql | 14 | 1 |
| 例外・エラー処理 | sample.sql | 17 | 1 |
| 合計（直接） | 1 ファイル | | 11 |

注: SQL 分類器は `WHERE` パターンが `INSERT/UPDATE` よりも先に評価されるため、INSERT/UPDATE値 タイプを得るには `WHERE` 句を含まない INSERT/UPDATE 文を別途配置する必要がある。

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 11 | sample.sql の各行 |
| 間接（PL/SQL 変数経由） | 12 | sample.sql:2 / sample.sql:12 で定義された `v_status_code` を同一ファイル内で参照 |

注: SQL の `batch_track_indirect` は同一ファイルスコープでのみ追跡し、対称的に変数定義行同士もお互いの「間接」として再カウントされる（行2 と行12 が両方とも `v_status_code := '777'` と評価される）。

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全23件（直接11 + 間接12） |

## ファイル一覧（src/ 配下、1 ファイル）
- sample.sql — 7使用タイプを単一スクリプトに集約。`v_status_code` を起点とした間接参照シナリオを内包

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_sql.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの SQL ファイル（`.sql`）を追加
2. ```bash
   ( cd tests/golden/sql/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/sql/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_sql.py \
     --source-dir tests/golden/sql/src \
     --input-dir tests/golden/sql/inputs \
     --output-dir /tmp/kpi_bootstrap_sql
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_sql/<文言>.tsv tests/golden/sql/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang sql` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に sql が追加された後)
