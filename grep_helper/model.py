"""共通データモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import NamedTuple


class RefType(Enum):
    DIRECT = "直接"
    INDIRECT = "間接"
    GETTER = "間接（getter経由）"
    SETTER = "間接（setter経由）"


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


@dataclass(frozen=True)
class ClassifyContext:
    """言語ハンドラの classify_usage が AST 解析等で使う共通コンテキスト。

    シンプル言語（python/perl/ts 等）はこの引数を受け取って無視する
    （`# noqa: ARG001` で明示）。Java など AST を見る言語は ``filepath`` ``lineno``
    ``source_dir`` を使う。dispatcher は常に渡す。
    """
    filepath: str
    lineno: int
    source_dir: Path
    stats: ProcessStats
    encoding_override: str | None = None
