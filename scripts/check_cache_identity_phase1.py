"""Phase 1 完了時のキャッシュ同一性チェック。

shim と新パッケージの両方から取得した dict が同一オブジェクトであることを確認する。
失敗した場合は AssertionError で終了する。
"""
from __future__ import annotations

import analyze_common
import grep_helper.file_cache
import grep_helper.source_files


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
