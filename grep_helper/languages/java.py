"""Java grep結果 自動分類・使用箇所洗い出しハンドラ。

公開 API:
- EXTENSIONS = (".java",)
- classify_usage(code, *, ctx=None)         — 新統一契約
- batch_track_indirect(direct_records, src_dir, encoding, *, workers=1)
- build_parser()                             — CLI パーサー構築
- print_report(stats, processed_files)      — 処理サマリ出力
- main()                                    — CLI エントリーポイント
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats
from grep_helper.source_files import grep_filter_files
from grep_helper.languages import java_ast
from grep_helper.languages import java_classify
from grep_helper.languages import java_track

EXTENSIONS: tuple[str, ...] = (".java",)


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:
    """Java コード行を分類する（AST 経路 + regex フォールバック）。

    ctx が None なら regex のみ。

    Args:
        code: 分類対象のコード行
        ctx:  分類コンテキスト（filepath, lineno, source_dir, stats, encoding_override）

    Returns:
        UsageType の value 文字列
    """
    if ctx is None:
        return java_classify.classify_usage_regex(code)
    tree = java_ast.get_ast(ctx.filepath, ctx.source_dir, encoding_override=ctx.encoding_override)
    if tree is None:
        if java_ast._JAVALANG_AVAILABLE:
            ctx.stats.fallback_files.add(ctx.filepath)
        return java_classify.classify_usage_regex(code)
    try:
        usage = java_classify._classify_by_ast(tree, ctx.lineno, ctx.filepath)
        if usage is not None:
            return usage
    except Exception:
        ctx.stats.fallback_files.add(ctx.filepath)
    return java_classify.classify_usage_regex(code)


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Java の間接参照（field/local/constant/getter/setter）をバッチ追跡する。

    analyze_all.py:316-351 (Java branch in _apply_indirect_tracking) と
    その後の _batch_track_combined 呼び出し (448-464) を統合する。

    Args:
        direct_records: 直接参照レコードのリスト（全言語混在可）
        src_dir:        ソースコードのルートディレクトリ
        encoding:       文字コード強制指定（省略時は自動検出）
        workers:        並列ワーカー数

    Returns:
        Java ファイル由来の間接参照 GrepRecord のリスト
    """
    import sys as _sys  # noqa: PLC0415
    from grep_helper.languages import detect_handler  # noqa: PLC0415
    self_module = _sys.modules[__name__]

    own_records = [r for r in direct_records if detect_handler(r.filepath, src_dir) is self_module]
    if not own_records:
        return []

    stats = ProcessStats()
    result: list[GrepRecord] = []

    project_tasks: dict[str, list[GrepRecord]] = {}
    getter_tasks:  dict[str, list[GrepRecord]] = {}
    setter_tasks:  dict[str, list[GrepRecord]] = {}

    for record in own_records:
        if record.usage_type not in (
            java_classify.UsageType.CONSTANT.value,
            java_classify.UsageType.VARIABLE.value,
        ):
            continue
        var_name = java_classify.extract_variable_name(record.code, record.usage_type)
        if not var_name:
            continue
        scope = java_classify.determine_scope(
            record.usage_type, record.code,
            record.filepath, src_dir, int(record.lineno),
            encoding_override=encoding,
        )
        if scope == "project":
            project_tasks.setdefault(var_name, []).append(record)
        elif scope == "class":
            class_file = java_track._resolve_java_file(record.filepath, src_dir)
            if class_file:
                result.extend(java_track.track_field(
                    var_name, class_file, record, src_dir, stats,
                    encoding_override=encoding,
                ))
                for g in java_track.find_getter_names(var_name, class_file, encoding_override=encoding):
                    getter_tasks.setdefault(g, []).append(record)
                for s in java_track.find_setter_names(var_name, class_file, encoding_override=encoding):
                    setter_tasks.setdefault(s, []).append(record)
        elif scope == "method":
            method_scope = java_track._get_method_scope(
                record.filepath, src_dir, int(record.lineno),
                encoding_override=encoding,
            )
            if method_scope:
                result.extend(java_track.track_local(
                    var_name, method_scope, record, src_dir, stats,
                    encoding_override=encoding,
                ))

    if project_tasks or getter_tasks or setter_tasks:
        all_names = list(dict.fromkeys(
            list(project_tasks.keys())
            + list(getter_tasks.keys())
            + list(setter_tasks.keys())
        ))
        java_candidates = grep_filter_files(
            all_names, src_dir, [".java"], label="Java追跡",
        )
        result.extend(java_track._batch_track_combined(
            const_tasks=project_tasks,
            getter_tasks=getter_tasks,
            setter_tasks=setter_tasks,
            source_dir=src_dir, stats=stats, file_list=java_candidates,
            encoding_override=encoding,
            workers=workers,
        ))

    return result


# ---------------------------------------------------------------------------
# CLI entry point helpers
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


def print_report(stats: ProcessStats, processed_files: list[str]) -> None:
    """処理サマリを標準出力に出力する。"""
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


def main() -> None:
    """エントリーポイント。argparse でオプションを解析し、全処理を統括する。"""
    from grep_helper.tsv_output import write_tsv  # noqa: PLC0415

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
                    f"警告: {grep_path.name} のサイズが {file_size_mb:.1f}MB を超えています。"
                    "処理に時間がかかる場合があります。",
                    file=sys.stderr,
                )
            from grep_helper.pipeline import process_grep_file as _pgf  # noqa: PLC0415
            import sys as _sys  # noqa: PLC0415
            _java_self = _sys.modules[__name__]
            direct_records = _pgf(
                grep_path, source_dir, _java_self,
                keyword=keyword, encoding=encoding_override, stats=stats,
            )
            all_records: list[GrepRecord] = list(direct_records)

            project_scope_tasks: dict[str, list[GrepRecord]] = {}
            getter_tasks: dict[str, list[GrepRecord]] = {}
            setter_tasks_map: dict[str, list[GrepRecord]] = {}

            for record in direct_records:
                if record.usage_type not in (
                    java_classify.UsageType.CONSTANT.value,
                    java_classify.UsageType.VARIABLE.value,
                ):
                    continue

                var_name = java_classify.extract_variable_name(record.code, record.usage_type)
                if not var_name:
                    continue

                scope = java_classify.determine_scope(
                    record.usage_type, record.code,
                    record.filepath, source_dir, int(record.lineno),
                    encoding_override=encoding_override,
                )

                if scope == "project":
                    project_scope_tasks.setdefault(var_name, []).append(record)

                elif scope == "class":
                    class_file = java_track._resolve_java_file(record.filepath, source_dir)
                    if class_file:
                        indirect = java_track.track_field(
                            var_name, class_file, record, source_dir, stats,
                            encoding_override=encoding_override,
                        )
                        all_records.extend(indirect)

                        for getter_name in java_track.find_getter_names(
                            var_name, class_file, encoding_override=encoding_override,
                        ):
                            getter_tasks.setdefault(getter_name, []).append(record)
                        for setter_name in java_track.find_setter_names(
                            var_name, class_file, encoding_override=encoding_override,
                        ):
                            setter_tasks_map.setdefault(setter_name, []).append(record)

                elif scope == "method":
                    method_scope = java_track._get_method_scope(
                        record.filepath, source_dir, int(record.lineno),
                        encoding_override=encoding_override,
                    )
                    if method_scope:
                        all_records.extend(
                            java_track.track_local(
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
                all_records.extend(java_track._batch_track_combined(
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
