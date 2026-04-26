"""Phase 1 完了時のキャッシュ同一性チェック。

grep_helper パッケージ内でキャッシュ dict が単一オブジェクトであることを確認する。
失敗した場合は AssertionError で終了する。
"""
from __future__ import annotations

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grep_helper.file_cache  # noqa: E402
import grep_helper.source_files  # noqa: E402


def main() -> None:
    # grep_helper 内での同一性確認（自己完結テスト）
    from grep_helper.file_cache import _file_lines_cache as cache1
    from grep_helper.source_files import _source_files_cache as cache2
    from grep_helper.source_files import _resolve_file_cache as cache3

    assert cache1 is grep_helper.file_cache._file_lines_cache, \
        "_file_lines_cache identity broken"
    assert cache2 is grep_helper.source_files._source_files_cache, \
        "_source_files_cache identity broken"
    assert cache3 is grep_helper.source_files._resolve_file_cache, \
        "_resolve_file_cache identity broken"
    print("Phase 1 cache identity: OK")


if __name__ == "__main__":
    main()
