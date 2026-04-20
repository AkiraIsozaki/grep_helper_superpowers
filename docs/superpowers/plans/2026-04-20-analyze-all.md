# analyze_all.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `analyze_all.py`, a single-entry dispatcher that routes each grep line to the correct language classifier based on file extension (or shebang for extension-less files), applies per-language indirect tracking, and writes one merged TSV — so no grep hit is missed or misclassified.

**Architecture:** Parse every grep line, detect language via `_EXT_TO_LANG` dict (falling back to shebang scan for extension-less files), call the matching `classify_usage_<lang>()`, then run that language's `track_*()` functions for indirect references. Unknown extensions produce `"その他"` records rather than being dropped. Existing modules are imported, never modified.

**Tech Stack:** Python 3.11+, standard library only; re-uses all existing `analyze_*.py` + `analyze_common.py`.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `analyze_all.py` | Dispatcher: routing, classification, indirect tracking, main() |
| Create | `tests/test_all_analyzer.py` | Unit + E2E tests for analyze_all |
| Create | `tests/all/input/TARGET.grep` | Mixed-language grep fixture |
| Create | `tests/all/src/Main.java` | Java source fixture |
| Create | `tests/all/src/Service.groovy` | Groovy source fixture |
| Create | `tests/all/src/deploy.sh` | Shell source fixture |
| Create | `tests/all/src/config.xml` | Unknown-extension fixture |
| Create | `tests/all/src/cleanup` | Extension-less Perl fixture |
| Create | `tests/all/expected/TARGET.tsv` | Expected TSV output |
| Modify | `README.md` | `analyze_all.py` を対応言語表・実行例に追加 |
| Modify | `docs/tool-overview.md` | `analyze_all.py` の概要・呼び出し方を追記 |
| Modify | `docs/repository-structure.md` | `analyze_all.py` エントリを追加 |

---

## Task 1: Language Detection

