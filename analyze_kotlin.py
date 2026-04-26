# analyze_kotlin.py
"""DEPRECATED shim: ``grep_helper.languages.kotlin``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import kotlin as _handler
from grep_helper.languages.kotlin import (  # noqa: F401
    classify_usage as _classify_usage_new,
    extract_const_name,
    track_const,
)

# analyze_common 互換シンボルの再エクスポート（テスト互換のため）
from analyze_common import ProcessStats, write_tsv  # noqa: F401

# 旧 API 互換 (Phase 7 で削除予定)
classify_usage_kotlin = _classify_usage_new  # noqa: E305


def process_grep_file(path, keyword, source_dir, stats, encoding_override=None):
    """後方互換ラッパー。"""
    from grep_helper.pipeline import process_grep_file as _pgf
    return _pgf(path, source_dir, _handler, keyword=keyword, encoding=encoding_override, stats=stats)


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Kotlin grep結果 自動分類・使用箇所洗い出しツール"))
