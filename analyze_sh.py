"""CLI entry point: ``grep_helper.languages.sh``。"""
from grep_helper.cli import run
from grep_helper.languages import sh as _handler

if __name__ == "__main__":
    raise SystemExit(run(_handler, description="シェルスクリプト grep結果 自動分類・使用箇所洗い出しツール"))
