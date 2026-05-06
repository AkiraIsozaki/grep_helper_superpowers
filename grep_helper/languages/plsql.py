"""PL/SQL grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding
from grep_helper.source_files import grep_filter_files, iter_source_files, resolve_file_cached

EXTENSIONS: tuple[str, ...] = (".pls", ".pck", ".prc", ".pkb", ".pks", ".fnc", ".trg")

_PLSQL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bCONSTANT\b|:=', re.IGNORECASE),                    "定数/変数宣言"),
    (re.compile(r'\bWHEN\b.*\bTHEN\b|\bRAISE\b', re.IGNORECASE),       "EXCEPTION処理"),
    (re.compile(r'\bIF\b.*\bTHEN\b|\bCASE\s+WHEN\b', re.IGNORECASE),   "条件判定"),
    (re.compile(r'\bCURSOR\b.*\bIS\b', re.IGNORECASE),                  "カーソル定義"),
    (re.compile(r'\bINSERT\b|\bUPDATE\b.*\bSET\b', re.IGNORECASE),     "INSERT/UPDATE値"),
    (re.compile(r'\bWHERE\b', re.IGNORECASE),                           "WHERE条件"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """PL/SQLコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PLSQL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_PLSQL_CONSTANT_PAT = re.compile(r'^\s*(\w+)\s+CONSTANT\b', re.IGNORECASE)


def extract_plsql_constant_name(code: str) -> str | None:
    """PL/SQL CONSTANT 宣言から定数名を抽出する。同一行マルチステートメントは取りこぼし許容。"""
    m = _PLSQL_CONSTANT_PAT.match(code)
    return m.group(1) if m else None


def track_plsql_constant(
    name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """PL/SQL 定数の使用箇所を src_dir 配下の .pls/.pkb/.pks/etc ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = iter_source_files(src_dir, list(EXTENSIONS))
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def _scan_files_for_plsql_constant(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: PL/SQL 定数を一括スキャン。

    case-insensitive 検索のため、build_batch_scanner ではなく re で個別に検索する。
    （build_batch_scanner は文字列リテラル一致前提で、case-insensitive 非対応のため）
    finditer を使い、1行に同名定数が複数出現する場合は出現回数分のレコードを返す
    （python/ts/perl/kotlin の scanner.findall と同じ multi-emit 挙動）。
    """
    name_patterns = [(n, re.compile(r'\b' + re.escape(n) + r'\b', re.IGNORECASE)) for n in names]
    results: list[GrepRecord] = []
    for src_file in files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for name, pattern in name_patterns:
                for _ in pattern.finditer(line):
                    for origin, def_resolved, def_lineno in tasks_ext[name]:
                        if def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                            continue
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.INDIRECT.value,
                            usage_type=classify_usage(code),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=code,
                            src_var=name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
    return results


def _batch_track_plsql_constant(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """PL/SQL CONSTANT 名をプロジェクト全体に対して 1 パスでバッチスキャンする。"""
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, list(EXTENSIONS), label="PL/SQL定数追跡")
    if not src_files:
        return []
    total = len(src_files)

    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]] = {}
    for name, origins in tasks.items():
        ext_list = []
        for origin in origins:
            def_path = resolve_file_cached(origin.filepath, src_dir)
            ext_list.append((origin, def_path.resolve() if def_path else None, int(origin.lineno)))
        tasks_ext[name] = ext_list

    if workers >= 2 and total >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [src_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(_scan_files_for_plsql_constant, chunk, src_dir, encoding, names, tasks_ext)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [PL/SQL定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    results = _scan_files_for_plsql_constant(src_files, src_dir, encoding, names, tasks_ext)
    print(f"  [PL/SQL定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """PL/SQL の間接参照（CONSTANT 経由）をバッチ追跡する。"""
    from grep_helper.languages import detect_handler
    self_module = sys.modules[__name__]

    tasks: dict[str, list[GrepRecord]] = {}
    for r in direct_records:
        if detect_handler(r.filepath, src_dir) is not self_module:
            continue
        if r.usage_type != "定数/変数宣言":
            continue
        # CONSTANT キーワード必須（普通の変数宣言は除外）
        if not re.search(r'\bCONSTANT\b', r.code, re.IGNORECASE):
            continue
        name = extract_plsql_constant_name(r.code)
        if name:
            tasks.setdefault(name, []).append(r)
    if not tasks:
        return []
    stats = ProcessStats()
    return _batch_track_plsql_constant(tasks, src_dir, stats, encoding, workers=workers)
