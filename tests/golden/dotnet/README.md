# C# / VB.NET ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

各使用タイプ最低1件、間接参照（const×1 + static readonly×1）を含む。`.cs` と `.vb` の両拡張子を含む。

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数（直接） |
|---|---|---|---|
| 定数定義(Const/readonly) | Sample.cs | 6, 7 | 2 |
| 定数定義(Const/readonly) | Helper.vb | 2 | 1 |
| 属性(Attribute) | Sample.cs | 3 | 1 |
| 変数代入 | Sample.cs | 11 | 1 |
| 条件判定 | Sample.cs | 12 / Helper.vb | 5 | 2 |
| メソッド引数 | Sample.cs | 24 | 1 |
| return文 | Sample.cs | 30 | 1 |
| その他 | Sample.cs | 33 / Helper.vb | 12 | 2 |
| 合計（直接） | 2 ファイル（cs + vb） | | 11 |

## 参照種別シナリオ
| シナリオ | 件数 | 配置 |
|---|---|---|
| 直接 | 11 | Sample.cs / Helper.vb の各行 |
| 間接（const 経由） | 1 | Sample.cs:16 で `STATUS_CODE` を if 条件に使用（Sample.cs:6 の const 定義を起点） |
| 間接（static readonly 経由） | 1 | Sample.cs:20 で `DEFAULT_CODE` を if 条件に使用（Sample.cs:7 の static readonly 定義を起点） |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅。全13件（直接11 + 間接2） |

## ファイル一覧（src/ 配下、2 ファイル）
- Sample.cs — 7使用タイプを集約。const + static readonly を起点とした間接参照を内包
- Helper.vb — VB.NET 側の使用タイプ（`Public Const ... As String`）も網羅

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

本ディレクトリの expected TSV は `analyze_dotnet.py` の出力をそのまま採用している（dedup なし）。

## サンプル追加手順
1. `src/` に新パターンの C# / VB.NET ファイル（`.cs` / `.vb`）を追加
2. ```bash
   ( cd tests/golden/dotnet/src && grep -rn "<文言>" . ) | sed 's|^\./||' > tests/golden/dotnet/inputs/<文言>.grep
   ```
3. ```bash
   python analyze_dotnet.py \
     --source-dir tests/golden/dotnet/src \
     --input-dir tests/golden/dotnet/inputs \
     --output-dir /tmp/kpi_bootstrap_dotnet
   ```
4. 人間レビュー後 `expected/` に確定 (`cp /tmp/kpi_bootstrap_dotnet/<文言>.tsv tests/golden/dotnet/expected/<文言>.tsv`)
5. `python scripts/measure_kpi.py --lang dotnet` で網羅率 100% を確認 (Task 19 で `LANG_SPECS` に dotnet が追加された後)
