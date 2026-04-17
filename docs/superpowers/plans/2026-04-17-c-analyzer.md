# 純Cアナライザー ＋ Pro*C 混在対応 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 純C用アナライザー `analyze_c.py` を新規作成し、`analyze_proc.py` が `.c/.pc` 混在 grep 結果を拡張子ベースで正しく分類・追跡できるようにする。

**Architecture:** `analyze_c.py` が `classify_usage_c` を定義し、`analyze_proc.py` がそれを import して拡張子ディスパッチ（`.c/.h` → C分類、`.pc` → Pro*C分類）を行う。`track_define` は `.c/.h/.pc` すべてをスキャンする。循環参照を避けるため `analyze_c.py` は `analyze_proc.py` を import しない。

**Tech Stack:** Python 3.11+、標準ライブラリのみ（re, pathlib, argparse）、pytest

---

## ファイル構成

| 操作 | ファイル | 役割 |
|------|---------|------|
| 新規作成 | `analyze_c.py` | 純C アナライザー |
| 新規作成 | `tests/test_c_analyzer.py` | analyze_c ユニット + E2E テスト |
| 新規作成 | `tests/c/src/sample.c` | C E2E フィクスチャ |
| 新規作成 | `tests/c/input/TARGET.grep` | C E2E grep フィクスチャ |
| 新規作成 | `tests/c/expected/TARGET.tsv` | C E2E 期待 TSV |
| 変更 | `analyze_proc.py` | 拡張子ディスパッチ追加、track_define 拡張 |
| 変更 | `test_analyze_proc.py` | TestDispatch + TestE2EMixed 追加 |
| 新規作成 | `tests/proc/src/sample_c.c` | 混在 E2E 用 C ソース |
| 新規作成 | `tests/proc/src/mixed.pc` | 混在 E2E 用 Pro*C ソース |
| 新規作成 | `tests/proc/input/MIXVAL.grep` | 混在 E2E grep フィクスチャ |
| 新規作成 | `tests/proc/expected/MIXVAL.tsv` | 混在 E2E 期待 TSV |

---

## Task 1: analyze_c.py のユニットテストと実装

**Files:**
- Create: `tests/test_c_analyzer.py`
- Create: `analyze_c.py`

- [ ] **Step 1: 失敗するユニットテストを書く**

```python
# tests/test_c_analyzer.py
import sys, unittest, tempfile, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_c as ac


class TestClassifyUsageC(unittest.TestCase):
    def test_define(self):
        self.assertEqual(ac.classify_usage_c('#define MAX_SIZE 100'), "#define定数定義")

    def test_define_with_spaces(self):
        self.assertEqual(ac.classify_usage_c('# define STATUS "value"'), "#define定数定義")

    def test_condition_if(self):
        self.assertEqual(ac.classify_usage_c('if (code == STATUS)'), "条件判定")

    def test_condition_strcmp(self):
        self.assertEqual(ac.classify_usage_c('strcmp(code, STATUS)'), "条件判定")

    def test_condition_strncmp(self):
        self.assertEqual(ac.classify_usage_c('strncmp(code, STATUS, 4)'), "条件判定")

    def test_condition_switch(self):
        self.assertEqual(ac.classify_usage_c('switch (code) {'), "条件判定")

    def test_return(self):
        self.assertEqual(ac.classify_usage_c('return STATUS;'), "return文")

    def test_variable_assignment(self):
        self.assertEqual(ac.classify_usage_c('char buf[32] = STATUS;'), "変数代入")

    def test_function_argument(self):
        self.assertEqual(ac.classify_usage_c('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(ac.classify_usage_c('STATUS'), "その他")

    def test_no_exec_sql(self):
        # EXEC SQL は C ファイルでは "EXEC SQL文" にならない
        result = ac.classify_usage_c('EXEC SQL SELECT * FROM t;')
        self.assertNotEqual(result, "EXEC SQL文")


class TestExtractDefineName(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ac.extract_define_name('#define STATUS "value"'), "STATUS")

    def test_with_spaces_after_hash(self):
        self.assertEqual(ac.extract_define_name('# define STATUS "value"'), "STATUS")

    def test_no_match(self):
        self.assertIsNone(ac.extract_define_name('if (x == STATUS)'))

    def test_no_value(self):
        # 値のない #define は None
        self.assertIsNone(ac.extract_define_name('#define STATUS'))


class TestExtractVariableNameC(unittest.TestCase):
    def test_char_array(self):
        self.assertEqual(ac.extract_variable_name_c('char buf[32];'), "buf")

    def test_int_with_assignment(self):
        self.assertEqual(ac.extract_variable_name_c('int count = 0;'), "count")

    def test_pointer(self):
        self.assertEqual(ac.extract_variable_name_c('char *ptr;'), "ptr")

    def test_no_match(self):
        self.assertIsNone(ac.extract_variable_name_c('if (x == 1)'))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
python -m pytest tests/test_c_analyzer.py -v 2>&1 | head -10
```
期待: `ModuleNotFoundError: No module named 'analyze_c'`

