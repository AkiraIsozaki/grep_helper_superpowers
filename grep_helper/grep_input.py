"""grep 結果ファイルの読み込みとパース。"""
from __future__ import annotations

import re
from pathlib import Path

_BINARY_PATTERN = re.compile(r'^Binary file .+ matches$')
_GREP_LINE_PATTERN = re.compile(r':(\d+):')
_FILEPATH_MAX_BYTES = 4096  # Linux PATH_MAX 相当。これを超える filepath はバイナリ混入の疑い
_DEFAULT_LINE_SIZE_LIMIT = 1024 * 1024  # 1MB。これを超える行はバイナリ混入として読み飛ばす


def iter_grep_lines(path: Path, encoding: str, *, max_line_size: int = _DEFAULT_LINE_SIZE_LIMIT):
    """grep 結果ファイルを 1 行ずつジェネレータで返す。

    巨大ファイル対策。改行は除去済み。max_line_size を超える単一行は
    （改行を含まない jar 等のバイナリ混入の疑いがあるため）読み飛ばす。
    """
    chunk = max_line_size + 1  # +1 で「上限を超えて打ち切られた」状態を判別可能にする
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        skipping = False
        while True:
            line = f.readline(chunk)
            if not line:
                break
            terminated = line.endswith(("\n", "\r"))
            if not terminated and len(line) >= chunk:
                # 改行に到達せず上限ぶん読んだ = 行が長すぎる。後続も含めスキップ。
                skipping = True
                continue
            if skipping:
                # スキップ中の行の最終断片（改行 or EOF まで到達）。捨てて再開。
                skipping = False
                continue
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
    if "\x00" in filepath or len(filepath) > _FILEPATH_MAX_BYTES:
        return None
    return {"filepath": filepath, "lineno": lineno, "code": code.strip()}
