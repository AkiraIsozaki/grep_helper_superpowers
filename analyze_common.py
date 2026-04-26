"""DEPRECATED: ``grep_helper`` への移行用 shim。Phase 7 で削除予定。"""
from __future__ import annotations

from pathlib import Path as _Path

# エンコーディング（detect_encoding は analyze_common.open を patch するテストのため
# このモジュールの globals 内で定義する必要がある）
try:
    import chardet as _chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False
    _chardet = None  # type: ignore[assignment]

# モデル・列挙型・データクラス
from grep_helper.model import GrepRecord, ProcessStats, RefType, ClassifyContext  # noqa: F401

# grep 入力
from grep_helper.grep_input import (  # noqa: F401
    iter_grep_lines, parse_grep_line, _BINARY_PATTERN, _GREP_LINE_PATTERN,
)

# TSV 出力
from grep_helper.tsv_output import write_tsv, _TSV_HEADERS, _EXTERNAL_SORT_THRESHOLD  # noqa: F401

# ソースファイル探索（`as _Y` は PEP 484 の意図的 re-export マーカー。
# dict 同一性はソースモジュールでの再代入がないことで保証される）
from grep_helper.source_files import (  # noqa: F401
    iter_source_files, grep_filter_files, resolve_file_cached,
    _source_files_cache_clear, _resolve_file_cache_clear,
    _source_files_cache as _source_files_cache,
    _resolve_file_cache as _resolve_file_cache,
)

# ファイル行 LRU キャッシュ（同一性保証は上記 source_files セクションのコメント参照）
from grep_helper.file_cache import (  # noqa: F401
    cached_file_lines, set_file_lines_cache_limit, _file_lines_cache_clear,
    _file_lines_cache as _file_lines_cache,
)

# スキャナ
from grep_helper.scanner import build_batch_scanner, _BatchScanner  # noqa: F401


def detect_encoding(path: _Path, override: str | None = None) -> str:
    """ファイルの文字コードを検出する。overrideがあればそのまま返す。

    巨大ファイル対策として先頭 4096 バイトのみを読む。
    テスト互換性のためこのモジュールの globals 内で定義する。
    """
    if override is not None:
        return override
    try:
        with open(path, "rb") as f:  # noqa: WPS433
            raw = f.read(4096)
    except OSError:
        return "cp932"
    if not _CHARDET_AVAILABLE:
        return "cp932"
    result = _chardet.detect(raw)
    if result and result.get("confidence", 0) >= 0.6 and result.get("encoding"):
        return result["encoding"]
    return "cp932"
