# PL/SQL ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件を含む。間接追跡（クロスファイル）も B-1 で対応。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| 定数/変数宣言 | sample.pkb | 2, 12 | 2 |
| カーソル定義 | sample.pkb | 3 | 1 |
| 条件判定 | sample.pkb | 6 | 1 |
| INSERT/UPDATE値 | sample.pkb | 7 | 1 |
| WHERE条件 | sample.pkb | 8 | 1 |
| EXCEPTION処理 | sample.pkb | 13 | 1 |
| その他 | sample.pkb | 16 | 1 |
| 合計（直接） | 1 ファイル | | 8 |

注: EXCEPTION処理 タイプは `\bRAISE\b` パターンで判定されるため、`RAISE_APPLICATION_ERROR(...)` のようなアンダースコア付き呼び出しは `\b` 境界が成立せず *その他* に落ちる。スモークでは単独の `RAISE error_777;` を採用。

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 8 | sample.pkb の各行 |
| 間接 | 3 | other.pkb の各行 |

## 間接参照サンプル

- `src/other.pkb`: `sample.pkb` の `c_default_code` を別パッケージから `sample_pkg.c_default_code` 形式で参照する。
  クロスファイル間接追跡（B-1）の検証用。
- 期待行: `expected/777.tsv` に間接行 3 件あり（other.pkb の IF 行 / INSERT 値行 / RETURN 行）。

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全8件（直接のみ） |

## ファイル一覧（src/ 配下、1 ファイル）
- sample.pkb — 7使用タイプを単一パッケージボディに集約

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_plsql.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの PL/SQL ファイル（`.pkb` / `.pks` / `.prc` / `.fnc` / `.trg` / `.pls` / `.pck`）を追加
2. ```bash
   ( cd tests/golden/plsql/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/plsql/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_plsql.py \
     --source-dir tests/golden/plsql/src \
     --input-dir tests/golden/plsql/inputs \
     --output-dir /tmp/kpi_bootstrap_plsql
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_plsql/<文言>.tsv tests/golden/plsql/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang plsql` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に plsql が追加された後)
