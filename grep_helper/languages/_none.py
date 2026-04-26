"""言語不明ファイル用の no-op ハンドラ。"""
from __future__ import annotations

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = ()


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    return "その他"
