""".NET (C#/VB) grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from analyze_common import (
    GrepRecord, RefType,
    build_batch_scanner,
    cached_file_lines, detect_encoding,
    grep_filter_files, iter_source_files, resolve_file_cached,
)
from grep_helper.model import ClassifyContext, ProcessStats

EXTENSIONS: tuple[str, ...] = (".cs", ".vb")

_DOTNET_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\b|\bConst\b|\breadonly\b'),                           "定数定義(Const/readonly)"),
    (re.compile(r'\b(?:var|string|int|String)\s+\w+\s*=|\bDim\b.*='),          "変数代入"),
    (re.compile(r'\bif\s*\(|\bIf\b|==|!=|<>|\.Equals\s*\('),                  "条件判定"),
    (re.compile(r'\breturn\b|\bReturn\b'),                                       "return文"),
    (re.compile(r'^\s*\[[\w]+|^\s*<[\w]+'),                                     "属性(Attribute)"),
    (re.compile(r'\w+\s*\('),                                                    "メソッド引数"),
]

_CS_CONST_PATS = [
    re.compile(r'\bconst\s+\w[\w<>]*\s+(\w+)\s*='),
    re.compile(r'\bpublic\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*='),
    re.compile(r'\bprivate\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*='),
]
_VB_CONST_PAT = re.compile(r'\bConst\s+(\w+)\s+As\b')


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """C#/VB.NETコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _DOTNET_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_const_name_dotnet(code: str) -> str | None:
    """C# const/static readonly または VB Const 宣言から定数名を抽出する。"""
    for pat in _CS_CONST_PATS:
        m = pat.search(code)
        if m:
            return m.group(1)
    m = _VB_CONST_PAT.search(code)
    return m.group(1) if m else None


def track_const_dotnet(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """定数の使用箇所を src_dir 配下の .cs / .vb ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = Path(record.filepath)

    src_files = iter_source_files(src_dir, list(EXTENSIONS))

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


def _scan_files_for_dotnet_const(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: .NET const/static readonly を一括スキャン。"""
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


def _batch_track_dotnet_const(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """.NET const/static readonly をプロジェクト全体に対して1パスでバッチスキャンする。

    workers >= 2 のとき ProcessPoolExecutor で並列化する。
    """
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, [".cs", ".vb"], label=".NET定数追跡")
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
                ex.submit(_scan_files_for_dotnet_const, chunk, src_dir, encoding, names, tasks_ext)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [.NET定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    # 直列実行
    scanner = build_batch_scanner(names)
    results = []
    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [.NET定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
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

    print(f"  [.NET定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """.NET (C#/VB) の間接参照（Const/readonly 経由）をバッチ追跡する。

    direct_records から .cs / .vb ファイルかつ usage_type "定数定義(Const/readonly)" の
    レコードだけを内部で抽出し、_batch_track_dotnet_const に委譲する。
    """
    import sys as _sys
    from grep_helper.languages import detect_handler
    self_module = _sys.modules[__name__]

    tasks: dict[str, list[GrepRecord]] = {}
    for r in direct_records:
        if detect_handler(r.filepath, src_dir) is not self_module:
            continue
        if r.usage_type != "定数定義(Const/readonly)":
            continue
        name = extract_const_name_dotnet(r.code)
        if name:
            tasks.setdefault(name, []).append(r)
    if not tasks:
        return []
    stats = ProcessStats()
    return _batch_track_dotnet_const(tasks, src_dir, stats, encoding, workers=workers)
