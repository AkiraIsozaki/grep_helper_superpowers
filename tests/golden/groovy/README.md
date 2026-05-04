# Groovy ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件、間接参照（static final + フィールド + getter + setter）すべての段階を含む。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| アノテーション | Sample.groovy | 3 | 1 |
| static final定数定義 | Sample.groovy | 5 | 1 |
| 変数代入 | Sample.groovy | 6, 17 | 2 |
| 条件判定 | Sample.groovy | 18 | 1 |
| メソッド引数 | Sample.groovy | 24 / Caller.groovy | 7 | 2 |
| return文 | Sample.groovy | 29 | 1 |
| その他 | Sample.groovy | 32 | 1 |
| 合計（直接） | 2 ファイル | | 9 |

注: フィールドの間接追跡を発火させるには `_CLASS_FIELD_PAT` に合致する宣言形式（`private`/`protected`/`public` 修飾子付き、または `def`）が必要。`String type = ...` のような型のみの宣言では発火しないため、スモークでは `public String type = "777"` を採用。

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 9 | Sample.groovy 各行 + Caller.groovy:7 |
| 間接（static final 経由） | 1 | Sample.groovy:21 で `STATUS_CODE` を if 条件に使用（Sample.groovy:5 を起点） |
| 間接（フィールド経由） | 2 | Sample.groovy:9, 13 で `this.type` を参照（Sample.groovy:6 を起点） |
| 間接（getter経由） | 2 | Caller.groovy:6 で `s.getType()`、Sample.groovy:8 の getter 定義行（Sample.groovy:6 を起点） |
| 間接（setter経由） | 2 | Caller.groovy:7 で `s.setType("777")`、Sample.groovy:12 の setter 定義行（Sample.groovy:6 を起点） |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全16件（直接9 + 間接7） |

## ファイル一覧（src/ 配下、2 ファイル）
- Sample.groovy — 7使用タイプ + static final + 公開フィールド + getter/setter 定義
- Caller.groovy — 別クラスから getter/setter を呼び出す側

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_groovy.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの Groovy ファイル（`.groovy` / `.gvy`）を追加
2. ```bash
   ( cd tests/golden/groovy/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/groovy/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_groovy.py \
     --source-dir tests/golden/groovy/src \
     --input-dir tests/golden/groovy/inputs \
     --output-dir /tmp/kpi_bootstrap_groovy
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_groovy/<文言>.tsv tests/golden/groovy/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang groovy` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に groovy が追加された後)
