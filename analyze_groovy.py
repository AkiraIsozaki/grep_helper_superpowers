# analyze_groovy.py
"""DEPRECATED shim: ``grep_helper.languages.groovy``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import groovy as _handler
from grep_helper.languages.groovy import (  # noqa: F401
    classify_usage as _classify_usage_new,
    extract_static_final_name,
    is_class_level_field,
    find_getter_names_groovy,
    find_setter_names_groovy,
    track_static_final_groovy,
    track_field_groovy,
)
from analyze_common import ProcessStats, write_tsv  # noqa: F401

classify_usage_groovy = _classify_usage_new  # noqa: E305


def process_grep_file(path, keyword, source_dir, stats, encoding_override=None):
    """後方互換ラッパー。"""
    from grep_helper.pipeline import process_grep_file as _pgf
    return _pgf(path, source_dir, _handler, keyword=keyword, encoding=encoding_override, stats=stats)


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Groovy grep結果 自動分類・使用箇所洗い出しツール"))
