# Language Extensions + Groovy Setter Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TypeScript/JS, Python, Perl, C#/VB.NET, and Groovy analyzers, plus Groovy setter tracking; Java setter tracking is already implemented.

**Architecture:** Each new analyzer follows the `analyze_kotlin.py` / `analyze_plsql.py` pattern: `classify_usage_<lang>()`, `process_grep_file()`, `build_parser()`, `main()`, plus `_file_cache` and `detect_encoding()`. Groovy additionally implements indirect tracking (static final constants + class fields) and setter tracking. Dotnet implements constant + readonly field indirect tracking. TS/JS, Python, Perl are direct-reference only.

**Tech Stack:** Python 3.11+, `analyze_common` (GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv), unittest, javalang (Java only — not used in new analyzers)

**IMPORTANT — Java setter tracking:** `find_setter_names`, `track_setter_calls`, `_batch_track_setters` are **already implemented** in `analyze.py` and integrated in `main()`. Task 7 (Java setter verification) confirms this is working — no new code needed.

---

## File Map

| Action | File |
|--------|------|
| Create | `analyze_ts.py` |
| Create | `analyze_python.py` |
| Create | `analyze_perl.py` |
| Create | `analyze_dotnet.py` |
| Create | `analyze_groovy.py` |
| Create | `tests/ts/input/TARGET.grep` |
| Create | `tests/ts/src/sample.ts` |
| Create | `tests/ts/src/sample.js` |
| Create | `tests/ts/expected/TARGET.tsv` |
| Create | `tests/test_ts_analyzer.py` |
| Create | `tests/python/input/TARGET.grep` |
| Create | `tests/python/src/sample.py` |
| Create | `tests/python/expected/TARGET.tsv` |
| Create | `tests/test_python_analyzer.py` |
| Create | `tests/perl/input/TARGET.grep` |
| Create | `tests/perl/src/sample.pl` |
| Create | `tests/perl/expected/TARGET.tsv` |
| Create | `tests/test_perl_analyzer.py` |
| Create | `tests/dotnet/input/TARGET.grep` |
| Create | `tests/dotnet/src/sample.cs` |
| Create | `tests/dotnet/src/sample.vb` |
| Create | `tests/dotnet/expected/TARGET.tsv` |
| Create | `tests/test_dotnet_analyzer.py` |
| Create | `tests/groovy/input/TARGET.grep` |
| Create | `tests/groovy/src/sample.groovy` |
| Create | `tests/groovy/expected/TARGET.tsv` |
| Create | `tests/test_groovy_analyzer.py` |
| Modify | `docs/product-requirements.md` |
| Modify | `docs/architecture.md` |
| Modify | `docs/repository-structure.md` |
| Modify | `docs/functional-design.md` |
| Modify | `docs/development-guidelines.md` |
| Modify | `docs/glossary.md` |

---

### Task 1: TypeScript/JavaScript Analyzer (direct only)

**Files:**
- Create: `analyze_ts.py`
- Create: `tests/ts/input/TARGET.grep`
- Create: `tests/ts/src/sample.ts`
- Create: `tests/ts/src/sample.js`
- Create: `tests/ts/expected/TARGET.tsv`
- Create: `tests/test_ts_analyzer.py`

- [ ] **Step 1: Create fixture files**

`tests/ts/src/sample.ts`:
```typescript
// sample.ts - TS/JS E2E test fixture
const STATUS = "TARGET";
let alias = STATUS;
if (alias === STATUS) {
    return STATUS;
}
```

`tests/ts/src/sample.js`:
```javascript
// sample.js - TS/JS E2E test fixture
function check(code) {
    process(STATUS);
}
```

`tests/ts/input/TARGET.grep`:
```
tests/ts/src/sample.ts:2:const STATUS = "TARGET";
tests/ts/src/sample.js:3:    process(STATUS);
```

- [ ] **Step 2: Write failing tests**

