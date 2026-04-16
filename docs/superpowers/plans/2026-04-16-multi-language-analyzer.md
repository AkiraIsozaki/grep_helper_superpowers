# 多言語対応 grep結果アナライザー 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** analyze.py を多言語対応に拡張し、Oracle SQL / Pro*C / シェルスクリプトの grep 結果を言語固有の使用タイプで分類・間接参照追跡できるようにする

**Architecture:** 共通インフラ（GrepRecord, ProcessStats, parse_grep_line, write_tsv）を `analyze_common.py` に切り出し、各言語モジュール（analyze_proc.py / analyze_sql.py / analyze_sh.py）が import する。言語固有の分類・追跡ロジックは各モジュール内に完結させる。

**Tech Stack:** Python 3.11+、標準ライブラリのみ（re, csv, pathlib, argparse）、cp932エンコーディング読み込み

> **設計上の注記:** 承認済み設計では `analyzers/` ディレクトリ（ストラテジーパターン）を想定していたが、既存の `test_analyze_proc.py` が `import analyze_proc as ap` という flat module API を期待しているため、`analyze_common.py` を共有基盤とするスタンドアロンモジュール方式を採用する。挙動・分類カテゴリも pre-written test の定義に従う。

---

## ファイル構成

| 操作 | ファイル | 役割 |
|------|---------|------|
| 新規作成 | `analyze_common.py` | 全言語共通: GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv |
| 変更 | `analyze.py` | `analyze_common` から import するよう最小変更。Java固有コードはそのまま。 |
| 新規作成 | `analyze_proc.py` | Pro*C アナライザー（test_analyze_proc.py の契約に従う） |
| 新規作成 | `analyze_sql.py` | Oracle SQL (11g) アナライザー |
| 新規作成 | `analyze_sh.py` | Shell スクリプトアナライザー（BASH/CSH/TCSH） |
| 新規作成 | `tests/test_sql_analyzer.py` | SQL ユニットテスト |
| 新規作成 | `tests/test_sh_analyzer.py` | Shell ユニットテスト |
| 新規作成 | `tests/proc/src/sample.pc` | Pro*C E2E テストフィクスチャ（ソース） |
| 新規作成 | `tests/proc/input/TARGET.grep` | Pro*C E2E テストフィクスチャ（grep 結果） |
| 新規作成 | `tests/proc/expected/TARGET.tsv` | Pro*C E2E テストフィクスチャ（期待 TSV） |
| 新規作成 | `tests/sql/src/sample.sql` | SQL E2E テストフィクスチャ |
| 新規作成 | `tests/sql/input/TARGET.grep` | SQL E2E フィクスチャ |
| 新規作成 | `tests/sql/expected/TARGET.tsv` | SQL 期待 TSV |
| 新規作成 | `tests/sh/src/sample.sh` | Shell E2E テストフィクスチャ |
| 新規作成 | `tests/sh/input/TARGET.grep` | Shell E2E フィクスチャ |
| 新規作成 | `tests/sh/expected/TARGET.tsv` | Shell 期待 TSV |

---

## Task 1: analyze_common.py の作成

**Files:**
- Create: `analyze_common.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_common.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv
import tempfile, csv

class TestCommonImports(unittest.TestCase):
    def test_grep_record_fields(self):
        r = GrepRecord("kw", "直接", "その他", "f.sql", "1", "code")
        self.assertEqual(r.keyword, "kw")
        self.assertEqual(r.src_var, "")

    def test_parse_grep_line_valid(self):
        result = parse_grep_line("src/sample.sql:10:WHERE code = 'A';")
        self.assertEqual(result["filepath"], "src/sample.sql")
        self.assertEqual(result["lineno"], "10")
        self.assertEqual(result["code"], "WHERE code = 'A';")

    def test_parse_grep_line_binary(self):
        self.assertIsNone(parse_grep_line("Binary file ./obj/sample.o matches"))

    def test_write_tsv_creates_bom(self):
        records = [GrepRecord("K", "直接", "その他", "f.sql", "1", "code")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            write_tsv(records, out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))

    def test_write_tsv_sort_direct_before_indirect(self):
        records = [
            GrepRecord("K", "間接", "その他", "b.sql", "5", "c",
                       src_var="V", src_file="a.sql", src_lineno="2"),
            GrepRecord("K", "直接", "その他", "a.sql", "2", "c"),
        ]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            write_tsv(records, out)
            with open(out, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter="\t"))[1:]
            self.assertEqual(rows[0][1], "直接")
            self.assertEqual(rows[1][1], "間接")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
python -m pytest tests/test_common.py -v 2>&1 | head -20
```
期待: `ModuleNotFoundError: No module named 'analyze_common'`

- [ ] **Step 3: analyze_common.py を実装する**

