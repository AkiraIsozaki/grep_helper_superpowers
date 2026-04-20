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
