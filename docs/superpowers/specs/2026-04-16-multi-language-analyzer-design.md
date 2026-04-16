# 多言語対応 grep結果アナライザー 設計ドキュメント

**作成日**: 2026-04-16
**対象**: analyze.py の多言語拡張（Oracle SQL / Pro*C / シェルスクリプト）

---

## 目的

プロジェクト内の特定の文言（文字列値）を転用・削除しようとする開発者が、「この値は今どこでどのように使われているか」を言語横断で完全に把握できるようにする。

grep結果の各ヒット行を、そのファイル拡張子から自動的に言語判別し、言語固有の「使用タイプ」に分類する。さらに値が変数に代入されている場合は間接参照も追跡する。

---

## アーキテクチャ: 言語ストラテジーパターン（案B）

### ディレクトリ構成

```
analyze.py                ← CLIエントリーポイント + 共通処理
analyzers/
  __init__.py
  base.py                 ← LanguageAnalyzer 抽象基底クラス
  java.py                 ← 既存Javaロジックを移行
  sql.py                  ← Oracle SQL (11g)
  proc.py                 ← Pro*C
  shell.py                ← BASH / CSH / TCSH
  registry.py             ← 拡張子 → アナライザーのマッピング
tests/
  test_sql_analyzer.py
  test_proc_analyzer.py
  test_shell_analyzer.py
  fixtures/               ← 各言語のサンプルソースファイル
```

### 処理フロー

```
analyze.py
  ↓ .grep ファイルを読む（既存）
  ↓ 各行: parse_grep_line() → filepath の拡張子を取得
  ↓ registry.get_analyzer(ext) → 対応する LanguageAnalyzer を取得
  ↓ analyzer.classify_usage(code, filepath, lineno, source_dir, stats)
  ↓ analyzer.track_indirect(records, source_dir, stats) → 間接参照レコード
  ↓ write_tsv() → output/*.tsv（既存・共通）
```

### 言語判別

各 grep ヒット行の `filepath` 拡張子から自動判別する。1つの `.grep` ファイルに複数言語のヒット行が混在することを前提とする。

---

## analyze.py の共通基盤（変更なし・流用）

- `parse_grep_line()` — grep行パース
- `write_tsv()` — UTF-8 BOM付きTSV出力
- `ProcessStats` — 処理統計
- `GrepRecord` — データモデル（カラム構成は言語問わず共通）
- `main()` / `build_parser()` — CLI（`--source-dir` を全言語で共用）

---

## analyzers/base.py: 抽象基底クラス

```python
class LanguageAnalyzer(ABC):
    @abstractmethod
    def classify_usage(
        self,
        code: str,
        filepath: str,
        lineno: int,
        source_dir: Path,
        stats: ProcessStats,
    ) -> str:
        """grep ヒット行の使用タイプを返す。"""
        ...

    @abstractmethod
    def track_indirect(
        self,
        records: list[GrepRecord],
        source_dir: Path,
        stats: ProcessStats,
    ) -> list[GrepRecord]:
        """直接参照レコードから間接参照レコードを生成して返す。"""
        ...
```

---

## analyzers/registry.py: 拡張子マッピング

```python
EXTENSION_MAP = {
    ".java": JavaAnalyzer,
    ".sql":  SqlAnalyzer,
    ".pks":  SqlAnalyzer,
    ".pkb":  SqlAnalyzer,
    ".prc":  SqlAnalyzer,
    ".fnc":  SqlAnalyzer,
    ".trg":  SqlAnalyzer,
    ".vw":   SqlAnalyzer,
    ".pc":   ProcAnalyzer,
    ".h":    ProcAnalyzer,
    ".sh":   ShellAnalyzer,
    ".csh":  ShellAnalyzer,
    ".tcsh": ShellAnalyzer,
    ".ksh":  ShellAnalyzer,
}

def get_analyzer(ext: str) -> LanguageAnalyzer:
    """拡張子に対応するアナライザーを返す。未知の拡張子は UnknownAnalyzer。"""
    return EXTENSION_MAP.get(ext.lower(), UnknownAnalyzer())
```

---

## analyzers/sql.py: Oracle SQL (11g)

### 対象拡張子
`.sql`, `.pks`, `.pkb`, `.prc`, `.fnc`, `.trg`, `.vw`

### 使用タイプ分類（優先度順）

| 使用タイプ | 判定パターン |
|-----------|------------|
| 例外・エラー処理 | `RAISE_APPLICATION_ERROR`, `EXCEPTION\b` |
| 定数・変数定義 | `:=`, `CONSTANT\b` |
| WHERE条件 | `\bWHERE\b`, `\bAND\b.*=`, `\bOR\b.*=` |
| 比較・DECODE | `\bDECODE\s*\(`, `\bCASE\b.*\bWHEN\b` |
| INSERT/UPDATE値 | `\bINSERT\b`, `\bUPDATE\b.*\bSET\b`, `\bVALUES\s*\(` |
| SELECT/INTO | `\bSELECT\b`, `\bINTO\b` |
| その他 | 上記に該当しない |

### 間接参照追跡

