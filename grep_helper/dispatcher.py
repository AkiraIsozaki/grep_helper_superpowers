"""全言語ディスパッチャー。analyze_all.py の本体実装。"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

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


def _run_one_handler(
    handler_module_name: str,
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    workers: int,
    use_mmap: bool,
) -> list[GrepRecord]:
    """子プロセスで動的 import → batch_track_indirect 呼び出し。

    handler_module_name はトップレベル import 可能な完全修飾名（例:
    "grep_helper.languages.java"）。pickle 安全のためモジュールオブジェクト
    そのものは渡さない。handler 識別は呼び出し側の future_to_name で行うため、
    戻り値は records のみ。

    子プロセス内の例外（ImportError, AttributeError, batch_track_indirect 内の
    例外など）はそのまま親プロセスへ propagate する。親側の apply_indirect_tracking
    が fut.result() を try/except で囲んで 1 handler スキップを実現する。
    """
    import importlib
    mod = importlib.import_module(handler_module_name)
    fn = getattr(mod, "batch_track_indirect", None)
    if fn is None:
        return []
    return fn(direct_records, src_dir, encoding, workers=workers, use_mmap=use_mmap)


def apply_indirect_tracking(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
    use_mmap: bool = True,
    handler_workers: int = 1,
    on_handler_complete: "Callable[[str, list[GrepRecord]], None] | None" = None,
) -> list[GrepRecord]:
    """登録済み全ハンドラの batch_track_indirect を呼び出し、結果を結合する。

    handler_workers > 1 のとき ProcessPoolExecutor で handler 単位の並列実行。
    1 handler の例外（子プロセス内 ImportError 等を含む）は stderr 警告のみで
    他 handler に伝播しない。on_handler_complete は親プロセスのメインスレッドから
    as_completed の同期ループ内で呼ばれる（thread-safe 前提）。
    """
    handler_modules = [
        h.__name__ for h in _all_handlers()
        if getattr(h, "batch_track_indirect", None) is not None
    ]
    results: list[GrepRecord] = []

    def _safe_complete(hname: str, partial: list[GrepRecord]) -> None:
        results.extend(partial)
        if on_handler_complete is not None:
            on_handler_complete(hname, partial)

    def _run_serial() -> list[GrepRecord]:
        for hname in handler_modules:
            try:
                partial = _run_one_handler(
                    hname, direct_records, src_dir, encoding, workers, use_mmap,
                )
            except Exception as exc:
                print(
                    f"  警告: handler {hname} の間接追跡で例外 ({exc!r}) - "
                    f"この handler の indirect は欠落、他 handler は継続",
                    file=sys.stderr, flush=True,
                )
                continue
            _safe_complete(hname, partial)
        return results

    if handler_workers <= 1:
        return _run_serial()

    try:
        with ProcessPoolExecutor(max_workers=handler_workers) as ex:
            future_to_name = {
                ex.submit(_run_one_handler, hname, direct_records, src_dir,
                          encoding, workers, use_mmap): hname
                for hname in handler_modules
            }
            for fut in as_completed(future_to_name):
                hname = future_to_name[fut]
                try:
                    partial = fut.result()
                except Exception as exc:
                    print(
                        f"  警告: handler {hname} の間接追跡で例外 ({exc!r}) - "
                        f"この handler の indirect は欠落、他 handler は継続",
                        file=sys.stderr, flush=True,
                    )
                    continue
                _safe_complete(hname, partial)
        return results
    except OSError as exc:
        print(
            f"  警告: ProcessPool 起動に失敗 ({exc!r}) - handler_workers=1 で直列実行に切替",
            file=sys.stderr, flush=True,
        )
        return _run_serial()


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
    parser.add_argument(
        "--no-mmap", action="store_true",
        help="mmap 経由のファイル絞り込みを使わず read 経由にする（Solaris+NFS で推奨）",
    )
    return parser


def _resolve_use_mmap(no_mmap_arg: bool, env: dict | None = None) -> bool:
    """CLI フラグと環境変数から use_mmap の値を決定する。

    優先順:
      - CLI で --no-mmap 明示 (no_mmap_arg=True) なら use_mmap=False
      - 未指定なら GREP_HELPER_NO_MMAP=1 のとき use_mmap=False
      - それ以外は use_mmap=True
    """
    if no_mmap_arg:
        return False
    if env is None:
        env = os.environ
    if env.get("GREP_HELPER_NO_MMAP") == "1":
        return False
    return True


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

    output_dir.mkdir(parents=True, exist_ok=True)

    stats = ProcessStats()
    direct_by_keyword: dict[str, list[GrepRecord]] = {}
    processed_files: list[str] = []

    # フェーズ 1: 直接分類（個別 grep 失敗は他に巻き込まない）
    for grep_path in grep_files:
        keyword = grep_path.stem
        try:
            enc = detect_encoding(grep_path, args.encoding)
            direct = process_grep_lines_all(
                iter_grep_lines(grep_path, enc), keyword, source_dir, stats,
                encoding=args.encoding,
            )
        except Exception as exc:
            print(
                f"  警告: {grep_path.name} の直接分類で例外 ({exc!r}) - スキップして継続",
                file=sys.stderr, flush=True,
            )
            continue
        direct_by_keyword[keyword] = direct
        processed_files.append(grep_path.name)

    # フェーズ 2: 間接追跡を 1 回だけ
    indirect_by_keyword: dict[str, list[GrepRecord]] = {}
    if direct_by_keyword:
        all_direct: list[GrepRecord] = []
        for records in direct_by_keyword.values():
            all_direct.extend(records)
        try:
            indirect_all = apply_indirect_tracking(
                all_direct, source_dir, args.encoding,
                workers=args.workers,
                use_mmap=_resolve_use_mmap(args.no_mmap),
            )
        except Exception as exc:
            print(f"予期しないエラー（間接追跡フェーズ）: {exc}", file=sys.stderr)
            return 2
        for rec in indirect_all:
            indirect_by_keyword.setdefault(rec.keyword, []).append(rec)

    # フェーズ 3: keyword で振り分けて TSV 出力
    for keyword, direct_records in direct_by_keyword.items():
        indirect_records = indirect_by_keyword.get(keyword, [])
        all_records = list(direct_records) + list(indirect_records)
        output_path = output_dir / f"{keyword}.tsv"
        write_tsv(all_records, output_path)
        print(f"  {keyword}.grep → {output_path} "
              f"(直接: {len(direct_records)} 件, 間接: {len(indirect_records)} 件)")

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
