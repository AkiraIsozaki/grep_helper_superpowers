"""Java 追跡ヘルパー層。

_resolve_java_file, _get_method_scope, _search_in_lines, _get_java_files,
track_constant, track_field, track_local, find_getter_names, find_setter_names,
track_setter_calls, track_getter_calls, _scan_files_for_combined,
_batch_track_combined, _batch_track_constants, _batch_track_getters,
_batch_track_setters を提供する。

依存: java_ast のみ（java_classify には依存しない）。
classify_usage_regex は java_ast から取得する。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import GrepRecord, ProcessStats, RefType
from grep_helper.encoding import detect_encoding
from grep_helper.file_cache import cached_file_lines
from grep_helper.scanner import build_batch_scanner
from grep_helper.source_files import grep_filter_files, iter_source_files
from grep_helper.languages import java_ast
from grep_helper.languages.java_ast import classify_usage_regex


# ---------------------------------------------------------------------------
# ファイル解決ヘルパー
# ---------------------------------------------------------------------------

def _resolve_java_file(filepath: str, source_dir: Path) -> Path | None:
    """filepathをPathオブジェクトに解決する。

    Args:
        filepath:   Javaファイルのパス（相対または絶対）
        source_dir: Javaソースのルートディレクトリ

    Returns:
        存在する Path、または解決できない場合は None
    """
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    resolved = source_dir / filepath
    if resolved.exists():
        return resolved
    return None


# ---------------------------------------------------------------------------
# メソッドスコープ
# ---------------------------------------------------------------------------

def _get_method_scope(
    filepath: str,
    source_dir: Path,
    lineno: int,
    *,
    encoding_override: str | None = None,
) -> tuple[int, int] | None:
    """指定行を含むメソッドの行範囲を返す（内部ヘルパー）。

    javalang でメソッド開始行を取得し、ブレースカウンタで終了行を特定する。
    javalang はノードの終了行を提供しないため、ブレースカウンタ方式を採用。

    Args:
        filepath:          Javaファイルのパス
        source_dir:        Javaソースのルートディレクトリ
        lineno:            対象行の行番号
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        (start_line, end_line) のタプル、または特定不能の場合は None
    """
    if not java_ast._JAVALANG_AVAILABLE:
        return None

    # キャッシュ済みメソッド開始行を取得（AST再フィルタリングを省略）
    method_starts = java_ast._get_method_starts(filepath, source_dir, encoding_override=encoding_override)
    if not method_starts:
        return None

    # lineno を含むメソッドの開始行を特定（lineno 以下で最大のもの）
    method_start = None
    for start in method_starts:
        if start <= lineno:
            method_start = start

    if method_start is None:
        return None

    # ソースを読み込んでブレースカウンタでメソッド終了行を探す
    java_file = _resolve_java_file(filepath, source_dir)
    if java_file is None:
        return None

    lines = cached_file_lines(Path(java_file), detect_encoding(Path(java_file), encoding_override))
    if not lines:
        return None

    brace_count = 0
    found_open = False
    for i, line in enumerate(lines[method_start - 1:], start=method_start):
        brace_count += line.count('{') - line.count('}')
        if not found_open and brace_count > 0:
            found_open = True
        if found_open and brace_count <= 0:
            return (method_start, i)

    return None


# ---------------------------------------------------------------------------
# 行検索ヘルパー
# ---------------------------------------------------------------------------

def _search_in_lines(
    lines: list[str],
    var_name: str,
    start_line: int,
    origin: GrepRecord,
    source_dir: Path,
    ref_type: str,
    stats: ProcessStats,
    filepath_for_record: str,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """行リストから var_name を検索してGrepRecordを生成する（内部ヘルパー）。

    Args:
        lines:              検索対象の行リスト（0-indexed）
        var_name:           検索する変数名（単語境界マッチ）
        start_line:         lines[0] に対応する行番号（1-indexed）
        origin:             間接参照元の直接参照レコード
        source_dir:         Javaソースのルートディレクトリ
        ref_type:           参照種別（RefType.INDIRECT.value 等）
        stats:              処理統計
        filepath_for_record: GrepRecord に記録するファイルパス文字列
        encoding_override:  文字コード強制指定（省略時は自動検出）

    Returns:
        生成した GrepRecord のリスト
    """
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    records: list[GrepRecord] = []

    for idx, line in enumerate(lines):
        current_lineno = start_line + idx
        # 定義行（origin）はスキップ
        if (filepath_for_record == origin.filepath
                and str(current_lineno) == origin.lineno):
            continue
        if not pattern.search(line):
            continue

        code = line.strip()
        usage_type = classify_usage_regex(code)
        records.append(GrepRecord(
            keyword=origin.keyword,
            ref_type=ref_type,
            usage_type=usage_type,
            filepath=filepath_for_record,
            lineno=str(current_lineno),
            code=code,
            src_var=var_name,
            src_file=origin.filepath,
            src_lineno=origin.lineno,
        ))

    return records


# ---------------------------------------------------------------------------
# Java ファイル一覧
# ---------------------------------------------------------------------------

def _get_java_files(source_dir: Path) -> list[Path]:
    """source_dir 配下の .java ファイルリストをキャッシュ付きで返す。

    共通の `_source_files_cache` を経由するため、他の解析モジュールと
    キャッシュを共有しつつ rglob のディスクスキャン回数を削減する。
    """
    return iter_source_files(source_dir, [".java"])


# ---------------------------------------------------------------------------
# 追跡関数
# ---------------------------------------------------------------------------

def track_constant(
    var_name: str,
    source_dir: Path,
    origin: GrepRecord,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """static final の定数をプロジェクト全体で追跡する。

    Args:
        var_name:          追跡する定数名
        source_dir:        Javaソースのルートディレクトリ
        origin:            定数定義の直接参照レコード
        stats:             処理統計
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        間接参照 GrepRecord のリスト
    """
    records: list[GrepRecord] = []

    for java_file in _get_java_files(source_dir):
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(Path(filepath_abs), detect_encoding(Path(filepath_abs), encoding_override), stats)
        if not lines:
            continue

        records.extend(_search_in_lines(
            lines=lines,
            var_name=var_name,
            start_line=1,
            origin=origin,
            source_dir=source_dir,
            ref_type=RefType.INDIRECT.value,
            stats=stats,
            filepath_for_record=filepath_str,
            encoding_override=encoding_override,
        ))

    return records


def track_field(
    var_name: str,
    class_file: Path,
    origin: GrepRecord,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """フィールドを同一クラス内で追跡する。

    Args:
        var_name:          追跡するフィールド名
        class_file:        フィールドが定義されたJavaファイル
        origin:            フィールド定義の直接参照レコード
        source_dir:        Javaソースのルートディレクトリ
        stats:             処理統計
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        間接参照 GrepRecord のリスト
    """
    lines = cached_file_lines(Path(class_file), detect_encoding(Path(class_file), encoding_override), stats)
    if not lines:
        return []

    try:
        filepath_for_record = str(class_file.relative_to(source_dir))
    except ValueError:
        filepath_for_record = str(class_file)

    return _search_in_lines(
        lines=lines,
        var_name=var_name,
        start_line=1,
        origin=origin,
        source_dir=source_dir,
        ref_type=RefType.INDIRECT.value,
        stats=stats,
        filepath_for_record=filepath_for_record,
        encoding_override=encoding_override,
    )


def track_local(
    var_name: str,
    method_scope: tuple[int, int],
    origin: GrepRecord,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """ローカル変数を同一メソッド内で追跡する。

    Args:
        var_name:          追跡するローカル変数名
        method_scope:      (開始行番号, 終了行番号) のタプルでメソッドの行範囲を指定
        origin:            変数定義の直接参照レコード
        source_dir:        Javaソースのルートディレクトリ
        stats:             処理統計
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        間接参照 GrepRecord のリスト
    """
    java_file = _resolve_java_file(origin.filepath, source_dir)
    if java_file is None:
        return []

    all_lines = cached_file_lines(Path(java_file), detect_encoding(Path(java_file), encoding_override), stats)
    if not all_lines:
        return []

    start_line, end_line = method_scope
    # 0-indexed スライス: lines[start-1 : end]
    method_lines = all_lines[start_line - 1:end_line]

    return _search_in_lines(
        lines=method_lines,
        var_name=var_name,
        start_line=start_line,
        origin=origin,
        source_dir=source_dir,
        ref_type=RefType.INDIRECT.value,
        stats=stats,
        filepath_for_record=origin.filepath,
        encoding_override=encoding_override,
    )


# ---------------------------------------------------------------------------
# F-04: GetterTracker
# ---------------------------------------------------------------------------

def find_getter_names(
    field_name: str,
    class_file: Path,
    *,
    encoding_override: str | None = None,
) -> list[str]:
    """クラスファイルからgetterメソッド名の候補リストを返す。

    2方式を併用:
    1. 命名規則: field_name="type" → "getType"
    2. return文解析: `return field_name;` しているメソッドを全て検出（非標準命名も対象）

    Args:
        field_name:        フィールド名
        class_file:        フィールドが定義されたJavaファイル
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        getter候補名の重複なしリスト
    """
    candidates: list[str] = []

    # 方式1: 命名規則（field_name="type" → "getType"）
    getter_by_convention = "get" + field_name[0].upper() + field_name[1:]
    candidates.append(getter_by_convention)

    # 方式2: ASTからreturn文を解析（javalangのAST walk）
    if java_ast._JAVALANG_AVAILABLE:
        import javalang  # noqa: PLC0415
        cache_key = str(class_file)
        # in 演算子でキー存在確認（.get() はNone値と未設定の区別ができないため）
        if cache_key not in java_ast._ast_cache:
            try:
                source = class_file.read_text(encoding=detect_encoding(class_file, encoding_override), errors="replace")
                java_ast._ast_cache[cache_key] = javalang.parse.parse(source)
            except Exception:
                java_ast._ast_cache[cache_key] = None

        tree = java_ast._ast_cache[cache_key]
        if tree is not None:
            try:
                for _, method_decl in tree.filter(javalang.tree.MethodDeclaration):
                    for _, stmt in method_decl.filter(javalang.tree.ReturnStatement):
                        if (stmt.expression is not None
                                and hasattr(stmt.expression, 'member')
                                and stmt.expression.member == field_name):
                            candidates.append(method_decl.name)
            except Exception:
                # AST walk失敗時は方式1(命名規則)のみで継続
                print(
                    f"警告: {class_file} のAST walk中にエラーが発生しました。"
                    "getter候補を命名規則のみで決定します。",
                    file=sys.stderr,
                )

    return list(set(candidates))


def find_setter_names(
    field_name: str,
    class_file: Path,
    *,
    encoding_override: str | None = None,
) -> list[str]:
    """クラスファイルからsetterメソッド名の候補リストを返す。

    2方式を併用:
    1. 命名規則: field_name="type" → "setType"
    2. AST解析: `this.field_name = 引数` しているメソッドを全て検出（非標準命名も対象）
    """
    candidates: list[str] = []

    # 方式1: 命名規則
    setter_by_convention = "set" + field_name[0].upper() + field_name[1:]
    candidates.append(setter_by_convention)

    # 方式2: ASTから this.field = 代入を解析
    if java_ast._JAVALANG_AVAILABLE:
        import javalang  # noqa: PLC0415
        cache_key = str(class_file)
        if cache_key not in java_ast._ast_cache:
            try:
                source = class_file.read_text(encoding=detect_encoding(class_file, encoding_override), errors="replace")
                java_ast._ast_cache[cache_key] = javalang.parse.parse(source)
            except Exception:
                java_ast._ast_cache[cache_key] = None

        tree = java_ast._ast_cache[cache_key]
        if tree is not None:
            try:
                for _, method_decl in tree.filter(javalang.tree.MethodDeclaration):
                    for _, stmt in method_decl.filter(javalang.tree.StatementExpression):
                        expr = stmt.expression
                        if (expr is not None
                                and hasattr(expr, 'expressionl')
                                and hasattr(expr.expressionl, 'member')
                                and expr.expressionl.member == field_name):
                            candidates.append(method_decl.name)
            except Exception:
                pass

    return list(set(candidates))


def track_setter_calls(
    setter_name: str,
    source_dir: Path,
    origin: GrepRecord,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """プロジェクト全体でsetter呼び出し箇所を検索・分類する。"""
    pattern = re.compile(r'\b' + re.escape(setter_name) + r'\s*\(')
    records: list[GrepRecord] = []

    for java_file in _get_java_files(source_dir):
        filepath_abs = str(java_file)
        lines = cached_file_lines(Path(filepath_abs), detect_encoding(Path(filepath_abs), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if not pattern.search(line):
                continue
            usage_type = classify_usage_regex(line)
            try:
                filepath_str = str(java_file.relative_to(source_dir))
            except ValueError:
                filepath_str = filepath_abs
            records.append(GrepRecord(
                keyword=origin.keyword,
                ref_type=RefType.SETTER.value,
                usage_type=usage_type,
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=origin.src_var or setter_name,
                src_file=origin.filepath,
                src_lineno=origin.lineno,
            ))
    return records


def track_getter_calls(
    getter_name: str,
    source_dir: Path,
    origin: GrepRecord,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """プロジェクト全体でgetter呼び出し箇所を検索・分類する。

    false positive は許容（もれなく優先）。
    他クラスの同名getterが混入する可能性があるが仕様上許容。

    Args:
        getter_name:       追跡するgetterメソッド名
        source_dir:        Javaソースのルートディレクトリ
        origin:            フィールド定義の直接参照レコード
        stats:             処理統計
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        間接（getter経由）参照 GrepRecord のリスト
    """
    # getter_name() の呼び出しパターン（単語境界 + 開き括弧）
    pattern = re.compile(r'\b' + re.escape(getter_name) + r'\s*\(')
    records: list[GrepRecord] = []

    for java_file in _get_java_files(source_dir):
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(Path(filepath_abs), detect_encoding(Path(filepath_abs), encoding_override), stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            if not pattern.search(line):
                continue

            code = line.strip()
            usage_type = classify_usage_regex(code)
            records.append(GrepRecord(
                keyword=origin.keyword,
                ref_type=RefType.GETTER.value,
                usage_type=usage_type,
                filepath=filepath_str,
                lineno=str(i),
                code=code,
                src_var=getter_name,
                src_file=origin.filepath,
                src_lineno=origin.lineno,
            ))

    return records


# ---------------------------------------------------------------------------
# バッチスキャン（プロジェクト全体を1パスで複数パターン検索）
# ---------------------------------------------------------------------------

def _scan_files_for_combined(
    files: list[Path],
    source_dir: Path,
    encoding_override: str | None,
    all_names: list[str],
    const_tasks: dict[str, list[GrepRecord]],
    getter_tasks: dict[str, list[GrepRecord]],
    setter_tasks: dict[str, list[GrepRecord]],
) -> list[GrepRecord]:
    """ProcessPool worker: 渡されたファイル群を 1 パススキャンしてレコードを返す。

    pickle 経由で worker に渡せるよう、引数は basic 型 / NamedTuple / Path のみ。
    パターンの代わりに名前リストを受け取り、worker 内で build_batch_scanner で再構築する。

    注意: stats は worker プロセス内ではローカルなため、ここでは更新しない
    （並列モードでは stats 追跡はしない）。
    """
    scanner = build_batch_scanner(all_names)
    records: list[GrepRecord] = []
    for java_file in files:
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(java_file, detect_encoding(java_file, encoding_override))
        if not lines:
            continue
        for i, line in enumerate(lines, start=1):
            for pos, name in scanner.findall(line):
                end = pos + len(name)
                followed_by_paren = line[end:].lstrip().startswith("(")
                # 分類: '(' 後続なら getter/setter（getter 優先）、なければ const
                if followed_by_paren:
                    if name in getter_tasks:
                        ref_type = RefType.GETTER.value
                        origins = getter_tasks[name]
                    elif name in setter_tasks:
                        ref_type = RefType.SETTER.value
                        origins = setter_tasks[name]
                    else:
                        continue
                    code = line.strip()
                    usage_type = classify_usage_regex(code)
                    for origin in origins:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=ref_type,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                else:
                    if name not in const_tasks:
                        continue
                    code = line.strip()
                    usage_type = classify_usage_regex(code)
                    for origin in const_tasks[name]:
                        if filepath_str == origin.filepath and str(i) == origin.lineno:
                            continue
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.INDIRECT.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
    return records


def _batch_track_combined(
    const_tasks: dict[str, list[GrepRecord]],
    getter_tasks: dict[str, list[GrepRecord]],
    setter_tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
    *,
    encoding_override: str | None = None,
    workers: int = 1,
) -> list[GrepRecord]:
    """定数 / getter / setter を 1 パスで一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする。
    workers >= 2 を指定した場合、ファイルを n 等分して ProcessPoolExecutor で並列スキャンする。
    並列モードでは AST キャッシュ・行キャッシュは worker 毎に再構築されるトレードオフがあり、
    また stats は worker プロセス間で共有されないため更新されない（直列パスでのみ更新）。
    """
    if not const_tasks and not getter_tasks and not setter_tasks:
        return []

    all_names = list(dict.fromkeys(
        list(const_tasks.keys()) + list(getter_tasks.keys()) + list(setter_tasks.keys())
    ))
    java_files = file_list if file_list is not None else grep_filter_files(
        all_names, source_dir, [".java"], label="Java追跡(統合)",
    )
    if not java_files:
        return []

    # 並列実行: ファイル数が十分多く、workers が 2 以上の場合。
    if workers >= 2 and len(java_files) >= 2:
        from concurrent.futures import ProcessPoolExecutor  # noqa: PLC0415
        chunks = [java_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(
                    _scan_files_for_combined, chunk, source_dir, encoding_override,
                    all_names, const_tasks, getter_tasks, setter_tasks,
                )
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        return results

    # 直列実行（従来通り）: stats を更新し、進捗ログも出す。
    # build_batch_scanner は閾値以上で AC バックエンドに自動切替する。
    scanner = build_batch_scanner(all_names)
    records: list[GrepRecord] = []
    total = len(java_files)
    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            print(f"  [Java追跡] {idx}/{total} ファイル処理済み", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(java_file, detect_encoding(java_file, encoding_override), stats)
        if not lines:
            continue
        for i, line in enumerate(lines, start=1):
            for pos, name in scanner.findall(line):
                end = pos + len(name)
                followed_by_paren = line[end:].lstrip().startswith("(")
                # 分類: '(' 後続なら getter/setter（getter 優先）、なければ const
                if followed_by_paren:
                    if name in getter_tasks:
                        ref_type = RefType.GETTER.value
                        origins = getter_tasks[name]
                    elif name in setter_tasks:
                        ref_type = RefType.SETTER.value
                        origins = setter_tasks[name]
                    else:
                        continue
                    code = line.strip()
                    usage_type = classify_usage_regex(code)
                    for origin in origins:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=ref_type,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                else:
                    if name not in const_tasks:
                        continue
                    code = line.strip()
                    usage_type = classify_usage_regex(code)
                    for origin in const_tasks[name]:
                        if filepath_str == origin.filepath and str(i) == origin.lineno:
                            continue
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.INDIRECT.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
    return records


def _batch_track_constants(
    tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """複数の定数をプロジェクト全体で一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする（rglob 共有）。
    """
    if not tasks:
        return []

    java_files = file_list if file_list is not None else grep_filter_files(
        list(tasks.keys()), source_dir, [".java"], label="Java定数追跡",
    )

    if not java_files:
        return []

    scanner = build_batch_scanner(list(tasks.keys()))
    records: list[GrepRecord] = []
    total = len(java_files)

    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Java定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(Path(filepath_abs), detect_encoding(Path(filepath_abs), encoding_override), stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            for _pos, matched_name in scanner.findall(line):
                origins = tasks.get(matched_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage_regex(code)
                for origin in origins:
                    if filepath_str == origin.filepath and str(i) == origin.lineno:
                        continue
                    records.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=usage_type,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=matched_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Java定数追跡] 完了: {total} ファイルスキャン / 参照 {len(records)} 件発見", file=sys.stderr, flush=True)
    return records


def _batch_track_getters(
    tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """複数のgetterをプロジェクト全体で一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする（rglob 共有）。
    """
    if not tasks:
        return []

    java_files = file_list if file_list is not None else grep_filter_files(
        list(tasks.keys()), source_dir, [".java"], label="Javaゲッター追跡",
    )

    if not java_files:
        return []

    scanner = build_batch_scanner(list(tasks.keys()))
    records: list[GrepRecord] = []
    total = len(java_files)

    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Javaゲッター追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(Path(filepath_abs), detect_encoding(Path(filepath_abs), encoding_override), stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            for pos, getter_name in scanner.findall(line):
                end = pos + len(getter_name)
                if not line[end:].lstrip().startswith("("):
                    continue
                origins = tasks.get(getter_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage_regex(code)
                for origin in origins:
                    records.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.GETTER.value,
                        usage_type=usage_type,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=getter_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Javaゲッター追跡] 完了: {total} ファイルスキャン / 参照 {len(records)} 件発見", file=sys.stderr, flush=True)
    return records


def _batch_track_setters(
    tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """複数のsetterをプロジェクト全体で一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする（rglob 共有）。
    """
    if not tasks:
        return []

    java_files = file_list if file_list is not None else grep_filter_files(
        list(tasks.keys()), source_dir, [".java"], label="Javaセッター追跡",
    )

    if not java_files:
        return []

    scanner = build_batch_scanner(list(tasks.keys()))
    records: list[GrepRecord] = []
    total = len(java_files)

    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Javaセッター追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(Path(filepath_abs), detect_encoding(Path(filepath_abs), encoding_override), stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            for pos, setter_name in scanner.findall(line):
                end = pos + len(setter_name)
                if not line[end:].lstrip().startswith("("):
                    continue
                origins = tasks.get(setter_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage_regex(code)
                for origin in origins:
                    records.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.SETTER.value,
                        usage_type=usage_type,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=setter_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Javaセッター追跡] 完了: {total} ファイルスキャン / 参照 {len(records)} 件発見", file=sys.stderr, flush=True)
    return records
