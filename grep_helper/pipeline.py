"""共通パイプライン（Phase 2 で本実装）。"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType


def process_grep_file(  # pragma: no cover - phase2 で実装
    grep_path: Path,
    src_dir: Path,
    handler: ModuleType,
    *,
    encoding: str | None = None,
    workers: int = 1,
):
    raise NotImplementedError
