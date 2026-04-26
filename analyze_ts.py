"""CLI entry point: ``grep_helper.languages.ts``。"""
from grep_helper.cli import run
from grep_helper.languages import ts as _handler

if __name__ == "__main__":
    raise SystemExit(run(_handler, description="TypeScript/JavaScript grep結果 自動分類・使用箇所洗い出しツール"))
