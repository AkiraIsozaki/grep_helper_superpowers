"""全言語ディスパッチャー。analyze_all.py の本体実装。"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from grep_helper.encoding import detect_encoding
from grep_helper.grep_input import iter_grep_lines, parse_grep_line
from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.tsv_output import write_tsv
from grep_helper.languages import EXT_TO_HANDLER, detect_handler


def _all_handlers():
    """登録済みのユニークなハンドラ集合を返す。"""
    seen: set[str] = set()
    for h in EXT_TO_HANDLER.values():
        if h.__name__ not in seen:
            seen.add(h.__name__)
            yield h


def process_grep_lines_all(
    lines: Iterable[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding: str | None = None,
) -> list[GrepRecord]:
    """grep 行を読んで、ファイル拡張子から handler を引いて分類する。"""
    records: list[GrepRecord] = []
    for line in lines:
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        try:
            lineno_int = int(parsed["lineno"])
        except ValueError:
            lineno_int = 0
        handler = detect_handler(parsed["filepath"], source_dir)
        ctx = ClassifyContext(
            filepath=parsed["filepath"], lineno=lineno_int,
            source_dir=source_dir, stats=stats, encoding_override=encoding,
        )
        usage = handler.classify_usage(parsed["code"], ctx=ctx)
        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=usage,
            filepath=parsed["filepath"],
            lineno=parsed["lineno"],
            code=parsed["code"],
        ))
        stats.valid_lines += 1
    return records


def apply_indirect_tracking(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """登録済み全ハンドラの batch_track_indirect を順次呼び出し、結果を結合する。"""
    results: list[GrepRecord] = []
    for handler in _all_handlers():
        fn = getattr(handler, "batch_track_indirect", None)
        if fn is None:
            continue
        results.extend(fn(direct_records, src_dir, encoding, workers=workers))
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="全言語対応ディスパッチャー grep結果 自動分類・使用箇所洗い出しツール"
    )
    parser.add_argument("--source-dir", required=True, help="ソースコードのルートディレクトリ")
    parser.add_argument("--input-dir", default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding", default=None, help="文字コード強制指定（省略時は自動検出）")
    parser.add_argument(
        "--workers", type=int, default=1,
        help=f"並列ワーカー数（デフォルト: 1, 推奨: {os.cpu_count() or 4}）",
    )
    return parser


def main() -> int:
    parser = build_parser()
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
            enc = detect_encoding(grep_path, args.encoding)
            direct_records = process_grep_lines_all(
                iter_grep_lines(grep_path, enc), keyword, source_dir, stats,
                encoding=args.encoding,
            )
            indirect_records = apply_indirect_tracking(
                direct_records, source_dir, args.encoding, workers=args.workers,
            )
            all_records = list(direct_records) + list(indirect_records)
            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            print(f"  {grep_path.name} → {output_path} "
                  f"(直接: {len(direct_records)} 件, 間接: {len(indirect_records)} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        return 2

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
