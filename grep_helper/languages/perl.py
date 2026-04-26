"""Perl grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".pl", ".pm")
SHEBANGS: tuple[str, ...] = ("perl",)

_PERL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\buse\s+constant\b'),                          "use constant定義"),
    (re.compile(r'\bif\s*\(|\bunless\s*\(|==|\bne\b|\beq\b'),   "条件判定"),
    (re.compile(r'\$\w+\s*=|\bmy\b.*=|\bour\b.*='),             "変数代入"),
    (re.compile(r'\bprint\b|\bsay\b|\bprintf\b'),                "print/say出力"),
    (re.compile(r'\w+\s*\('),                                    "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Perlコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PERL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