```python
# analyze_common.py
"""全言語アナライザー共通インフラ。

GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv を提供する。
analyze.py / analyze_proc.py / analyze_sql.py / analyze_sh.py から import される。
"""
from __future__ import annotations

import csv
import heapq
import re
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import NamedTuple


class RefType(Enum):
    DIRECT   = "直接"
    INDIRECT = "間接"
    GETTER   = "間接（getter経由）"


class GrepRecord(NamedTuple):
    keyword:    str
    ref_type:   str
    usage_type: str
    filepath:   str
    lineno:     str
    code:       str
    src_var:    str = ""
    src_file:   str = ""
    src_lineno: str = ""


@dataclass
class ProcessStats:
    total_lines:     int = 0
    valid_lines:     int = 0
    skipped_lines:   int = 0
    fallback_files:  set[str] = field(default_factory=set)
    encoding_errors: set[str] = field(default_factory=set)


_BINARY_PATTERN   = re.compile(r'^Binary file .+ matches$')
_GREP_LINE_PATTERN = re.compile(r':(\d+):')

_TSV_HEADERS = [
    "文言", "参照種別", "使用タイプ", "ファイルパス", "行番号", "コード行",
    "参照元変数名", "参照元ファイル", "参照元行番号",
]

_EXTERNAL_SORT_THRESHOLD = 1_000_000


def parse_grep_line(line: str) -> dict | None:
    """grep結果の1行をパースする。不正行はNoneを返す。"""
    stripped = line.rstrip('\n\r')
    if not stripped.strip():
        return None
    if _BINARY_PATTERN.match(stripped):
        return None
    parts = _GREP_LINE_PATTERN.split(stripped, maxsplit=1)
    if len(parts) != 3:
        return None
    filepath, lineno, code = parts
    if not filepath or not lineno:
        return None
    return {"filepath": filepath, "lineno": lineno, "code": code.strip()}


def write_tsv(records: list[GrepRecord], output_path: Path) -> None:
    """GrepRecordのリストをUTF-8 BOM付きTSVに出力する（ソート済み）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _sort_key(r: GrepRecord) -> tuple:
        lineno_int = int(r.lineno) if r.lineno.isdigit() else 0
        if r.ref_type == RefType.DIRECT.value:
            return (r.keyword, r.filepath, lineno_int, 0, "", 0)
        src_lineno_int = int(r.src_lineno) if r.src_lineno.isdigit() else 0
        return (r.keyword, r.src_file, src_lineno_int, 1, r.filepath, lineno_int)

    def _row_sort_key(row: list[str]) -> tuple:
        lineno_int = int(row[4]) if row[4].isdigit() else 0
        if row[1] == RefType.DIRECT.value:
            return (row[0], row[3], lineno_int, 0, "", 0)
        src_int = int(row[8]) if row[8].isdigit() else 0
        return (row[0], row[7], src_int, 1, row[3], lineno_int)

    if len(records) < _EXTERNAL_SORT_THRESHOLD:
        records.sort(key=_sort_key)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(_TSV_HEADERS)
            for r in records:
                writer.writerow([
                    r.keyword, r.ref_type, r.usage_type, r.filepath,
                    r.lineno, r.code, r.src_var, r.src_file, r.src_lineno,
                ])
        return

    _CHUNK_SIZE = 500_000
    tmp_paths: list[Path] = []
    tmp_dir = output_path.parent
    try:
        for i in range(0, len(records), _CHUNK_SIZE):
            chunk = records[i:i + _CHUNK_SIZE]
            chunk.sort(key=_sort_key)
            fd, tmp_str = tempfile.mkstemp(
                suffix=".tmp", prefix=f".{output_path.stem}_chunk_", dir=tmp_dir,
            )
            tmp_path = Path(tmp_str)
            tmp_paths.append(tmp_path)
            with open(fd, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, delimiter="\t")
                for r in chunk:
                    w.writerow([
                        r.keyword, r.ref_type, r.usage_type, r.filepath,
                        r.lineno, r.code, r.src_var, r.src_file, r.src_lineno,
                    ])
            del chunk
        del records
        handles = [open(p, "r", encoding="utf-8", newline="") for p in tmp_paths]
        readers = [csv.reader(h, delimiter="\t") for h in handles]
        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(_TSV_HEADERS)
                for row in heapq.merge(*readers, key=_row_sort_key):
                    writer.writerow(row)
        finally:
            for h in handles:
                h.close()
    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)
```

- [ ] **Step 4: テストが通ることを確認する**