- 「定数・変数定義」タイプのレコードから変数名を抽出（`:=` の左辺をトリム）
- 同一ファイル内を全行スキャンし、変数名が出現する行を追跡
- 各出現行を再分類して間接参照レコードとして追加
- スコープ: 同一ファイル（PL/SQLブロック・プロシージャ・パッケージ単位）

---

## analyzers/proc.py: Pro*C

### 対象拡張子
`.pc`, `.h`（`.h` は EXEC SQL を含む行のみ実質的にヒット）

### 使用タイプ分類（優先度順）

| 使用タイプ | 判定パターン |
|-----------|------------|
| 文字列定数定義 | `#define\b`, `const\s+char`, `\[\s*\]` |
| EXEC SQL WHERE条件 | `\bEXEC\s+SQL\b.*\bWHERE\b` |
| EXEC SQL INSERT/UPDATE値 | `\bEXEC\s+SQL\s+(INSERT\|UPDATE)\b` |
| ホスト変数代入 | `strcpy\s*\(`, `strncpy\s*\(`, `sprintf\s*\(`, `=\s*"` |
| 比較・条件分岐（C） | `strcmp\s*\(`, `strncmp\s*\(`, `\bif\s*\(` |
| その他 | 上記に該当しない |

### 変数名抽出ルール

| パターン | 変数名取得方法 |
|---------|------------|
| `strcpy(hv, "VALUE")` | 第1引数 |
| `strncpy(hv, "VALUE", N)` | 第1引数 |
| `hv = "VALUE"` | `=` の左辺 |
| `#define NAME "VALUE"` | `#define` 直後の識別子 |

### 間接参照追跡

- 「ホスト変数代入」「文字列定数定義」タイプから変数名を抽出
- 同一関数スコープ内（`{` ～ `}` の対応で判定）を追跡
- `#define` 定数はファイル全体を追跡

---

## analyzers/shell.py: シェルスクリプト（BASH / CSH / TCSH）

### 対象拡張子
`.sh`, `.csh`, `.tcsh`, `.ksh`

### 方言判別
- `.csh`, `.tcsh` → CSH構文（`set VAR = VALUE`, `setenv VAR VALUE`）
- `.sh`, `.ksh` および shebang `#!/bin/bash` 等 → BASH/SH構文
- 判別できない場合は BASH構文をデフォルトとする

### 使用タイプ分類（優先度順）

| 使用タイプ | 判定パターン |
|-----------|------------|
| 環境変数エクスポート | `\bexport\b`, `\bsetenv\b` |
| 変数代入 | `\w+=`, `\bset\s+\w+\s*=`（CSH） |
| 条件判定 | `\bif\s*\[`, `\bcase\b`, `[!=]=`, `\b-eq\b`, `\b-ne\b` |
| echo/print出力 | `\becho\b`, `\bprint\b`, `\bprintf\b` |
| コマンド引数 | 上記に該当しない行でコマンド後の引数として出現 |
| その他 | 上記に該当しない |

### 変数名抽出ルール

| パターン | 変数名取得方法 |
|---------|------------|
| `VAR="VALUE"` | `=` の左辺 |
| `VAR='VALUE'` | `=` の左辺 |
| `set VAR = VALUE`（CSH） | `set` 直後の語 |

### 間接参照追跡

- 「変数代入」「環境変数エクスポート」タイプから変数名を抽出
- `$VAR` または `${VAR}` の出現をファイル全体でスキャン
- 各出現行を再分類して間接参照レコードとして追加

---

## TSV出力形式（言語共通）

`GrepRecord` カラム構成は全言語で統一。`usage_type` の値のみ言語ごとに異なる。

| カラム | 説明 |
|--------|------|
| keyword | 検索文言（入力ファイル名のstem） |
| ref_type | 直接 / 間接 |
| usage_type | 言語別使用タイプ（例: "WHERE条件", "変数代入"） |
| filepath | ヒットしたファイルパス |
| lineno | 行番号 |
| code | 該当コード行（trim済み） |
| src_var | 間接参照の場合: 経由した変数名 |
| src_file | 間接参照の場合: 変数定義ファイル |
| src_lineno | 間接参照の場合: 変数定義行番号 |

---

## テスト方針

既存の `test_analyze.py` と同じ構造で各言語テストを追加する。

- `tests/test_sql_analyzer.py` — SQL分類・間接追跡のユニットテスト
- `tests/test_proc_analyzer.py` — Pro*C分類・間接追跡のユニットテスト
- `tests/test_shell_analyzer.py` — Shell分類・間接追跡のユニットテスト
- `tests/fixtures/sample.sql`, `sample.pc`, `sample.sh` — テスト用サンプルソース

---

## 未対応・今後の検討事項

- `.h` ファイルはPro*CとC言語で共用される場合があるが、EXEC SQLを含まない純粋なCヘッダーは `UnknownAnalyzer` にフォールバック
- Oracle SQL の `INCLUDE` / `@` ファイル参照による間接追跡はスコープ外
- シェルスクリプトの `source` / `.` コマンドによるファイル横断追跡はスコープ外
