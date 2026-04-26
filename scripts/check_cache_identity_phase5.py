"""Phase 5 完了時のキャッシュ同一性チェック（Pro*C の _define_map_cache）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyze_proc  # noqa: E402
import grep_helper.languages.proc_define_map  # noqa: E402


def main() -> None:
    assert analyze_proc._define_map_cache is grep_helper.languages.proc_define_map._define_map_cache, \
        "_define_map_cache (proc) identity broken"
    print("Phase 5 cache identity: OK")


if __name__ == "__main__":
    main()
