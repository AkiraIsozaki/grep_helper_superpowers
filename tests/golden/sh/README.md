# Shell ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件、同一ファイル内のシェル変数経由間接参照を1件含む。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| 環境変数エクスポート | sample.sh | 2 | 1 |
| 変数代入 | sample.sh | 3 | 1 |
| 条件判定 | sample.sh | 4 | 1 |
| echo/print出力 | sample.sh | 5 | 1 |
| コマンド引数 | sample.sh | 6 | 1 |
| その他 | sample.sh | 8 | 1 |
| 合計（直接） | 1 ファイル | | 6 |

注: コマンド引数 タイプは `^\s*\w+\s+\S` で判定されるため、コマンド名が `\w+` で始まる必要がある（`/usr/bin/notify` は不可、`notify_cmd` は可）。

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 6 | sample.sh:2/3/4/5/6/8 |
| 間接（変数経由） | 1 | sample.sh:4 で `$local_code` を if 条件に使用（sample.sh:3 の代入を起点） |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全7件（直接6 + 間接1） |

## ファイル一覧（src/ 配下、1 ファイル）
- sample.sh — 6使用タイプを単一スクリプトに集約。`local_code` を起点とした同一ファイル内間接参照を内包

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_sh.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの シェルスクリプト（`.sh` / `.bash`）を追加
2. ```bash
   ( cd tests/golden/sh/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/sh/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_sh.py \
     --source-dir tests/golden/sh/src \
     --input-dir tests/golden/sh/inputs \
     --output-dir /tmp/kpi_bootstrap_sh
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_sh/<文言>.tsv tests/golden/sh/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang sh` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に sh が追加された後)
