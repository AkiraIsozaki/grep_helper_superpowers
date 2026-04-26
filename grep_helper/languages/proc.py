"""Pro*C grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.source_files import grep_filter_files, resolve_file_cached
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding

EXTENSIONS: tuple[str, ...] = (".pc", ".pcc")

# ---------------------------------------------------------------------------
# 使用タイプ分類パターン（優先度順）
# ---------------------------------------------------------------------------

_PROC_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bEXEC\s+SQL\b', re.IGNORECASE), "EXEC SQL文"),
    (re.compile(r'#\s*define\b'),                  "#define定数定義"),
    (re.compile(r'\bif\s*\(|strcmp\s*\(|strncmp\s*\('), "条件判定"),
    (re.compile(r'\breturn\b'),                    "return文"),
    (re.compile(r'\b\w+\s*(?:\[[^\]]*\])?\s*=(?!=)'), "変数代入"),
    (re.compile(r'\w+\s*\('),                      "関数引数"),
]

# ---------------------------------------------------------------------------
# 使用タイプ分類
# ---------------------------------------------------------------------------


def classify_usage_proc(code: str) -> str:
    """Pro*Cコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PROC_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def _classify_for_filepath(code: str, filepath: str) -> str:
    """ファイルパスの拡張子に基づいて適切な分類関数を呼び出す。"""
    ext = Path(filepath).suffix.lower()
    if ext in ('.c', '.h'):
        from grep_helper.languages.c import classify_usage as c_classify
        return c_classify(code)
    return classify_usage_proc(code)


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:
    """Pro*C コード行を分類する。ctx.filepath が .c/.h の場合は C の分類器を使う。"""
    if ctx is not None:
        from grep_helper.languages.c import classify_usage as c_classify
        ext = Path(ctx.filepath).suffix.lower()
        if ext in ('.c', '.h'):
            return c_classify(code)
    return classify_usage_proc(code)


# ---------------------------------------------------------------------------
# Re-exports from sub-modules (for tests and shim)
# ---------------------------------------------------------------------------

from grep_helper.languages.proc_define_map import (  # noqa: E402, F401
    _define_map_cache,
    _build_define_map,
    _get_reverse_define_map,
)
from grep_helper.languages.proc_track import (  # noqa: E402, F401
    extract_variable_name_proc,
    extract_define_name,
    extract_host_var_name,
    track_define,
    track_variable,
)

# ---------------------------------------------------------------------------
# Batch scanning (picklable module-level functions)
# ---------------------------------------------------------------------------


def _scan_files_for_define_proc_all(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    scan_tasks: dict[str, list[tuple[bool, str, GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: Pro*C #define エイリアス込みで一括スキャン。"""
    from grep_helper.languages.c import classify_usage as classify_usage_c  # noqa: PLC0415
    scanner = build_batch_scanner(names)
    results: list[GrepRecord] = []
    for src_file in files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        ext = src_file.suffix.lower()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            usage_fn = classify_usage_c if ext in (".c", ".h") else classify_usage_proc
            for _pos, scan_name in scanner.findall(line):
                for is_primary, _, origin, def_resolved, def_lineno in scan_tasks[scan_name]:
                    if is_primary and def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=usage_fn(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=scan_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))
    return results


def _batch_track_define_proc_all(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Pro*C #define をエイリアス解決込みで1パスでバッチスキャンする。

    workers >= 2 のとき ProcessPoolExecutor で並列化する。
    """
    from grep_helper.languages.c import _collect_define_aliases  # noqa: PLC0415

    if not tasks:
        return []
    define_map = _build_define_map(src_dir, stats, encoding)
    reverse_map = _get_reverse_define_map(src_dir, encoding)

    scan_tasks: dict[str, list[tuple[bool, str, GrepRecord, Path | None, int]]] = {}
    for var_name, records in tasks.items():
        aliases = _collect_define_aliases(var_name, define_map, reverse=reverse_map)
        for scan_name in [var_name] + aliases:
            is_primary = (scan_name == var_name)
            for record in records:
                if is_primary:
                    def_path = resolve_file_cached(record.filepath, src_dir)
                    def_resolved = def_path.resolve() if def_path else None
                    def_lineno = int(record.lineno)
                else:
                    def_resolved = None
                    def_lineno = 0
                scan_tasks.setdefault(scan_name, []).append(
                    (is_primary, var_name, record, def_resolved, def_lineno)
                )

    if not scan_tasks:
        return []

    names = list(scan_tasks.keys())
    src_files = grep_filter_files(names, src_dir, [".pc", ".c", ".h"], label="Pro*C #define追跡")
    if not src_files:
        return []
    total = len(src_files)

    # 並列実行
    if workers >= 2 and total >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [src_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(_scan_files_for_define_proc_all, chunk, src_dir, encoding, names, scan_tasks)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [Pro*C #define追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    # 直列実行
    from grep_helper.languages.c import classify_usage as classify_usage_c  # noqa: PLC0415
    scanner = build_batch_scanner(names)
    results = []
    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Pro*C #define追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        ext = src_file.suffix.lower()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            usage_fn = classify_usage_c if ext in (".c", ".h") else classify_usage_proc
            for _pos, scan_name in scanner.findall(line):
                for is_primary, _, origin, def_resolved, def_lineno in scan_tasks[scan_name]:
                    if is_primary and def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=usage_fn(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=scan_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Pro*C #define追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Pro*C の間接参照（#define + 変数代入）をバッチ追跡する。"""
    import sys as _sys  # noqa: PLC0415
    from grep_helper.languages import detect_handler  # noqa: PLC0415
    self_module = _sys.modules[__name__]

    own_records = [r for r in direct_records if detect_handler(r.filepath, src_dir) is self_module]
    if not own_records:
        return []

    stats = ProcessStats()
    result: list[GrepRecord] = []
    define_tasks: dict[str, list[GrepRecord]] = {}

    for record in own_records:
        if record.usage_type == "#define定数定義":
            var_name = extract_define_name(record.code)
            if var_name:
                define_tasks.setdefault(var_name, []).append(record)
        elif record.usage_type == "変数代入":
            var_name = extract_variable_name_proc(record.code) or extract_host_var_name(record.code)
            if var_name:
                candidate = resolve_file_cached(record.filepath, src_dir)
                if candidate:
                    result.extend(track_variable(
                        var_name, candidate, int(record.lineno),
                        src_dir, record, stats, encoding,
                    ))

    result.extend(_batch_track_define_proc_all(define_tasks, src_dir, stats, encoding, workers=workers))
    return result