```bash
python -m pytest tests/test_common.py -v
```
期待: 5 tests passed

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat: add analyze_common.py with shared infrastructure"
```

---

## Task 2: analyze.py を analyze_common.py から import するよう変更

**Files:**
- Modify: `analyze.py`（先頭の定義を import に置き換え）

- [ ] **Step 1: 既存テストが通ることを確認しておく（ベースライン）**

```bash
python -m pytest test_analyze.py -v --tb=short 2>&1 | tail -10
```
期待: 全テスト passed

- [ ] **Step 2: analyze.py の先頭を書き換える**

`analyze.py` の以下のブロック（現行 1〜90行の定数・Enum・データモデル定義）を:

```python
from __future__ import annotations
import argparse
import csv
import heapq
import re
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import NamedTuple

try:
    import javalang
    _JAVALANG_AVAILABLE = True
except ImportError:
    _JAVALANG_AVAILABLE = False

# USAGE_PATTERNS (Java専用、残す)
# _BINARY_PATTERN (削除)
# _GREP_LINE_PATTERN (削除)
# RefType (削除)
# UsageType (残す)
# GrepRecord (削除)
# ProcessStats (削除)
```

次のように置き換える:

```python
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import javalang
    _JAVALANG_AVAILABLE = True
except ImportError:
    _JAVALANG_AVAILABLE = False

from analyze_common import (
    GrepRecord,
    ProcessStats,
    RefType,
    parse_grep_line,
    write_tsv,
)

# ---------------------------------------------------------------------------
# Java専用定数
# ---------------------------------------------------------------------------

USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'@\w+\s*\('),                                  "アノテーション"),
    (re.compile(r'\bstatic\s+final\b'),                         "定数定義"),
    (re.compile(r'\bif\s*\(|\bwhile\s*\(|\.equals\s*\(|[!=]='), "条件判定"),
    (re.compile(r'\breturn\b'),                                  "return文"),
    (re.compile(r'\b\w[\w<>\[\]]*\s+\w+\s*='),                 "変数代入"),
    (re.compile(r'\w+\s*\('),                                    "メソッド引数"),
]
```

また、analyze.py 内の `parse_grep_line` 関数定義（約30行）と `write_tsv` 関数定義（約70行）と `_TSV_HEADERS`・`_EXTERNAL_SORT_THRESHOLD` 定数を**削除**する（analyze_common.py で提供されるため）。

同様に `_BINARY_PATTERN`・`_GREP_LINE_PATTERN` の定義を削除する。

- [ ] **Step 3: 既存テストが通ることを確認する**

```bash
python -m pytest test_analyze.py -v --tb=short 2>&1 | tail -15
```
期待: 全テスト passed（エラーがあれば import 漏れを修正する）

- [ ] **Step 4: コミット**

```bash
git add analyze.py
git commit -m "refactor: import shared infrastructure from analyze_common"
```

---

## Task 3: analyze_proc.py のユニットテストを全て通す

**Files:**
- Create: `analyze_proc.py`

> **前提:** `test_analyze_proc.py` は既に存在する。このタスクではユニットテスト（E2E以外）を通す。

- [ ] **Step 1: 現在のテスト失敗を確認する**

```bash
python -m pytest test_analyze_proc.py -v --tb=short -k "not TestE2E" 2>&1 | tail -20
```
期待: `ModuleNotFoundError: No module named 'analyze_proc'`

- [ ] **Step 2: analyze_proc.py を作成する**

```python
# analyze_proc.py
"""Pro*C grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv

# ---------------------------------------------------------------------------
# 使用タイプ分類パターン（優先度順）
# ---------------------------------------------------------------------------

_PROC_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bEXEC\s+SQL\b', re.IGNORECASE), "EXEC SQL文"),
    (re.compile(r'#\s*define\b'),                  "#define定数定義"),
    (re.compile(r'\bif\s*\(|strcmp\s*\(|strncmp\s*\('), "条件判定"),
    (re.compile(r'\breturn\b'),                    "return文"),
    (re.compile(r'\b\w+\s*(?:\[[^\]]*\])?\s*=(?!=)'), "変数代入"),
    (re.compile(r'\w+\s*\('),                      "関数引数"),
]

# ---------------------------------------------------------------------------
# ファイル行キャッシュ
# ---------------------------------------------------------------------------

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            _file_cache[key] = Path(filepath).read_text(
                encoding="cp932", errors="replace"
            ).splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]


def _resolve_source_file(filepath: str, src_dir: Path) -> Path | None:
    """ファイルパスを解決する。CWD相対→src_dir相対の順で試みる。"""
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    if resolved.exists():
        return resolved
    return None


# ---------------------------------------------------------------------------
# 使用タイプ分類
# ---------------------------------------------------------------------------

def classify_usage_proc(code: str) -> str:
    """Pro*Cコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PROC_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


# ---------------------------------------------------------------------------
# 変数名・マクロ名抽出
# ---------------------------------------------------------------------------

