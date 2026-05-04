"""Perl grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding
from grep_helper.source_files import grep_filter_files, iter_source_files, resolve_file_cached

EXTENSIONS: tuple[str, ...] = (".pl", ".pm")
SHEBANGS: tuple[str, ...] = ("perl",)

_PERL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\buse\s+constant\b'),                          "use constant定義"),
    (re.compile(r'\buse\s+\w+\b'),                                "その他"),
    (re.compile(r'\bif\s*\(|\bunless\s*\(|==|\bne\b|\beq\b'),   "条件判定"),
    (re.compile(r'\$\w+\s*=|\bmy\b.*=|\bour\b.*='),             "変数代入"),
    (re.compile(r'\bprint\b|\bsay\b|\bprintf\b'),                "print/say出力"),
    (re.compile(r'\w+\s*\('),                                    "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Perlコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PERL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_PERL_USE_CONSTANT_PAT = re.compile(r'\buse\s+constant\s+(\w+)\s*=>')
_PERL_USE_CONSTANT_HASH_PAT = re.compile(r'\buse\s+constant\s*\{([^}]*)\}', re.DOTALL)
_PERL_HASH_KEY_PAT = re.compile(r'(\w+)\s*=>')
_PERL_OUR_SCALAR_PAT = re.compile(r'\bour\s+\$(\w+)\s*=')


def extract_perl_constant_name(code: str) -> str | None:
    """単一形式 use constant FOO => ... から名前を抽出する。"""
    m = _PERL_USE_CONSTANT_PAT.search(code)
    return m.group(1) if m else None


def extract_perl_constant_hash_names(code: str) -> list[str]:
    """ハッシュ形式 use constant {A => 1, B => 2} から名前リストを抽出する。"""
    m = _PERL_USE_CONSTANT_HASH_PAT.search(code)
    if not m:
        return []
    return _PERL_HASH_KEY_PAT.findall(m.group(1))


def extract_perl_our_name(code: str) -> str | None:
    """our $FOO = ... から変数名（シジル除く）を抽出する。"""
    m = _PERL_OUR_SCALAR_PAT.search(code)
    return m.group(1) if m else None


def _make_search_pattern(name: str, kind: str) -> re.Pattern:
    """検索パターンを kind に応じて生成する。bareword=`\\bNAME\\b`, scalar=`\\$NAME\\b`."""
    if kind == "scalar":
        return re.compile(r'\$' + re.escape(name) + r'\b')
    return re.compile(r'\b' + re.escape(name) + r'\b')


def track_perl_constant(
    name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
    *,
    kind: str = "bareword",
) -> list[GrepRecord]:
    """Perl 定数 / our scalar の使用箇所を src_dir 配下の .pl/.pm ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = _make_search_pattern(name, kind)
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = iter_source_files(src_dir, [".pl", ".pm"])
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


def _scan_files_for_perl_constant(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
    kind: str,
) -> list[GrepRecord]:
    """ProcessPool worker: Perl 定数 / our scalar を一括スキャン。

    両 kind とも bare な名前で build_batch_scanner を使い、scalar の場合は
    マッチ位置の直前文字が `$` であることを後置フィルタで確認する。
    `$` プレフィックスをそのままスキャナに渡すと regex 経路で `\\b\\$NAME\\b`
    となり `print $FOO` のように `$` の左が単語境界でない箇所を取り逃す。
    """
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
                if kind == "scalar":
                    if _pos == 0 or line[_pos - 1] != '$':
                        continue
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


def _batch_track_perl_constant(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    kind: str = "bareword",
    workers: int = 1,
) -> list[GrepRecord]:
    """Perl 定数 / our scalar をプロジェクト全体に対して 1 パスでバッチスキャンする。

    kind: "bareword"（use constant FOO の裸名）または "scalar"（our $FOO のシジル付き）。
    """
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, [".pl", ".pm"], label=f"Perl{kind}追跡")
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
                ex.submit(_scan_files_for_perl_constant, chunk, src_dir, encoding, names, tasks_ext, kind)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [Perl{kind}追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    # 直列実行（worker 関数を直接呼ぶ）
    results = _scan_files_for_perl_constant(src_files, src_dir, encoding, names, tasks_ext, kind)
    print(f"  [Perl{kind}追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Perl の間接参照（use constant / our $）をバッチ追跡する。

    use constant 系統と our scalar 系統で検索パターンが違うため、
    _batch_track_perl_constant を 2 回呼び分ける。
    """
    from grep_helper.languages import detect_handler
    self_module = sys.modules[__name__]

    constant_tasks: dict[str, list[GrepRecord]] = {}
    our_tasks: dict[str, list[GrepRecord]] = {}

    for r in direct_records:
        if detect_handler(r.filepath, src_dir) is not self_module:
            continue
        if r.usage_type == "use constant定義":
            # 単一形式
            name = extract_perl_constant_name(r.code)
            if name:
                constant_tasks.setdefault(name, []).append(r)
            # ハッシュ形式（同じ行から複数名前）
            for hash_name in extract_perl_constant_hash_names(r.code):
                constant_tasks.setdefault(hash_name, []).append(r)
        elif r.usage_type == "変数代入":
            # our $FOO のみ。my は除外（パターンに `\bour\b` のみマッチ）。
            name = extract_perl_our_name(r.code)
            if name:
                our_tasks.setdefault(name, []).append(r)

    stats = ProcessStats()
    results: list[GrepRecord] = []
    if constant_tasks:
        results.extend(_batch_track_perl_constant(constant_tasks, src_dir, stats, encoding, kind="bareword", workers=workers))
    if our_tasks:
        results.extend(_batch_track_perl_constant(our_tasks, src_dir, stats, encoding, kind="scalar", workers=workers))
    return results
