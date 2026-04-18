# grep_analyzer 拡張機能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** grep_analyzer に文字コード自動検出（F-07）、C/Pro*Cマクロ多段追跡（Indirect-1）、Javaのsetter逆伝播追跡（Java-4）、Kotlin対応（New-1）、PL/SQL対応（New-2）の5機能を追加する。

**Architecture:** 既存の「共通インフラ（analyze_common.py）+ 言語別アナライザー」アーキテクチャを維持する。F-07は analyze_common.py に `detect_encoding()` を追加し全アナライザーから呼ぶ。Indirect-1/Java-4 は既存ファイルを拡張。Kotlin/PL/SQL は analyze_sh.py をテンプレートに新ファイルを作成する。

**Tech Stack:** Python 3.12、chardet>=5.0.0（新規追加）、既存: javalang、re、pathlib、unittest

**フェーズ順序:** Phase 1（F-07）→ Phase 2（Indirect-1）→ Phase 3（Java-4）→ Phase 4（Kotlin）→ Phase 5（PL/SQL）。Phase 4/5 は Phase 1 完了後に開始できる。

---

## File Map

| 操作 | ファイル | 内容 |
|------|---------|------|
| Modify | `analyze_common.py` | `detect_encoding()` 追加、`RefType.SETTER` 追加 |
| Modify | `requirements.txt` | chardet>=5.0.0 追加 |
| Modify | `analyze_c.py` | `_encoding_override`、`_build_define_map`、`_expand_define_aliases`、`track_define` 拡張 |
| Modify | `analyze_proc.py` | 同上（analyze_c.py と同じ変更セット） |
| Modify | `analyze_sh.py` | `_encoding_override`、`--encoding` CLI オプション |
| Modify | `analyze_sql.py` | 同上 |
| Modify | `analyze.py` | `_encoding_override`、`find_setter_names`、`_batch_track_setters`、main() 拡張 |
| Create | `analyze_kotlin.py` | Kotlin アナライザー（全体） |
| Create | `analyze_plsql.py` | PL/SQL アナライザー（全体） |
| Modify | `tests/test_common.py` | `detect_encoding` テスト追加 |
| Modify | `tests/test_c_analyzer.py` | `_expand_define_aliases`、多段追跡テスト追加 |
| Modify | `test_analyze.py` | `find_setter_names`、setter 追跡テスト追加 |
| Create | `tests/test_kotlin_analyzer.py` | Kotlin 分類・追跡テスト |
| Create | `tests/test_plsql_analyzer.py` | PL/SQL 分類テスト |
| Create | `tests/kotlin/src/sample.kt` | Kotlin E2E フィクスチャ |
| Create | `tests/kotlin/input/TARGET.grep` | |
| Create | `tests/kotlin/expected/TARGET.tsv` | |
| Create | `tests/plsql/src/sample.pls` | PL/SQL E2E フィクスチャ |
| Create | `tests/plsql/input/TARGET.grep` | |
| Create | `tests/plsql/expected/TARGET.tsv` | |

---

## Phase 1: F-07 文字コード自動検出

### Task 1: detect_encoding を analyze_common.py に追加

**Files:**
- Modify: `analyze_common.py`
- Modify: `requirements.txt`
- Modify: `tests/test_common.py`

- [ ] **Step 1: requirements.txt に chardet を追加してインストール**

```
# requirements.txt に追記
chardet>=5.0.0
```

```bash
cd /workspaces/grep_helper_superpowers
.venv/bin/pip install chardet
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_common.py` の末尾、`if __name__ == "__main__":` の前に追加:

```python
from analyze_common import detect_encoding
import tempfile

class TestDetectEncoding(unittest.TestCase):
    def test_override_returned_as_is(self):
        result = detect_encoding(Path("any_file.txt"), override="utf-8")
        self.assertEqual(result, "utf-8")

    def test_utf8_file_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_text("hello world 日本語", encoding="utf-8")
            enc = detect_encoding(p)
            self.assertIn(enc.lower().replace("-", ""), ("utf8", "ascii", "utf8sig", "utf-8"))

    def test_fallback_on_undetectable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.bin"
            p.write_bytes(b'\x00\x01\x02\x03\x04\x05')
            enc = detect_encoding(p)
            self.assertEqual(enc, "cp932")

    def test_fallback_on_missing_file(self):
        enc = detect_encoding(Path("/nonexistent/missing_file.txt"))
        self.assertEqual(enc, "cp932")
```

- [ ] **Step 3: テストを実行して失敗を確認**

```bash
.venv/bin/python -m pytest tests/test_common.py::TestDetectEncoding -v
```

Expected: `ImportError: cannot import name 'detect_encoding'`

- [ ] **Step 4: detect_encoding を analyze_common.py に実装**

`analyze_common.py` の `from __future__ import annotations` の直後のインポートブロックに追加:

```python
try:
    import chardet as _chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False
```

`write_tsv` 関数の前（`_EXTERNAL_SORT_THRESHOLD` 定数の後）に追加:

