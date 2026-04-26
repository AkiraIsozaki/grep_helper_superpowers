"""PL/SQL grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".pls", ".pck", ".prc", ".pkb", ".pks", ".fnc", ".trg")

_PLSQL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bCONSTANT\b|:=', re.IGNORECASE),                    "定数/変数宣言"),
    (re.compile(r'\bWHEN\b.*\bTHEN\b|\bRAISE\b', re.IGNORECASE),       "EXCEPTION処理"),
    (re.compile(r'\bIF\b.*\bTHEN\b|\bCASE\s+WHEN\b', re.IGNORECASE),   "条件判定"),
    (re.compile(r'\bCURSOR\b.*\bIS\b', re.IGNORECASE),                  "カーソル定義"),
    (re.compile(r'\bINSERT\b|\bUPDATE\b.*\bSET\b', re.IGNORECASE),     "INSERT/UPDATE値"),
    (re.compile(r'\bWHERE\b', re.IGNORECASE),                           "WHERE条件"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """PL/SQLコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PLSQL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