- [ ] **Step 3: analyze_c.py を実装する**

```python
# analyze_c.py
"""純C grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv

# ---------------------------------------------------------------------------
# 使用タイプ分類パターン（優先度順）
# ---------------------------------------------------------------------------

_C_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'#\s*define\b'),                               "#define定数定義"),
    (re.compile(r'\bif\s*\(|strcmp\s*\(|strncmp\s*\(|switch\s*\('), "条件判定"),
    (re.compile(r'\breturn\b'),                                 "return文"),
    (re.compile(r'\b\w+\s*(?:\[[^\]]*\])?\s*=(?!=)'),          "変数代入"),
    (re.compile(r'\w+\s*\('),                                   "関数引数"),
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
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    return resolved if resolved.exists() else None


# ---------------------------------------------------------------------------
# 使用タイプ分類
# ---------------------------------------------------------------------------

def classify_usage_c(code: str) -> str:
    """純Cコード行の使用タイプを分類する（6種）。EXEC SQL は対象外。"""
    stripped = code.strip()
    for pattern, usage_type in _C_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


# ---------------------------------------------------------------------------
# 変数名・マクロ名抽出
# ---------------------------------------------------------------------------

_C_TYPES_PAT = re.compile(
    r'\b(?:char|int|short|long|float|double|unsigned|signed|struct|void)\b\s*\**\s*(\w+)'
)


def extract_variable_name_c(code: str) -> str | None:
    """C変数宣言から変数名を抽出する（型名の後の識別子）。"""
    m = _C_TYPES_PAT.search(code)
    return m.group(1) if m else None


_DEFINE_PAT = re.compile(r'#\s*define\s+(\w+)\s+')


def extract_define_name(code: str) -> str | None:
    """#define からマクロ名を抽出する。値のない #define は None を返す。"""
    m = _DEFINE_PAT.match(code)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# 間接参照追跡
# ---------------------------------------------------------------------------

def track_define(
    var_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """#define マクロ名の使用箇所を src_dir 配下の .c/.h/.pc ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    def_file = _resolve_source_file(record.filepath, src_dir)

    src_files = (sorted(src_dir.rglob("*.c"))
                 + sorted(src_dir.rglob("*.h"))
                 + sorted(src_dir.rglob("*.pc")))
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = _get_cached_lines(src_file, stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage_c(line.strip()),
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
                usage_type=classify_usage_c(line.strip()),
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
                usage_type=classify_usage_c(parsed["code"]),
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
    parser = argparse.ArgumentParser(description="純C grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="C ソースのルートディレクトリ")
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
                    var_name = extract_variable_name_c(record.code)
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

- [ ] **Step 4: ユニットテストが通ることを確認する**

```bash
python -m pytest tests/test_c_analyzer.py -v --tb=short
```
期待: `TestClassifyUsageC`（11件）、`TestExtractDefineName`（4件）、`TestExtractVariableNameC`（4件）= 19 passed

- [ ] **Step 5: コミット**

```bash
git add analyze_c.py tests/test_c_analyzer.py
git commit -m "feat: add analyze_c.py for plain C grep classification"
```

---

## Task 2: analyze_c.py E2E フィクスチャと E2E テスト

**Files:**
- Create: `tests/c/src/sample.c`
- Create: `tests/c/input/TARGET.grep`
- Create: `tests/c/expected/TARGET.tsv`
- Modify: `tests/test_c_analyzer.py`（E2E テストクラスを追加）

- [ ] **Step 1: フィクスチャディレクトリとソースを作成する**

```bash
mkdir -p tests/c/src tests/c/input tests/c/expected
```

`tests/c/src/sample.c`:
```c
/* sample.c - C E2E test fixture */
#define STATUS "TARGET"

