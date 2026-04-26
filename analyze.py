"""DEPRECATED shim: ``grep_helper.languages.java``。Phase 7 で削除。

全シンボルを後方互換のために再エクスポートする。
テストは `import analyze` および `from analyze import ...` でこれらのシンボルを使用する。
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable as _Iterable
from pathlib import Path

# ---------------------------------------------------------------------------
# AST キャッシュ（dict identity を保持する as-form インポート）
# ---------------------------------------------------------------------------
from grep_helper.languages.java_ast import (  # noqa: F401
    _JAVALANG_AVAILABLE,
    _ast_cache as _ast_cache,
    _ast_line_index as _ast_line_index,
    _method_starts_cache as _method_starts_cache,
    get_ast,
    _get_or_build_ast_index,
    _get_method_starts,
    USAGE_PATTERNS,
)

# ---------------------------------------------------------------------------
# 分類（java_classify → java_ast.classify_usage_regex を含む）
# ---------------------------------------------------------------------------
from grep_helper.languages.java_classify import (  # noqa: F401
    UsageType,
    classify_usage_regex,
    _classify_by_ast,
    determine_scope,
    extract_variable_name,
    _FIELD_DECL_PATTERN,
)

# ---------------------------------------------------------------------------
# 追跡
# ---------------------------------------------------------------------------
from grep_helper.languages.java_track import (  # noqa: F401
    _resolve_java_file,
    _get_method_scope,
    _search_in_lines,
    _get_java_files,
    track_constant,
    track_field,
    track_local,
    find_getter_names,
    find_setter_names,
    track_setter_calls,
    track_getter_calls,
    _scan_files_for_combined,
    _batch_track_combined,
    _batch_track_constants,
    _batch_track_getters,
    _batch_track_setters,
)

# ---------------------------------------------------------------------------
# 共通（analyze_common 経由）
# ---------------------------------------------------------------------------
from analyze_common import (  # noqa: F401
    GrepRecord,
    ProcessStats,
    RefType,
    parse_grep_line,
    write_tsv,
    cached_file_lines,
    detect_encoding,
    iter_grep_lines,
    iter_source_files,
    grep_filter_files,
    build_batch_scanner,
)

# ---------------------------------------------------------------------------
# classify_usage: 旧シグネチャ互換ラッパー（テストが positional 引数で呼び出す）
# ---------------------------------------------------------------------------


def classify_usage(
    code: str,
    filepath: str,
    lineno: int,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> str:
    """旧シグネチャ互換ラッパ。Phase 7 で削除予定。

    新しい classify_usage は grep_helper.languages.java.classify_usage(code, *, ctx=None)。
    """
    from grep_helper.model import ClassifyContext  # noqa: PLC0415
    from grep_helper.languages import java as _java_handler  # noqa: PLC0415
    ctx = ClassifyContext(
        filepath=filepath,
        lineno=lineno,
        source_dir=source_dir,
        stats=stats,
        encoding_override=encoding_override,
    )
    return _java_handler.classify_usage(code, ctx=ctx)


# ---------------------------------------------------------------------------
# process_grep_lines / process_grep_file
# ---------------------------------------------------------------------------


def process_grep_lines(
    lines: _Iterable[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    *,
    report_progress: bool = False,
    path_name: str = "",
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """grep行イテラブルを処理し、第1段階（直接参照）レコードのリストを返す。"""
    records: list[GrepRecord] = []
    _PROGRESS_INTERVAL = 100_000

    for line in lines:
        stats.total_lines += 1

        if report_progress and stats.total_lines % _PROGRESS_INTERVAL == 0:
            print(
                f"  進捗: {path_name} {stats.total_lines:,} 行処理済み"
                f" (有効: {stats.valid_lines:,})",
                file=sys.stderr,
                flush=True,
            )

        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue

        usage_type = classify_usage(
            code=parsed["code"],
            filepath=parsed["filepath"],
            lineno=int(parsed["lineno"]),
            source_dir=source_dir,
            stats=stats,
            encoding_override=encoding_override,
        )

        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=usage_type,
            filepath=parsed["filepath"],
            lineno=parsed["lineno"],
            code=parsed["code"],
        ))
        stats.valid_lines += 1

    return records


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """grepファイル全行を処理し、第1段階（直接参照）レコードのリストを返す。後方互換ラッパー。"""
    file_size_mb = path.stat().st_size / (1024 * 1024)
    report_progress = file_size_mb > 50
    if file_size_mb > 500:
        print(
            f"警告: {path.name} のサイズが {file_size_mb:.1f}MB を超えています。処理に時間がかかる場合があります。",
            file=sys.stderr,
        )
    enc = detect_encoding(path, encoding_override)
    return process_grep_lines(
        iter_grep_lines(path, enc),
        keyword,
        source_dir,
        stats,
        report_progress=report_progress,
        path_name=path.name,
        encoding_override=encoding_override,
    )


# ---------------------------------------------------------------------------
# print_report
# ---------------------------------------------------------------------------

def print_report(stats: ProcessStats, processed_files: list[str]) -> None:
    """処理サマリを標準出力に出力する。全ファイル処理完了後に1回呼び出す。

    Args:
        stats:           処理統計
        processed_files: 処理した .grep ファイル名のリスト
    """
    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(
        f"総行数: {stats.total_lines}  "
        f"有効: {stats.valid_lines}  "
        f"スキップ: {stats.skipped_lines}"
    )
    if stats.fallback_files:
        print(f"ASTフォールバック ({len(stats.fallback_files)} 件):")
        for f in sorted(stats.fallback_files):
            print(f"  {f}")
    if stats.encoding_errors:
        print(f"エンコーディングエラー ({len(stats.encoding_errors)} 件):")
        for f in sorted(stats.encoding_errors):
            print(f"  {f}")


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """CLIオプションのパーサーを構築して返す。"""
    parser = argparse.ArgumentParser(
        description="Java grep結果 自動分類・使用箇所洗い出しツール"
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Javaソースコードのルートディレクトリ",
    )
    parser.add_argument(
        "--input-dir",
        default="input",
        help="grep結果ファイルの配置ディレクトリ（デフォルト: input/）",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="TSV出力先ディレクトリ（デフォルト: output/）",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="文字コード強制指定（省略時は自動検出）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=f"並列ワーカー数（デフォルト: 1, 推奨: {os.cpu_count() or 4}）",
    )
    return parser


# ---------------------------------------------------------------------------
# main（CLI エントリーポイント）
# ---------------------------------------------------------------------------

def main() -> None:
    """エントリーポイント。argparse でオプションを解析し、全処理を統括する。"""
    parser = build_parser()
    args = parser.parse_args()

    encoding_override: str | None = args.encoding

    source_dir = Path(args.source_dir)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(
            f"エラー: --source-dir で指定したディレクトリが存在しません: {source_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not input_dir.exists() or not input_dir.is_dir():
        print(
            f"エラー: --input-dir で指定したディレクトリが存在しません: {input_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print(
            "エラー: input/ディレクトリにgrep結果ファイルがありません",
            file=sys.stderr,
        )
        sys.exit(1)

    stats = ProcessStats()
    processed_files: list[str] = []

    try:
        for grep_path in grep_files:
            print(f"  処理中: {grep_path.name} ...", file=sys.stderr, flush=True)
            keyword = grep_path.stem

            file_size_mb = grep_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 500:
                print(
                    f"警告: {grep_path.name} のサイズが {file_size_mb:.1f}MB を超えています。処理に時間がかかる場合があります。",
                    file=sys.stderr,
                )
            enc = detect_encoding(grep_path, encoding_override)
            direct_records = process_grep_lines(
                iter_grep_lines(grep_path, enc),
                keyword,
                source_dir,
                stats,
                report_progress=file_size_mb > 50,
                path_name=grep_path.name,
                encoding_override=encoding_override,
            )
            all_records: list[GrepRecord] = list(direct_records)

            project_scope_tasks: dict[str, list[GrepRecord]] = {}
            getter_tasks: dict[str, list[GrepRecord]] = {}
            setter_tasks_map: dict[str, list[GrepRecord]] = {}

            for record in direct_records:
                if record.usage_type not in (
                    UsageType.CONSTANT.value, UsageType.VARIABLE.value
                ):
                    continue

                var_name = extract_variable_name(record.code, record.usage_type)
                if not var_name:
                    continue

                scope = determine_scope(
                    record.usage_type, record.code,
                    record.filepath, source_dir, int(record.lineno),
                    encoding_override=encoding_override,
                )

                if scope == "project":
                    project_scope_tasks.setdefault(var_name, []).append(record)

                elif scope == "class":
                    class_file = _resolve_java_file(record.filepath, source_dir)
                    if class_file:
                        indirect = track_field(
                            var_name, class_file, record, source_dir, stats,
                            encoding_override=encoding_override,
                        )
                        all_records.extend(indirect)

                        for getter_name in find_getter_names(
                            var_name, class_file, encoding_override=encoding_override,
                        ):
                            getter_tasks.setdefault(getter_name, []).append(record)
                        for setter_name in find_setter_names(
                            var_name, class_file, encoding_override=encoding_override,
                        ):
                            setter_tasks_map.setdefault(setter_name, []).append(record)

                elif scope == "method":
                    method_scope = _get_method_scope(
                        record.filepath, source_dir, int(record.lineno),
                        encoding_override=encoding_override,
                    )
                    if method_scope:
                        all_records.extend(
                            track_local(
                                var_name, method_scope, record, source_dir, stats,
                                encoding_override=encoding_override,
                            )
                        )

            if project_scope_tasks or getter_tasks or setter_tasks_map:
                all_java_names = list(dict.fromkeys(
                    list(project_scope_tasks.keys())
                    + list(getter_tasks.keys())
                    + list(setter_tasks_map.keys())
                ))
                java_candidates = grep_filter_files(
                    all_java_names, source_dir, [".java"], label="Java追跡",
                )
                all_records.extend(_batch_track_combined(
                    const_tasks=project_scope_tasks,
                    getter_tasks=getter_tasks,
                    setter_tasks=setter_tasks_map,
                    source_dir=source_dir, stats=stats, file_list=java_candidates,
                    encoding_override=encoding_override,
                    workers=args.workers,
                ))

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)

            processed_files.append(grep_path.name)
            direct_count = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} (直接: {direct_count} 件, 間接: {indirect_count} 件)")

    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print_report(stats, processed_files)


if __name__ == "__main__":
    main()
