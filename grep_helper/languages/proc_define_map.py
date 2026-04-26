"""Pro*C: #define リバースマップ構築・キャッシュ層。"""
from __future__ import annotations

import re
from pathlib import Path

from grep_helper.encoding import detect_encoding
from grep_helper.file_cache import cached_file_lines
from grep_helper.model import ProcessStats
from grep_helper.source_files import iter_source_files
from grep_helper.languages.c import _build_reverse_define_map  # reuse from C

# キャッシュ同一性保持: shim から `as _define_map_cache` で参照される
_define_map_cache: dict[tuple[str, str], tuple[dict[str, str], dict[str, list[str]]]] = {}

_DEFINE_PAT = re.compile(r'#\s*define\s+(\w+)\s+')
_DEFINE_ALIAS_PAT = re.compile(r'#\s*define\s+(\w+)\s+(\w+)\s*$')


def _build_define_map(
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> dict[str, str]:
    """src_dir 配下の全 .pc/.c/.h ソースから #define NAME IDENTIFIER 形式のマップを構築する。"""
    cache_key = (str(src_dir), encoding_override or "")
    cached = _define_map_cache.get(cache_key)
    if cached is not None:
        return cached[0]
    define_map: dict[str, str] = {}
    src_files = iter_source_files(src_dir, [".pc", ".c", ".h"])
    for src_file in src_files:
        enc = detect_encoding(src_file, encoding_override)
        for line in cached_file_lines(src_file, enc, stats):
            m = _DEFINE_ALIAS_PAT.match(line.strip())
            if m:
                define_map[m.group(1)] = m.group(2)
    _define_map_cache[cache_key] = (define_map, _build_reverse_define_map(define_map))
    return define_map


def _get_reverse_define_map(src_dir: Path, encoding_override: str | None) -> dict[str, list[str]]:
    cache_key = (str(src_dir), encoding_override or "")
    cached = _define_map_cache.get(cache_key)
    return cached[1] if cached is not None else {}
