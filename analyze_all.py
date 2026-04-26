# analyze_all.py
"""全言語対応ディスパッチャーアナライザー。"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from collections.abc import Iterable

from analyze_common import (
    GrepRecord, ProcessStats, RefType,
    build_batch_scanner,
    cached_file_lines, detect_encoding, parse_grep_line, write_tsv,
    grep_filter_files, iter_grep_lines, resolve_file_cached,
)

# ---------------------------------------------------------------------------
# 言語ルーティング
# ---------------------------------------------------------------------------

_EXT_TO_LANG: dict[str, str] = {
    ".java":  "java",
    ".kt":    "kotlin",  ".kts":  "kotlin",
    ".c":     "c",       ".h":    "c",
    ".pc":    "proc",    ".pcc":  "proc",
    ".sql":   "sql",
    ".sh":    "sh",      ".bash": "sh",
    ".ts":    "ts",      ".js":   "ts",   ".tsx": "ts",  ".jsx": "ts",
    ".py":    "python",
    ".pl":    "perl",    ".pm":   "perl",
    ".cs":    "dotnet",  ".vb":   "dotnet",
    ".groovy":"groovy",  ".gvy":  "groovy",
    ".pls":   "plsql",   ".pck":  "plsql", ".prc": "plsql",
    ".pkb":   "plsql",   ".pks":  "plsql", ".fnc": "plsql", ".trg": "plsql",
}

_SHEBANG_PAT = re.compile(r'^#!\s*(?:.*/)?(?:env\s+)?(\S+)')
_SHEBANG_TO_LANG: dict[str, str] = {
    "perl":   "perl",
    "sh":     "sh",  "bash":  "sh",
    "csh":    "sh",  "tcsh":  "sh",
    "ksh":    "sh",  "ksh93": "sh",
}


def detect_language(filepath: str, source_dir: Path) -> str:
    """ファイルパスから言語キーを返す。拡張子なしはシバン判定、不明は 'other'。"""
    ext = Path(filepath).suffix.lower()
    if ext:
        return _EXT_TO_LANG.get(ext, "other")

    # 拡張子なし: CWD相対 → source_dir相対の順でシバン判定
    p = Path(filepath)
    if p.is_absolute():
        candidate = p if p.exists() else None
    elif p.exists():
        candidate = p
    else:
        resolved = source_dir / filepath
        candidate = resolved if resolved.exists() else None
    if candidate is None:
        return "other"
    try:
        first_line = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        m = _SHEBANG_PAT.match(first_line)
        if m:
            return _SHEBANG_TO_LANG.get(m.group(1).lower(), "other")
    except Exception:
        pass
    return "other"


# ---------------------------------------------------------------------------
# 分類器インポート
# ---------------------------------------------------------------------------

from collections.abc import Callable

from grep_helper.languages import java as _java_mod
from analyze_kotlin  import classify_usage_kotlin
from analyze_c       import classify_usage_c
from analyze_proc    import classify_usage_proc
from analyze_sql     import classify_usage_sql
from analyze_sh      import classify_usage_sh
from analyze_ts      import classify_usage_ts
from analyze_python  import classify_usage_python
from analyze_perl    import classify_usage_perl
from analyze_dotnet  import classify_usage_dotnet
from analyze_groovy  import classify_usage_groovy
from analyze_plsql   import classify_usage_plsql

_SIMPLE_CLASSIFIERS: dict[str, Callable[[str], str]] = {
    "kotlin": classify_usage_kotlin,
    "c":      classify_usage_c,
    "proc":   classify_usage_proc,
    "sql":    classify_usage_sql,
    "sh":     classify_usage_sh,
    "ts":     classify_usage_ts,
    "python": classify_usage_python,
    "perl":   classify_usage_perl,
    "dotnet": classify_usage_dotnet,
    "groovy": classify_usage_groovy,
    "plsql":  classify_usage_plsql,
}


def _classify_for_lang(
    lang: str,
    code: str,
    filepath: str,
    lineno: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> str:
    """言語キーに対応する classify_usage 関数を呼び出す。"""
    if lang == "java":
        from grep_helper.model import ClassifyContext  # noqa: PLC0415
        ctx = ClassifyContext(
            filepath=filepath,
            lineno=int(lineno),
            source_dir=source_dir,
            stats=stats,
            encoding_override=encoding,
        )
        return _java_mod.classify_usage(code, ctx=ctx)
    if lang == "other":
        return "その他"
    classifier = _SIMPLE_CLASSIFIERS.get(lang)
    if classifier:
        return classifier(code)
    return "その他"


def process_grep_lines_all(
    lines: Iterable[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """grep行リストを全行パースして直接参照 GrepRecord を返す。"""
    records: list[GrepRecord] = []
    for line in lines:
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        lang = detect_language(parsed["filepath"], source_dir)
        usage_type = _classify_for_lang(
            lang, parsed["code"], parsed["filepath"],
            parsed["lineno"], source_dir, stats, encoding,
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


# ---------------------------------------------------------------------------
# 間接追跡用インポート
# ---------------------------------------------------------------------------

# Java
from grep_helper.languages.java_classify import (  # noqa: F401
    UsageType, extract_variable_name, determine_scope,
)
from grep_helper.languages.java_track import (  # noqa: F401
    track_field, track_local,
    find_getter_names, find_setter_names,
    _resolve_java_file, _get_method_scope,
    _batch_track_combined,
)

# Kotlin

# C
from grep_helper.languages.c import (
    extract_define_name as _extract_define_name_c,
    extract_variable_name_c,
    track_variable as _track_variable_c,
    _collect_define_aliases,
    _get_reverse_define_map as _get_reverse_define_map_c,
    _build_define_map as _build_define_map_c,
)

# Pro*C
from grep_helper.languages.proc_track import (
    extract_define_name as _extract_define_name_proc,
    extract_variable_name_proc,
    extract_host_var_name,
    track_variable as _track_variable_proc,
)
from grep_helper.languages.proc_define_map import (
    _build_define_map as _build_define_map_proc,
    _get_reverse_define_map as _get_reverse_define_map_proc,
)

# Shell
from analyze_sh import extract_sh_variable_name, track_sh_variable

# SQL
from analyze_sql import extract_sql_variable_name, track_sql_variable

# .NET
from analyze_dotnet import extract_const_name_dotnet

# Groovy
from grep_helper.languages.groovy import (
    extract_static_final_name, is_class_level_field,
    find_getter_names_groovy, find_setter_names_groovy,
    track_field_groovy,
    _batch_track_getter_setter_groovy,
)


# Phase 4: kotlin 移植により、ここはハンドラ呼び出しに委譲。
# Phase 7 のクリーンアップで dispatcher.apply_indirect_tracking に統合される。
from grep_helper.languages.kotlin import (  # noqa: F401,E402
    _batch_track_kotlin_const as _batch_track_kotlin_const_new,
    _scan_files_for_kotlin_const,
)


def _batch_track_kotlin_const(tasks, src_dir, stats, encoding, *, workers=1):
    """旧 API 互換ラッパ。Phase 7 で削除予定。"""
    return _batch_track_kotlin_const_new(tasks, src_dir, stats, encoding, workers=workers)


# Phase 4: dotnet 移植により、ここはハンドラ呼び出しに委譲。
# Phase 7 のクリーンアップで dispatcher.apply_indirect_tracking に統合される。
from grep_helper.languages.dotnet import (
    _batch_track_dotnet_const as _batch_track_dotnet_const_new,
    _scan_files_for_dotnet_const,  # noqa: F401
)


def _batch_track_dotnet_const(tasks, src_dir, stats, encoding, *, workers=1):
    """旧 API 互換ラッパ。Phase 7 で削除予定。"""
    return _batch_track_dotnet_const_new(tasks, src_dir, stats, encoding, workers=workers)


# Phase 4: groovy 移植により、ここはハンドラ呼び出しに委譲。
# Phase 7 のクリーンアップで dispatcher.apply_indirect_tracking に統合される。
from grep_helper.languages.groovy import (  # noqa: F401
    _batch_track_groovy_static_final as _batch_track_groovy_static_final_new,
    _scan_files_for_groovy_static_final,
)


def _batch_track_groovy_static_final(tasks, src_dir, stats, encoding, *, workers=1):
    """旧 API 互換ラッパ。Phase 7 で削除予定。"""
    return _batch_track_groovy_static_final_new(tasks, src_dir, stats, encoding, workers=workers)


# Phase 4: c 移植により、ここはハンドラ呼び出しに委譲。
# Phase 7 のクリーンアップで dispatcher.apply_indirect_tracking に統合される。
from grep_helper.languages.c import (  # noqa: F401
    _batch_track_define_c_all as _batch_track_define_c_all_new,
    _scan_files_for_define_c_all,
)


def _batch_track_define_c_all(tasks, src_dir, stats, encoding, *, workers=1):
    """旧 API 互換ラッパ。Phase 7 で削除予定。"""
    return _batch_track_define_c_all_new(tasks, src_dir, stats, encoding, workers=workers)


# Phase 5: proc 移植により、ここはハンドラ呼び出しに委譲。
# Phase 7 のクリーンアップで dispatcher.apply_indirect_tracking に統合される。
from grep_helper.languages.proc import (  # noqa: F401, E402
    _batch_track_define_proc_all as _batch_track_define_proc_all_new,
    _scan_files_for_define_proc_all,
)


def _batch_track_define_proc_all(tasks, src_dir, stats, encoding, *, workers=1):
    """旧 API 互換ラッパ。Phase 7 で削除予定。"""
    return _batch_track_define_proc_all_new(tasks, src_dir, stats, encoding, workers=workers)


def _apply_indirect_tracking(
    direct_records: list[GrepRecord],
    source_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    workers: int = 1,
) -> list[GrepRecord]:
    """直接参照レコードから言語別間接追跡を行い、追加レコードを返す。"""
    result: list[GrepRecord] = []

    # バッチ集積用（各言語・追跡種別）
    java_project_tasks: dict[str, list[GrepRecord]] = {}
    java_getter_tasks:  dict[str, list[GrepRecord]] = {}
    java_setter_tasks:  dict[str, list[GrepRecord]] = {}
    kotlin_const_tasks: dict[str, list[GrepRecord]] = {}
    c_define_tasks:     dict[str, list[GrepRecord]] = {}
    proc_define_tasks:  dict[str, list[GrepRecord]] = {}
    dotnet_const_tasks: dict[str, list[GrepRecord]] = {}
    groovy_sf_tasks:    dict[str, list[GrepRecord]] = {}
    groovy_getter_tasks: dict[str, list[GrepRecord]] = {}
    groovy_setter_tasks: dict[str, list[GrepRecord]] = {}

    for record in direct_records:
        lang = detect_language(record.filepath, source_dir)

        # ── Java ──────────────────────────────────────────────────────────
        if lang == "java":
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
                encoding_override=encoding,
            )
            if scope == "project":
                java_project_tasks.setdefault(var_name, []).append(record)
            elif scope == "class":
                class_file = _resolve_java_file(record.filepath, source_dir)
                if class_file:
                    result.extend(track_field(
                        var_name, class_file, record, source_dir, stats,
                        encoding_override=encoding,
                    ))
                    for g in find_getter_names(var_name, class_file, encoding_override=encoding):
                        java_getter_tasks.setdefault(g, []).append(record)
                    for s in find_setter_names(var_name, class_file, encoding_override=encoding):
                        java_setter_tasks.setdefault(s, []).append(record)
            elif scope == "method":
                method_scope = _get_method_scope(
                    record.filepath, source_dir, int(record.lineno),
                    encoding_override=encoding,
                )
                if method_scope:
                    result.extend(track_local(
                        var_name, method_scope, record, source_dir, stats,
                        encoding_override=encoding,
                    ))

        # ── Kotlin ────────────────────────────────────────────────────────
        elif lang == "kotlin":
            if record.usage_type == "const val定数定義":
                m = re.search(r'\bconst\s+val\s+(\w+)', record.code)
                if m:
                    kotlin_const_tasks.setdefault(m.group(1), []).append(record)

        # ── C ─────────────────────────────────────────────────────────────
        elif lang == "c":
            if record.usage_type == "#define定数定義":
                var_name = _extract_define_name_c(record.code)
                if var_name:
                    c_define_tasks.setdefault(var_name, []).append(record)
            elif record.usage_type == "変数代入":
                var_name = extract_variable_name_c(record.code)
                if var_name:
                    candidate = resolve_file_cached(record.filepath, source_dir)
                    if candidate:
                        result.extend(_track_variable_c(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── Pro*C ─────────────────────────────────────────────────────────
        elif lang == "proc":
            if record.usage_type == "#define定数定義":
                var_name = _extract_define_name_proc(record.code)
                if var_name:
                    proc_define_tasks.setdefault(var_name, []).append(record)
            elif record.usage_type == "変数代入":
                var_name = extract_variable_name_proc(record.code) or extract_host_var_name(record.code)
                if var_name:
                    candidate = resolve_file_cached(record.filepath, source_dir)
                    if candidate:
                        result.extend(_track_variable_proc(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── Shell ─────────────────────────────────────────────────────────
        elif lang == "sh":
            if record.usage_type in ("変数代入", "環境変数エクスポート"):
                var_name = extract_sh_variable_name(record.code)
                if var_name:
                    candidate = resolve_file_cached(record.filepath, source_dir)
                    if candidate:
                        result.extend(track_sh_variable(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── SQL ───────────────────────────────────────────────────────────
        elif lang == "sql":
            if record.usage_type == "定数・変数定義":
                var_name = extract_sql_variable_name(record.code)
                if var_name:
                    candidate = resolve_file_cached(record.filepath, source_dir)
                    if candidate:
                        result.extend(track_sql_variable(
                            var_name, candidate, int(record.lineno),
                            source_dir, record, stats, encoding,
                        ))

        # ── .NET ──────────────────────────────────────────────────────────
        elif lang == "dotnet":
            if record.usage_type == "定数定義(Const/readonly)":
                const_name = extract_const_name_dotnet(record.code)
                if const_name:
                    dotnet_const_tasks.setdefault(const_name, []).append(record)

        # ── Groovy ────────────────────────────────────────────────────────
        elif lang == "groovy":
            if record.usage_type == "static final定数定義":
                const_name = extract_static_final_name(record.code)
                if const_name:
                    groovy_sf_tasks.setdefault(const_name, []).append(record)
            elif record.usage_type == "変数代入" and is_class_level_field(record.code):
                m = re.search(r'(\w+)\s*[=;]', record.code.strip())
                if m:
                    fname = m.group(1)
                    src_file = resolve_file_cached(record.filepath, source_dir)
                    if src_file:
                        result.extend(track_field_groovy(
                            fname, src_file, record, source_dir, stats, encoding,
                        ))
                        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
                        for g in find_getter_names_groovy(fname, lines):
                            groovy_getter_tasks.setdefault(g, []).append(record)
                        for s in find_setter_names_groovy(fname, lines):
                            groovy_setter_tasks.setdefault(s, []).append(record)

        # ts / python / perl / plsql / other: 間接追跡なし

    # Java バッチ処理: 定数・getter・setter の事前フィルタを1回の rglob で共有し、
    # 1 パスで定数/getter/setter を統合追跡する。
    if java_project_tasks or java_getter_tasks or java_setter_tasks:
        all_java_names = list(dict.fromkeys(
            list(java_project_tasks.keys())
            + list(java_getter_tasks.keys())
            + list(java_setter_tasks.keys())
        ))
        java_candidates = grep_filter_files(
            all_java_names, source_dir, [".java"], label="Java追跡",
        )
        result.extend(_batch_track_combined(
            const_tasks=java_project_tasks,
            getter_tasks=java_getter_tasks,
            setter_tasks=java_setter_tasks,
            source_dir=source_dir, stats=stats, file_list=java_candidates,
            encoding_override=encoding,
            workers=workers,
        ))

    # Kotlin / .NET / Groovy static final / C #define / Pro*C #define バッチ処理
    result.extend(_batch_track_kotlin_const(kotlin_const_tasks, source_dir, stats, encoding, workers=workers))
    result.extend(_batch_track_dotnet_const(dotnet_const_tasks, source_dir, stats, encoding, workers=workers))
    result.extend(_batch_track_groovy_static_final(groovy_sf_tasks, source_dir, stats, encoding, workers=workers))
    result.extend(_batch_track_define_c_all(c_define_tasks, source_dir, stats, encoding, workers=workers))
    result.extend(_batch_track_define_proc_all(proc_define_tasks, source_dir, stats, encoding, workers=workers))

    # Groovy getter/setter バッチ処理
    result.extend(_batch_track_getter_setter_groovy(
        groovy_getter_tasks, groovy_setter_tasks, source_dir, stats, encoding,
    ))

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="全言語対応ディスパッチャー grep結果 自動分類・使用箇所洗い出しツール"
    )
    parser.add_argument("--source-dir", required=True, help="ソースコードのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input",  help="grep結果ファイルのディレクトリ")
    parser.add_argument("--output-dir", default="output", help="TSV出力先ディレクトリ")
    parser.add_argument("--encoding",   default=None,     help="文字コード強制指定（例: utf-8, cp932）")
    parser.add_argument(
        "--workers", type=int, default=1,
        help=f"並列ワーカー数（デフォルト: 1, 推奨: {os.cpu_count() or 4}）",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"エラー: --source-dir が存在しません: {source_dir}", file=sys.stderr)
        sys.exit(1)
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"エラー: --input-dir が存在しません: {input_dir}", file=sys.stderr)
        sys.exit(1)

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print("エラー: grep結果ファイルがありません", file=sys.stderr)
        sys.exit(1)

    stats = ProcessStats()
    processed_files: list[str] = []

    try:
        for grep_path in grep_files:
            print(f"  処理中: {grep_path.name} ...", file=sys.stderr, flush=True)
            keyword = grep_path.stem
            enc = detect_encoding(grep_path, args.encoding)

            direct_records = process_grep_lines_all(
                iter_grep_lines(grep_path, enc),
                keyword, source_dir, stats, args.encoding,
            )
            all_records = list(direct_records)
            all_records.extend(
                _apply_indirect_tracking(direct_records, source_dir, stats, args.encoding, workers=args.workers)
            )

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} "
                  f"(直接: {direct_count} 件, 間接: {indirect_count} 件)")

    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}"
          f"  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
