"""共通 CLI 雛形。

各言語の analyze_<lang>.py shim から
``raise SystemExit(run(handler))`` の形で呼ばれる。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import ModuleType

from grep_helper.model import ProcessStats
from grep_helper.pipeline import process_grep_file
from grep_helper.tsv_output import write_tsv


def build_parser(description: str) -> argparse.ArgumentParser:
    """共通 argparse 雛形（--source-dir / --input-dir / --output-dir / --encoding / --workers）。"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source-dir", required=True, help="ソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None, help="文字コード強制指定（省略時は自動検出）")
    parser.add_argument(
        "--workers", type=int, default=1,
        help=f"並列ワーカー数（デフォルト: 1, 推奨: {os.cpu_count() or 4}）",
    )
    return parser


def run(handler: ModuleType, *, description: str | None = None) -> int:
    """ハンドラを使って input/*.grep を処理し、output/*.tsv を書き出す。

    終了コード: 0=成功, 1=引数エラー, 2=実行時エラー。
    """
    desc = description or f"{getattr(handler, '__name__', 'analyzer')} grep結果 自動分類ツール"
    parser = build_parser(desc)
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"エラー: --source-dir が存在しません: {source_dir}", file=sys.stderr)
        return 1
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"エラー: --input-dir が存在しません: {input_dir}", file=sys.stderr)
        return 1

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print("エラー: grep結果ファイルがありません", file=sys.stderr)
        return 1

    stats = ProcessStats()
    processed_files: list[str] = []
    try:
        for grep_path in grep_files:
            keyword = grep_path.stem
            direct_records = process_grep_file(
                grep_path, source_dir, handler,
                keyword=keyword, encoding=args.encoding, stats=stats,
            )
            indirect_fn = getattr(handler, "batch_track_indirect", None)
            indirect_records: list = []
            if indirect_fn is not None:
                indirect_records = indirect_fn(
                    direct_records, source_dir, args.encoding, workers=args.workers,
                )
            all_records = list(direct_records) + list(indirect_records)
            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            if indirect_records:
                print(
                    f"  {grep_path.name} → {output_path}"
                    f" (直接: {len(direct_records)} 件, 間接: {len(indirect_records)} 件)"
                )
            else:
                print(f"  {grep_path.name} → {output_path} (直接: {len(direct_records)} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        return 2

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")
    return 0
