"""Python grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".py",)

_PYTHON_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^\s*\w+\s*='),                          "変数代入"),
    (re.compile(r'\bif\b|\belif\b|==|!=|\bin\b'),         "条件判定"),
    (re.compile(r'\breturn\b'),                            "return文"),
    (re.compile(r'@\w+'),                                  "デコレータ"),
    (re.compile(r'\w+\s*\('),                              "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Pythonコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PYTHON_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
