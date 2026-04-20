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
