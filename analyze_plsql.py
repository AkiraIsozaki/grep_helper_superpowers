"""DEPRECATED shim: ``grep_helper.languages.plsql``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import plsql as _handler
from grep_helper.languages.plsql import classify_usage as _classify_usage_new

# analyze_common から後方互換シンボルを再エクスポート
from analyze_common import (  # noqa: F401
    ProcessStats,
    GrepRecord,
    RefType,
    write_tsv,
    detect_encoding,
    iter_grep_lines,
    parse_grep_line,
)

# 旧 API 互換 (Phase 7 で削除予定)
classify_usage_plsql = _classify_usage_new  # noqa: E305
_PLSQL_EXTENSIONS = _handler.EXTENSIONS


def process_grep_file(path, keyword, source_dir, stats, encoding_override=None):  # noqa: ANN001
    """後方互換ラッパー。"""
    from analyze_common import detect_encoding, iter_grep_lines
    from grep_helper.model import GrepRecord, RefType
    from grep_helper.grep_input import parse_grep_line

    enc = detect_encoding(path, encoding_override)
    records = []
    for line in iter_grep_lines(path, enc):
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


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="PL/SQL grep結果 自動分類・使用箇所洗い出しツール"))