```python
def detect_encoding(path: Path, override: str | None = None) -> str:
    """ファイルの文字コードを検出する。override が指定された場合はそれを返す。

    chardet の信頼度 < 0.6 またはファイル読み込み失敗時は cp932 にフォールバックする。
    フォールバック時は stats.encoding_errors への記録は呼び出し元が行う。
    """
    if override is not None:
        return override
    if not _CHARDET_AVAILABLE:
        return "cp932"
    try:
        raw = Path(path).read_bytes()[:4096]
        result = _chardet.detect(raw)
        if result and result.get("confidence", 0) >= 0.6 and result.get("encoding"):
            return result["encoding"]
    except Exception:
        pass
    return "cp932"
```

- [ ] **Step 5: テストを実行してパスを確認**

```bash
.venv/bin/python -m pytest tests/test_common.py -v
```

Expected: 全テスト PASS

- [ ] **Step 6: コミット**

```bash
git add requirements.txt analyze_common.py tests/test_common.py
git commit -m "feat(F-07): add detect_encoding to analyze_common, add chardet dependency"
```

---

### Task 2: analyze_c.py に encoding override を適用

**Files:**
- Modify: `analyze_c.py`

- [ ] **Step 1: analyze_c.py を以下のように変更**

`from analyze_common import ...` の行を:
```python
from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv
```

`_file_cache: dict[str, list[str]] = {}` の直後に追加:
```python
_encoding_override: str | None = None
```

`_get_cached_lines` 関数の `encoding="cp932"` を置換:
```python
def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            enc = detect_encoding(Path(filepath), _encoding_override)
            _file_cache[key] = Path(filepath).read_text(
                encoding=enc, errors="replace"
            ).splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]
```

`process_grep_file` 内の `open(path, encoding="cp932", ...)` を置換:
```python
    with open(path, encoding=detect_encoding(path, _encoding_override), errors="replace") as f:
```

`build_parser` に `--encoding` オプションを追加:
```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="純C grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="C ソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None,
                        help="ソースファイルの文字コード（省略時は自動検出）")
    return parser
```

`main()` の先頭（`parser = build_parser()` の直後）に追加:
```python
def main() -> None:
    global _encoding_override
    parser = build_parser()
    args = parser.parse_args()
    _encoding_override = args.encoding
    _file_cache.clear()
    ...  # 残りはそのまま
```

- [ ] **Step 2: 既存テストが通ることを確認**

```bash
.venv/bin/python -m pytest tests/test_c_analyzer.py -v
```

Expected: 全テスト PASS

- [ ] **Step 3: コミット**

```bash
git add analyze_c.py
git commit -m "feat(F-07): add encoding override to analyze_c.py"
```

---

### Task 3: analyze_sh.py / analyze_sql.py / analyze_proc.py に encoding override を適用

**Files:**
- Modify: `analyze_sh.py`, `analyze_sql.py`, `analyze_proc.py`

Task 2 と同じパターンを 3 ファイルに適用する。

- [ ] **Step 1: analyze_sh.py を変更**

`from analyze_common import ...` に `detect_encoding` を追加:
```python
from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv
```

`_file_cache: dict[str, list[str]] = {}` の直後に追加:
```python
_encoding_override: str | None = None
```

`_get_cached_lines` 内の `encoding="cp932"` を `detect_encoding(Path(filepath), _encoding_override)` に置換（Task 2 と同じ実装）:
```python
def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            enc = detect_encoding(Path(filepath), _encoding_override)
            _file_cache[key] = Path(filepath).read_text(
                encoding=enc, errors="replace"
            ).splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]
```

`process_grep_file` 内の `open(path, encoding="cp932", ...)` を置換:
```python
    with open(path, encoding=detect_encoding(path, _encoding_override), errors="replace") as f:
```

`build_parser` に `--encoding` を追加:
```python
    parser.add_argument("--encoding", default=None,
                        help="ソースファイルの文字コード（省略時は自動検出）")
```

`main()` の `args = parser.parse_args()` の直後に追加:
```python
    global _encoding_override
    _encoding_override = args.encoding
    _file_cache.clear()
```

- [ ] **Step 2: analyze_sql.py に同じ変更を適用**

`analyze_sql.py` を開き、Step 1 と同じ 5 箇所を変更する（`from analyze_common import` への追加、`_encoding_override` 変数、`_get_cached_lines`、`process_grep_file`、`build_parser`、`main()`）。

- [ ] **Step 3: analyze_proc.py に同じ変更を適用**

`analyze_proc.py` を開き、同じ 5 箇所を変更する。

- [ ] **Step 4: 既存テストが通ることを確認**

```bash
.venv/bin/python -m pytest tests/test_sh_analyzer.py tests/test_sql_analyzer.py tests/test_analyze_proc.py -v
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add analyze_sh.py analyze_sql.py analyze_proc.py
git commit -m "feat(F-07): add encoding override to analyze_sh, analyze_sql, analyze_proc"
```

---

### Task 4: analyze.py に encoding override を適用

**Files:**
- Modify: `analyze.py`

analyze.py は `shift_jis` を複数箇所で使用しており、変更箇所が多い。

- [ ] **Step 1: インポートに detect_encoding を追加**

```python
from analyze_common import (
    GrepRecord,
    ProcessStats,
    RefType,
    detect_encoding,
    parse_grep_line,
    write_tsv,
)
```

- [ ] **Step 2: モジュールレベルに _encoding_override を追加**

`_java_files_cache: dict[...] = {}` の直後に追加:
```python
_encoding_override: str | None = None
```

- [ ] **Step 3: _cached_read_lines を更新**

