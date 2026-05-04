# Perl ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件を含む。間接追跡（クロスファイル）も B-1 で対応。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| use constant定義 | Sample.pm | 4 | 1 |
| 変数代入 | Sample.pm | 8 | 1 |
| 条件判定 | Sample.pm | 9 | 1 |
| print/say出力 | Sample.pm | 12 | 1 |
| 関数引数 | Sample.pm | 13 | 1 |
| その他 | Sample.pm | 17 | 1 |
| 合計（直接） | 1 ファイル | | 6 |

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 6 | Sample.pm の各行 |
| 間接 | 3 | Service.pm / Worker.pm の各行 |

## 間接参照サンプル

- `src/Service.pm` / `src/Worker.pm`: `Sample.pm` の `STATUS_CODE` を別モジュールから参照する。
  クロスファイル間接追跡（B-1）の検証用。
- 期待行: `expected/777.tsv` に間接行 3 件あり（Service.pm の if 行 / use 行、Worker.pm の do_notify 行）。

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全6件（直接のみ） |

## ファイル一覧（src/ 配下、1 ファイル）
- Sample.pm — 6使用タイプを単一モジュールに集約

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_perl.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの Perl ファイル（`.pl` / `.pm`）を追加
2. ```bash
   ( cd tests/golden/perl/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/perl/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_perl.py \
     --source-dir tests/golden/perl/src \
     --input-dir tests/golden/perl/inputs \
     --output-dir /tmp/kpi_bootstrap_perl
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_perl/<文言>.tsv tests/golden/perl/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang perl` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に perl が追加された後)
