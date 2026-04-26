"""Pro*C: 変数名・マクロ名抽出および間接参照追跡ヘルパー。"""
from __future__ import annotations

import re
from pathlib import Path

from grep_helper.model import GrepRecord, ProcessStats, RefType
from grep_helper.encoding import detect_encoding
from grep_helper.file_cache import cached_file_lines
from grep_helper.source_files import iter_source_files, resolve_file_cached
from grep_helper.languages.c import _collect_define_aliases
from grep_helper.languages.proc_define_map import (
    _build_define_map,
    _get_reverse_define_map,
    _DEFINE_PAT,
)

# ---------------------------------------------------------------------------
# 変数名・マクロ名抽出
# ---------------------------------------------------------------------------

_C_TYPES_PAT = re.compile(
    r'\b(?:char|int|short|long|float|double|unsigned|signed|struct|void'
    r'|SQLCHAR|SQLINT|VARCHAR)\b\s*\**\s*(\w+)'
)


def extract_variable_name_proc(code: str) -> str | None:
    """C変数宣言から変数名を抽出する（型名の後の識別子）。"""
    m = _C_TYPES_PAT.search(code)
    return m.group(1) if m else None


def extract_define_name(code: str) -> str | None:
    """#define からマクロ名を抽出する。値のない #define は None を返す。"""
    m = _DEFINE_PAT.match(code)
    return m.group(1) if m else None


def extract_host_var_name(code: str) -> str | None:
    """ホスト変数名を抽出する（strcpy / EXEC SQL INTO / 単純代入）。"""
    m = re.match(r'\s*str(?:n?cpy)\s*\(\s*(\w+)', code)
    if m:
        return m.group(1)
    m = re.match(r'\s*sprintf\s*\(\s*(\w+)', code)
    if m:
        return m.group(1)
    m = re.search(r'\bINTO\s*:(\w+)', code, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.match(r'\s*(\w+)\s*=\s*"', code)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 間接参照追跡
# ---------------------------------------------------------------------------

def track_define(
    var_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """#define マクロ名の使用箇所を src_dir 配下の全 .pc/.c/.h ファイルでスキャンする（多段解決）。"""
    # deferred import to avoid circular dependency with proc.py
    from grep_helper.languages.proc import _classify_for_filepath  # noqa: PLC0415

    results: list[GrepRecord] = []
    def_file = resolve_file_cached(record.filepath, src_dir)

    pc_files = iter_source_files(src_dir, [".pc", ".c", ".h"])

    define_map = _build_define_map(src_dir, stats, encoding_override)
    aliases = _collect_define_aliases(
        var_name, define_map, reverse=_get_reverse_define_map(src_dir, encoding_override)
    )
    scan_names = [var_name] + aliases

    for scan_name in scan_names:
        pattern = re.compile(r'\b' + re.escape(scan_name) + r'\b')
        for pc_file in pc_files:
            try:
                filepath_str = str(pc_file.relative_to(src_dir))
            except ValueError:
                filepath_str = str(pc_file)

            lines = cached_file_lines(
                Path(pc_file), detect_encoding(Path(pc_file), encoding_override), stats
            )
            for i, line in enumerate(lines, 1):
                if (scan_name == var_name
                        and def_file is not None
                        and pc_file.resolve() == def_file.resolve()
                        and i == int(record.lineno)):
                    continue
                if pattern.search(line):
                    results.append(GrepRecord(
                        keyword=record.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=_classify_for_filepath(line.strip(), str(pc_file)),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=line.strip(),
                        src_var=scan_name,
                        src_file=record.filepath,
                        src_lineno=record.lineno,
                    ))
    return results


def track_variable(
    var_name: str,
    candidate: Path,
    def_lineno: int,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """C変数名の使用箇所を同一ファイル内でスキャンする。"""
    # deferred import to avoid circular dependency with proc.py
    from grep_helper.languages.proc import classify_usage_proc  # noqa: PLC0415

    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    try:
        filepath_str = str(candidate.relative_to(src_dir))
    except ValueError:
        filepath_str = str(candidate)

    lines = cached_file_lines(
        Path(candidate), detect_encoding(Path(candidate), encoding_override), stats
    )
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_proc(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results
