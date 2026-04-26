"""TypeScript/JavaScript grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx")

_TS_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\s+\w+\s*='),                          "const定数定義"),
    (re.compile(r'\b(?:let|var)\s+\w+\s*='),                    "変数代入(let/var)"),
    (re.compile(r'\bif\s*\(|\bswitch\s*\(|===|!==|==(?!=)|!=(?!=)'), "条件判定"),
    (re.compile(r'\breturn\b'),                                  "return文"),
    (re.compile(r'@\w+'),                                        "デコレータ"),
    (re.compile(r'\w+\s*\('),                                    "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """TypeScript/JavaScriptコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _TS_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
