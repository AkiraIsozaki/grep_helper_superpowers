"""DEPRECATED shim: ``grep_helper.languages.sql``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import sql as _handler
from grep_helper.languages.sql import (  # noqa: F401
    classify_usage as _classify_usage_new,
    extract_sql_variable_name,
    track_sql_variable,
)

# analyze_common から後方互換シンボルを再エクスポート
from analyze_common import (  # noqa: F401
    ProcessStats,
    write_tsv,
)

# 旧 API 互換 (Phase 7 で削除予定)
classify_usage_sql = _classify_usage_new  # noqa: E305


def process_grep_file(path, keyword, source_dir, stats, encoding_override=None):  # noqa: ANN001
    """後方互換ラッパー。"""
    from grep_helper.pipeline import process_grep_file as _pgf
    return _pgf(path, source_dir, _handler, keyword=keyword, encoding=encoding_override, stats=stats)


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="SQL grep結果 自動分類・使用箇所洗い出しツール"))
