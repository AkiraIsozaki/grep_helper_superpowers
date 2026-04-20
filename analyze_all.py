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


# ---------------------------------------------------------------------------
# 分類器インポート
# ---------------------------------------------------------------------------

from collections.abc import Callable

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

_SIMPLE_CLASSIFIERS: dict[str, Callable[[str], str]] = {
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
    # NOTE: _encoding_override is a module global in analyze.py — not thread-safe.
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
        return classifier(code)
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
                m = re.search(r'\bconst\s+val\s+(\w+)', record.code)
                if m:
                    result.extend(_track_const_kotlin(
                        m.group(1), source_dir, record, stats, encoding,
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
                m = re.search(r'(\w+)\s*[=;]', record.code.strip())
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
