"""Groovy grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from analyze_common import (
    GrepRecord, RefType,
    iter_source_files,
)
from grep_helper.model import ClassifyContext, ProcessStats
from grep_helper.scanner import build_batch_scanner
from grep_helper.source_files import grep_filter_files, resolve_file_cached
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding

EXTENSIONS: tuple[str, ...] = (".groovy", ".gvy")

_GROOVY_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bstatic\s+final\b'),                                              "static final定数定義"),
    (re.compile(r'\bdef\s+\w+\s*=|[\w<>\[\]]+\s+\w+\s*='),                          "変数代入"),
    (re.compile(r'\bif\s*\(|\bswitch\s*\(|==|!=|\.equals\s*\('),                    "条件判定"),
    (re.compile(r'\breturn\b'),                                                       "return文"),
    (re.compile(r'@\w+'),                                                             "アノテーション"),
    (re.compile(r'\w+\s*\('),                                                         "メソッド引数"),
]

_GROOVY_EXTENSIONS = (".groovy", ".gvy")

_STATIC_FINAL_PAT = re.compile(
    r'\bstatic\s+final\s+\w[\w<>]*\s+(\w+)\s*='
)
_CLASS_FIELD_PAT = re.compile(
    r'^(?:(?:private|protected|public)\s+\w[\w<>]*\s+\w+\s*[=;]|def\s+\w+\s*[=;])'
)
_GETTER_RETURN_PAT = re.compile(r'\breturn\s+(?:this\.)?(\w+)')
_SETTER_ASSIGN_PAT = re.compile(r'(?:this\.)?(\w+)\s*=\s*\w+')
_METHOD_DEF_PAT = re.compile(r'\b(?:def|void|\w+)\s+(\w+)\s*\(')  # noqa: E221


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Groovyコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _GROOVY_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_static_final_name(code: str) -> str | None:
    """static final 定義から定数名を抽出する。"""
    m = _STATIC_FINAL_PAT.search(code)
    return m.group(1) if m else None


def is_class_level_field(code: str) -> bool:
    """クラスレベルのフィールド宣言かどうかを判定する（インデントなしの行）。"""
    return bool(_CLASS_FIELD_PAT.match(code.strip())) and not code.startswith((' ', '\t'))


def find_getter_names_groovy(field_name: str, lines: list[str]) -> list[str]:
    """正規表現でgetterメソッド名候補を返す（2方式）。"""
    candidates = ["get" + field_name[0].upper() + field_name[1:]]
    current_method: str | None = None

    for line in lines:
        m = _METHOD_DEF_PAT.search(line)
        if m and '{' in line:
            current_method = m.group(1)
        if current_method and _GETTER_RETURN_PAT.search(line):
            rm = _GETTER_RETURN_PAT.search(line)
            if rm and rm.group(1) == field_name:
                candidates.append(current_method)

    return list(set(candidates))


def find_setter_names_groovy(field_name: str, lines: list[str]) -> list[str]:
    """正規表現でsetterメソッド名候補を返す（2方式）。"""
    candidates = ["set" + field_name[0].upper() + field_name[1:]]
    current_method: str | None = None

    for line in lines:
        m = _METHOD_DEF_PAT.search(line)
        if m and '{' in line:
            current_method = m.group(1)
        if current_method and _SETTER_ASSIGN_PAT.search(line):
            am = _SETTER_ASSIGN_PAT.search(line)
            if am and am.group(1) == field_name:
                candidates.append(current_method)

    return list(set(candidates))


def track_static_final_groovy(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """static final 定数の使用箇所を src_dir 配下の .groovy/.gvy ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = Path(record.filepath)

    src_files = iter_source_files(src_dir, list(_GROOVY_EXTENSIONS))

    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if src_file.resolve() == def_file.resolve() and i == int(record.lineno):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=const_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def track_field_groovy(
    field_name: str,
    src_file: Path,
    record: GrepRecord,
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """同一ファイル内でフィールド使用箇所を追跡する。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(field_name) + r'\b')
    lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)

    try:
        filepath_str = str(src_file.relative_to(src_dir))
    except ValueError:
        filepath_str = str(src_file)

    for i, line in enumerate(lines, 1):
        if i == int(record.lineno):
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=field_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


# NOTE: 並列化対象外（patterns 数が小さい想定; 必要なら _scan_files_for_groovy_static_final と同じ要領で追加可）
def _batch_track_getter_setter_groovy(
    getter_tasks: dict[str, list[GrepRecord]],
    setter_tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """getter/setter をプロジェクト全体に対して1パスで一括スキャンする。"""
    all_tasks = {**getter_tasks, **setter_tasks}
    if not all_tasks:
        return []

    combined = re.compile(
        r'\b(' + '|'.join(re.escape(k) for k in all_tasks) + r')\s*\('
    )
    results: list[GrepRecord] = []

    src_files = iter_source_files(src_dir, list(_GROOVY_EXTENSIONS))

    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                method_name = m.group(1)
                if method_name in getter_tasks:
                    for origin in getter_tasks[method_name]:
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.GETTER.value,
                            usage_type=classify_usage(line.strip()),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=line.strip(),
                            src_var=method_name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
                if method_name in setter_tasks:
                    for origin in setter_tasks[method_name]:
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.SETTER.value,
                            usage_type=classify_usage(line.strip()),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=line.strip(),
                            src_var=method_name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
    return results


def _resolve_groovy_file(filepath: str, src_dir: Path) -> Path | None:
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    return resolved if resolved.exists() else None


def _scan_files_for_groovy_static_final(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: Groovy static final を一括スキャン。"""
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
            for _pos, name in scanner.findall(line):
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


def _batch_track_groovy_static_final(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Groovy static final 定数をプロジェクト全体に対して1パスでバッチスキャンする。

    workers >= 2 のとき ProcessPoolExecutor で並列化する。
    """
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, [".groovy", ".gvy"], label="Groovy定数追跡")
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

    # 並列実行
    if workers >= 2 and total >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [src_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(_scan_files_for_groovy_static_final, chunk, src_dir, encoding, names, tasks_ext)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [Groovy定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    # 直列実行
    scanner = build_batch_scanner(names)
    results = []
    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Groovy定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for _pos, name in scanner.findall(line):
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

    print(f"  [Groovy定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Groovy の間接参照（static final + class field + getter/setter）をバッチ追跡する。"""
    from grep_helper.languages import detect_handler
    self_module = sys.modules[__name__]

    # Filter to .groovy/.gvy records
    own_records = [r for r in direct_records if detect_handler(r.filepath, src_dir) is self_module]
    if not own_records:
        return []

    stats = ProcessStats()
    result: list[GrepRecord] = []

    sf_tasks: dict[str, list[GrepRecord]] = {}
    getter_tasks: dict[str, list[GrepRecord]] = {}
    setter_tasks: dict[str, list[GrepRecord]] = {}

    for record in own_records:
        if record.usage_type == "static final定数定義":
            const_name = extract_static_final_name(record.code)
            if const_name:
                sf_tasks.setdefault(const_name, []).append(record)
        elif record.usage_type == "変数代入" and is_class_level_field(record.code):
            import re as _re
            m = _re.search(r'(\w+)\s*[=;]', record.code.strip())
            if m:
                fname = m.group(1)
                src_file = resolve_file_cached(record.filepath, src_dir)
                if src_file:
                    result.extend(track_field_groovy(
                        fname, src_file, record, src_dir, stats, encoding,
                    ))
                    lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
                    for g in find_getter_names_groovy(fname, lines):
                        getter_tasks.setdefault(g, []).append(record)
                    for s in find_setter_names_groovy(fname, lines):
                        setter_tasks.setdefault(s, []).append(record)

    # static final batch
    result.extend(_batch_track_groovy_static_final(sf_tasks, src_dir, stats, encoding, workers=workers))

    # getter/setter batch
    result.extend(_batch_track_getter_setter_groovy(
        getter_tasks, setter_tasks, src_dir, stats, encoding,
    ))

    return result
