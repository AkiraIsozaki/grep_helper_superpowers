"""Java grep結果 自動分類・使用箇所洗い出しハンドラ。

公開 API:
- EXTENSIONS = (".java",)
- classify_usage(code, *, ctx=None)         — 新統一契約
- batch_track_indirect(direct_records, src_dir, encoding, *, workers=1)
"""
from __future__ import annotations

from pathlib import Path

from analyze_common import GrepRecord
from grep_helper.model import ClassifyContext, ProcessStats
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
