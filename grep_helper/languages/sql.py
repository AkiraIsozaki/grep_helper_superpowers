"""SQL grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType

EXTENSIONS: tuple[str, ...] = (".sql",)

_SQL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bRAISE_APPLICATION_ERROR\b|\bEXCEPTION\b', re.IGNORECASE), "例外・エラー処理"),
    (re.compile(r':=|\bCONSTANT\b', re.IGNORECASE),                          "定数・変数定義"),
    (re.compile(r'\bWHERE\b|\bAND\b.*=|\bOR\b.*=', re.IGNORECASE),           "WHERE条件"),
    (re.compile(r'\bDECODE\s*\(|\bCASE\b.*\bWHEN\b', re.IGNORECASE),         "比較・DECODE"),
    (re.compile(r'\bINSERT\b|\bUPDATE\b.*\bSET\b|\bVALUES\s*\(', re.IGNORECASE), "INSERT/UPDATE値"),
    (re.compile(r'\bSELECT\b|\bINTO\b', re.IGNORECASE),                      "SELECT/INTO"),
]

_SQL_VAR_PATTERN = re.compile(r'^\s*(\w+)(?:\s+\w[\w\s\(\),]*?)?\s*:=', re.IGNORECASE)


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Oracle SQLコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _SQL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_sql_variable_name(code: str) -> str | None:
    """PL/SQL変数定義から変数名を抽出する（:= の左辺の最初の識別子）。"""
    m = _SQL_VAR_PATTERN.match(code)
    return m.group(1) if m else None


def track_sql_variable(
    var_name: str,
    filepath: Path,
    def_lineno: int,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """PL/SQL変数名の使用箇所を同一ファイル内でスキャンする。"""
    from grep_helper.file_cache import cached_file_lines
    from grep_helper.encoding import detect_encoding

    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b', re.IGNORECASE)
    try:
        filepath_str = str(filepath.relative_to(src_dir))
    except ValueError:
        filepath_str = str(filepath)

    lines = cached_file_lines(Path(filepath), detect_encoding(Path(filepath), encoding_override), stats)
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results
