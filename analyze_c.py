# analyze_c.py
"""DEPRECATED shim: ``grep_helper.languages.c``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import c as _handler
from grep_helper.languages.c import (  # noqa: F401
    classify_usage as _classify_usage_new,
    extract_variable_name_c,
    extract_define_name,
    _build_define_map,
    _build_reverse_define_map,
    _get_reverse_define_map,
    _collect_define_aliases,
    track_define,
    track_variable,
    _define_map_cache as _define_map_cache,  # dict identity preserved
)
from analyze_common import ProcessStats, write_tsv  # noqa: F401

classify_usage_c = _classify_usage_new  # noqa: E305


def process_grep_file(path, keyword, source_dir, stats, encoding_override=None):
    """後方互換ラッパー。"""
    from grep_helper.pipeline import process_grep_file as _pgf
    return _pgf(path, source_dir, _handler, keyword=keyword, encoding=encoding_override, stats=stats)


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="C grep結果 自動分類・使用箇所洗い出しツール"))