既存の `_cached_read_lines` 関数内の `encoding="shift_jis"` を置換:
```python
def _cached_read_lines(filepath_abs: str, stats: ProcessStats) -> list[str]:
    key = filepath_abs
    if key not in _file_lines_cache:
        if len(_file_lines_cache) >= _MAX_FILE_CACHE_SIZE:
            _file_lines_cache.pop(next(iter(_file_lines_cache)))
        path = Path(filepath_abs)
        try:
            enc = detect_encoding(path, _encoding_override)
            content = path.read_text(encoding=enc, errors="replace")
            _file_lines_cache[key] = content.splitlines()
        except Exception:
            stats.encoding_errors.add(filepath_abs)
            _file_lines_cache[key] = []
    return _file_lines_cache[key]
```

- [ ] **Step 4: get_ast と find_getter_names の shift_jis を置換**

`get_ast()` 内の `encoding="shift_jis"` を置換:
```python
            source = candidate.read_text(
                encoding=detect_encoding(candidate, _encoding_override), errors="replace"
            )
```

`find_getter_names()` 内の `class_file.read_text(encoding="shift_jis", ...)` を置換:
```python
                source = class_file.read_text(
                    encoding=detect_encoding(class_file, _encoding_override), errors="replace"
                )
```

`process_grep_file()` 内の `open(path, encoding="cp932", ...)` を置換:
```python
    with open(path, encoding=detect_encoding(path, _encoding_override), errors="replace") as f:
```

- [ ] **Step 5: build_parser と main() を更新**

`build_parser()` に追加:
```python
    parser.add_argument("--encoding", default=None,
                        help="ソースファイルの文字コード（省略時は自動検出）")
```

`main()` の `args = parser.parse_args()` 直後に追加:
```python
    global _encoding_override
    _encoding_override = args.encoding
    _file_lines_cache.clear()
    _ast_cache.clear()
    _ast_line_index.clear()
```

- [ ] **Step 6: 既存テストが通ることを確認**

```bash
.venv/bin/python -m pytest test_analyze.py -v
```

Expected: 全テスト PASS

- [ ] **Step 7: コミット**

```bash
git add analyze.py
git commit -m "feat(F-07): add encoding override to analyze.py (shift_jis -> detect_encoding)"
```

---

## Phase 2: Indirect-1 C/Pro*C マクロ多段追跡

### Task 5: analyze_c.py に多段 #define 解決を追加

**Files:**
- Modify: `analyze_c.py`
- Modify: `tests/test_c_analyzer.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_c_analyzer.py` に新クラスを追加（`TestExtractVariableNameC` の後）:

```python
class TestExpandDefineAliases(unittest.TestCase):
    def test_no_aliases(self):
        self.assertEqual(ac._expand_define_aliases("A", {}), set())

    def test_one_level(self):
        define_map = {"B": "A", "C": "D"}
        self.assertEqual(ac._expand_define_aliases("A", define_map), {"B"})

    def test_two_levels(self):
        define_map = {"B": "A", "C": "B"}
        self.assertEqual(ac._expand_define_aliases("A", define_map), {"B", "C"})

    def test_circular_reference_no_infinite_loop(self):
        define_map = {"B": "A", "A": "B"}
        aliases = ac._expand_define_aliases("A", define_map)
        self.assertIn("B", aliases)
        self.assertNotIn("A", aliases)

    def test_max_depth_guard(self):
        define_map = {f"X{i+1}": f"X{i}" for i in range(15)}  # 16-level chain
        aliases = ac._expand_define_aliases("X0", define_map, max_depth=10)
        self.assertLessEqual(len(aliases), 10)
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
.venv/bin/python -m pytest tests/test_c_analyzer.py::TestExpandDefineAliases -v
```

Expected: `AttributeError: module 'analyze_c' has no attribute '_expand_define_aliases'`

- [ ] **Step 3: _build_define_map と _expand_define_aliases を analyze_c.py に実装**

`_DEFINE_PAT` 定義の直後に追加:

```python
_DEFINE_VALUE_TOKEN_PAT = re.compile(r'#\s*define\s+(\w+)\s+(\w+)\s*(?:/.*)?$')

_define_map_cache: dict[str, dict[str, str]] = {}


def _build_define_map(src_dir: Path, stats: ProcessStats) -> dict[str, str]:
    """src_dir 配下の全 .c/.h/.pc ファイルから #define マップを構築する。

    マクロ名 → 値トークン（値が識別子の場合のみ）のマップを返す。
    """
    key = str(src_dir)
    if key in _define_map_cache:
        return _define_map_cache[key]
    define_map: dict[str, str] = {}
    src_files = (sorted(src_dir.rglob("*.c"))
                 + sorted(src_dir.rglob("*.h"))
                 + sorted(src_dir.rglob("*.pc")))
    for src_file in src_files:
        for line in _get_cached_lines(src_file, stats):
            m = _DEFINE_VALUE_TOKEN_PAT.match(line.strip())
            if m:
                define_map[m.group(1)] = m.group(2)
    _define_map_cache[key] = define_map
    return define_map


def _expand_define_aliases(
    var_name: str,
    define_map: dict[str, str],
    max_depth: int = 10,
) -> set[str]:
    """var_name を参照する定数名を連鎖的に解決する（var_name 自身は含まない）。"""
    reverse: dict[str, list[str]] = {}
    for k, v in define_map.items():
        reverse.setdefault(v, []).append(k)

    aliases: set[str] = set()
    frontier = {var_name}
    for _ in range(max_depth):
        new_frontier: set[str] = set()
        for name in frontier:
            for alias in reverse.get(name, []):
                if alias not in aliases:
                    new_frontier.add(alias)
                    aliases.add(alias)
        if not new_frontier:
            break
        frontier = new_frontier
    return aliases
```

