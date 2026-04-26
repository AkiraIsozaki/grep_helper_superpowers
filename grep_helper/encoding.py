"""文字コード検出。"""
from __future__ import annotations

from pathlib import Path

try:
    import chardet as _chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False


def detect_encoding(path: Path, override: str | None = None) -> str:
    """ファイルの文字コードを検出する。overrideがあればそのまま返す。

    巨大ファイル対策として先頭 4096 バイトのみを読む。
    """
    if override is not None:
        return override
    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
    except OSError:
        return "cp932"
    if not _CHARDET_AVAILABLE:
        return "cp932"
    result = _chardet.detect(raw)
    if result and result.get("confidence", 0) >= 0.6 and result.get("encoding"):
        return result["encoding"]
    return "cp932"
