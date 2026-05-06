"""文字コード検出。"""
from __future__ import annotations

from pathlib import Path

try:
    import chardet as _chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False


# プロセス内グローバルキャッシュ。override が None のケースのみキャッシュする。
# キーは str(path)。Path.resolve() は使わない（NFS で realpath コストが効くため、
# source_files._resolve_file_cache と同じ流儀）。
_encoding_cache: dict[str, str] = {}


def _encoding_cache_clear() -> None:
    """テスト/チューニング用: キャッシュをクリア。"""
    _encoding_cache.clear()


def detect_encoding(path: Path, override: str | None = None) -> str:
    """ファイルの文字コードを検出する。overrideがあればそのまま返す。

    巨大ファイル対策として先頭 4096 バイトのみを読む。
    結果はパス単位でキャッシュし、同一プロセス内の重複呼び出しでは
    chardet・I/O を起動しない。
    """
    if override is not None:
        return override
    key = str(path)
    cached = _encoding_cache.get(key)
    if cached is not None:
        return cached

    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
    except OSError:
        _encoding_cache[key] = "cp932"
        return "cp932"
    if not _CHARDET_AVAILABLE:
        _encoding_cache[key] = "cp932"
        return "cp932"
    result = _chardet.detect(raw)
    if result and result.get("confidence", 0) >= 0.6 and result.get("encoding"):
        encoding = result["encoding"]
    else:
        encoding = "cp932"
    _encoding_cache[key] = encoding
    return encoding
