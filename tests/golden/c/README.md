# C ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件、間接参照（#define / 変数）を1件ずつ含む。本ディレクトリは Task 18 で他10言語に展開する際の雛形となる。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数 |
|---|---|---|---|
| #define定数定義 | header.h | 3 | 1 |
| 条件判定 | sample.c | 5 | 1 |
| 変数代入 | sample.c | 12 | 1 |
| 関数引数 | sample.c | 13 | 1 |
| その他 | sample.c | 16 | 1 |
| 合計 | 2 ファイル | | 5 |

注: `return 1;` / `return 0;` の行は文字列リテラル "777" を含まないため grep にヒットしない。
return文 タイプは本スモークセットでは出現しない（`return "777"` のような形を意図しないシンプルな C コードのため）。

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 4 | header.h:3, sample.c:5/12/16 |
| 間接（変数経由） | 1 | sample.c:13 で `local` を関数引数として渡す（sample.c:12 の代入を起点） |
| 間接（#define経由） | 0 | サンプル内で `CODE` の参照箇所はないが、`CODE.grep` は `#define CODE "777"` 自体（直接の定数定義）を捕捉 |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全5件 |
| CODE.grep | CODE | `#define CODE "777"` の定数名検索ケース。 #define 定数定義そのものを直接ヒット |

## ファイル一覧（src/ 配下、2 ファイル）
- header.h — `#define CODE "777"` 1 件
- sample.c — 条件判定・変数代入・関数引数（間接）・その他 各 1 件

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_c.py` の出力をそのまま採用している（dedup なし）。
これは「bootstrap」「現状を保つ」サンプル的位置づけで、後続の改造で差分が生じたら検出するベースライン。
KPI 計測の compare() は `(ファイルパス, 行番号, 参照種別)` を2次キーとしてマッチングするため、
重複行があってもデデュープせずに突合できる。

## サンプル追加手順
1. `src/` に新パターンの C ファイル（`.c` / `.h`）を追加
2. ```bash
   ( cd tests/golden/c/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/c/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_c.py \
     --source-dir tests/golden/c/src \
     --input-dir tests/golden/c/inputs \
     --output-dir /tmp/kpi_bootstrap_c
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_c/<文言>.tsv tests/golden/c/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang c` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に c が追加された後)

## 注意
Task 17 時点では `LANG_SPECS` に c がまだ無いため `python scripts/measure_kpi.py --lang c` は exit 1（未対応 lang）になる。これは正常。Task 19 で c を追加した後で動作確認する。