**Files:**
- Create: `analyze_all.py` (routing tables + `detect_language()` only)
- Create: `tests/test_all_analyzer.py` (unit tests for `detect_language`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_all_analyzer.py
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_all as aa


class TestDetectLanguage(unittest.TestCase):

    def test_java_extension(self):
        self.assertEqual(aa.detect_language("src/Foo.java", Path(".")), "java")

    def test_kotlin_kt(self):
        self.assertEqual(aa.detect_language("src/Foo.kt", Path(".")), "kotlin")

    def test_kotlin_kts(self):
        self.assertEqual(aa.detect_language("src/build.kts", Path(".")), "kotlin")

    def test_c_extension(self):
        self.assertEqual(aa.detect_language("src/util.c", Path(".")), "c")

    def test_header_extension(self):
        self.assertEqual(aa.detect_language("src/util.h", Path(".")), "c")

    def test_proc_pc(self):
        self.assertEqual(aa.detect_language("src/proc.pc", Path(".")), "proc")

    def test_sql_extension(self):
        self.assertEqual(aa.detect_language("src/query.sql", Path(".")), "sql")

    def test_sh_extension(self):
        self.assertEqual(aa.detect_language("src/run.sh", Path(".")), "sh")

    def test_bash_extension(self):
        self.assertEqual(aa.detect_language("src/run.bash", Path(".")), "sh")

    def test_ts_extension(self):
        self.assertEqual(aa.detect_language("src/app.ts", Path(".")), "ts")

    def test_js_extension(self):
        self.assertEqual(aa.detect_language("src/app.js", Path(".")), "ts")

    def test_tsx_extension(self):
        self.assertEqual(aa.detect_language("src/app.tsx", Path(".")), "ts")

    def test_jsx_extension(self):
        self.assertEqual(aa.detect_language("src/app.jsx", Path(".")), "ts")

    def test_python_extension(self):
        self.assertEqual(aa.detect_language("src/util.py", Path(".")), "python")

    def test_perl_pl(self):
        self.assertEqual(aa.detect_language("src/script.pl", Path(".")), "perl")

    def test_perl_pm(self):
        self.assertEqual(aa.detect_language("src/Mod.pm", Path(".")), "perl")

    def test_dotnet_cs(self):
        self.assertEqual(aa.detect_language("src/App.cs", Path(".")), "dotnet")

    def test_dotnet_vb(self):
        self.assertEqual(aa.detect_language("src/App.vb", Path(".")), "dotnet")

    def test_groovy_extension(self):
        self.assertEqual(aa.detect_language("src/Svc.groovy", Path(".")), "groovy")

    def test_groovy_gvy(self):
        self.assertEqual(aa.detect_language("src/Svc.gvy", Path(".")), "groovy")

    def test_plsql_pls(self):
        self.assertEqual(aa.detect_language("src/pkg.pls", Path(".")), "plsql")

    def test_plsql_pck(self):
        self.assertEqual(aa.detect_language("src/pkg.pck", Path(".")), "plsql")

    def test_xml_is_other(self):
        self.assertEqual(aa.detect_language("src/config.xml", Path(".")), "other")

    def test_yaml_is_other(self):
        self.assertEqual(aa.detect_language("src/app.yaml", Path(".")), "other")

    def test_no_extension_perl_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "myscript"
            f.write_text("#!/usr/bin/perl\nprint 1;\n")
            self.assertEqual(aa.detect_language("myscript", src), "perl")

    def test_no_extension_env_perl_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "myscript"
            f.write_text("#!/usr/bin/env perl\nprint 1;\n")
            self.assertEqual(aa.detect_language("myscript", src), "perl")

    def test_no_extension_bash_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/bash\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_sh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/sh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_csh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/csh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_tcsh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/tcsh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_ksh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/ksh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_ksh93_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/ksh93\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_unknown_shebang_is_other(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/usr/bin/ruby\nputs 1\n")
            self.assertEqual(aa.detect_language("run", src), "other")

    def test_no_extension_no_shebang_is_other(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("some content\n")
            self.assertEqual(aa.detect_language("run", src), "other")

    def test_no_extension_file_missing_is_other(self):
        self.assertEqual(aa.detect_language("nonexistent_file", Path("/tmp")), "other")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /workspaces/grep_helper_superpowers
python -m pytest tests/test_all_analyzer.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'analyze_all'`

- [ ] **Step 3: Implement `detect_language()` in `analyze_all.py`**

Create `analyze_all.py` with the following content:

```python
# analyze_all.py
"""全言語対応ディスパッチャーアナライザー。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import (
    GrepRecord, ProcessStats, RefType,
    detect_encoding, parse_grep_line, write_tsv,
)

# ---------------------------------------------------------------------------
# 言語ルーティング
# ---------------------------------------------------------------------------

_EXT_TO_LANG: dict[str, str] = {
    ".java":  "java",
    ".kt":    "kotlin",  ".kts":  "kotlin",
    ".c":     "c",       ".h":    "c",
    ".pc":    "proc",    ".pcc":  "proc",
    ".sql":   "sql",
    ".sh":    "sh",      ".bash": "sh",
    ".ts":    "ts",      ".js":   "ts",   ".tsx": "ts",  ".jsx": "ts",
    ".py":    "python",
    ".pl":    "perl",    ".pm":   "perl",
    ".cs":    "dotnet",  ".vb":   "dotnet",
    ".groovy":"groovy",  ".gvy":  "groovy",
    ".pls":   "plsql",   ".pck":  "plsql", ".prc": "plsql",
    ".pkb":   "plsql",   ".pks":  "plsql", ".fnc": "plsql", ".trg": "plsql",
}

_SHEBANG_PAT = re.compile(r'^#!\s*(?:.*/)?(?:env\s+)?(\S+)')
_SHEBANG_TO_LANG: dict[str, str] = {
    "perl":   "perl",
    "sh":     "sh",  "bash":  "sh",
    "csh":    "sh",  "tcsh":  "sh",
    "ksh":    "sh",  "ksh93": "sh",
}


def detect_language(filepath: str, source_dir: Path) -> str:
    """ファイルパスから言語キーを返す。拡張子なしはシバン判定、不明は 'other'。"""
    ext = Path(filepath).suffix.lower()
    if ext:
        return _EXT_TO_LANG.get(ext, "other")

    # 拡張子なし: source_dir からシバン判定
    candidate = source_dir / filepath
    if not candidate.exists():
        p = Path(filepath)
        candidate = p if p.is_absolute() and p.exists() else None
        if candidate is None:
            return "other"
    try:
        first_line = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        m = _SHEBANG_PAT.match(first_line)
        if m:
            return _SHEBANG_TO_LANG.get(m.group(1).lower(), "other")
    except Exception:
        pass
    return "other"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_all_analyzer.py::TestDetectLanguage -v
```

Expected: all `TestDetectLanguage` tests PASS

- [ ] **Step 5: Commit**

```bash
git add analyze_all.py tests/test_all_analyzer.py
git commit -m "feat: add analyze_all.py with detect_language() routing"
```

---

## Task 2: Direct Reference Processing

**Files:**
- Modify: `analyze_all.py` (add classifier imports + `_classify_for_lang()` + `process_grep_lines_all()`)
- Modify: `tests/test_all_analyzer.py` (add `TestDirectClassification`)

- [ ] **Step 1: Write the failing tests**

Add this class to `tests/test_all_analyzer.py`:

```python
class TestDirectClassification(unittest.TestCase):
    """各言語の行が正しい usage_type に分類されることを確認する。"""

    def _make_direct_records(self, grep_lines: list[str], source_dir: Path) -> list:
        from analyze_common import ProcessStats
        stats = ProcessStats()
        return aa.process_grep_lines_all(grep_lines, "TEST", source_dir, stats, None)

    def test_java_line_classified(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/Foo.java:10:    static final String X = \"TARGET\""],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertIn("定数", records[0].usage_type)
            self.assertEqual(records[0].ref_type, "直接")

    def test_groovy_line_classified(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/Svc.groovy:5:    if (code == TARGET) {{ return }}"],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "条件判定")

    def test_sh_line_classified(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/run.sh:3:TARGET=\"777\""],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "変数代入")

    def test_unknown_extension_is_other(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/config.xml:1:<value>TARGET</value>"],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "その他")
            self.assertEqual(records[0].ref_type, "直接")

    def test_no_extension_perl_shebang_classified(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            script = src / "cleanup"
            script.write_text("#!/usr/bin/perl\nmy $x = TARGET;\n")
            records = self._make_direct_records(
                [f"{src}/cleanup:2:my $x = TARGET;"],
                src,
            )
            self.assertEqual(len(records), 1)
            # Perl classifies assignment as "変数代入" or similar — just not "その他"
            self.assertNotEqual(records[0].usage_type, "その他")

    def test_invalid_grep_line_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                ["not a valid grep line"],
                src,
            )
            self.assertEqual(len(records), 0)

    def test_binary_line_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                ["Binary file src/app.bin matches"],
                src,
            )
            self.assertEqual(len(records), 0)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_all_analyzer.py::TestDirectClassification -v 2>&1 | head -10
```

Expected: `AttributeError: module 'analyze_all' has no attribute 'process_grep_lines_all'`

- [ ] **Step 3: Implement classifier imports and `process_grep_lines_all()` in `analyze_all.py`**

Append the following to `analyze_all.py` after the `detect_language` function:

```python
# ---------------------------------------------------------------------------
# 分類器インポート
# ---------------------------------------------------------------------------

import analyze as _java_mod
from analyze_kotlin  import classify_usage_kotlin
from analyze_c       import classify_usage_c
from analyze_proc    import classify_usage_proc
from analyze_sql     import classify_usage_sql
from analyze_sh      import classify_usage_sh
from analyze_ts      import classify_usage_ts
from analyze_python  import classify_usage_python
from analyze_perl    import classify_usage_perl
from analyze_dotnet  import classify_usage_dotnet
from analyze_groovy  import classify_usage_groovy
from analyze_plsql   import classify_usage_plsql

_SIMPLE_CLASSIFIERS: dict[str, object] = {
    "kotlin": classify_usage_kotlin,
    "c":      classify_usage_c,
    "proc":   classify_usage_proc,
    "sql":    classify_usage_sql,
    "sh":     classify_usage_sh,
    "ts":     classify_usage_ts,
    "python": classify_usage_python,
    "perl":   classify_usage_perl,
    "dotnet": classify_usage_dotnet,
    "groovy": classify_usage_groovy,
    "plsql":  classify_usage_plsql,
}


def _classify_for_lang(
    lang: str,
    code: str,
    filepath: str,
    lineno: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> str:
    """言語キーに対応する classify_usage 関数を呼び出す。"""
    if lang == "java":
        _java_mod._encoding_override = encoding
        return _java_mod.classify_usage(
            code=code,
            filepath=filepath,
            lineno=int(lineno),
            source_dir=source_dir,
            stats=stats,
        )
    if lang == "other":
        return "その他"
    classifier = _SIMPLE_CLASSIFIERS.get(lang)
    if classifier:
        return classifier(code)  # type: ignore[call-arg]
    return "その他"


def process_grep_lines_all(
    lines: list[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """grep行リストを全行パースして直接参照 GrepRecord を返す。"""
    records: list[GrepRecord] = []
    for line in lines:
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        lang = detect_language(parsed["filepath"], source_dir)
        usage_type = _classify_for_lang(
            lang, parsed["code"], parsed["filepath"],
            parsed["lineno"], source_dir, stats, encoding,
        )
        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=usage_type,
            filepath=parsed["filepath"],
            lineno=parsed["lineno"],
            code=parsed["code"],
        ))
        stats.valid_lines += 1
    return records
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_all_analyzer.py::TestDetectLanguage tests/test_all_analyzer.py::TestDirectClassification -v
```

Expected: all tests PASS

- [ ] **Step 5: Confirm existing test suite still passes**

```bash
python -m pytest tests/ -q --no-header 2>&1 | tail -3
```

Expected: `161 passed` (no regressions)

- [ ] **Step 6: Commit**

```bash
git add analyze_all.py tests/test_all_analyzer.py
git commit -m "feat: add direct classification dispatch to analyze_all"
```

---

## Task 3: Indirect Tracking Dispatch

**Files:**
- Modify: `analyze_all.py` (add indirect tracking imports + `_resolve_file()` + `_apply_indirect_tracking()`)
- Modify: `tests/test_all_analyzer.py` (add `TestIndirectTracking`)

- [ ] **Step 1: Write the failing tests**

Add this class to `tests/test_all_analyzer.py`:

```python
class TestIndirectTracking(unittest.TestCase):

    def test_groovy_static_final_tracks_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Const.groovy").write_text(
                'static final String STATUS = "TARGET"\n'
            )
            (src / "Service.groovy").write_text(
                'if (s == STATUS) { return }\n'
            )
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="static final定数定義",
                filepath=str(src / "Const.groovy"), lineno="1",
                code='static final String STATUS = "TARGET"',
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("Service.groovy" in r.filepath for r in indirect))

    def test_sh_variable_tracks_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            script = src / "deploy.sh"
            script.write_text('STATUS="TARGET"\necho $STATUS\n')
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(script), lineno="1",
                code='STATUS="TARGET"',
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("deploy.sh" in r.filepath for r in indirect))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in indirect))

    def test_dotnet_const_tracks_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Consts.cs").write_text('const string STATUS = "TARGET";\n')
            (src / "Service.cs").write_text('if (x == STATUS) { return; }\n')
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="定数定義(Const/readonly)",
                filepath=str(src / "Consts.cs"), lineno="1",
                code='const string STATUS = "TARGET";',
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("Service.cs" in r.filepath for r in indirect))

    def test_other_language_no_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="その他",
                filepath=str(src / "config.xml"), lineno="1",
                code="<value>TARGET</value>",
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertEqual(indirect, [])
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_all_analyzer.py::TestIndirectTracking -v 2>&1 | head -10
```

Expected: `AttributeError: module 'analyze_all' has no attribute '_apply_indirect_tracking'`

- [ ] **Step 3: Implement `_resolve_file()` and `_apply_indirect_tracking()` in `analyze_all.py`**

Append the following to `analyze_all.py` after the `process_grep_lines_all` function:

```python
# ---------------------------------------------------------------------------
# 間接追跡用インポート
# ---------------------------------------------------------------------------

# Java
from analyze import (
    UsageType, extract_variable_name, determine_scope,
    track_constant, track_field, track_local,
    find_getter_names, find_setter_names,
    track_getter_calls, track_setter_calls,
)
from analyze import _resolve_java_file  # type: ignore[attr-defined]

# Kotlin
from analyze_kotlin import track_const as _track_const_kotlin

# C
from analyze_c import (
    extract_define_name as _extract_define_name_c,
    extract_variable_name_c,
    track_define as _track_define_c,
    track_variable as _track_variable_c,
)

# Pro*C
from analyze_proc import (
    extract_define_name as _extract_define_name_proc,
    extract_variable_name_proc,
    extract_host_var_name,
    track_define as _track_define_proc,
    track_variable as _track_variable_proc,
)

# Shell
from analyze_sh import extract_sh_variable_name, track_sh_variable

# SQL
from analyze_sql import extract_sql_variable_name, track_sql_variable

# .NET
from analyze_dotnet import extract_const_name_dotnet, track_const_dotnet

# Groovy
from analyze_groovy import (
    extract_static_final_name, is_class_level_field,
    find_getter_names_groovy, find_setter_names_groovy,
    track_static_final_groovy, track_field_groovy,
    _batch_track_getter_setter_groovy,  # type: ignore[attr-defined]
)


def _resolve_file(filepath: str, source_dir: Path) -> Path | None:
    """ファイルパスを解決する（CWD相対 → source_dir相対の順）。"""
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = source_dir / filepath
    return resolved if resolved.exists() else None


def _read_lines(filepath: Path, encoding: str | None) -> list[str]:
    enc = detect_encoding(filepath, encoding)
    try:
        return filepath.read_text(encoding=enc, errors="replace").splitlines()
    except Exception:
        return []


def _apply_indirect_tracking(
    direct_records: list[GrepRecord],
    source_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """直接参照レコードから言語別間接追跡を行い、追加レコードを返す。"""
    result: list[GrepRecord] = []

    # Java バッチ集積用
    java_project_tasks: dict[str, list[GrepRecord]] = {}
    java_getter_tasks:  dict[str, list[GrepRecord]] = {}
    java_setter_tasks:  dict[str, list[GrepRecord]] = {}

    # Groovy getter/setter バッチ集積用
    groovy_getter_tasks: dict[str, list[GrepRecord]] = {}
    groovy_setter_tasks: dict[str, list[GrepRecord]] = {}

    for record in direct_records:
        lang = detect_language(record.filepath, source_dir)

        # ── Java ──────────────────────────────────────────────────────────
        if lang == "java":
            if record.usage_type not in (
                UsageType.CONSTANT.value, UsageType.VARIABLE.value
            ):
                continue
            var_name = extract_variable_name(record.code, record.usage_type)
            if not var_name:
                continue
            _java_mod._encoding_override = encoding
            scope = determine_scope(
                record.usage_type, record.code,
                record.filepath, source_dir, int(record.lineno),
            )
            if scope == "project":
                java_project_tasks.setdefault(var_name, []).append(record)
            elif scope == "class":
                class_file = _resolve_java_file(record.filepath, source_dir)
                if class_file:
                    result.extend(track_field(var_name, class_file, record, source_dir, stats))
                    for g in find_getter_names(var_name, class_file):
                        java_getter_tasks.setdefault(g, []).append(record)
                    for s in find_setter_names(var_name, class_file):
                        java_setter_tasks.setdefault(s, []).append(record)
            elif scope == "method":
                from analyze import _get_method_scope  # type: ignore[attr-defined]
                method_scope = _get_method_scope(record.filepath, source_dir, int(record.lineno))
                if method_scope:
                    result.extend(track_local(var_name, method_scope, record, source_dir, stats))

        # ── Kotlin ────────────────────────────────────────────────────────
        elif lang == "kotlin":
            if record.usage_type == "const val定数定義":
                result.extend(_track_const_kotlin(
                    record.code.split("=")[0].strip().split()[-1],
                    source_dir, record, stats, encoding,
                ))

        # ── C ─────────────────────────────────────────────────────────────
        elif lang == "c":
            if record.usage_type == "#define定数定義":
                var_name = _extract_define_name_c(record.code)
                if var_name:
                    result.extend(_track_define_c(var_name, source_dir, record, stats, encoding))
            elif record.usage_type == "変数代入":
                var_name = extract_variable_name_c(record.code)
                if var_name:
                    candidate = _resolve_file(record.filepath, source_dir)
                    if candidate:
                        result.extend(_track_variable_c(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── Pro*C ─────────────────────────────────────────────────────────
        elif lang == "proc":
            if record.usage_type == "#define定数定義":
                var_name = _extract_define_name_proc(record.code)
                if var_name:
                    result.extend(_track_define_proc(var_name, source_dir, record, stats, encoding))
            elif record.usage_type == "変数代入":
                var_name = extract_variable_name_proc(record.code) or extract_host_var_name(record.code)
                if var_name:
                    candidate = _resolve_file(record.filepath, source_dir)
                    if candidate:
                        result.extend(_track_variable_proc(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── Shell ─────────────────────────────────────────────────────────
        elif lang == "sh":
            if record.usage_type in ("変数代入", "環境変数エクスポート"):
                var_name = extract_sh_variable_name(record.code)
                if var_name:
                    candidate = _resolve_file(record.filepath, source_dir)
                    if candidate:
                        result.extend(track_sh_variable(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── SQL ───────────────────────────────────────────────────────────
        elif lang == "sql":
            if record.usage_type == "定数・変数定義":
                var_name = extract_sql_variable_name(record.code)
                if var_name:
                    candidate = _resolve_file(record.filepath, source_dir)
                    if candidate:
                        result.extend(track_sql_variable(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── .NET ──────────────────────────────────────────────────────────
        elif lang == "dotnet":
            if record.usage_type == "定数定義(Const/readonly)":
                const_name = extract_const_name_dotnet(record.code)
                if const_name:
                    result.extend(track_const_dotnet(const_name, source_dir, record, stats, encoding))

        # ── Groovy ────────────────────────────────────────────────────────
        elif lang == "groovy":
            if record.usage_type == "static final定数定義":
                const_name = extract_static_final_name(record.code)
                if const_name:
                    result.extend(track_static_final_groovy(
                        const_name, source_dir, record, stats, encoding,
                    ))
            elif record.usage_type == "変数代入" and is_class_level_field(record.code):
                import re as _re
                m = _re.search(r'(\w+)\s*[=;]', record.code.strip())
                if m:
                    fname = m.group(1)
                    src_file = _resolve_file(record.filepath, source_dir)
                    if src_file:
                        result.extend(track_field_groovy(
                            fname, src_file, record, source_dir, stats, encoding,
                        ))
                        lines = _read_lines(src_file, encoding)
                        for g in find_getter_names_groovy(fname, lines):
                            groovy_getter_tasks.setdefault(g, []).append(record)
                        for s in find_setter_names_groovy(fname, lines):
                            groovy_setter_tasks.setdefault(s, []).append(record)

        # ts / python / perl / plsql / other: 間接追跡なし

    # Java バッチ処理
    for var_name, origins in java_project_tasks.items():
        for origin in origins:
            result.extend(track_constant(var_name, source_dir, origin, stats))
    for getter_name, origins in java_getter_tasks.items():
        for origin in origins:
            result.extend(track_getter_calls(getter_name, source_dir, origin, stats))
    for setter_name, origins in java_setter_tasks.items():
        for origin in origins:
            result.extend(track_setter_calls(setter_name, source_dir, origin, stats))

    # Groovy getter/setter バッチ処理
    result.extend(_batch_track_getter_setter_groovy(
        groovy_getter_tasks, groovy_setter_tasks, source_dir, stats, encoding,
    ))

    return result
```

**Note on Kotlin const name extraction:** In the Kotlin branch, `record.code.split("=")[0].strip().split()[-1]` extracts the constant name from a line like `const val STATUS = "TARGET"`. This gives `"STATUS"`. If the code format is different (e.g., type annotation), use the same extraction logic as `analyze_kotlin.py` which relies on the pattern `const val \w+ =`.

- [ ] **Step 4: Fix Kotlin const extraction to use a regex**

Replace the Kotlin indirect tracking branch in `_apply_indirect_tracking` with:

```python
        # ── Kotlin ────────────────────────────────────────────────────────
        elif lang == "kotlin":
            if record.usage_type == "const val定数定義":
                m = re.search(r'\bconst\s+val\s+(\w+)', record.code)
                if m:
                    result.extend(_track_const_kotlin(
                        m.group(1), source_dir, record, stats, encoding,
                    ))
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/test_all_analyzer.py::TestIndirectTracking -v
```

Expected: all `TestIndirectTracking` tests PASS

- [ ] **Step 6: Confirm no regressions**

```bash
python -m pytest tests/ -q --no-header 2>&1 | tail -3
```

Expected: `161 passed`

- [ ] **Step 7: Commit**

```bash
git add analyze_all.py tests/test_all_analyzer.py
git commit -m "feat: add indirect tracking dispatch to analyze_all"
```

---

## Task 4: main() + E2E Test

**Files:**
- Modify: `analyze_all.py` (add `build_parser()` + `main()`)
- Create: `tests/all/input/TARGET.grep`
- Create: `tests/all/src/Main.java`
- Create: `tests/all/src/Service.groovy`
- Create: `tests/all/src/deploy.sh`
- Create: `tests/all/src/config.xml`
- Create: `tests/all/src/cleanup` (Perl, no extension)
- Create: `tests/all/expected/TARGET.tsv`
- Modify: `tests/test_all_analyzer.py` (add `TestE2EAll`)

- [ ] **Step 1: Create test fixture source files**

```bash
mkdir -p tests/all/src tests/all/input tests/all/expected
```

Create `tests/all/src/Main.java`:
```java
public class Main {
    static final String THRESHOLD = "TARGET";
}
```

Create `tests/all/src/Service.groovy`:
```groovy
class Service {
    def check(code) {
        if (code == THRESHOLD) { return true }
    }
}
```

Create `tests/all/src/deploy.sh`:
```bash
#!/bin/sh
THRESHOLD="TARGET"
echo $THRESHOLD
```

Create `tests/all/src/config.xml`:
```xml
<config><value>TARGET</value></config>
```

Create `tests/all/src/cleanup` (no extension, Perl):
```perl
#!/usr/bin/perl
my $val = "TARGET";
print $val;
```

- [ ] **Step 2: Create input grep file**

Create `tests/all/input/TARGET.grep` with these exact lines (replace `tests/all/src` with the relative path that matches what grep would produce — use relative paths from repo root):

```
tests/all/src/Main.java:2:    static final String THRESHOLD = "TARGET";
tests/all/src/Service.groovy:3:        if (code == THRESHOLD) { return true }
tests/all/src/deploy.sh:2:THRESHOLD="TARGET"
tests/all/src/config.xml:1:<config><value>TARGET</value></config>
tests/all/src/cleanup:2:my $val = "TARGET";
```

- [ ] **Step 3: Write the E2E test (will fail until main() exists)**

Add to `tests/test_all_analyzer.py`:

```python
class TestE2EAll(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "all"

    def test_all_input_lines_appear_in_output(self):
        """全grep行がTSVに含まれること（漏れゼロ確認）。"""
        src_dir   = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"

        self.assertTrue(src_dir.exists(), f"src_dir not found: {src_dir}")
        self.assertTrue(input_dir.exists(), f"input_dir not found: {input_dir}")

        grep_path = input_dir / "TARGET.grep"
        input_lines = [
            l for l in grep_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        self.assertGreater(len(input_lines), 0)

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = aa.ProcessStats()
            keyword = "TARGET"

            direct_records = aa.process_grep_lines_all(
                input_lines, keyword, src_dir, stats, None,
            )
            all_records = list(direct_records)
            all_records.extend(
                aa._apply_indirect_tracking(direct_records, src_dir, stats, None)
            )
            output_path = output_dir / "TARGET.tsv"
            aa.write_tsv(all_records, output_path)

            # すべての直接参照 filepath が出力に含まれる
            output_filepaths = {r.filepath for r in all_records if r.ref_type == "直接"}
            for line in input_lines:
                parsed = aa.parse_grep_line(line)
                if parsed:
                    self.assertIn(
                        parsed["filepath"], output_filepaths,
                        f"Missing in output: {parsed['filepath']}",
                    )

    def test_unknown_extension_has_other_usage_type(self):
        src_dir   = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"
        grep_path = input_dir / "TARGET.grep"
        input_lines = grep_path.read_text(encoding="utf-8").splitlines()
        stats = aa.ProcessStats()
        records = aa.process_grep_lines_all(input_lines, "TARGET", src_dir, stats, None)
        xml_records = [r for r in records if r.filepath.endswith(".xml")]
        self.assertEqual(len(xml_records), 1)
        self.assertEqual(xml_records[0].usage_type, "その他")

    def test_no_extension_perl_not_other(self):
        src_dir   = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"
        grep_path = input_dir / "TARGET.grep"
        input_lines = grep_path.read_text(encoding="utf-8").splitlines()
        stats = aa.ProcessStats()
        records = aa.process_grep_lines_all(input_lines, "TARGET", src_dir, stats, None)
        cleanup_records = [r for r in records if r.filepath.endswith("cleanup")]
        self.assertEqual(len(cleanup_records), 1)
        self.assertNotEqual(cleanup_records[0].usage_type, "その他")
```

- [ ] **Step 4: Run E2E test to confirm it passes (process_grep_lines_all + write_tsv already exist)**

```bash
python -m pytest tests/test_all_analyzer.py::TestE2EAll -v
```

Expected: all `TestE2EAll` tests PASS (they only use `process_grep_lines_all` and `_apply_indirect_tracking`, not `main()`)

- [ ] **Step 5: Implement `build_parser()` and `main()` in `analyze_all.py`**

Append to `analyze_all.py`:

```python
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="全言語対応ディスパッチャー grep結果 自動分類・使用箇所洗い出しツール"
    )
    parser.add_argument("--source-dir", required=True, help="ソースコードのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input",  help="grep結果ファイルのディレクトリ")
    parser.add_argument("--output-dir", default="output", help="TSV出力先ディレクトリ")
    parser.add_argument("--encoding",   default=None,     help="文字コード強制指定（例: utf-8, cp932）")
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
            enc = detect_encoding(grep_path, args.encoding)
            raw_lines = grep_path.read_text(encoding=enc, errors="replace").splitlines()

            direct_records = process_grep_lines_all(
                raw_lines, keyword, source_dir, stats, args.encoding,
            )
            all_records = list(direct_records)
            all_records.extend(
                _apply_indirect_tracking(direct_records, source_dir, stats, args.encoding)
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

- [ ] **Step 6: Smoke-test CLI with --help**

```bash
python analyze_all.py --help
```

Expected: prints usage with `--source-dir`, `--input-dir`, `--output-dir`, `--encoding` options

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -q --no-header 2>&1 | tail -5
```

Expected: all tests pass (161 + new tests = no failures)

- [ ] **Step 8: Commit**

```bash
git add analyze_all.py tests/test_all_analyzer.py \
        tests/all/src/Main.java tests/all/src/Service.groovy \
        tests/all/src/deploy.sh tests/all/src/config.xml \
        tests/all/src/cleanup tests/all/input/TARGET.grep
git commit -m "feat: complete analyze_all.py with main() and E2E tests"
```

---

---

## Task 5: Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/tool-overview.md`
- Modify: `docs/repository-structure.md`

- [ ] **Step 1: Update `README.md`**

In the `## 対応言語` 表に1行追加（表の末尾）:

```markdown
| 全言語（振り分け） | `analyze_all.py` | ✅ 各言語に準ずる | ✅ 各言語に準ずる |
```

`## 言語別の実行例` セクション先頭に追加:

```markdown
# 全言語まとめて処理（推奨）
python analyze_all.py --source-dir ./src --input-dir input --output-dir output
```

- [ ] **Step 2: Update `docs/tool-overview.md`**

`analyze_all.py` の説明を追記する。既存ツール一覧の末尾、または「振り分けシェルの代替」として以下の内容を追加:

```markdown
## analyze_all.py（全言語ディスパッチャー）

grep結果に複数言語のファイルが混在する場合に使用する。1回の実行で全行を処理し、
ファイル拡張子（または拡張子なしファイルのシバン行）で言語を判定して適切な分類器に振り分ける。
対応外拡張子（.xml / .yaml / .properties など）は使用タイプ「その他」として出力され、漏れゼロを保証する。
出力は `output/TARGET.tsv` 1本（既存アナライザーと同形式）。
```

- [ ] **Step 3: Update `docs/repository-structure.md`**

`analyze_all.py` を `analyze_groovy.py` の次行などに追記:

```
analyze_all.py          全言語対応ディスパッチャー（拡張子/シバン判定 → 各分類器に振り分け）
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/tool-overview.md docs/repository-structure.md
git commit -m "docs: document analyze_all.py in README and tool docs"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ 拡張子ルーティングテーブル → `_EXT_TO_LANG` (Task 1)
- ✅ シバン判定 (perl/sh/csh/tcsh/ksh/ksh93) → `detect_language()` (Task 1)
- ✅ 対応外拡張子 → `"その他"` で出力 → `_classify_for_lang()` (Task 2)
- ✅ 全言語分類器ディスパッチ → `_SIMPLE_CLASSIFIERS` + Java特殊処理 (Task 2)
- ✅ 間接追跡 (java/kotlin/c/proc/sh/sql/dotnet/groovy) → `_apply_indirect_tracking()` (Task 3)
- ✅ ts/python/perl/plsql/other は間接追跡なし → Task 3 の各 `elif` に含まれない
- ✅ 出力は1本のTSV → `write_tsv()` (Task 4)
- ✅ CLI引数は既存アナライザーと共通 → `build_parser()` (Task 4)
- ✅ テスト: 拡張子あり各言語、拡張子なし+シバン、未知拡張子、漏れゼロ確認 → Task 1-4
- ✅ ドキュメント更新 (README / tool-overview / repository-structure) → Task 5

**Type consistency check:**
- `process_grep_lines_all` returns `list[GrepRecord]` ✅ consumed by `_apply_indirect_tracking` ✅
- `detect_language` returns `str` ✅ used in `_classify_for_lang` and `_apply_indirect_tracking` ✅
- `_apply_indirect_tracking(direct_records, source_dir, stats, encoding)` — all callers pass exactly these 4 args ✅
