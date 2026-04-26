"""Phase 4 完了時のキャッシュ同一性チェック（C の _define_map_cache）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyze_c  # noqa: E402
import grep_helper.languages.c  # noqa: E402


def main() -> None:
    assert analyze_c._define_map_cache is grep_helper.languages.c._define_map_cache, \
        "_define_map_cache (c) identity broken"
    print("Phase 4 cache identity: OK")


if __name__ == "__main__":
    main()
