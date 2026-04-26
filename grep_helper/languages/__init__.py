"""言語ハンドラレジストリ。"""
from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType

from grep_helper.languages import _none

EXT_TO_HANDLER: dict[str, ModuleType] = {}
SHEBANG_TO_HANDLER: dict[str, ModuleType] = {}

_SHEBANG_PAT = re.compile(r'^#!\s*(?:.*/)?(?:env\s+)?(\S+)')


def _register(handler: ModuleType) -> None:
    for ext in getattr(handler, "EXTENSIONS", ()):
        EXT_TO_HANDLER[ext] = handler
    for sb in getattr(handler, "SHEBANGS", ()):
        SHEBANG_TO_HANDLER[sb] = handler


def detect_handler(filepath: str, src_dir: Path) -> ModuleType:
    """拡張子 → シバン の順でハンドラを引く。不明は _none。"""
    ext = Path(filepath).suffix.lower()
    if ext:
        return EXT_TO_HANDLER.get(ext, _none)

    # 拡張子なし: ファイル先頭行を読んでシバン判定
    from grep_helper.source_files import resolve_file_cached  # noqa: PLC0415
    candidate = resolve_file_cached(filepath, src_dir)
    if candidate is None:
        return _none
    try:
        first_line = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        m = _SHEBANG_PAT.match(first_line)
        if m:
            return SHEBANG_TO_HANDLER.get(m.group(1).lower(), _none)
    except Exception:
        pass
    return _none


# 全言語登録
from grep_helper.languages import (  # noqa: E402
    java, kotlin, c, proc, sql, sh, ts, python, perl, dotnet, groovy, plsql,
)

for _h in (java, kotlin, c, proc, sql, sh, ts, python, perl, dotnet, groovy, plsql, _none):
    _register(_h)