`tests/test_ts_analyzer.py`:
```python
import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_ts as at


class TestClassifyUsageTs(unittest.TestCase):
    def test_const_def(self):
        self.assertEqual(at.classify_usage_ts('const STATUS = "TARGET"'), "const定数定義")

    def test_let_assignment(self):
        self.assertEqual(at.classify_usage_ts('let x = STATUS'), "変数代入(let/var)")

    def test_var_assignment(self):
        self.assertEqual(at.classify_usage_ts('var x = STATUS'), "変数代入(let/var)")

    def test_if_condition(self):
        self.assertEqual(at.classify_usage_ts('if (code === STATUS)'), "条件判定")

    def test_switch_condition(self):
        self.assertEqual(at.classify_usage_ts('switch (STATUS)'), "条件判定")

    def test_return(self):
        self.assertEqual(at.classify_usage_ts('return STATUS'), "return文")

    def test_decorator(self):
        self.assertEqual(at.classify_usage_ts('@Component'), "デコレータ")

    def test_function_arg(self):
        self.assertEqual(at.classify_usage_ts('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(at.classify_usage_ts('STATUS'), "その他")


class TestE2ETs(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "ts"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        at._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = at.ProcessStats()
            grep_path = input_dir / "TARGET.grep"

            direct_records = at.process_grep_file(grep_path, "TARGET", src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            at.write_tsv(list(direct_records), output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to confirm failure**

```
python -m pytest tests/test_ts_analyzer.py -v
```
Expected: `ModuleNotFoundError: No module named 'analyze_ts'`

- [ ] **Step 4: Implement `analyze_ts.py`**

```python
# analyze_ts.py
"""TypeScript / JavaScript grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv

_TS_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\s+\w+\s*='),                          "const定数定義"),
    (re.compile(r'\b(?:let|var)\s+\w+\s*='),                    "変数代入(let/var)"),
    (re.compile(r'\bif\s*\(|\bswitch\s*\(|===|!==|==(?!=)|!=(?!=)'), "条件判定"),
    (re.compile(r'\breturn\b'),                                  "return文"),
    (re.compile(r'@\w+'),                                        "デコレータ"),
    (re.compile(r'\w+\s*\('),                                    "関数引数"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def classify_usage_ts(code: str) -> str:
    """TypeScript/JavaScriptコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _TS_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    enc = detect_encoding(path, encoding_override)
    with open(path, encoding=enc, errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_ts(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TypeScript/JavaScript grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None)
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
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats, args.encoding)
            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(list(direct_records), output_path)
            processed_files.append(grep_path.name)
            print(f"  {grep_path.name} → {output_path} (直接: {len(direct_records)} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Generate expected TSV**

Run once to capture expected output:
```bash
mkdir -p tests/ts/expected
python -c "
import sys; sys.path.insert(0,'.')
import analyze_ts as at
from pathlib import Path
stats = at.ProcessStats()
recs = at.process_grep_file(Path('tests/ts/input/TARGET.grep'), 'TARGET', Path('tests/ts/src'), stats)
at.write_tsv(list(recs), Path('tests/ts/expected/TARGET.tsv'))
print('done')
"
```
Then verify the file contents look correct:
```bash
cat tests/ts/expected/TARGET.tsv
```
Expected: header row + 2 data rows (sample.ts line 2 = const定数定義, sample.js line 3 = 関数引数)

- [ ] **Step 6: Run tests to confirm pass**

```
python -m pytest tests/test_ts_analyzer.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add analyze_ts.py tests/ts/ tests/test_ts_analyzer.py
git commit -m "feat: add analyze_ts.py with TypeScript/JS direct-reference analyzer"
```

---

### Task 2: Python Analyzer (direct only)

**Files:**
- Create: `analyze_python.py`
- Create: `tests/python/input/TARGET.grep`
- Create: `tests/python/src/sample.py`
- Create: `tests/python/expected/TARGET.tsv`
- Create: `tests/test_python_analyzer.py`

- [ ] **Step 1: Create fixture files**

`tests/python/src/sample.py`:
```python
# sample.py - Python E2E test fixture
STATUS = "TARGET"
if code == STATUS:
    return STATUS
```

`tests/python/input/TARGET.grep`:
```
tests/python/src/sample.py:2:STATUS = "TARGET"
tests/python/src/sample.py:3:if code == STATUS:
```

- [ ] **Step 2: Write failing tests**

`tests/test_python_analyzer.py`:
```python
import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_python as ap


class TestClassifyUsagePython(unittest.TestCase):
    def test_assignment(self):
        self.assertEqual(ap.classify_usage_python('STATUS = "TARGET"'), "変数代入")

    def test_indented_assignment(self):
        self.assertEqual(ap.classify_usage_python('    x = STATUS'), "変数代入")

    def test_if_condition(self):
        self.assertEqual(ap.classify_usage_python('if code == STATUS:'), "条件判定")

    def test_elif_condition(self):
        self.assertEqual(ap.classify_usage_python('elif STATUS in values:'), "条件判定")

    def test_return(self):
        self.assertEqual(ap.classify_usage_python('return STATUS'), "return文")

    def test_decorator(self):
        self.assertEqual(ap.classify_usage_python('@property'), "デコレータ")

    def test_function_arg(self):
        self.assertEqual(ap.classify_usage_python('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(ap.classify_usage_python('STATUS'), "その他")


class TestE2EPython(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "python"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        ap._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ap.ProcessStats()
            grep_path = input_dir / "TARGET.grep"

            direct_records = ap.process_grep_file(grep_path, "TARGET", src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            ap.write_tsv(list(direct_records), output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to confirm failure**

```
python -m pytest tests/test_python_analyzer.py -v
```
Expected: `ModuleNotFoundError: No module named 'analyze_python'`

- [ ] **Step 4: Implement `analyze_python.py`**

```python
# analyze_python.py
"""Python grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv

_PYTHON_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^\s*\w+\s*='),                          "変数代入"),
    (re.compile(r'\bif\b|\belif\b|==|!=|\bin\b'),         "条件判定"),
    (re.compile(r'\breturn\b'),                            "return文"),
    (re.compile(r'@\w+'),                                  "デコレータ"),
    (re.compile(r'\w+\s*\('),                              "関数引数"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def classify_usage_python(code: str) -> str:
    """Pythonコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PYTHON_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    enc = detect_encoding(path, encoding_override)
    with open(path, encoding=enc, errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_python(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Python grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None)
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
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats, args.encoding)
            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(list(direct_records), output_path)
            processed_files.append(grep_path.name)
            print(f"  {grep_path.name} → {output_path} (直接: {len(direct_records)} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Generate expected TSV**

```bash
mkdir -p tests/python/expected
python -c "
import sys; sys.path.insert(0,'.')
import analyze_python as ap
from pathlib import Path
stats = ap.ProcessStats()
recs = ap.process_grep_file(Path('tests/python/input/TARGET.grep'), 'TARGET', Path('tests/python/src'), stats)
ap.write_tsv(list(recs), Path('tests/python/expected/TARGET.tsv'))
print('done')
"
cat tests/python/expected/TARGET.tsv
```
Expected: 2 rows — line 2 = 変数代入, line 3 = 条件判定

- [ ] **Step 6: Run tests to confirm pass**

```
python -m pytest tests/test_python_analyzer.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add analyze_python.py tests/python/ tests/test_python_analyzer.py
git commit -m "feat: add analyze_python.py with Python direct-reference analyzer"
```

---

### Task 3: Perl Analyzer (direct only)

**Files:**
- Create: `analyze_perl.py`
- Create: `tests/perl/input/TARGET.grep`
- Create: `tests/perl/src/sample.pl`
- Create: `tests/perl/expected/TARGET.tsv`
- Create: `tests/test_perl_analyzer.py`

- [ ] **Step 1: Create fixture files**

`tests/perl/src/sample.pl`:
```perl
# sample.pl - Perl E2E test fixture
use constant STATUS => "TARGET";
my $code = STATUS;
if ($code eq STATUS) {
    print STATUS;
}
```

`tests/perl/input/TARGET.grep`:
```
tests/perl/src/sample.pl:2:use constant STATUS => "TARGET";
tests/perl/src/sample.pl:3:my $code = STATUS;
tests/perl/src/sample.pl:5:    print STATUS;
```

- [ ] **Step 2: Write failing tests**

`tests/test_perl_analyzer.py`:
```python
import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_perl as ap


class TestClassifyUsagePerl(unittest.TestCase):
    def test_use_constant(self):
        self.assertEqual(ap.classify_usage_perl('use constant STATUS => "TARGET";'), "use constant定義")

    def test_scalar_assignment(self):
        self.assertEqual(ap.classify_usage_perl('$code = STATUS;'), "変数代入")

    def test_my_assignment(self):
        self.assertEqual(ap.classify_usage_perl('my $x = STATUS;'), "変数代入")

    def test_our_assignment(self):
        self.assertEqual(ap.classify_usage_perl('our $x = STATUS;'), "変数代入")

    def test_if_condition(self):
        self.assertEqual(ap.classify_usage_perl('if ($code eq STATUS)'), "条件判定")

    def test_unless_condition(self):
        self.assertEqual(ap.classify_usage_perl('unless ($x == STATUS)'), "条件判定")

    def test_print(self):
        self.assertEqual(ap.classify_usage_perl('print STATUS;'), "print/say出力")

    def test_say(self):
        self.assertEqual(ap.classify_usage_perl('say STATUS;'), "print/say出力")

    def test_printf(self):
        self.assertEqual(ap.classify_usage_perl('printf "%s", STATUS;'), "print/say出力")

    def test_function_arg(self):
        self.assertEqual(ap.classify_usage_perl('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(ap.classify_usage_perl('STATUS'), "その他")


class TestE2EPerl(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "perl"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        ap._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ap.ProcessStats()
            grep_path = input_dir / "TARGET.grep"

            direct_records = ap.process_grep_file(grep_path, "TARGET", src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            ap.write_tsv(list(direct_records), output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to confirm failure**

```
python -m pytest tests/test_perl_analyzer.py -v
```
Expected: `ModuleNotFoundError: No module named 'analyze_perl'`

- [ ] **Step 4: Implement `analyze_perl.py`**

```python
# analyze_perl.py
"""Perl grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv

_PERL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\buse\s+constant\b'),                          "use constant定義"),
    (re.compile(r'\$\w+\s*=|\bmy\b.*=|\bour\b.*='),             "変数代入"),
    (re.compile(r'\bif\s*\(|\bunless\s*\(|==|\bne\b|\beq\b'),   "条件判定"),
    (re.compile(r'\bprint\b|\bsay\b|\bprintf\b'),                "print/say出力"),
    (re.compile(r'\w+\s*\('),                                    "関数引数"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def classify_usage_perl(code: str) -> str:
    """Perlコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PERL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    enc = detect_encoding(path, encoding_override)
    with open(path, encoding=enc, errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_perl(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Perl grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None)
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
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats, args.encoding)
            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(list(direct_records), output_path)
            processed_files.append(grep_path.name)
            print(f"  {grep_path.name} → {output_path} (直接: {len(direct_records)} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Generate expected TSV**

```bash
mkdir -p tests/perl/expected
python -c "
import sys; sys.path.insert(0,'.')
import analyze_perl as ap
from pathlib import Path
stats = ap.ProcessStats()
recs = ap.process_grep_file(Path('tests/perl/input/TARGET.grep'), 'TARGET', Path('tests/perl/src'), stats)
ap.write_tsv(list(recs), Path('tests/perl/expected/TARGET.tsv'))
print('done')
"
cat tests/perl/expected/TARGET.tsv
```
Expected: 3 rows — line 2 = use constant定義, line 3 = 変数代入, line 5 = print/say出力

- [ ] **Step 6: Run tests to confirm pass**

```
python -m pytest tests/test_perl_analyzer.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add analyze_perl.py tests/perl/ tests/test_perl_analyzer.py
git commit -m "feat: add analyze_perl.py with Perl direct-reference analyzer"
```

---

### Task 4: .NET Analyzer (direct + indirect const/readonly)

**Files:**
- Create: `analyze_dotnet.py`
- Create: `tests/dotnet/input/TARGET.grep`
- Create: `tests/dotnet/src/sample.cs`
- Create: `tests/dotnet/src/sample.vb`
- Create: `tests/dotnet/expected/TARGET.tsv`
- Create: `tests/test_dotnet_analyzer.py`

- [ ] **Step 1: Create fixture files**

`tests/dotnet/src/sample.cs`:
```csharp
// sample.cs - .NET E2E test fixture
public class StatusCodes {
    public const string STATUS = "TARGET";
    public static readonly string ALIAS = STATUS;
}
public class Service {
    public void Check(string code) {
        if (code == StatusCodes.STATUS) {
            return;
        }
    }
}
```

`tests/dotnet/src/sample.vb`:
```vb
' sample.vb - .NET E2E test fixture
Module StatusModule
    Const STATUS As String = "TARGET"
    Dim alias As String = STATUS
End Module
```

`tests/dotnet/input/TARGET.grep`:
```
tests/dotnet/src/sample.cs:3:    public const string STATUS = "TARGET";
```

- [ ] **Step 2: Write failing tests**

`tests/test_dotnet_analyzer.py`:
```python
import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_dotnet as ad


class TestClassifyUsageDotnet(unittest.TestCase):
    def test_cs_const(self):
        self.assertEqual(ad.classify_usage_dotnet('public const string STATUS = "TARGET";'), "定数定義(Const/readonly)")

    def test_cs_readonly(self):
        self.assertEqual(ad.classify_usage_dotnet('public static readonly string ALIAS = STATUS;'), "定数定義(Const/readonly)")

    def test_vb_const(self):
        self.assertEqual(ad.classify_usage_dotnet('Const STATUS As String = "TARGET"'), "定数定義(Const/readonly)")

    def test_cs_var_assignment(self):
        self.assertEqual(ad.classify_usage_dotnet('string code = STATUS;'), "変数代入")

    def test_cs_var_keyword(self):
        self.assertEqual(ad.classify_usage_dotnet('var x = STATUS;'), "変数代入")

    def test_vb_dim(self):
        self.assertEqual(ad.classify_usage_dotnet('Dim x As String = STATUS'), "変数代入")

    def test_cs_if(self):
        self.assertEqual(ad.classify_usage_dotnet('if (code == STATUS)'), "条件判定")

    def test_vb_if(self):
        self.assertEqual(ad.classify_usage_dotnet('If code = STATUS Then'), "条件判定")

    def test_cs_return(self):
        self.assertEqual(ad.classify_usage_dotnet('return STATUS;'), "return文")

    def test_vb_return(self):
        self.assertEqual(ad.classify_usage_dotnet('Return STATUS'), "return文")

    def test_cs_attribute(self):
        self.assertEqual(ad.classify_usage_dotnet('[Obsolete]'), "属性(Attribute)")

    def test_vb_attribute(self):
        self.assertEqual(ad.classify_usage_dotnet('<Serializable>'), "属性(Attribute)")

    def test_method_arg(self):
        self.assertEqual(ad.classify_usage_dotnet('Process(STATUS)'), "メソッド引数")

    def test_other(self):
        self.assertEqual(ad.classify_usage_dotnet('STATUS'), "その他")


class TestExtractConstNameDotnet(unittest.TestCase):
    def test_cs_const(self):
        self.assertEqual(ad.extract_const_name_dotnet('public const string STATUS = "TARGET";'), "STATUS")

    def test_cs_public_static_readonly(self):
        self.assertEqual(ad.extract_const_name_dotnet('public static readonly string ALIAS = STATUS;'), "ALIAS")

    def test_cs_private_static_readonly(self):
        self.assertEqual(ad.extract_const_name_dotnet('private static readonly int COUNT = 1;'), "COUNT")

    def test_vb_const(self):
        self.assertEqual(ad.extract_const_name_dotnet('Const STATUS As String = "TARGET"'), "STATUS")

    def test_no_match(self):
        self.assertIsNone(ad.extract_const_name_dotnet('string x = STATUS;'))


class TestTrackConstDotnet(unittest.TestCase):
    def test_finds_usages_in_cs_and_vb(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Codes.cs").write_text('public const string STATUS = "TARGET";\n')
            (src / "Service.cs").write_text('if (code == STATUS) { return; }\n')
            (src / "Module.vb").write_text('Dim x As String = STATUS\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="定数定義(Const/readonly)",
                filepath=str(src / "Codes.cs"),
                lineno="1",
                code='public const string STATUS = "TARGET";',
            )
            stats = ProcessStats()
            ad._file_cache.clear()
            results = ad.track_const_dotnet("STATUS", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.cs" in fp for fp in filepaths))
            self.assertTrue(any("Module.vb" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_skips_definition_line(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Codes.cs").write_text('public const string STATUS = "TARGET";\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="定数定義(Const/readonly)",
                filepath=str(src / "Codes.cs"),
                lineno="1",
                code='public const string STATUS = "TARGET";',
            )
            stats = ProcessStats()
            ad._file_cache.clear()
            results = ad.track_const_dotnet("STATUS", src, record, stats)
            self.assertEqual(results, [])


class TestE2EDotnet(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "dotnet"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        ad._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ad.ProcessStats()
            grep_path = input_dir / "TARGET.grep"
            keyword = "TARGET"

            direct_records = ad.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "定数定義(Const/readonly)":
                    const_name = ad.extract_const_name_dotnet(record.code)
                    if const_name:
                        all_records.extend(ad.track_const_dotnet(const_name, src_dir, record, stats))

            output_path = output_dir / "TARGET.tsv"
            ad.write_tsv(all_records, output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to confirm failure**

```
python -m pytest tests/test_dotnet_analyzer.py -v
```
Expected: `ModuleNotFoundError: No module named 'analyze_dotnet'`

- [ ] **Step 4: Implement `analyze_dotnet.py`**

```python
# analyze_dotnet.py
"""C# / VB.NET grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv

_DOTNET_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\b|\bConst\b|\breadonly\b'),                           "定数定義(Const/readonly)"),
    (re.compile(r'\b(?:var|string|int|String)\s+\w+\s*=|\bDim\b.*='),          "変数代入"),
    (re.compile(r'\bif\s*\(|\bIf\b|==|!=|<>|\.Equals\s*\('),                  "条件判定"),
    (re.compile(r'\breturn\b|\bReturn\b'),                                       "return文"),
    (re.compile(r'^\s*\[[\w]+|^\s*<[\w]+'),                                     "属性(Attribute)"),
    (re.compile(r'\w+\s*\('),                                                    "メソッド引数"),
]

_DOTNET_EXTENSIONS = (".cs", ".vb")

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800

_CS_CONST_PATS = [
    re.compile(r'\bconst\s+\w[\w<>]*\s+(\w+)\s*='),
    re.compile(r'\bpublic\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*='),
    re.compile(r'\bprivate\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*='),
]
_VB_CONST_PAT = re.compile(r'\bConst\s+(\w+)\s+As\b')


def _get_cached_lines(
    filepath: str | Path,
    stats: ProcessStats | None = None,
    encoding_override: str | None = None,
) -> list[str]:
    path = Path(filepath)
    enc = detect_encoding(path, encoding_override)
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            _file_cache[key] = path.read_text(encoding=enc, errors="replace").splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]


def classify_usage_dotnet(code: str) -> str:
    """C#/VB.NETコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _DOTNET_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_const_name_dotnet(code: str) -> str | None:
    """C# const/static readonly または VB Const 宣言から定数名を抽出する。"""
    for pat in _CS_CONST_PATS:
        m = pat.search(code)
        if m:
            return m.group(1)
    m = _VB_CONST_PAT.search(code)
    return m.group(1) if m else None


def track_const_dotnet(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """定数の使用箇所を src_dir 配下の .cs / .vb ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = Path(record.filepath)

    src_files: list[Path] = []
    for ext in _DOTNET_EXTENSIONS:
        src_files.extend(sorted(src_dir.rglob(f"*{ext}")))

    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = _get_cached_lines(src_file, stats, encoding_override)
        for i, line in enumerate(lines, 1):
            if src_file.resolve() == def_file.resolve() and i == int(record.lineno):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage_dotnet(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=const_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    enc = detect_encoding(path, encoding_override)
    with open(path, encoding=enc, errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_dotnet(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C#/VB.NET grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None)
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
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats, args.encoding)
            all_records: list[GrepRecord] = list(direct_records)

            for record in direct_records:
                if record.usage_type == "定数定義(Const/readonly)":
                    const_name = extract_const_name_dotnet(record.code)
                    if const_name:
                        all_records.extend(track_const_dotnet(const_name, source_dir, record, stats, args.encoding))

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} (直接: {direct_count} 件, 間接: {indirect_count} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Generate expected TSV**

```bash
mkdir -p tests/dotnet/expected
python -c "
import sys; sys.path.insert(0,'.')
import analyze_dotnet as ad
from pathlib import Path
stats = ad.ProcessStats()
src_dir = Path('tests/dotnet/src')
grep_path = Path('tests/dotnet/input/TARGET.grep')
direct = ad.process_grep_file(grep_path, 'TARGET', src_dir, stats)
all_records = list(direct)
for r in direct:
    if r.usage_type == '定数定義(Const/readonly)':
        n = ad.extract_const_name_dotnet(r.code)
        if n:
            all_records.extend(ad.track_const_dotnet(n, src_dir, r, stats))
ad.write_tsv(all_records, Path('tests/dotnet/expected/TARGET.tsv'))
print('done')
"
cat tests/dotnet/expected/TARGET.tsv
```
Expected: 1 direct row (sample.cs:3 = 定数定義) + indirect rows for STATUS in sample.cs:4 (変数代入), sample.cs:8 (条件判定), sample.vb:3 (変数代入)

- [ ] **Step 6: Run tests to confirm pass**

```
python -m pytest tests/test_dotnet_analyzer.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add analyze_dotnet.py tests/dotnet/ tests/test_dotnet_analyzer.py
git commit -m "feat: add analyze_dotnet.py with C#/VB.NET analyzer and const indirect tracking"
```

---

### Task 5: Groovy Analyzer (direct + indirect + setter tracking)

**Files:**
- Create: `analyze_groovy.py`
- Create: `tests/groovy/input/TARGET.grep`
- Create: `tests/groovy/src/sample.groovy`
- Create: `tests/groovy/expected/TARGET.tsv`
- Create: `tests/test_groovy_analyzer.py`

- [ ] **Step 1: Create fixture files**

`tests/groovy/src/sample.groovy`:
```groovy
// sample.groovy - Groovy E2E test fixture
class StatusCodes {
    static final String STATUS = "TARGET"
    private String type = STATUS

    void setType(String value) {
        this.type = value
    }

    String getType() {
        return this.type
    }

    void check(String code) {
        if (code == STATUS) {
            return
        }
    }
}

class Service {
    void process(StatusCodes sc) {
        sc.setType(StatusCodes.STATUS)
        if (sc.getType() == StatusCodes.STATUS) {
            return
        }
    }
}
```

`tests/groovy/input/TARGET.grep`:
```
tests/groovy/src/sample.groovy:3:    static final String STATUS = "TARGET"
```

- [ ] **Step 2: Write failing tests**

`tests/test_groovy_analyzer.py`:
```python
import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_groovy as ag


class TestClassifyUsageGroovy(unittest.TestCase):
    def test_static_final(self):
        self.assertEqual(ag.classify_usage_groovy('static final String STATUS = "TARGET"'), "static final定数定義")

    def test_def_assignment(self):
        self.assertEqual(ag.classify_usage_groovy('def code = STATUS'), "変数代入")

    def test_typed_assignment(self):
        self.assertEqual(ag.classify_usage_groovy('String x = STATUS'), "変数代入")

    def test_if_condition(self):
        self.assertEqual(ag.classify_usage_groovy('if (code == STATUS)'), "条件判定")

    def test_switch_condition(self):
        self.assertEqual(ag.classify_usage_groovy('switch (STATUS)'), "条件判定")

    def test_return(self):
        self.assertEqual(ag.classify_usage_groovy('return STATUS'), "return文")

    def test_annotation(self):
        self.assertEqual(ag.classify_usage_groovy('@Canonical'), "アノテーション")

    def test_method_arg(self):
        self.assertEqual(ag.classify_usage_groovy('process(STATUS)'), "メソッド引数")

    def test_other(self):
        self.assertEqual(ag.classify_usage_groovy('STATUS'), "その他")


class TestExtractStaticFinalName(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ag.extract_static_final_name('static final String STATUS = "TARGET"'), "STATUS")

    def test_with_access_modifier(self):
        self.assertEqual(ag.extract_static_final_name('public static final String CODE = "TARGET"'), "CODE")

    def test_no_match(self):
        self.assertIsNone(ag.extract_static_final_name('def x = STATUS'))


class TestIsClassLevelField(unittest.TestCase):
    def test_private_field(self):
        self.assertTrue(ag.is_class_level_field('private String type = STATUS'))

    def test_protected_field(self):
        self.assertTrue(ag.is_class_level_field('protected int count = 0'))

    def test_public_field(self):
        self.assertTrue(ag.is_class_level_field('public String name = "x"'))

    def test_def_field(self):
        self.assertTrue(ag.is_class_level_field('def code = STATUS'))

    def test_local_var_not_field(self):
        self.assertFalse(ag.is_class_level_field('    def code = STATUS'))


class TestFindGetterNamesGroovy(unittest.TestCase):
    def test_convention(self):
        names = ag.find_getter_names_groovy("type", [
            "String getType() {",
            "    return this.type",
            "}",
        ])
        self.assertIn("getType", names)

    def test_non_standard_getter(self):
        names = ag.find_getter_names_groovy("type", [
            "String fetchType() {",
            "    return type",
            "}",
        ])
        self.assertIn("fetchType", names)


class TestFindSetterNamesGroovy(unittest.TestCase):
    def test_convention(self):
        names = ag.find_setter_names_groovy("type", [
            "void setType(String v) {",
            "    this.type = v",
            "}",
        ])
        self.assertIn("setType", names)

    def test_non_standard_setter(self):
        names = ag.find_setter_names_groovy("type", [
            "void assignType(String v) {",
            "    type = v",
            "}",
        ])
        self.assertIn("assignType", names)


class TestTrackStaticFinalGroovy(unittest.TestCase):
    def test_finds_usages_in_groovy_files(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Codes.groovy").write_text('static final String STATUS = "TARGET"\n')
            (src / "Service.groovy").write_text('if (code == STATUS) { return }\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="static final定数定義",
                filepath=str(src / "Codes.groovy"),
                lineno="1",
                code='static final String STATUS = "TARGET"',
            )
            stats = ProcessStats()
            ag._file_cache.clear()
            results = ag.track_static_final_groovy("STATUS", src, record, stats)
            self.assertTrue(any("Service.groovy" in r.filepath for r in results))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))


class TestE2EGroovy(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "groovy"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        ag._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ag.ProcessStats()
            grep_path = input_dir / "TARGET.grep"
            keyword = "TARGET"

            direct_records = ag.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "static final定数定義":
                    const_name = ag.extract_static_final_name(record.code)
                    if const_name:
                        all_records.extend(ag.track_static_final_groovy(const_name, src_dir, record, stats))

            output_path = output_dir / "TARGET.tsv"
            ag.write_tsv(all_records, output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to confirm failure**

```
python -m pytest tests/test_groovy_analyzer.py -v
```
Expected: `ModuleNotFoundError: No module named 'analyze_groovy'`

- [ ] **Step 4: Implement `analyze_groovy.py`**

```python
# analyze_groovy.py
"""Groovy grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv

_GROOVY_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bstatic\s+final\b'),                                              "static final定数定義"),
    (re.compile(r'\bdef\s+\w+\s*=|[\w<>\[\]]+\s+\w+\s*='),                          "変数代入"),
    (re.compile(r'\bif\s*\(|\bswitch\s*\(|==|!=|\.equals\s*\('),                    "条件判定"),
    (re.compile(r'\breturn\b'),                                                       "return文"),
    (re.compile(r'@\w+'),                                                             "アノテーション"),
    (re.compile(r'\w+\s*\('),                                                         "メソッド引数"),
]

_GROOVY_EXTENSIONS = (".groovy", ".gvy")

_STATIC_FINAL_PAT = re.compile(
    r'\bstatic\s+final\s+\w[\w<>]*\s+(\w+)\s*='
)
_CLASS_FIELD_PAT = re.compile(
    r'^(?:private|protected|public|def)\s+\w[\w<>]*\s+\w+\s*[=;]'
)
_GETTER_RETURN_PAT = re.compile(r'\breturn\s+(?:this\.)?(\w+)')
_SETTER_ASSIGN_PAT = re.compile(r'(?:this\.)?(\w+)\s*=\s*\w+')
_METHOD_DEF_PAT    = re.compile(r'\b(?:def|void|\w+)\s+(\w+)\s*\(')

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def _get_cached_lines(
    filepath: str | Path,
    stats: ProcessStats | None = None,
    encoding_override: str | None = None,
) -> list[str]:
    path = Path(filepath)
    enc = detect_encoding(path, encoding_override)
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            _file_cache[key] = path.read_text(encoding=enc, errors="replace").splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]


def classify_usage_groovy(code: str) -> str:
    """Groovyコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _GROOVY_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_static_final_name(code: str) -> str | None:
    """static final 定義から定数名を抽出する。"""
    m = _STATIC_FINAL_PAT.search(code)
    return m.group(1) if m else None


def is_class_level_field(code: str) -> bool:
    """クラスレベルのフィールド宣言かどうかを判定する（インデントなしの行）。"""
    return bool(_CLASS_FIELD_PAT.match(code.strip())) and not code.startswith((' ', '\t'))


def _extract_method_body(lines: list[str], method_start: int) -> list[str]:
    """method_start（0-indexed）から対応する `}` までの行を返す。"""
    depth = 0
    body: list[str] = []
    for line in lines[method_start:]:
        body.append(line)
        depth += line.count('{') - line.count('}')
        if depth <= 0 and len(body) > 1:
            break
    return body


def find_getter_names_groovy(field_name: str, class_lines: list[str]) -> list[str]:
    """正規表現でgetterメソッド名候補を返す（2方式）。"""
    candidates = ["get" + field_name[0].upper() + field_name[1:]]
    current_method: str | None = None
    method_start = 0

    for i, line in enumerate(class_lines):
        m = _METHOD_DEF_PAT.search(line)
        if m and '{' in line:
            current_method = m.group(1)
            method_start = i
        if current_method and _GETTER_RETURN_PAT.search(line):
            rm = _GETTER_RETURN_PAT.search(line)
            if rm and rm.group(1) == field_name:
                candidates.append(current_method)

    return list(set(candidates))


def find_setter_names_groovy(field_name: str, class_lines: list[str]) -> list[str]:
    """正規表現でsetterメソッド名候補を返す（2方式）。"""
    candidates = ["set" + field_name[0].upper() + field_name[1:]]
    current_method: str | None = None

    for line in class_lines:
        m = _METHOD_DEF_PAT.search(line)
        if m and '{' in line:
            current_method = m.group(1)
        if current_method and _SETTER_ASSIGN_PAT.search(line):
            am = _SETTER_ASSIGN_PAT.search(line)
            if am and am.group(1) == field_name:
                candidates.append(current_method)

    return list(set(candidates))


def track_static_final_groovy(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """static final 定数の使用箇所を src_dir 配下の .groovy/.gvy ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = Path(record.filepath)

    src_files: list[Path] = []
    for ext in _GROOVY_EXTENSIONS:
        src_files.extend(sorted(src_dir.rglob(f"*{ext}")))

    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = _get_cached_lines(src_file, stats, encoding_override)
        for i, line in enumerate(lines, 1):
            if src_file.resolve() == def_file.resolve() and i == int(record.lineno):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage_groovy(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=const_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def track_field_groovy(
    field_name: str,
    src_file: Path,
    record: GrepRecord,
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """同一ファイル内でフィールド使用箇所を追跡し、getter/setter もバッチリストに返す。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(field_name) + r'\b')
    lines = _get_cached_lines(src_file, stats, encoding_override)

    try:
        filepath_str = str(src_file.relative_to(src_dir))
    except ValueError:
        filepath_str = str(src_file)

    for i, line in enumerate(lines, 1):
        if i == int(record.lineno):
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_groovy(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=field_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


def _batch_track_getter_setter_groovy(
    getter_tasks: dict[str, list[GrepRecord]],
    setter_tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """getter/setter をプロジェクト全体に対して1パスで一括スキャンする。"""
    all_tasks = {**getter_tasks, **setter_tasks}
    if not all_tasks:
        return []

    combined = re.compile(
        r'\b(' + '|'.join(re.escape(k) for k in all_tasks) + r')\s*\('
    )
    results: list[GrepRecord] = []

    src_files: list[Path] = []
    for ext in _GROOVY_EXTENSIONS:
        src_files.extend(sorted(src_dir.rglob(f"*{ext}")))

    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = _get_cached_lines(src_file, stats, encoding_override)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                method_name = m.group(1)
                if method_name in getter_tasks:
                    for origin in getter_tasks[method_name]:
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.GETTER.value,
                            usage_type=classify_usage_groovy(line.strip()),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=line.strip(),
                            src_var=method_name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
                if method_name in setter_tasks:
                    for origin in setter_tasks[method_name]:
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.SETTER.value,
                            usage_type=classify_usage_groovy(line.strip()),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=line.strip(),
                            src_var=method_name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
    return results


def _resolve_groovy_file(filepath: str, src_dir: Path) -> Path | None:
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    return resolved if resolved.exists() else None


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    enc = detect_encoding(path, encoding_override)
    with open(path, encoding=enc, errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_groovy(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Groovy grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None)
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
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats, args.encoding)
            all_records: list[GrepRecord] = list(direct_records)

            getter_tasks: dict[str, list[GrepRecord]] = {}
            setter_tasks: dict[str, list[GrepRecord]] = {}

            for record in direct_records:
                if record.usage_type == "static final定数定義":
                    const_name = extract_static_final_name(record.code)
                    if const_name:
                        all_records.extend(
                            track_static_final_groovy(const_name, source_dir, record, stats, args.encoding)
                        )
                elif record.usage_type == "変数代入" and is_class_level_field(record.code):
                    field_name_match = re.search(r'(\w+)\s*[=;]', record.code.strip())
                    if field_name_match:
                        fname = field_name_match.group(1)
                        src_file = _resolve_groovy_file(record.filepath, source_dir)
                        if src_file:
                            all_records.extend(
                                track_field_groovy(fname, src_file, record, source_dir, stats, args.encoding)
                            )
                            lines = _get_cached_lines(src_file, stats, args.encoding)
                            for g in find_getter_names_groovy(fname, lines):
                                getter_tasks.setdefault(g, []).append(record)
                            for s in find_setter_names_groovy(fname, lines):
                                setter_tasks.setdefault(s, []).append(record)

            all_records.extend(
                _batch_track_getter_setter_groovy(getter_tasks, setter_tasks, source_dir, stats, args.encoding)
            )

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} (直接: {direct_count} 件, 間接: {indirect_count} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Generate expected TSV**

```bash
mkdir -p tests/groovy/expected
python -c "
import sys, re; sys.path.insert(0,'.')
import analyze_groovy as ag
from pathlib import Path
stats = ag.ProcessStats()
src_dir = Path('tests/groovy/src')
grep_path = Path('tests/groovy/input/TARGET.grep')
direct = ag.process_grep_file(grep_path, 'TARGET', src_dir, stats)
all_records = list(direct)
getter_tasks = {}
setter_tasks = {}
for r in direct:
    if r.usage_type == 'static final定数定義':
        n = ag.extract_static_final_name(r.code)
        if n:
            all_records.extend(ag.track_static_final_groovy(n, src_dir, r, stats))
    elif r.usage_type == '変数代入' and ag.is_class_level_field(r.code):
        m = re.search(r'(\w+)\s*[=;]', r.code.strip())
        if m:
            fname = m.group(1)
            sf = ag._resolve_groovy_file(r.filepath, src_dir)
            if sf:
                all_records.extend(ag.track_field_groovy(fname, sf, r, src_dir, stats))
                lines = ag._get_cached_lines(sf, stats)
                for g in ag.find_getter_names_groovy(fname, lines): getter_tasks.setdefault(g,[]).append(r)
                for s in ag.find_setter_names_groovy(fname, lines): setter_tasks.setdefault(s,[]).append(r)
all_records.extend(ag._batch_track_getter_setter_groovy(getter_tasks, setter_tasks, src_dir, stats))
ag.write_tsv(all_records, Path('tests/groovy/expected/TARGET.tsv'))
print('done')
"
cat tests/groovy/expected/TARGET.tsv
```
Verify the TSV contains:
- 1 direct row: sample.groovy:3 = static final定数定義
- Indirect rows for STATUS usages in the file (lines 4, 13, 20, 22 etc.)
- SETTER rows for `setType` calls
- GETTER rows for `getType` calls

- [ ] **Step 6: Run tests to confirm pass**

```
python -m pytest tests/test_groovy_analyzer.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add analyze_groovy.py tests/groovy/ tests/test_groovy_analyzer.py
git commit -m "feat: add analyze_groovy.py with indirect const/field tracking and setter/getter tracking"
```

---

### Task 6: Verify Java Setter Tracking (existing implementation)

Java setter tracking (`find_setter_names`, `track_setter_calls`, `_batch_track_setters`) is already fully implemented in `analyze.py`. This task verifies it works correctly.

**Files:**
- No new files — verify existing `tests/test_analyze.py` covers setter tracking

- [ ] **Step 1: Check existing test coverage for setter tracking**

```bash
grep -n "setter\|SETTER\|setType\|find_setter\|track_setter\|batch_track_setter" tests/test_analyze.py
```
If any setter-related tests exist, note their names. If none exist, proceed to Step 2.

- [ ] **Step 2: Add setter tracking tests to `tests/test_analyze.py`**

Open `tests/test_analyze.py` and add these tests in the appropriate test class (or create a new class `TestSetterTracking`):

```python
class TestFindSetterNames(unittest.TestCase):
    def test_convention(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "Model.java"
            src.write_text(
                "class Model {\n"
                "    private String type;\n"
                "    public void setType(String v) { this.type = v; }\n"
                "}\n"
            )
            import analyze as a
            names = a.find_setter_names("type", src)
            self.assertIn("setType", names)

    def test_convention_only_when_no_ast(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "Model.java"
            src.write_text("")  # empty file — AST parse will fail
            import analyze as a
            names = a.find_setter_names("code", src)
            self.assertIn("setCode", names)


class TestBatchTrackSetters(unittest.TestCase):
    def test_finds_setter_calls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src_dir = Path(d)
            (src_dir / "Model.java").write_text(
                "class Model { private String type; }\n"
            )
            (src_dir / "Service.java").write_text(
                "class Service { void m(Model m) { m.setType(\"TARGET\"); } }\n"
            )
            from analyze_common import GrepRecord, ProcessStats, RefType
            import analyze as a
            origin = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="変数宣言",
                filepath="Model.java",
                lineno="1",
                code='private String type = "TARGET";',
            )
            stats = ProcessStats()
            a._file_cache.clear()
            results = a._batch_track_setters({"setType": [origin]}, src_dir, stats)
            self.assertTrue(any("Service.java" in r.filepath for r in results))
            self.assertTrue(all(r.ref_type == RefType.SETTER.value for r in results))
```

- [ ] **Step 3: Run setter tests**

```
python -m pytest tests/test_analyze.py -k "setter or Setter" -v
```
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_analyze.py
git commit -m "test: add explicit setter tracking tests for analyze.py (verify existing implementation)"
```

---

### Task 7: Documentation Updates

**Files to modify:** `docs/product-requirements.md`, `docs/architecture.md`, `docs/repository-structure.md`, `docs/functional-design.md`, `docs/development-guidelines.md`, `docs/glossary.md`

- [ ] **Step 1: Update `docs/product-requirements.md`**

Add the 5 new languages to the supported languages table. Find the section listing supported languages (currently includes Java, Groovy?, Kotlin, PL/SQL, C/Pro*C, Shell/SQL). Add:

| 言語 | 拡張子 | 間接追跡 | setter追跡 |
|---|---|---|---|
| TypeScript/JavaScript | .ts/.tsx/.js/.jsx | — | — |
| Python | .py | — | — |
| Perl | .pl/.pm | — | — |
| C#/VB.NET | .cs/.vb | ✅ Const/readonly static | — |
| Groovy | .groovy/.gvy | ✅ static final + フィールド | ✅ |

- [ ] **Step 2: Update `docs/architecture.md`**

In the analysis layer section, add the 5 new analyzers alongside `analyze_kotlin.py` and `analyze_plsql.py`. Add brief descriptions of each new module.

- [ ] **Step 3: Update `docs/repository-structure.md`**

Add entries for:
- `analyze_ts.py`, `analyze_python.py`, `analyze_perl.py`, `analyze_dotnet.py`, `analyze_groovy.py`
- `tests/ts/`, `tests/python/`, `tests/perl/`, `tests/dotnet/`, `tests/groovy/`
- `tests/test_ts_analyzer.py`, `tests/test_python_analyzer.py`, `tests/test_perl_analyzer.py`, `tests/test_dotnet_analyzer.py`, `tests/test_groovy_analyzer.py`

- [ ] **Step 4: Update `docs/functional-design.md`**

In the language support table (F-07 or equivalent), add the 5 new languages with their usage types and indirect tracking capability flags.

- [ ] **Step 5: Update `docs/development-guidelines.md`**

Add `analyze_ts.py`, `analyze_python.py`, `analyze_perl.py`, `analyze_dotnet.py`, `analyze_groovy.py` to any filename lists or "adding a new analyzer" documentation.

- [ ] **Step 6: Update `docs/glossary.md`**

Add usage type definitions for each new language:
- TypeScript/JS: const定数定義、変数代入(let/var)、条件判定、return文、デコレータ、関数引数、その他
- Python: 変数代入、条件判定、return文、デコレータ、関数引数、その他
- Perl: use constant定義、変数代入、条件判定、print/say出力、関数引数、その他
- C#/VB.NET: 定数定義(Const/readonly)、変数代入、条件判定、return文、属性(Attribute)、メソッド引数、その他
- Groovy: static final定数定義、変数代入、条件判定、return文、アノテーション、メソッド引数、その他

- [ ] **Step 7: Commit**

```bash
git add docs/product-requirements.md docs/architecture.md docs/repository-structure.md \
        docs/functional-design.md docs/development-guidelines.md docs/glossary.md
git commit -m "docs: update all docs to reflect 5 new language analyzers and Groovy setter tracking"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered in plan |
|---|---|
| analyze_ts.py (TS/JS, 7 usage types, direct only) | Task 1 ✅ |
| analyze_python.py (Python, 6 usage types, direct only) | Task 2 ✅ |
| analyze_perl.py (Perl, 6 usage types, direct only) | Task 3 ✅ |
| analyze_dotnet.py (C#/VB.NET, 7 usage types, const indirect) | Task 4 ✅ |
| analyze_groovy.py (Groovy, 7 usage types, static final + field + setter) | Task 5 ✅ |
| Java setter tracking (Stage 2.5) | Task 6 ✅ (verify existing) |
| detect_encoding() + --encoding in all new analyzers | All tasks ✅ |
| _file_cache / _MAX_FILE_CACHE in all new analyzers | All tasks ✅ |
| build_parser() / main() structure unified | All tasks ✅ |
| Documentation updates | Task 7 ✅ |

**Type consistency check:** All tasks use `GrepRecord`, `ProcessStats`, `RefType` from `analyze_common`. The `classify_usage_<lang>()` function name follows the same pattern across all tasks. The `_file_cache` dict and `_MAX_FILE_CACHE = 800` constant are defined at module level in every analyzer.

**No placeholders found.**
