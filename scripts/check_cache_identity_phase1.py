"""Phase 1 完了時のキャッシュ同一性チェック。

shim と新パッケージの両方から取得した dict が同一オブジェクトであることを確認する。
失敗した場合は AssertionError で終了する。
"""
from __future__ import annotations

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加（`python scripts/check_cache_identity_phase1.py`
# 形式での起動でも analyze_common を import できるようにする）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyze_common  # noqa: E402
import grep_helper.file_cache  # noqa: E402
import grep_helper.source_files  # noqa: E402


def main() -> None:
    assert analyze_common._file_lines_cache is grep_helper.file_cache._file_lines_cache, \
        "_file_lines_cache identity broken"
    assert analyze_common._source_files_cache is grep_helper.source_files._source_files_cache, \
        "_source_files_cache identity broken"
    assert analyze_common._resolve_file_cache is grep_helper.source_files._resolve_file_cache, \
        "_resolve_file_cache identity broken"
    print("Phase 1 cache identity: OK")


if __name__ == "__main__":
    main()