- [ ] **Step 4: テストを実行してパスを確認**

```bash
.venv/bin/python -m pytest tests/test_c_analyzer.py::TestExpandDefineAliases -v
```

Expected: 全テスト PASS

- [ ] **Step 5: track_define を多段対応に更新**

既存の `track_define` 関数全体を置換:

```python
def track_define(
    var_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """#define マクロ名の使用箇所を src_dir 配下でスキャンする（多段マクロ連鎖対応）。"""
    define_map = _build_define_map(src_dir, stats)
    aliases = _expand_define_aliases(var_name, define_map)
    all_names = {var_name} | aliases

    combined = re.compile(r'\b(' + '|'.join(re.escape(n) for n in all_names) + r')\b')
    def_file = _resolve_source_file(record.filepath, src_dir)

    results: list[GrepRecord] = []
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
            m = combined.search(line)
            if m:
                matched = m.group(1)
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage_c(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=matched,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results
```

- [ ] **Step 6: 全既存テストが通ることを確認**

```bash
.venv/bin/python -m pytest tests/test_c_analyzer.py -v
```

Expected: 全テスト PASS

- [ ] **Step 7: コミット**

```bash
git add analyze_c.py tests/test_c_analyzer.py
git commit -m "feat(Indirect-1): add multi-level #define chain tracking to analyze_c.py"
```

---

### Task 6: analyze_proc.py に同じ多段 #define 解決を適用

**Files:**
- Modify: `analyze_proc.py`

- [ ] **Step 1: analyze_proc.py に _build_define_map, _expand_define_aliases, _define_map_cache を追加**

`analyze_proc.py` の `_DEFINE_PAT` 定義の直後に、Task 5 Step 3 と全く同じコードを追加する（`_DEFINE_VALUE_TOKEN_PAT`、`_define_map_cache`、`_build_define_map`、`_expand_define_aliases`）。

スキャン対象ファイルは `.pc`, `.c`, `.h`（analyze_proc.py のスコープと一致）。

- [ ] **Step 2: analyze_proc.py の track_define を多段対応に更新**

analyze_proc.py の `track_define` 関数を Task 5 Step 5 と同じパターンで置換する（classify 関数は `classify_usage_proc` / `classify_usage_c` に適宜変更）。

- [ ] **Step 3: 既存テストが通ることを確認**

```bash
.venv/bin/python -m pytest tests/test_analyze_proc.py -v 2>/dev/null || .venv/bin/python -m pytest test_analyze_proc.py -v
```

Expected: 全テスト PASS

- [ ] **Step 4: コミット**

```bash
git add analyze_proc.py
git commit -m "feat(Indirect-1): add multi-level #define chain tracking to analyze_proc.py"
```

---

## Phase 3: Java-4 setter 経由の逆伝播追跡

### Task 7: RefType.SETTER を analyze_common.py に追加

**Files:**
- Modify: `analyze_common.py`
- Modify: `tests/test_common.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_common.py` の `TestCommonImports` クラスに追加:

```python
    def test_reftype_setter_value(self):
        self.assertEqual(RefType.SETTER.value, "間接（setter経由）")
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
.venv/bin/python -m pytest tests/test_common.py::TestCommonImports::test_reftype_setter_value -v
```

Expected: `AttributeError: 'RefType' has no attribute 'SETTER'`

- [ ] **Step 3: RefType.SETTER を analyze_common.py に追加**

```python
class RefType(Enum):
    DIRECT   = "直接"
    INDIRECT = "間接"
    GETTER   = "間接（getter経由）"
    SETTER   = "間接（setter経由）"
```

- [ ] **Step 4: テストを実行してパスを確認**

```bash
.venv/bin/python -m pytest tests/test_common.py -v
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat(Java-4): add RefType.SETTER to analyze_common"
```

---

### Task 8: find_setter_names を analyze.py に追加

**Files:**
- Modify: `analyze.py`
- Modify: `test_analyze.py`

- [ ] **Step 1: 失敗するテストを書く**

`test_analyze.py` に以下を追加（既存クラスの外）:

```python
import tempfile

class TestFindSetterNames(unittest.TestCase):
    def test_convention_always_included(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "Foo.java"
            f.write_text("class Foo { private String code; }", encoding="utf-8")
            names = find_setter_names("code", f)
        self.assertIn("setCode", names)

    def test_non_standard_setter_detected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "Foo.java"
            f.write_text(
                "class Foo {\n"
                "    private String code;\n"
                "    public void assignCode(String v) {\n"
                "        this.code = v;\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            names = find_setter_names("code", f)
        self.assertIn("setCode", names)
        self.assertIn("assignCode", names)

    def test_no_false_positive_for_other_field(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "Foo.java"
            f.write_text(
                "class Foo {\n"
                "    public void setName(String v) {\n"
                "        this.name = v;\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            names = find_setter_names("code", f)
        self.assertNotIn("setName", names)
```

