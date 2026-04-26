"""言語ハンドラレジストリ。

Phase 4 時点では拡張子マップ + ``detect_handler`` の簡易版のみ提供する。
シバン判定は Phase 7 で完成させる。
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

from grep_helper.languages import _none

EXT_TO_HANDLER: dict[str, ModuleType] = {}
SHEBANG_TO_HANDLER: dict[str, ModuleType] = {}


def _register(handler: ModuleType) -> None:
    for ext in getattr(handler, "EXTENSIONS", ()):
        EXT_TO_HANDLER[ext] = handler
    for sb in getattr(handler, "SHEBANGS", ()):
        SHEBANG_TO_HANDLER[sb] = handler


def detect_handler(filepath: str, src_dir: Path) -> ModuleType:
    """拡張子からハンドラを引く。拡張子なしや未登録は ``_none`` を返す。

    Phase 4 簡易版: シバン判定は実装しない（Phase 7 で完成）。
    """
    ext = Path(filepath).suffix.lower()
    if ext:
        return EXT_TO_HANDLER.get(ext, _none)
    return _none


# 既存ハンドラ登録（Phase ごとに追記）
from grep_helper.languages import (  # noqa: E402
    python as _python,
    perl as _perl,
    ts as _ts,
    plsql as _plsql,
    sh as _sh,
    sql as _sql,
    kotlin as _kotlin,
    dotnet as _dotnet,
    groovy as _groovy,
    c as _c,
)

for _h in (_python, _perl, _ts, _plsql, _sh, _sql, _kotlin, _dotnet, _groovy, _c, _none):
    _register(_h)
