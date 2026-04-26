"""grep 結果ファイルの読み込みとパース。"""
from __future__ import annotations

import re
from pathlib import Path

_BINARY_PATTERN = re.compile(r'^Binary file .+ matches$')
_GREP_LINE_PATTERN = re.compile(r':(\d+):')


def iter_grep_lines(path: Path, encoding: str):
    """grep 結果ファイルを 1 行ずつジェネレータで返す。

    巨大ファイル対策。改行は除去済み。
    """
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        for line in f:
            yield line.rstrip("\n").rstrip("\r")


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