`test_analyze.py` の先頭付近の `from analyze import ...` 行に `find_setter_names` を追加（まだ存在しないので import エラーになる）:
```python
from analyze import (
    ...,   # 既存の import に追加
    find_setter_names,
)
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
.venv/bin/python -m pytest test_analyze.py::TestFindSetterNames -v
```

Expected: `ImportError: cannot import name 'find_setter_names'`

- [ ] **Step 3: find_setter_names を analyze.py に実装**

`find_getter_names` 関数の直後（`track_getter_calls` の前）に追加:

```python
_METHOD_DECL_PAT = re.compile(
    r'^\s*(?:(?:public|private|protected|static|final|synchronized)\s+)*'
    r'[\w<>\[\]]+\s+(\w+)\s*\('
)


def find_setter_names(field_name: str, class_file: Path) -> list[str]:
    """setterメソッド名候補を返す。

    2方式を併用:
    1. 命名規則: field_name="code" → "setCode"
    2. ライン解析: `this.field_name = ` を含むメソッドを全て検出
    """
    candidates: list[str] = [
        "set" + field_name[0].upper() + field_name[1:]
    ]

    lines = _cached_read_lines(str(class_file), None)
    assign_pat = re.compile(r'\bthis\.' + re.escape(field_name) + r'\s*=')
    current_method: str | None = None

    for line in lines:
        m = _METHOD_DECL_PAT.match(line)
        if m:
            current_method = m.group(1)
        if current_method and assign_pat.search(line):
            if current_method not in candidates:
                candidates.append(current_method)

    return list(set(candidates))
```

- [ ] **Step 4: テストを実行してパスを確認**

```bash
.venv/bin/python -m pytest test_analyze.py::TestFindSetterNames -v
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add analyze.py test_analyze.py
git commit -m "feat(Java-4): add find_setter_names to analyze.py"
```

---

### Task 9: _batch_track_setters を実装し main() に統合

**Files:**
- Modify: `analyze.py`
- Modify: `test_analyze.py`

- [ ] **Step 1: _batch_track_setters の失敗するテストを書く**

`test_analyze.py` の `TestFindSetterNames` クラスの後に追加:

```python
from analyze_common import GrepRecord, ProcessStats, RefType

class TestBatchTrackSetters(unittest.TestCase):
    def test_setter_call_produces_setter_ref_type(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            src.mkdir()
            (src / "Entity.java").write_text(
                "class Entity {\n"
                "    private String code;\n"
                "    public void setCode(String v) { this.code = v; }\n"
                "}\n",
                encoding="utf-8",
            )
            (src / "Service.java").write_text(
                'class Service {\n'
                '    void run(Entity e) { e.setCode("TARGET"); }\n'
                '}\n',
                encoding="utf-8",
            )
            from analyze_common import RefType
            origin = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="変数代入", filepath="Entity.java",
                lineno="2", code='private String code = "TARGET";',
            )
            import analyze as ana
            ana._file_lines_cache.clear()
            ana._java_files_cache.clear()
            tasks = {"setCode": [origin]}
            stats = ProcessStats()
            records = ana._batch_track_setters(tasks, src, stats)

        self.assertTrue(any(r.ref_type == RefType.SETTER.value for r in records))
        self.assertTrue(any("Service.java" in r.filepath for r in records))
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
.venv/bin/python -m pytest test_analyze.py::TestBatchTrackSetters -v
```

Expected: `AttributeError: module 'analyze' has no attribute '_batch_track_setters'`

- [ ] **Step 3: _batch_track_setters を analyze.py に実装**

`_batch_track_getters` 関数の直後に追加:

```python
def _batch_track_setters(
    tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """複数の setter をプロジェクト全体で一括追跡する。

    _batch_track_getters と同じ1パスバッチ方式。参照種別 = 間接（setter経由）。
    """
    if not tasks:
        return []

    combined = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in tasks) + r")\s*\("
    )
    records: list[GrepRecord] = []

    for java_file in _get_java_files(source_dir):
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = _cached_read_lines(filepath_abs, stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            for m in combined.finditer(line):
                setter_name = m.group(1)
                origins = tasks.get(setter_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage(
                    code=code,
                    filepath=filepath_str,
                    lineno=i,
                    source_dir=source_dir,
                    stats=stats,
                )
                for origin in origins:
                    if filepath_str == origin.filepath and str(i) == origin.lineno:
                        continue
                    records.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.SETTER.value,
                        usage_type=usage_type,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=setter_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    return records
```

- [ ] **Step 4: main() の setter_tasks 収集と _batch_track_setters 呼び出しを追加**

`analyze.py` の `main()` 内、`getter_tasks: dict[...] = {}` の直後に追加:
```python
            setter_tasks: dict[str, list[GrepRecord]] = {}
```

`scope == "class"` ブロック内の `find_getter_names` 呼び出しの後に追加:
```python
                        # 第4段階: setter 逆伝播候補を収集
                        for setter_name in find_setter_names(var_name, class_file):
                            setter_tasks.setdefault(setter_name, []).append(record)
```

`if getter_tasks:` ブロックの後に追加:
```python
            if setter_tasks:
                all_records.extend(
                    _batch_track_setters(setter_tasks, source_dir, stats)
                )
```