int check_status(char *code) {
    if (strcmp(code, STATUS) == 0) {
        return 1;
    }
    return 0;
}
```

`tests/c/input/TARGET.grep`:
```
tests/c/src/sample.c:2:#define STATUS "TARGET"
```

- [ ] **Step 2: ツールを実行して期待 TSV を生成する**

```bash
python analyze_c.py \
  --source-dir tests/c/src \
  --input-dir  tests/c/input \
  --output-dir /tmp/c_out
cat /tmp/c_out/TARGET.tsv
```

期待（目視確認）:
- 直接1件: `sample.c:2` または `tests/c/src/sample.c:2`、`#define定数定義`
- 間接1件以上: STATUS が使われている行、`条件判定` 等

出力が正しければ:
```bash
cp /tmp/c_out/TARGET.tsv tests/c/expected/TARGET.tsv
```

- [ ] **Step 3: E2E テストを tests/test_c_analyzer.py に追加する**

`tests/test_c_analyzer.py` の末尾（`if __name__ == "__main__"` の前）に追加:

```python
class TestE2EC(unittest.TestCase):
    """E2E統合テスト: sample.c でツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "c"

    def test_e2e_target(self):
        src_dir      = self.TESTS_DIR / "src"
        input_dir    = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        ac._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ac.ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = ac.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = ac.extract_define_name(record.code)
                    if var_name:
                        all_records.extend(ac.track_define(var_name, src_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = ac.extract_variable_name_c(record.code)
                    if var_name:
                        candidate = Path(record.filepath)
                        if not candidate.is_absolute():
                            candidate = src_dir / record.filepath
                        if candidate.exists():
                            all_records.extend(
                                ac.track_variable(var_name, candidate,
                                                  int(record.lineno), src_dir, record, stats)
                            )

            output_path = output_dir / "TARGET.tsv"
            ac.write_tsv(all_records, output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )
```

- [ ] **Step 4: E2E テストが通ることを確認する**

```bash
python -m pytest tests/test_c_analyzer.py -v --tb=short
```
期待: 全テスト passed（19 unit + 1 E2E = 20 passed）

- [ ] **Step 5: コミット**

```bash
git add tests/c/ tests/test_c_analyzer.py
git commit -m "feat: add C E2E test fixtures"
```

---

## Task 3: analyze_proc.py 拡張子ディスパッチ対応

**Files:**
- Modify: `analyze_proc.py`（import 追加、`_classify_for_filepath` 追加、`process_grep_file` 修正）
- Modify: `test_analyze_proc.py`（`TestDispatch` クラス追加）

- [ ] **Step 1: 失敗するディスパッチテストを test_analyze_proc.py に追加する**

`test_analyze_proc.py` の末尾（`if __name__ == "__main__"` の前）に追加:

```python
class TestDispatch(unittest.TestCase):
    """拡張子ベースのディスパッチテスト"""

    def test_c_file_exec_sql_not_classified_as_exec_sql(self):
        """.c ファイルでは EXEC SQL が 'EXEC SQL文' に分類されない"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'src/main.c')
        self.assertNotEqual(result, "EXEC SQL文")

    def test_pc_file_exec_sql_classified(self):
        """.pc ファイルでは EXEC SQL が 'EXEC SQL文' に分類される"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'src/main.pc')
        self.assertEqual(result, "EXEC SQL文")

    def test_h_file_uses_c_classifier(self):
        """.h ファイルは C 分類を使う（EXEC SQL文にならない）"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'include/config.h')
        self.assertNotEqual(result, "EXEC SQL文")

    def test_unknown_ext_defaults_to_proc(self):
        """未知拡張子はデフォルトで Pro*C 分類（後方互換）"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'src/main.sqc')
        self.assertEqual(result, "EXEC SQL文")
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
python -m pytest test_analyze_proc.py::TestDispatch -v --tb=short 2>&1 | head -15
```
期待: `AttributeError: module 'analyze_proc' has no attribute '_classify_for_filepath'`

