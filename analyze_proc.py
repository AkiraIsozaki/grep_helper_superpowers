# analyze_proc.py
"""DEPRECATED shim: ``grep_helper.languages.proc``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import proc as _handler
from grep_helper.languages.proc import (  # noqa: F401
    classify_usage as _classify_usage_new,
    classify_usage_proc,
    _classify_for_filepath,
)
from grep_helper.languages.proc_define_map import (  # noqa: F401
    _define_map_cache as _define_map_cache,
    _build_define_map,
    _get_reverse_define_map,
)
from grep_helper.languages.proc_track import (  # noqa: F401
    extract_variable_name_proc,
    extract_define_name,
    extract_host_var_name,
    track_define,
    track_variable,
)

# テスト互換のため
from analyze_common import GrepRecord, ProcessStats, parse_grep_line, write_tsv  # noqa: F401


def process_grep_file(path, keyword, source_dir, stats, encoding_override=None):
    """後方互換ラッパー。"""
    from grep_helper.pipeline import process_grep_file as _pgf
    return _pgf(path, source_dir, _handler, keyword=keyword, encoding=encoding_override, stats=stats)


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Pro*C grep結果 自動分類・使用箇所洗い出しツール"))