- [ ] **Step 5: 全テストが通ることを確認**

```bash
.venv/bin/python -m pytest test_analyze.py -v
```

Expected: 全テスト PASS

- [ ] **Step 6: コミット**

```bash
git add analyze.py test_analyze.py
git commit -m "feat(Java-4): add _batch_track_setters and integrate setter tracking into main()"
```

---

## Phase 4: New-1 Kotlin 対応

### Task 10: analyze_kotlin.py を作成（分類・追跡）

**Files:**
- Create: `analyze_kotlin.py`
- Create: `tests/test_kotlin_analyzer.py`

- [ ] **Step 1: 失敗するテストを書く**

新規ファイル `tests/test_kotlin_analyzer.py` を作成:

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_kotlin as ak


class TestClassifyUsageKotlin(unittest.TestCase):
    def test_const_val(self):
        self.assertEqual(ak.classify_usage_kotlin('const val STATUS = "TARGET"'), "const定数定義")

    def test_val_assignment(self):
        self.assertEqual(ak.classify_usage_kotlin('val code = "TARGET"'), "変数代入")

    def test_var_assignment(self):
        self.assertEqual(ak.classify_usage_kotlin('var code: String = "TARGET"'), "変数代入")

    def test_if_condition(self):
        self.assertEqual(ak.classify_usage_kotlin('if (code == "TARGET") {'), "条件判定")

    def test_when_condition(self):
        self.assertEqual(ak.classify_usage_kotlin('when (code) {'), "条件判定")

    def test_return(self):
        self.assertEqual(ak.classify_usage_kotlin('return "TARGET"'), "return文")

    def test_annotation(self):
        self.assertEqual(ak.classify_usage_kotlin('@SomeAnnotation("TARGET")'), "アノテーション")

    def test_function_arg(self):
        self.assertEqual(ak.classify_usage_kotlin('process("TARGET")'), "関数引数")

    def test_other(self):
        self.assertEqual(ak.classify_usage_kotlin('"TARGET"'), "その他")


class TestExtractConstNameKotlin(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ak.extract_const_name_kotlin('const val STATUS = "TARGET"'), "STATUS")

    def test_no_match(self):
        self.assertIsNone(ak.extract_const_name_kotlin('val code = "TARGET"'))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
.venv/bin/python -m pytest tests/test_kotlin_analyzer.py -v
```

Expected: `ModuleNotFoundError: No module named 'analyze_kotlin'`

- [ ] **Step 3: analyze_kotlin.py を作成**

```python
# analyze_kotlin.py
"""Kotlin grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv

_KT_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\s+val\s+\w+\s*='),               "const定数定義"),
    (re.compile(r'\b(?:val|var)\s+\w+\s*(?::\s*\S+)?\s*='), "変数代入"),
    (re.compile(r'\bif\s*\(|\bwhen\s*[\({]'),              "条件判定"),
    (re.compile(r'\breturn\b'),                             "return文"),
    (re.compile(r'@\w+'),                                   "アノテーション"),
    (re.compile(r'\w+\s*\('),                               "関数引数"),
]

_KT_CONST_PAT = re.compile(r'\bconst\s+val\s+(\w+)\s*=')

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800
_encoding_override: str | None = None


def classify_usage_kotlin(code: str) -> str:
    """Kotlinコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _KT_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_const_name_kotlin(code: str) -> str | None:
    """const val 定義から定数名を抽出する。"""
    m = _KT_CONST_PAT.search(code)
    return m.group(1) if m else None