- [ ] **Step 3: analyze_proc.py を変更する**

ファイル先頭の import 部分を変更する:

```python
# 変更前:
from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv

# 変更後:
from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv
from analyze_c import classify_usage_c
```

`classify_usage_proc` 関数の直後（約 line 68 付近）に追加:

```python
def _classify_for_filepath(code: str, filepath: str) -> str:
    """ファイルパスの拡張子に基づいて適切な分類関数を呼び出す。"""
    ext = Path(filepath).suffix.lower()
    if ext in ('.c', '.h'):
        return classify_usage_c(code)
    return classify_usage_proc(code)
```

`process_grep_file` 内の `classify_usage_proc` 呼び出しを変更:

```python
# 変更前:
usage_type=classify_usage_proc(parsed["code"]),

# 変更後:
usage_type=_classify_for_filepath(parsed["code"], parsed["filepath"]),
```

- [ ] **Step 4: ディスパッチテストが通ることを確認する**

```bash
python -m pytest test_analyze_proc.py::TestDispatch -v --tb=short
```
期待: 4 passed

- [ ] **Step 5: 既存テストが壊れていないことを確認する**

```bash
python -m pytest test_analyze_proc.py -v --tb=short 2>&1 | tail -10
```
期待: 全テスト passed（35+ passed）

- [ ] **Step 6: コミット**

```bash
git add analyze_proc.py test_analyze_proc.py
git commit -m "feat: add extension-based dispatch to analyze_proc.py"
```

---

## Task 4: analyze_proc.py track_define の .c スキャン対応 + 混在 E2E

**Files:**
- Modify: `analyze_proc.py`（`track_define` の変更）
- Create: `tests/proc/src/sample_c.c`
- Create: `tests/proc/src/mixed.pc`
- Create: `tests/proc/input/MIXVAL.grep`
- Create: `tests/proc/expected/MIXVAL.tsv`
- Modify: `test_analyze_proc.py`（`TestE2EMixed` 追加）

- [ ] **Step 1: analyze_proc.py の track_define を変更する**

`analyze_proc.py` の `track_define` 関数内、`pc_files` の定義を変更する:

```python
# 変更前:
pc_files = sorted(src_dir.rglob("*.pc")) + sorted(src_dir.rglob("*.h"))

# 変更後:
pc_files = (sorted(src_dir.rglob("*.pc"))
            + sorted(src_dir.rglob("*.c"))
            + sorted(src_dir.rglob("*.h")))
```

同じ `track_define` 関数内の `GrepRecord` 生成部分の `usage_type` を変更する:

```python
# 変更前:
usage_type=classify_usage_proc(line.strip()),

# 変更後:
usage_type=_classify_for_filepath(line.strip(), str(pc_file)),
```

- [ ] **Step 2: 既存の Pro*C テストが引き続き通ることを確認する**

```bash
python -m pytest test_analyze_proc.py -v --tb=short 2>&1 | tail -10
```
期待: 全テスト passed

- [ ] **Step 3: 混在 E2E フィクスチャを作成する**

```bash
mkdir -p tests/proc/src  # 既存
```

`tests/proc/src/sample_c.c`:
```c
/* sample_c.c - mixed E2E fixture (plain C) */
#define MK_CODE "MIXVAL"

int check(char *code) {
    if (strcmp(code, MK_CODE) == 0) {
        return 1;
    }
    return 0;
}
```

`tests/proc/src/mixed.pc`:
```c
/* mixed.pc - mixed E2E fixture (Pro*C) */
void process_pc() {
    EXEC SQL SELECT col INTO :hv WHERE code = 'MIXVAL';
    if (strcmp(hv, MK_CODE) != 0) {
        return;
    }
}
```

