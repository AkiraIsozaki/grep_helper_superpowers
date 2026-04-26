"""ファイル行リスト LRU キャッシュ。"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from grep_helper.model import ProcessStats

_file_lines_cache: OrderedDict[str, list[str]] = OrderedDict()
_file_lines_cache_bytes: int = 0
_file_lines_cache_limit: int = 256 * 1024 * 1024  # 256MB


def _file_lines_cache_clear() -> None:
    global _file_lines_cache_bytes
    _file_lines_cache.clear()
    _file_lines_cache_bytes = 0


def set_file_lines_cache_limit(n_bytes: int) -> None:
    """テスト/チューニング用: キャッシュの合計バイト上限を変更する。"""
    global _file_lines_cache_limit
    _file_lines_cache_limit = n_bytes


def _estimate_lines_bytes(lines: list[str]) -> int:
    return sum(len(s) for s in lines) + 64 * len(lines)  # おおよその overhead


def cached_file_lines(
    path: Path,
    encoding: str,
    stats: ProcessStats | None = None,
) -> list[str]:
    """ファイルの行リストをサイズベース LRU キャッシュ経由で返す。"""
    global _file_lines_cache_bytes
    key = str(path)
    if key in _file_lines_cache:
        _file_lines_cache.move_to_end(key)
        return _file_lines_cache[key]
    try:
        lines = path.read_text(encoding=encoding, errors="replace").splitlines()
    except Exception:
        if stats is not None:
            stats.encoding_errors.add(key)
        lines = []
    size = _estimate_lines_bytes(lines)
    _file_lines_cache[key] = lines
    _file_lines_cache_bytes += size
    while _file_lines_cache_bytes > _file_lines_cache_limit and len(_file_lines_cache) > 1:
        _, old_lines = _file_lines_cache.popitem(last=False)
        _file_lines_cache_bytes -= _estimate_lines_bytes(old_lines)
    return lines