def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            enc = detect_encoding(Path(filepath), _encoding_override)
            _file_cache[key] = Path(filepath).read_text(
                encoding=enc, errors="replace"
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


def track_const_kotlin(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """const val 定数名の使用箇所を src_dir 配下の .kt/.kts ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = _resolve_source_file(record.filepath, src_dir)

    src_files = sorted(src_dir.rglob("*.kt")) + sorted(src_dir.rglob("*.kts"))
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
                    usage_type=classify_usage_kotlin(line.strip()),
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
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    with open(path, encoding=detect_encoding(path, _encoding_override), errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_kotlin(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kotlin grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="Kotlin ソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None,
                        help="ソースファイルの文字コード（省略時は自動検出）")
    return parser


def main() -> None:
    global _encoding_override
    parser = build_parser()
    args = parser.parse_args()
    _encoding_override = args.encoding
    _file_cache.clear()

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
                if record.usage_type == "const定数定義":
                    const_name = extract_const_name_kotlin(record.code)
                    if const_name:
                        all_records.extend(
                            track_const_kotlin(const_name, source_dir, record, stats)
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

- [ ] **Step 4: テストを実行してパスを確認**

```bash
.venv/bin/python -m pytest tests/test_kotlin_analyzer.py -v
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add analyze_kotlin.py tests/test_kotlin_analyzer.py
git commit -m "feat(New-1): add analyze_kotlin.py with const val indirect tracking"
```

---

### Task 11: Kotlin E2E テストフィクスチャを作成

**Files:**
- Create: `tests/kotlin/src/sample.kt`
- Create: `tests/kotlin/input/TARGET.grep`
- Create: `tests/kotlin/expected/TARGET.tsv`
- Modify: `tests/test_kotlin_analyzer.py`

- [ ] **Step 1: フィクスチャディレクトリを作成**

```bash
mkdir -p /workspaces/grep_helper_superpowers/tests/kotlin/src \
         /workspaces/grep_helper_superpowers/tests/kotlin/input \
         /workspaces/grep_helper_superpowers/tests/kotlin/expected
```

- [ ] **Step 2: tests/kotlin/src/sample.kt を作成**

```kotlin
// sample.kt - Kotlin E2E test fixture
const val STATUS = "TARGET"

fun checkStatus(code: String): Boolean {
    if (code == STATUS) {
        return true
    }
    return false
}

fun printStatus() {
    println(STATUS)
}
```

- [ ] **Step 3: tests/kotlin/input/TARGET.grep を作成**

```
tests/kotlin/src/sample.kt:2:const val STATUS = "TARGET"
```

- [ ] **Step 4: 期待TSVを確認して tests/kotlin/expected/TARGET.tsv を作成**

まず実際に実行して出力を確認:
```bash
cd /workspaces/grep_helper_superpowers
.venv/bin/python analyze_kotlin.py \
  --source-dir tests/kotlin/src \
  --input-dir tests/kotlin/input \
  --output-dir /tmp/kotlin_out
cat /tmp/kotlin_out/TARGET.tsv
```

出力内容（直接参照1件 + 間接参照2件以上）を `tests/kotlin/expected/TARGET.tsv` にコピー。

- [ ] **Step 5: E2E テストを test_kotlin_analyzer.py に追加**

```python
import tempfile, csv

class TestE2EKotlin(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "kotlin"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        ak._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ak.ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = ak.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "const定数定義":
                    const_name = ak.extract_const_name_kotlin(record.code)
                    if const_name:
                        all_records.extend(
                            ak.track_const_kotlin(const_name, src_dir, record, stats)
                        )

            out_path = output_dir / "TARGET.tsv"
            from analyze_common import write_tsv
            write_tsv(all_records, out_path)

            with open(out_path, encoding="utf-8-sig", newline="") as f:
                actual = list(csv.reader(f, delimiter="\t"))
            with open(expected_path, encoding="utf-8-sig", newline="") as f:
                expected = list(csv.reader(f, delimiter="\t"))

        self.assertEqual(actual, expected)
```

- [ ] **Step 6: E2E テストが通ることを確認**

```bash
.venv/bin/python -m pytest tests/test_kotlin_analyzer.py::TestE2EKotlin -v
```

Expected: PASS

- [ ] **Step 7: コミット**

```bash
git add tests/kotlin/ tests/test_kotlin_analyzer.py
git commit -m "test(New-1): add Kotlin E2E fixture and integration test"
```

---

## Phase 5: New-2 PL/SQL 対応

### Task 12: analyze_plsql.py を作成

**Files:**
- Create: `analyze_plsql.py`
- Create: `tests/test_plsql_analyzer.py`

- [ ] **Step 1: 失敗するテストを書く**

新規ファイル `tests/test_plsql_analyzer.py` を作成:

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_plsql as ap


class TestClassifyUsagePlsql(unittest.TestCase):
    def test_constant_decl(self):
        self.assertEqual(
            ap.classify_usage_plsql("v_code CONSTANT VARCHAR2(10) := 'TARGET';"),
            "定数/変数宣言",
        )

    def test_assign(self):
        self.assertEqual(
            ap.classify_usage_plsql("v_code := 'TARGET';"),
            "定数/変数宣言",
        )

    def test_exception_when(self):
        self.assertEqual(
            ap.classify_usage_plsql("WHEN NO_DATA_FOUND THEN"),
            "EXCEPTION処理",
        )

    def test_exception_raise(self):
        self.assertEqual(
            ap.classify_usage_plsql("RAISE my_exception;"),
            "EXCEPTION処理",
        )

    def test_condition_if(self):
        self.assertEqual(
            ap.classify_usage_plsql("IF v_code = 'TARGET' THEN"),
            "条件判定",
        )

    def test_condition_case_when(self):
        self.assertEqual(
            ap.classify_usage_plsql("CASE WHEN v_code = 'TARGET' THEN 1"),
            "条件判定",
        )

    def test_cursor(self):
        self.assertEqual(
            ap.classify_usage_plsql("CURSOR c_data IS SELECT code FROM t;"),
            "カーソル定義",
        )

    def test_insert(self):
        self.assertEqual(
            ap.classify_usage_plsql("INSERT INTO t VALUES ('TARGET');"),
            "INSERT/UPDATE値",
        )

    def test_update(self):
        self.assertEqual(
            ap.classify_usage_plsql("UPDATE t SET code = 'TARGET'"),
            "INSERT/UPDATE値",
        )

    def test_where(self):
        self.assertEqual(
            ap.classify_usage_plsql("WHERE code = 'TARGET'"),
            "WHERE条件",
        )

    def test_other(self):
        self.assertEqual(
            ap.classify_usage_plsql("'TARGET'"),
            "その他",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
.venv/bin/python -m pytest tests/test_plsql_analyzer.py -v
```

Expected: `ModuleNotFoundError: No module named 'analyze_plsql'`

- [ ] **Step 3: analyze_plsql.py を作成**

```python
# analyze_plsql.py
"""PL/SQL grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv

_PLSQL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bCONSTANT\b|:=',           re.IGNORECASE), "定数/変数宣言"),
    (re.compile(r'\bWHEN\b.+\bTHEN\b|\bRAISE\b', re.IGNORECASE), "EXCEPTION処理"),
    (re.compile(r'\bIF\b.+\bTHEN\b|\bCASE\s+WHEN\b', re.IGNORECASE), "条件判定"),
    (re.compile(r'\bCURSOR\b.+\bIS\b',         re.IGNORECASE), "カーソル定義"),
    (re.compile(r'\bINSERT\b|\bUPDATE\b.+\bSET\b', re.IGNORECASE), "INSERT/UPDATE値"),
    (re.compile(r'\bWHERE\b',                  re.IGNORECASE), "WHERE条件"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800
_encoding_override: str | None = None

_PLSQL_EXTENSIONS = ("*.pls", "*.pck", "*.prc", "*.pkb", "*.pks", "*.fnc", "*.trg")


def classify_usage_plsql(code: str) -> str:
    """PL/SQLコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PLSQL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            enc = detect_encoding(Path(filepath), _encoding_override)
            _file_cache[key] = Path(filepath).read_text(
                encoding=enc, errors="replace"
            ).splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    records: list[GrepRecord] = []
    with open(path, encoding=detect_encoding(path, _encoding_override), errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_plsql(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PL/SQL grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="PL/SQL ソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None,
                        help="ソースファイルの文字コード（省略時は自動検出）")
    return parser


def main() -> None:
    global _encoding_override
    parser = build_parser()
    args = parser.parse_args()
    _encoding_override = args.encoding
    _file_cache.clear()

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
            all_records = process_grep_file(grep_path, keyword, source_dir, stats)

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            print(f"  {grep_path.name} → {output_path} (直接: {len(all_records)} 件)")
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

- [ ] **Step 4: テストを実行してパスを確認**

```bash
.venv/bin/python -m pytest tests/test_plsql_analyzer.py -v
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add analyze_plsql.py tests/test_plsql_analyzer.py
git commit -m "feat(New-2): add analyze_plsql.py"
```

---

### Task 13: PL/SQL E2E テストフィクスチャを作成

**Files:**
- Create: `tests/plsql/src/sample.pls`
- Create: `tests/plsql/input/TARGET.grep`
- Create: `tests/plsql/expected/TARGET.tsv`
- Modify: `tests/test_plsql_analyzer.py`

- [ ] **Step 1: フィクスチャディレクトリを作成**

```bash
mkdir -p /workspaces/grep_helper_superpowers/tests/plsql/src \
         /workspaces/grep_helper_superpowers/tests/plsql/input \
         /workspaces/grep_helper_superpowers/tests/plsql/expected
```

- [ ] **Step 2: tests/plsql/src/sample.pls を作成**

```sql
-- sample.pls - PL/SQL E2E test fixture
CREATE OR REPLACE PROCEDURE check_status AS
    v_code CONSTANT VARCHAR2(10) := 'TARGET';
BEGIN
    IF v_code = 'TARGET' THEN
        NULL;
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE;
END;
/
```

- [ ] **Step 3: tests/plsql/input/TARGET.grep を作成**

```
tests/plsql/src/sample.pls:3:    v_code CONSTANT VARCHAR2(10) := 'TARGET';
tests/plsql/src/sample.pls:5:    IF v_code = 'TARGET' THEN
```

- [ ] **Step 4: 期待TSVを生成して保存**

```bash
cd /workspaces/grep_helper_superpowers
.venv/bin/python analyze_plsql.py \
  --source-dir tests/plsql/src \
  --input-dir tests/plsql/input \
  --output-dir /tmp/plsql_out
cp /tmp/plsql_out/TARGET.tsv tests/plsql/expected/TARGET.tsv
```

- [ ] **Step 5: E2E テストを test_plsql_analyzer.py に追加**

```python
import tempfile, csv

class TestE2EPlsql(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "plsql"

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
            all_records = ap.process_grep_file(grep_path, "TARGET", src_dir, stats)

            out_path = output_dir / "TARGET.tsv"
            from analyze_common import write_tsv
            write_tsv(all_records, out_path)

            with open(out_path, encoding="utf-8-sig", newline="") as f:
                actual = list(csv.reader(f, delimiter="\t"))
            with open(expected_path, encoding="utf-8-sig", newline="") as f:
                expected = list(csv.reader(f, delimiter="\t"))

        self.assertEqual(actual, expected)
```

- [ ] **Step 6: E2E テストが通ることを確認**

```bash
.venv/bin/python -m pytest tests/test_plsql_analyzer.py::TestE2EPlsql -v
```

Expected: PASS

- [ ] **Step 7: 全テストスイートが通ることを確認**

```bash
.venv/bin/python -m pytest tests/ test_analyze.py test_analyze_proc.py -v
```

Expected: 全テスト PASS

- [ ] **Step 8: コミット**

```bash
git add tests/plsql/ tests/test_plsql_analyzer.py
git commit -m "test(New-2): add PL/SQL E2E fixture and integration test"
```

---

## 完了チェック

全タスク完了後に以下を実行して全テストがパスすることを確認:

```bash
.venv/bin/python -m pytest tests/ test_analyze.py test_analyze_proc.py -v
```

Expected: 全テスト PASS、エラー 0 件