`tests/proc/input/MIXVAL.grep`:
```
tests/proc/src/sample_c.c:2:#define MK_CODE "MIXVAL"
tests/proc/src/mixed.pc:3:    EXEC SQL SELECT col INTO :hv WHERE code = 'MIXVAL';
```

- [ ] **Step 4: ツールを実行して期待 TSV を生成する**

```bash
python analyze_proc.py \
  --source-dir tests/proc/src \
  --input-dir  tests/proc/input \
  --output-dir /tmp/proc_out
cat /tmp/proc_out/MIXVAL.tsv
```

目視確認ポイント:
- `sample_c.c:2` の行が `#define定数定義`（C分類）
- `mixed.pc:3` の行が `EXEC SQL文`（Pro*C分類）
- 間接レコードに `.c` の MK_CODE 使用箇所と `.pc` の MK_CODE 使用箇所が含まれる

正しければ:
```bash
cp /tmp/proc_out/MIXVAL.tsv tests/proc/expected/MIXVAL.tsv
```

- [ ] **Step 5: TestE2EMixed を test_analyze_proc.py に追加する**

`test_analyze_proc.py` の `TestDispatch` クラスの後に追加:

```python
class TestE2EMixed(unittest.TestCase):
    """混在E2Eテスト: .c と .pc が混在する grep ファイルの処理"""

    TESTS_DIR = Path(__file__).parent / "tests" / "proc"

    def test_e2e_mixval(self):
        """MIXVAL.grep を処理し、expected/MIXVAL.tsv と全行一致することを確認する"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "MIXVAL.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        ap._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ap.ProcessStats()
            keyword = "MIXVAL"
            grep_path = input_dir / "MIXVAL.grep"

            direct_records = ap.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = ap.extract_define_name(record.code)
                    if var_name:
                        all_records.extend(ap.track_define(var_name, src_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = ap.extract_variable_name_proc(record.code)
                    if not var_name:
                        var_name = ap.extract_host_var_name(record.code)
                    if var_name:
                        candidate = Path(record.filepath)
                        if not candidate.is_absolute():
                            candidate = src_dir / record.filepath
                        if candidate.exists():
                            all_records.extend(
                                ap.track_variable(var_name, candidate,
                                                  int(record.lineno), src_dir, record, stats)
                            )

            output_path = output_dir / "MIXVAL.tsv"
            ap.write_tsv(all_records, output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )
```

- [ ] **Step 6: 混在 E2E テストが通ることを確認する**

```bash
python -m pytest test_analyze_proc.py::TestE2EMixed -v --tb=short
```
期待: 1 passed

- [ ] **Step 7: 全テストが通ることを確認する**

```bash
python -m pytest test_analyze.py test_analyze_proc.py \
  tests/test_common.py tests/test_sql_analyzer.py \
  tests/test_sh_analyzer.py tests/test_c_analyzer.py \
  -v --tb=short 2>&1 | tail -10
```
期待: 全テスト passed

- [ ] **Step 8: コミット**

```bash
git add analyze_proc.py \
        tests/proc/src/sample_c.c tests/proc/src/mixed.pc \
        tests/proc/input/MIXVAL.grep tests/proc/expected/MIXVAL.tsv \
        test_analyze_proc.py
git commit -m "feat: extend track_define to scan .c files and add mixed E2E test"
```

---

## 完了チェック

- [ ] `analyze_c.py` が存在し、`classify_usage_c` が公開関数として定義されている
- [ ] `tests/test_c_analyzer.py` の全テスト（unit + E2E）が passed
- [ ] `analyze_proc.py` が `.c/.h` ファイルに対して C 分類を適用する
- [ ] `analyze_proc.py` の `track_define` が `.c/.h/.pc` をスキャンする
- [ ] 混在 E2E テスト（`TestE2EMixed`）が passed
- [ ] `analyze_c.py --source-dir / --input-dir / --output-dir` で単独動作可能
- [ ] 既存の全テスト（`test_analyze.py`、`test_analyze_proc.py` 等）が引き続き passed
