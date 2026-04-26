"""共通パイプライン: grep行 → handler.classify_usage → GrepRecord 変換。"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

from grep_helper.encoding import detect_encoding
from grep_helper.grep_input import iter_grep_lines, parse_grep_line
from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType


def process_grep_file(
    grep_path: Path,
    src_dir: Path,
    handler: ModuleType,
    *,
    keyword: str | None = None,
    encoding: str | None = None,
    stats: ProcessStats | None = None,
) -> list[GrepRecord]:
    """grep ファイルを 1 本処理し、handler.classify_usage で分類した直接参照レコードを返す。

    handler は ``classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str``
    を持つモジュール（duck typing）。
    """
    if keyword is None:
        keyword = grep_path.stem
    if stats is None:
        stats = ProcessStats()
    enc = detect_encoding(grep_path, encoding)

    records: list[GrepRecord] = []
    for line in iter_grep_lines(grep_path, enc):
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        try:
            lineno_int = int(parsed["lineno"])
        except ValueError:
            lineno_int = 0
        ctx = ClassifyContext(
            filepath=parsed["filepath"],
            lineno=lineno_int,
            source_dir=src_dir,
            stats=stats,
            encoding_override=encoding,
        )
        usage = handler.classify_usage(parsed["code"], ctx=ctx)
        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=usage,
            filepath=parsed["filepath"],
            lineno=parsed["lineno"],
            code=parsed["code"],
        ))
        stats.valid_lines += 1
    return records
