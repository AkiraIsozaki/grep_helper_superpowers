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
        return (r.keyword, r.filepath, lineno_int)

    def _row_sort_key(row: list[str]) -> tuple:
        lineno_int = int(row[4]) if row[4].isdigit() else 0
        return (row[0], row[3], lineno_int)

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
