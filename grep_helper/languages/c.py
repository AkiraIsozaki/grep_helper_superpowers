"""C grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.source_files import iter_source_files
from grep_helper.scanner import build_batch_scanner
from grep_helper.source_files import grep_filter_files, resolve_file_cached
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding

EXTENSIONS: tuple[str, ...] = (".c", ".h")

_C_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'#\s*define\b'),                               "#define定数定義"),
    (re.compile(r'\bif\s*\(|strcmp\s*\(|strncmp\s*\(|switch\s*\('), "条件判定"),
    (re.compile(r'\breturn\b'),                                 "return文"),
    (re.compile(r'\b\w+\s*(?:\[[^\]]*\])?\s*=(?!=)'),          "変数代入"),
    (re.compile(r'\w+\s*\('),                                   "関数引数"),
]

_define_map_cache: dict[tuple[str, str], tuple[dict[str, str], dict[str, list[str]]]] = {}


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """純Cコード行の使用タイプを分類する（6種）。EXEC SQL は対象外。"""
    stripped = code.strip()
    for pattern, usage_type in _C_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


# Pro*C SQL 型（SQLCHAR, SQLINT, VARCHAR）は純C対象外のため除外
_C_TYPES_PAT = re.compile(
    r'\b(?:char|int|short|long|float|double|unsigned|signed|struct|void)\b\s*\**\s*(\w+)'
)


def extract_variable_name_c(code: str) -> str | None:
    """C変数宣言から変数名を抽出する（型名の後の識別子）。"""
    m = _C_TYPES_PAT.search(code)
    return m.group(1) if m else None


_DEFINE_PAT = re.compile(r'#\s*define\s+(\w+)\s+')
_DEFINE_ALIAS_PAT = re.compile(r'#\s*define\s+(\w+)\s+(\w+)\s*$')


def extract_define_name(code: str) -> str | None:
    """#define からマクロ名を抽出する。値のない #define は None を返す。"""
    m = _DEFINE_PAT.match(code)
    return m.group(1) if m else None


def _build_reverse_define_map(define_map: dict[str, str]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for k, v in define_map.items():
        reverse.setdefault(v, []).append(k)
    return reverse


def _build_define_map(
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> dict[str, str]:
    """src_dir 配下の全ソースから #define NAME IDENTIFIER 形式のマップを構築する。
    内部キャッシュには forward と reverse map のタプルを保持する。
    """
    cache_key = (str(src_dir), encoding_override or "")
    cached = _define_map_cache.get(cache_key)
    if cached is not None:
        return cached[0]
    define_map: dict[str, str] = {}
    src_files = iter_source_files(src_dir, [".c", ".h", ".pc"])
    for src_file in src_files:
        enc = detect_encoding(src_file, encoding_override)
        for line in cached_file_lines(src_file, enc, stats):
            m = _DEFINE_ALIAS_PAT.match(line.strip())
            if m:
                define_map[m.group(1)] = m.group(2)
    _define_map_cache[cache_key] = (define_map, _build_reverse_define_map(define_map))
    return define_map


def _get_reverse_define_map(src_dir: Path, encoding_override: str | None) -> dict[str, list[str]]:
    cache_key = (str(src_dir), encoding_override or "")
    cached = _define_map_cache.get(cache_key)
    return cached[1] if cached is not None else {}


def _collect_define_aliases(
    var_name: str,
    define_map: dict[str, str],
    max_depth: int = 10,
    reverse: dict[str, list[str]] | None = None,
) -> list[str]:
    """var_nameを直接・間接的に参照する#define名のリストをBFSで返す。"""
    if reverse is None:
        reverse = _build_reverse_define_map(define_map)
    aliases: list[str] = []
    to_visit = [var_name]
    seen: set[str] = {var_name}
    for _ in range(max_depth):
        next_level: list[str] = []
        for name in to_visit:
            for k in reverse.get(name, []):
                if k not in seen:
                    aliases.append(k)
                    next_level.append(k)
                    seen.add(k)
        if not next_level:
            break
        to_visit = next_level
    return aliases


def track_define(
    var_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """#define マクロ名の使用箇所を src_dir 配下の .c/.h/.pc ファイルでスキャンする（多段解決）。"""
    results: list[GrepRecord] = []
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = iter_source_files(src_dir, [".c", ".h", ".pc"])

    # 多段 #define チェーンのエイリアスを収集
    define_map = _build_define_map(src_dir, stats, encoding_override)
    aliases = _collect_define_aliases(var_name, define_map, reverse=_get_reverse_define_map(src_dir, encoding_override))
    scan_names = [var_name] + aliases

    for scan_name in scan_names:
        pattern = re.compile(r'\b' + re.escape(scan_name) + r'\b')
        for src_file in src_files:
            try:
                filepath_str = str(src_file.relative_to(src_dir))
            except ValueError:
                filepath_str = str(src_file)

            lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
            for i, line in enumerate(lines, 1):
                if (scan_name == var_name
                        and def_file is not None
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
                        src_var=scan_name,
                        src_file=record.filepath,
                        src_lineno=record.lineno,
                    ))
    return results


def track_variable(
    var_name: str,
    candidate: Path,
    def_lineno: int,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """C変数名の使用箇所を同一ファイル内でスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    try:
        filepath_str = str(candidate.relative_to(src_dir))
    except ValueError:
        filepath_str = str(candidate)

    lines = cached_file_lines(Path(candidate), detect_encoding(Path(candidate), encoding_override), stats)
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


def _scan_files_for_define_c_all(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    scan_tasks: dict[str, list[tuple[bool, str, GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: C #define エイリアス込みで一括スキャン。"""
    scanner = build_batch_scanner(names)
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
            for _pos, scan_name in scanner.findall(line):
                for is_primary, _, origin, def_resolved, def_lineno in scan_tasks[scan_name]:
                    if is_primary and def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=scan_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))
    return results


def _batch_track_define_c_all(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """C #define をエイリアス解決込みで1パスでバッチスキャンする。

    workers >= 2 のとき ProcessPoolExecutor で並列化する。
    """
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
    src_files = grep_filter_files(names, src_dir, [".c", ".h", ".pc"], label="C #define追跡")
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
                ex.submit(_scan_files_for_define_c_all, chunk, src_dir, encoding, names, scan_tasks)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [C #define追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    # 直列実行
    scanner = build_batch_scanner(names)
    results = []
    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [C #define追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for _pos, scan_name in scanner.findall(line):
                for is_primary, _, origin, def_resolved, def_lineno in scan_tasks[scan_name]:
                    if is_primary and def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=scan_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [C #define追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """C の間接参照（#define + 変数代入）をバッチ追跡する。"""
    import sys as _sys
    from grep_helper.languages import detect_handler
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
            var_name = extract_variable_name_c(record.code)
            if var_name:
                candidate = resolve_file_cached(record.filepath, src_dir)
                if candidate:
                    result.extend(track_variable(
                        var_name, candidate, int(record.lineno),
                        src_dir, record, stats, encoding,
                    ))

    result.extend(_batch_track_define_c_all(define_tasks, src_dir, stats, encoding, workers=workers))
    return result
