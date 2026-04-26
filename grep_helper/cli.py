"""共通 CLI 雛形（Phase 2 で本実装）。"""
from __future__ import annotations

import argparse
from types import ModuleType


def build_parser(description: str) -> argparse.ArgumentParser:  # pragma: no cover - phase2 で実装
    raise NotImplementedError


def run(handler: ModuleType, *, description: str | None = None) -> int:  # pragma: no cover - phase2 で実装
    raise NotImplementedError
