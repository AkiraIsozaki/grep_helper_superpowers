# Kotlin ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件、間接参照（const val 経由）を1件含む。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| const定数定義 | Sample.kt | 4 | 1 |
| アノテーション | Sample.kt | 7 | 1 |
| 変数代入 | Sample.kt | 10 | 1 |
| 条件判定 | Sample.kt | 11 | 1 |
| 関数引数 | Sample.kt | 17 | 1 |
| return文 | Sample.kt | 22 | 1 |
| その他 | Sample.kt | 25 | 1 |
| 合計（直接） | 1 ファイル | | 7 |

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 7 | Sample.kt の各行 |
| 間接（const val 経由） | 1 | Sample.kt:14 で `Constants.STATUS_CODE` を if 条件に使用（Sample.kt:4 の定義を起点） |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全8件（直接7 + 間接1） |
| STATUS_CODE.grep | STATUS_CODE | `const val STATUS_CODE = "777"` の定数名検索ケース。全3件（直接2 + 間接1） |

## ファイル一覧（src/ 配下、1 ファイル）
- Sample.kt — 7使用タイプを単一クラスに集約。`Constants.STATUS_CODE` を起点とした const val 経由の間接参照を内包

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_kotlin.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの Kotlin ファイル（`.kt` / `.kts`）を追加
2. ```bash
   ( cd tests/golden/kotlin/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/kotlin/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_kotlin.py \
     --source-dir tests/golden/kotlin/src \
     --input-dir tests/golden/kotlin/inputs \
     --output-dir /tmp/kpi_bootstrap_kotlin
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_kotlin/<文言>.tsv tests/golden/kotlin/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang kotlin` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に kotlin が追加された後)
