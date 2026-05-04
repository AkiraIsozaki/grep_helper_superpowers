# Pro*C ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件、間接参照（#define / 変数）を1件ずつ含む。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数 |
|---|---|---|---|
| #define定数定義 | sample.pc | 3 | 1 |
| 変数代入 | sample.pc | 6 | 1 |
| EXEC SQL文 | sample.pc | 10 | 1 |
| 条件判定 | sample.pc | 11, 14 | 2 |
| 関数引数 | sample.pc | 17 | 1 |
| return文 | sample.pc | 22 | 1 |
| その他 | sample.pc | 25 | 1 |
| 合計 | 1 ファイル + ヘッダ1 | | 7 |

注: `EXEC SQL SELECT ... :status_code ... '777'` を追加し、EXEC SQL文 タイプのカバレッジを実現。
また `if (strcmp(input, STATUS_CODE) == 0)` を追加し、#define 経由の間接参照シナリオを実現。

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 7 | sample.pc:3/6/10/11/17/22/25 |
| 間接（変数経由） | 1 | sample.pc:10 で `status_code` を EXEC SQL の :ホスト変数として参照（sample.pc:6 の代入を起点） |
| 間接（#define経由） | 1 | sample.pc:14 で `STATUS_CODE` マクロを if 条件に使用（sample.pc:3 の定義を起点） |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全9件（直接7 + 間接2） |
| STATUS_CODE.grep | STATUS_CODE | `#define STATUS_CODE "777"` の定数名検索ケース。全3件（直接2 + 間接1） |

## ファイル一覧（src/ 配下、2 ファイル）
- header.h — Pro*C smoke 用の宣言ヘッダ（"777" を含まない）
- sample.pc — #define定数定義・変数代入・EXEC SQL文(間接)・条件判定(直接+#define経由)・関数引数・return文・その他 各 1 件

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_proc.py` の出力をそのまま採用している（dedup なし）。
これは「bootstrap」「現状を保つ」サンプル的位置づけで、後続の改造で差分が生じたら検出するベースライン。

## サンプル追加手順
1. `src/` に新パターンの Pro*C ファイル（`.pc` / `.h`）を追加
2. ```bash
   ( cd tests/golden/proc/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/proc/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_proc.py \
     --source-dir tests/golden/proc/src \
     --input-dir tests/golden/proc/inputs \
     --output-dir /tmp/kpi_bootstrap_proc
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_proc/<文言>.tsv tests/golden/proc/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang proc` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に proc が追加された後)

## 注意
Task 18-1 時点では `LANG_SPECS` に proc がまだ無いため `python scripts/measure_kpi.py --lang proc` は exit 1（未対応 lang）になる。これは正常。Task 19 で proc を追加した後で動作確認する。
