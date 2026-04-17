# 純Cアナライザー ＋ Pro*C 混在対応 設計仕様

**日付:** 2026-04-17  
**対象モジュール:** `analyze_c.py`（新規）、`analyze_proc.py`（変更）

---

## 背景・課題

grep 結果ファイルには `.c` ファイルと `.pc`（Pro*C）ファイルのヒットが**混在する**ことがある。  
現状の `analyze_proc.py` はすべての行を Pro*C パターンで分類するため、`.c` ファイルの行で以下の問題が発生する：

1. **分類の誤検知**: EXEC SQL は `.c` に存在しないため影響は小さいが、分類の意味論がずれる
2. **追跡漏れ**: `track_define` が `.pc/.h` しかスキャンしないため、`.c` ファイル内のマクロ使用箇所が追跡されない

---

## アーキテクチャ

```
analyze_c.py          純C専用アナライザー（単独 CLI としても動作）
      ↓ import
analyze_proc.py       拡張子ベース・ディスパッチャー兼 Pro*C アナライザー
      ↓ 共通
analyze_common.py     GrepRecord, write_tsv など（変更なし）
```

循環参照なし：`analyze_c` → `analyze_common`、`analyze_proc` → `analyze_c` → `analyze_common`

---

## analyze_c.py 仕様

### 使用タイプ分類（`classify_usage_c`）

優先度順に評価し、最初にマッチしたものを返す。

| 優先度 | マッチ条件 | 使用タイプ |
|--------|-----------|-----------|
| 1 | `#\s*define\b` | `#define定数定義` |
| 2 | `\bif\s*\(` / `strcmp(` / `strncmp(` / `switch\s*\(` | `条件判定` |
| 3 | `\breturn\b` | `return文` |
| 4 | C型名 + 変数名 + `=`（`char`/`int`/`short`/`long` 等） | `変数代入` |
| 5 | `識別子(` | `関数引数` |
| 6 | それ以外 | `その他` |

Pro*C との違いは「EXEC SQL文」パターンが存在しない点のみ。

### 変数名抽出（`extract_variable_name_c`）

C型宣言から変数名を抽出する。`analyze_proc.py` の `extract_variable_name_proc` と同じロジック。

### `extract_define_name`

`analyze_proc.py` と同じ実装を `analyze_c.py` 内に独立して持つ（循環参照を避けるため）。将来的に共通化が必要になれば `analyze_common.py` へ移動する。

### 間接参照追跡

- **`track_define`**: `src_dir` 配下の `.c/.h/.pc` すべてをスキャン（Pro*C と共通スコープ）
- **`track_variable`**: 同一ファイル内をスキャン（拡張子問わず）

### CLI

```
python analyze_c.py --source-dir <dir> --input-dir <dir> --output-dir <dir>
```

純Cプロジェクト専用として単独動作する。

---

## analyze_proc.py 変更仕様

### 拡張子ベース・ディスパッチ（`process_grep_file` 内）

各 grep 行のファイルパス拡張子を確認し、分類関数を切り替える：

| 拡張子 | 使用する分類関数 |
|--------|----------------|
| `.pc` | `classify_usage_proc`（EXEC SQL 含む） |
| `.c`、`.h` | `classify_usage_c`（純C） |
| それ以外 | `classify_usage_proc`（デフォルト・後方互換） |

`classify_usage_c` は `analyze_c` から import する。

### `track_define` の変更

| 変更前 | 変更後 |
|--------|--------|
| `.pc` + `.h` をスキャン | `.c` + `.h` + `.pc` をスキャン |

---

## テスト方針

### analyze_c.py ユニットテスト（`tests/test_c_analyzer.py` 新規）

- `classify_usage_c`: 各使用タイプ（6種）を網羅
- `extract_variable_name_c`: 型宣言からの変数名抽出
- `write_tsv`: BOM・ソート順（`analyze_common` 経由で実質共通テスト）

### analyze_c.py E2E テスト

```
tests/c/src/sample.c       純Cソースフィクスチャ
tests/c/input/TARGET.grep  grep 結果フィクスチャ
tests/c/expected/TARGET.tsv 期待 TSV（ツール実行で生成→目視確認）
```

### analyze_proc.py 混在対応テスト（`test_analyze_proc.py` に追記）

- `.c` 行 → `classify_usage_c` で分類されること
- `.pc` 行 → `classify_usage_proc` で分類されること
- `track_define` が `.c/.h/.pc` をスキャンすること
- 混在 E2E: `tests/proc/input/MIXED.grep`（`.c` と `.pc` 混在）＋ 期待 TSV

---

## 変更ファイル一覧

| 操作 | ファイル | 内容 |
|------|---------|------|
| 新規作成 | `analyze_c.py` | 純Cアナライザー |
| 新規作成 | `tests/test_c_analyzer.py` | ユニットテスト |
| 新規作成 | `tests/c/src/sample.c` | E2E フィクスチャ |
| 新規作成 | `tests/c/input/TARGET.grep` | E2E フィクスチャ |
| 新規作成 | `tests/c/expected/TARGET.tsv` | E2E 期待 TSV |
| 新規作成 | `tests/proc/input/MIXED.grep` | 混在 E2E フィクスチャ |
| 新規作成 | `tests/proc/expected/MIXED.tsv` | 混在 E2E 期待 TSV |
| 新規作成 | `tests/proc/src/sample_c.c` | 混在 E2E 用 C ソース |
| 変更 | `analyze_proc.py` | 拡張子ディスパッチ + track_define 拡張 |
| 変更 | `tests/test_analyze_proc.py` | 混在テスト追加 |
