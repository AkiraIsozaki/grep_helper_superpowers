"""CLI entry point: ``grep_helper.languages.c``。"""
from grep_helper.cli import run
from grep_helper.languages import c as _handler

if __name__ == "__main__":
    raise SystemExit(run(_handler, description="C grep結果 自動分類・使用箇所洗い出しツール"))
