"""Phase 6 完了時のキャッシュ同一性チェック（Java AST キャッシュ）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grep_helper.languages import java as _java_handler  # noqa: E402
import grep_helper.languages.java_ast as java_ast  # noqa: E402


def main() -> None:
    assert _java_handler.java_ast._ast_cache is java_ast._ast_cache, \
        "_ast_cache identity broken"
    assert _java_handler.java_ast._ast_line_index is java_ast._ast_line_index, \
        "_ast_line_index identity broken"
    assert _java_handler.java_ast._method_starts_cache is java_ast._method_starts_cache, \
        "_method_starts_cache identity broken"
    print("Phase 6 cache identity: OK")


if __name__ == "__main__":
    main()