_C_TYPES_PAT = re.compile(
    r'\b(?:char|int|short|long|float|double|unsigned|signed|struct|void'
    r'|SQLCHAR|SQLINT|VARCHAR)\b\s*\**\s*(\w+)'
)


def extract_variable_name_proc(code: str) -> str | None:
    """C変数宣言から変数名を抽出する（型名の後の識別子）。"""
    m = _C_TYPES_PAT.search(code)
    return m.group(1) if m else None


_DEFINE_PAT = re.compile(r'#\s*define\s+(\w+)\s+')


def extract_define_name(code: str) -> str | None:
    """#define からマクロ名を抽出する。値のない #define は None を返す。"""
    m = _DEFINE_PAT.match(code)
    return m.group(1) if m else None


def extract_host_var_name(code: str) -> str | None:
    """ホスト変数名を抽出する（strcpy / EXEC SQL INTO / 単純代入）。"""
    m = re.match(r'\s*str(?:n?cpy)\s*\(\s*(\w+)', code)
    if m:
        return m.group(1)
    m = re.match(r'\s*sprintf\s*\(\s*(\w+)', code)
    if m:
        return m.group(1)
    m = re.search(r'\bINTO\s*:(\w+)', code, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.match(r'\s*(\w+)\s*=\s*"', code)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 間接参照追跡
# ---------------------------------------------------------------------------

def track_define(
    var_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """#define マクロ名の使用箇所を src_dir 配下の全 .pc/.h ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    def_file = _resolve_source_file(record.filepath, src_dir)

    pc_files = sorted(src_dir.rglob("*.pc")) + sorted(src_dir.rglob("*.h"))
    for pc_file in pc_files:
        try:
            filepath_str = str(pc_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(pc_file)

        lines = _get_cached_lines(pc_file, stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and pc_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage_proc(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=var_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def track_variable(
    var_name: str,
    candidate: Path,
    def_lineno: int,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """C変数名の使用箇所を同一ファイル内でスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    try:
        filepath_str = str(candidate.relative_to(src_dir))
    except ValueError:
        filepath_str = str(candidate)

    lines = _get_cached_lines(candidate, stats)
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_proc(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


# ---------------------------------------------------------------------------
# grep ファイル処理
# ---------------------------------------------------------------------------

def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """grepファイル全行を処理し、直接参照レコードを返す。"""
    records: list[GrepRecord] = []
    with open(path, encoding="cp932", errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_proc(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pro*C grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="Pro*Cソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"エラー: --source-dir が存在しません: {source_dir}", file=sys.stderr)
        sys.exit(1)
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"エラー: --input-dir が存在しません: {input_dir}", file=sys.stderr)
        sys.exit(1)

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print("エラー: grep結果ファイルがありません", file=sys.stderr)
        sys.exit(1)

    stats = ProcessStats()
    processed_files: list[str] = []
    try:
        for grep_path in grep_files:
            keyword = grep_path.stem
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats)
            all_records: list[GrepRecord] = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = extract_define_name(record.code)
                    if var_name:
                        all_records.extend(track_define(var_name, source_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = extract_variable_name_proc(record.code)
                    if not var_name:
                        var_name = extract_host_var_name(record.code)
                    if var_name:
                        candidate = _resolve_source_file(record.filepath, source_dir)
                        if candidate:
                            all_records.extend(
                                track_variable(var_name, candidate,
                                               int(record.lineno), source_dir, record, stats)
                            )

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} "
                  f"(直接: {direct_count} 件, 間接: {indirect_count} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}"
          f"  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: ユニットテスト（E2E除く）が通ることを確認する**

```bash
python -m pytest test_analyze_proc.py -v --tb=short -k "not TestE2E" 2>&1 | tail -20
```
期待: `TestParseGrepLine`, `TestClassifyUsageProc`, `TestExtractDefineName`, `TestExtractVariableNameProc`, `TestWriteTsv` の全テスト passed

- [ ] **Step 4: コミット**

```bash
git add analyze_proc.py
git commit -m "feat: add analyze_proc.py for Pro*C grep classification"
```

---

## Task 4: Pro*C E2E テストフィクスチャを作成して E2E テストを通す

**Files:**
- Create: `tests/proc/src/sample.pc`
- Create: `tests/proc/input/TARGET.grep`
- Create: `tests/proc/expected/TARGET.tsv`

- [ ] **Step 1: E2E テストが失敗することを確認する**

```bash
python -m pytest test_analyze_proc.py::TestE2EProc -v --tb=short
```
期待: `tests/proc/src が存在しない` でスキップまたは失敗

- [ ] **Step 2: ソースファイルを作成する**

```bash
mkdir -p tests/proc/src tests/proc/input tests/proc/expected
```

`tests/proc/src/sample.pc`:
```c
/* sample.pc - Pro*C E2E test fixture */
#define TCODE "TARGET"

void test_proc() {
    char hv[32];
    EXEC SQL SELECT col INTO :hv WHERE code = 'data';
    if (strcmp(hv, TCODE) == 0) {
        strcpy(hv, TCODE);
    }
}
```

- [ ] **Step 3: grep 入力ファイルを作成する**

`tests/proc/input/TARGET.grep`:
```
tests/proc/src/sample.pc:2:#define TCODE "TARGET"
```

（"TARGET" を検索した場合に line 2 だけがヒットする。TCODE は "TARGET" を含まない）

- [ ] **Step 4: 期待 TSV を作成する**

Sort ルール確認:
- Direct record: sort key = `(TARGET, tests/proc/src/sample.pc, 2, 0, "", 0)`
- Indirect line7: sort key = `(TARGET, tests/proc/src/sample.pc, 2, 1, sample.pc, 7)`
- Indirect line8: sort key = `(TARGET, tests/proc/src/sample.pc, 2, 1, sample.pc, 8)`

`tests/proc/expected/TARGET.tsv`（UTF-8 BOM付き、タブ区切り）:
```
文言	参照種別	使用タイプ	ファイルパス	行番号	コード行	参照元変数名	参照元ファイル	参照元行番号
TARGET	直接	#define定数定義	tests/proc/src/sample.pc	2	#define TCODE "TARGET"
TARGET	間接	条件判定	sample.pc	7	if (strcmp(hv, TCODE) == 0) {	TCODE	tests/proc/src/sample.pc	2
TARGET	間接	関数引数	sample.pc	8	strcpy(hv, TCODE);	TCODE	tests/proc/src/sample.pc	2
```

（末尾に空行あり・各行はタブ区切り・UTF-8 BOM付き）

> **TSV 生成のヒント:** 期待 TSV は手作成より実際にツールを実行して生成するのが確実。
> 実行後に内容を目視確認してから expected に保存する。

```bash
python analyze_proc.py \
  --source-dir tests/proc/src \
  --input-dir  tests/proc/input \
  --output-dir /tmp/proc_out
cat /tmp/proc_out/TARGET.tsv
```
出力を確認し、正しければ:
```bash
cp /tmp/proc_out/TARGET.tsv tests/proc/expected/TARGET.tsv
```

- [ ] **Step 5: E2E テストが通ることを確認する**

```bash
python -m pytest test_analyze_proc.py -v --tb=short
```
期待: 全テスト passed（TestE2EProc.test_e2e_target を含む）

- [ ] **Step 6: 全テストが壊れていないことを確認する**

```bash
python -m pytest test_analyze.py test_analyze_proc.py tests/test_common.py -v --tb=short 2>&1 | tail -10
```
期待: 全テスト passed

- [ ] **Step 7: コミット**

```bash
git add tests/proc/ tests/test_common.py
git commit -m "feat: add Pro*C E2E test fixtures"
```

---

## Task 5: analyze_sql.py の作成

**Files:**
- Create: `analyze_sql.py`
- Create: `tests/test_sql_analyzer.py`
- Create: `tests/sql/src/sample.sql`
- Create: `tests/sql/input/TARGET.grep`
- Create: `tests/sql/expected/TARGET.tsv`

- [ ] **Step 1: 失敗するユニットテストを書く**

`tests/test_sql_analyzer.py`:
```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_sql as aq


class TestClassifyUsageSql(unittest.TestCase):
    def test_exception(self):
        self.assertEqual(
            aq.classify_usage_sql("RAISE_APPLICATION_ERROR(-20001, 'TARGET');"),
            "例外・エラー処理"
        )
    def test_variable_definition(self):
        self.assertEqual(aq.classify_usage_sql("v_code := 'TARGET';"), "定数・変数定義")
    def test_constant_definition(self):
        self.assertEqual(
            aq.classify_usage_sql("c_val CONSTANT VARCHAR2(10) := 'TARGET';"),
            "定数・変数定義"
        )
    def test_where(self):
        self.assertEqual(
            aq.classify_usage_sql("WHERE code = 'TARGET'"), "WHERE条件"
        )
    def test_decode(self):
        self.assertEqual(
            aq.classify_usage_sql("DECODE(code, 'TARGET', 'OK')"), "比較・DECODE"
        )
    def test_case_when(self):
        self.assertEqual(
            aq.classify_usage_sql("CASE WHEN code = 'TARGET' THEN 1 END"), "比較・DECODE"
        )
    def test_insert(self):
        self.assertEqual(
            aq.classify_usage_sql("INSERT INTO t VALUES ('TARGET')"), "INSERT/UPDATE値"
        )
    def test_update(self):
        self.assertEqual(
            aq.classify_usage_sql("UPDATE t SET code = 'TARGET'"), "INSERT/UPDATE値"
        )
    def test_select(self):
        self.assertEqual(
            aq.classify_usage_sql("SELECT 'TARGET' FROM dual"), "SELECT/INTO"
        )
    def test_other(self):
        self.assertEqual(aq.classify_usage_sql("TARGET"), "その他")


class TestExtractSqlVariableName(unittest.TestCase):
    def test_simple_assignment(self):
        self.assertEqual(
            aq.extract_sql_variable_name("v_code := 'TARGET';"), "v_code"
        )
    def test_type_declaration(self):
        self.assertEqual(
            aq.extract_sql_variable_name("l_val VARCHAR2(10) := 'TARGET';"), "l_val"
        )
    def test_no_match(self):
        self.assertIsNone(aq.extract_sql_variable_name("WHERE code = 'TARGET'"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
python -m pytest tests/test_sql_analyzer.py -v --tb=short 2>&1 | head -10
```
期待: `ModuleNotFoundError: No module named 'analyze_sql'`

- [ ] **Step 3: analyze_sql.py を実装する**

```python
# analyze_sql.py
"""Oracle SQL (11g) grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv

_SQL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bRAISE_APPLICATION_ERROR\b|\bEXCEPTION\b', re.IGNORECASE), "例外・エラー処理"),
    (re.compile(r':=|\bCONSTANT\b', re.IGNORECASE),                          "定数・変数定義"),
    (re.compile(r'\bWHERE\b|\bAND\b.*=|\bOR\b.*=', re.IGNORECASE),           "WHERE条件"),
    (re.compile(r'\bDECODE\s*\(|\bCASE\b.*\bWHEN\b', re.IGNORECASE),         "比較・DECODE"),
    (re.compile(r'\bINSERT\b|\bUPDATE\b.*\bSET\b|\bVALUES\s*\(', re.IGNORECASE), "INSERT/UPDATE値"),
    (re.compile(r'\bSELECT\b|\bINTO\b', re.IGNORECASE),                      "SELECT/INTO"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            _file_cache[key] = Path(filepath).read_text(
                encoding="cp932", errors="replace"
            ).splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]


def _resolve_source_file(filepath: str, src_dir: Path) -> Path | None:
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    return resolved if resolved.exists() else None


def classify_usage_sql(code: str) -> str:
    """Oracle SQLコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _SQL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_SQL_VAR_PATTERN = re.compile(r'^\s*(\w+)(?:\s+\w[\w\s\(\),]*?)?\s*:=', re.IGNORECASE)


def extract_sql_variable_name(code: str) -> str | None:
    """PL/SQL変数定義から変数名を抽出する（:= の左辺の最初の識別子）。"""
    m = _SQL_VAR_PATTERN.match(code)
    return m.group(1) if m else None


def track_sql_variable(
    var_name: str,
    filepath: Path,
    def_lineno: int,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """PL/SQL変数名の使用箇所を同一ファイル内でスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b', re.IGNORECASE)
    try:
        filepath_str = str(filepath.relative_to(src_dir))
    except ValueError:
        filepath_str = str(filepath)

    lines = _get_cached_lines(filepath, stats)
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_sql(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    with open(path, encoding="cp932", errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_sql(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Oracle SQL grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"エラー: --source-dir が存在しません: {source_dir}", file=sys.stderr)
        sys.exit(1)
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"エラー: --input-dir が存在しません: {input_dir}", file=sys.stderr)
        sys.exit(1)

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print("エラー: grep結果ファイルがありません", file=sys.stderr)
        sys.exit(1)

    stats = ProcessStats()
    processed_files: list[str] = []
    try:
        for grep_path in grep_files:
            keyword = grep_path.stem
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats)
            all_records: list[GrepRecord] = list(direct_records)

            for record in direct_records:
                if record.usage_type == "定数・変数定義":
                    var_name = extract_sql_variable_name(record.code)
                    if var_name:
                        resolved = _resolve_source_file(record.filepath, source_dir)
                        if resolved:
                            all_records.extend(
                                track_sql_variable(var_name, resolved,
                                                   int(record.lineno), source_dir, record, stats)
                            )

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} "
                  f"(直接: {direct_count} 件, 間接: {indirect_count} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}"
          f"  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: ユニットテストが通ることを確認する**

```bash
python -m pytest tests/test_sql_analyzer.py -v --tb=short
```
期待: 13 tests passed

- [ ] **Step 5: SQL E2E フィクスチャを作成する**

```bash
mkdir -p tests/sql/src tests/sql/input tests/sql/expected
```

`tests/sql/src/sample.sql`:
```sql
-- sample.sql - Oracle SQL E2E test fixture
CREATE OR REPLACE PROCEDURE test_proc AS
  v_code VARCHAR2(10) := 'TARGET';
BEGIN
  IF v_code = 'check' THEN
    DBMS_OUTPUT.PUT_LINE(v_code);
  END IF;
END;
/
```

`tests/sql/input/TARGET.grep`:
```
tests/sql/src/sample.sql:3:  v_code VARCHAR2(10) := 'TARGET';
```

実行して期待 TSV を生成する:
```bash
python analyze_sql.py \
  --source-dir tests/sql/src \
  --input-dir  tests/sql/input \
  --output-dir /tmp/sql_out
cat /tmp/sql_out/TARGET.tsv
```

出力を目視確認（直接レコード1件 + 間接レコード2件が期待される）。
正しければ:
```bash
cp /tmp/sql_out/TARGET.tsv tests/sql/expected/TARGET.tsv
```

- [ ] **Step 6: コミット**

```bash
git add analyze_sql.py tests/test_sql_analyzer.py tests/sql/
git commit -m "feat: add analyze_sql.py for Oracle SQL grep classification"
```

---

## Task 6: analyze_sh.py の作成

**Files:**
- Create: `analyze_sh.py`
- Create: `tests/test_sh_analyzer.py`
- Create: `tests/sh/src/sample.sh`
- Create: `tests/sh/input/TARGET.grep`
- Create: `tests/sh/expected/TARGET.tsv`

- [ ] **Step 1: 失敗するユニットテストを書く**

`tests/test_sh_analyzer.py`:
```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_sh as ash


class TestClassifyUsageSh(unittest.TestCase):
    def test_export(self):
        self.assertEqual(ash.classify_usage_sh('export TARGET_VAR="TARGET"'), "環境変数エクスポート")
    def test_setenv_csh(self):
        self.assertEqual(ash.classify_usage_sh("setenv MY_VAR TARGET"), "環境変数エクスポート")
    def test_variable_assignment(self):
        self.assertEqual(ash.classify_usage_sh('MY_VAR="TARGET"'), "変数代入")
    def test_set_csh(self):
        self.assertEqual(ash.classify_usage_sh("set MY_VAR = TARGET"), "変数代入")
    def test_condition_if(self):
        self.assertEqual(ash.classify_usage_sh('if [ "$MY_VAR" = "TARGET" ]; then'), "条件判定")
    def test_condition_case(self):
        self.assertEqual(ash.classify_usage_sh("case $MY_VAR in"), "条件判定")
    def test_echo(self):
        self.assertEqual(ash.classify_usage_sh('echo "TARGET"'), "echo/print出力")
    def test_printf(self):
        self.assertEqual(ash.classify_usage_sh('printf "%s\n" "TARGET"'), "echo/print出力")
    def test_command_argument(self):
        self.assertEqual(ash.classify_usage_sh("grep TARGET file.txt"), "コマンド引数")
    def test_other(self):
        self.assertEqual(ash.classify_usage_sh("TARGET"), "その他")


class TestExtractShVariableName(unittest.TestCase):
    def test_simple_assignment(self):
        self.assertEqual(ash.extract_sh_variable_name('MY_VAR="TARGET"'), "MY_VAR")
    def test_export_assignment(self):
        self.assertEqual(ash.extract_sh_variable_name('export MY_VAR="TARGET"'), "MY_VAR")
    def test_set_csh(self):
        self.assertEqual(ash.extract_sh_variable_name("set MY_VAR = TARGET"), "MY_VAR")
    def test_setenv_csh(self):
        self.assertEqual(ash.extract_sh_variable_name("setenv MY_VAR TARGET"), "MY_VAR")
    def test_no_match(self):
        self.assertIsNone(ash.extract_sh_variable_name("grep TARGET file.txt"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
python -m pytest tests/test_sh_analyzer.py -v --tb=short 2>&1 | head -5
```
期待: `ModuleNotFoundError: No module named 'analyze_sh'`

- [ ] **Step 3: analyze_sh.py を実装する**

```python
# analyze_sh.py
"""シェルスクリプト (BASH/CSH/TCSH) grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv

_SH_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bexport\b|\bsetenv\b'), "環境変数エクスポート"),
    (re.compile(r'^\s*(?:set\s+)?\w+\s*=(?!=)|^\s*\w+\s*=(?!=)'), "変数代入"),
    (re.compile(r'\bif\s*\[|\bcase\b|[!=]=|\b-eq\b|\b-ne\b|\b-lt\b|\b-gt\b|\b-le\b|\b-ge\b'),
     "条件判定"),
    (re.compile(r'\becho\b|\bprint\b|\bprintf\b'), "echo/print出力"),
    (re.compile(r'^\s*\w+\s+\S'), "コマンド引数"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            _file_cache[key] = Path(filepath).read_text(
                encoding="cp932", errors="replace"
            ).splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]


def _resolve_source_file(filepath: str, src_dir: Path) -> Path | None:
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    return resolved if resolved.exists() else None


def classify_usage_sh(code: str) -> str:
    """シェルスクリプトコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _SH_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_SH_VAR_PATTERNS = [
    re.compile(r'^\s*(?:export\s+)?(\w+)\s*='),   # VAR= or export VAR=
    re.compile(r'^\s*set\s+(\w+)\s*='),            # CSH: set VAR=
    re.compile(r'^\s*setenv\s+(\w+)\s+'),          # CSH: setenv VAR value
]


def extract_sh_variable_name(code: str) -> str | None:
    """シェルスクリプトの代入文から変数名を抽出する。"""
    for pattern in _SH_VAR_PATTERNS:
        m = pattern.match(code)
        if m:
            return m.group(1)
    return None


def track_sh_variable(
    var_name: str,
    filepath: Path,
    def_lineno: int,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """シェル変数名の使用箇所を同一ファイル内でスキャンする（$VAR / ${VAR}）。"""
    results: list[GrepRecord] = []
    # $VAR または ${VAR} の出現を検索
    pattern = re.compile(r'\$\{?' + re.escape(var_name) + r'\}?(?=\b|[^a-zA-Z0-9_]|$)')
    try:
        filepath_str = str(filepath.relative_to(src_dir))
    except ValueError:
        filepath_str = str(filepath)

    lines = _get_cached_lines(filepath, stats)
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_sh(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    with open(path, encoding="cp932", errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_sh(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="シェルスクリプト grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"エラー: --source-dir が存在しません: {source_dir}", file=sys.stderr)
        sys.exit(1)
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"エラー: --input-dir が存在しません: {input_dir}", file=sys.stderr)
        sys.exit(1)

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print("エラー: grep結果ファイルがありません", file=sys.stderr)
        sys.exit(1)

    stats = ProcessStats()
    processed_files: list[str] = []
    try:
        for grep_path in grep_files:
            keyword = grep_path.stem
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats)
            all_records: list[GrepRecord] = list(direct_records)

            for record in direct_records:
                if record.usage_type in ("変数代入", "環境変数エクスポート"):
                    var_name = extract_sh_variable_name(record.code)
                    if var_name:
                        resolved = _resolve_source_file(record.filepath, source_dir)
                        if resolved:
                            all_records.extend(
                                track_sh_variable(var_name, resolved,
                                                  int(record.lineno), source_dir, record, stats)
                            )

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} "
                  f"(直接: {direct_count} 件, 間接: {indirect_count} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}"
          f"  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: ユニットテストが通ることを確認する**

```bash
python -m pytest tests/test_sh_analyzer.py -v --tb=short
```
期待: 15 tests passed

- [ ] **Step 5: Shell E2E フィクスチャを作成する**

```bash
mkdir -p tests/sh/src tests/sh/input tests/sh/expected
```

`tests/sh/src/sample.sh`:
```bash
#!/bin/bash
# sample.sh - Shell E2E test fixture
MY_CODE="TARGET"

if [ "$MY_CODE" = "check" ]; then
    echo "$MY_CODE"
fi
grep "$MY_CODE" data.txt
```

`tests/sh/input/TARGET.grep`:
```
tests/sh/src/sample.sh:3:MY_CODE="TARGET"
```

実行して期待 TSV を生成する:
```bash
python analyze_sh.py \
  --source-dir tests/sh/src \
  --input-dir  tests/sh/input \
  --output-dir /tmp/sh_out
cat /tmp/sh_out/TARGET.tsv
```

出力を目視確認（直接1件 + 間接3件が期待される）。
正しければ:
```bash
cp /tmp/sh_out/TARGET.tsv tests/sh/expected/TARGET.tsv
```

- [ ] **Step 6: 全テストが通ることを確認する**

```bash
python -m pytest test_analyze.py test_analyze_proc.py \
  tests/test_common.py tests/test_sql_analyzer.py tests/test_sh_analyzer.py \
  -v --tb=short 2>&1 | tail -15
```
期待: 全テスト passed

- [ ] **Step 7: コミット**

```bash
git add analyze_sh.py tests/test_sh_analyzer.py tests/sh/
git commit -m "feat: add analyze_sh.py for Shell script grep classification"
```

---

## 完了チェック

- [ ] `analyze_common.py` が存在し、全言語モジュールが import 可能
- [ ] `analyze.py` の既存テスト（test_analyze.py）が全て passed
- [ ] `test_analyze_proc.py` の全テスト（TestE2EProc 含む）が passed
- [ ] `tests/test_sql_analyzer.py` の全テストが passed
- [ ] `tests/test_sh_analyzer.py` の全テストが passed
- [ ] 各言語モジュールが `--source-dir / --input-dir / --output-dir` オプションで単独実行可能
