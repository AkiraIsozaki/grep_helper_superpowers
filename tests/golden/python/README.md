# Python ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件を含む。**間接追跡なし**（Python ハンドラは `batch_track_indirect` を持たない）。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| 変数代入 | sample.py | 3 | 1 |
| デコレータ | sample.py | 6 | 1 |
| 条件判定 | sample.py | 8 | 1 |
| 関数引数 | sample.py | 10 | 1 |
| return文 | sample.py | 15 | 1 |
| その他 | sample.py | 18 | 1 |
| 合計（直接） | 1 ファイル | | 6 |

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 6 | sample.py の各行 |

注: Python ハンドラは間接追跡を実装していない（spec §Python に準拠）。

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全6件（直接のみ） |

## ファイル一覧（src/ 配下、1 ファイル）
- sample.py — 6使用タイプを単一モジュールに集約

## pytest 収集除外
本ディレクトリは `tests/golden/` 配下にあり、`pytest.ini` の `norecursedirs = tests/golden` により pytest 収集から除外される。`python -m pytest tests/ -q --collect-only 2>&1 | grep "tests/golden"` が無結果（または "no collect from golden, OK"）であれば設定は有効。

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_python.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの Python ファイル（`.py`）を追加
2. ```bash
   ( cd tests/golden/python/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/python/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_python.py \
     --source-dir tests/golden/python/src \
     --input-dir tests/golden/python/inputs \
     --output-dir /tmp/kpi_bootstrap_python
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_python/<文言>.tsv tests/golden/python/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang python` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に python が追加された後)
