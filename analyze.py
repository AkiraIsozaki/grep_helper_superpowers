"""Java grep結果 自動分類・使用箇所洗い出しツール

grep結果ファイル（input/*.grep）を読み込み、Java AST解析によって
使用タイプを分類し、UTF-8 BOM付きTSVに出力する。
"""
from __future__ import annotations

import argparse
import re
import sys
from enum import Enum
from pathlib import Path

try:
    import javalang
    _JAVALANG_AVAILABLE = True
except ImportError:
    _JAVALANG_AVAILABLE = False

from collections.abc import Iterable

from analyze_common import (
    GrepRecord,
    ProcessStats,
    RefType,
    cached_file_lines,
    detect_encoding,
    iter_grep_lines,
    parse_grep_line,
    write_tsv,
    grep_filter_files,
)

# ---------------------------------------------------------------------------
# Java専用定数
# ---------------------------------------------------------------------------

# 使用タイプ分類パターン（優先度順・モジュールレベルでプリコンパイル）
USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'@\w+\s*\('),                                  "アノテーション"),
    (re.compile(r'\bstatic\s+final\b'),                         "定数定義"),
    (re.compile(r'\bif\s*\(|\bwhile\s*\(|\.equals\s*\(|[!=]='), "条件判定"),
    (re.compile(r'\breturn\b'),                                  "return文"),
    (re.compile(r'\b\w[\w<>\[\]]*\s+\w+\s*='),                 "変数代入"),
    (re.compile(r'\w+\s*\('),                                    "メソッド引数"),
]


class UsageType(Enum):
    """使用タイプ（7種）。"""
    ANNOTATION = "アノテーション"
    CONSTANT = "定数定義"
    VARIABLE = "変数代入"
    CONDITION = "条件判定"
    RETURN = "return文"
    ARGUMENT = "メソッド引数"
    OTHER = "その他"


# ---------------------------------------------------------------------------
# ASTキャッシュ（モジュールレベル・シングルトン）
# ---------------------------------------------------------------------------

# キャッシュ上限（大規模プロジェクトでのOOM防止）
_MAX_AST_CACHE_SIZE = 2000   # 60GB規模のソースに対応（~2-6GB使用。メモリ不足時は500〜1000に調整）

# None = javalang パースエラーが発生したファイル（フォールバック対象）
_ast_cache: dict[str, object | None] = {}

# AST行インデックス: filepath → {lineno: (usage_type | None, scope | None)}
# usage_type: UsageType.value, scope: "class" | "method" | None
_ast_line_index: dict[str, dict[int, tuple[str | None, str | None]]] = {}

# Javaファイルリストキャッシュ: source_dir → sorted list of .java paths
_java_files_cache: dict[str, list[Path]] = {}

# メソッド開始行キャッシュ: filepath → sorted list of method start line numbers
_method_starts_cache: dict[str, list[int]] = {}


def process_grep_lines(
    lines: Iterable[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    *,
    report_progress: bool = False,
    path_name: str = "",
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """grep行イテラブルを処理し、第1段階（直接参照）レコードのリストを返す。

    Args:
        lines:             処理する行のイテラブル（iter_grep_lines 等）
        keyword:           検索文言（入力ファイル名から取得）
        source_dir:        Javaソースコードのルートディレクトリ
        stats:             処理統計（更新される）
        report_progress:   Trueのとき10万行ごとに進捗表示
        path_name:         進捗表示に使うファイル名（report_progress=True時のみ使用）
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        直接参照 GrepRecord のリスト
    """
    records: list[GrepRecord] = []
    _PROGRESS_INTERVAL = 100_000  # 10万行ごとに進捗表示

    for line in lines:
        stats.total_lines += 1

        if report_progress and stats.total_lines % _PROGRESS_INTERVAL == 0:
            print(
                f"  進捗: {path_name} {stats.total_lines:,} 行処理済み"
                f" (有効: {stats.valid_lines:,})",
                file=sys.stderr,
                flush=True,
            )

        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue

        usage_type = classify_usage(
            code=parsed["code"],
            filepath=parsed["filepath"],
            lineno=int(parsed["lineno"]),
            source_dir=source_dir,
            stats=stats,
            encoding_override=encoding_override,
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


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """grepファイル全行を処理し、第1段階（直接参照）レコードのリストを返す。後方互換ラッパー。

    Args:
        path:              処理する .grep ファイルのパス
        keyword:           検索文言（入力ファイル名から取得）
        source_dir:        Javaソースコードのルートディレクトリ
        stats:             処理統計（更新される）
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        直接参照 GrepRecord のリスト
    """
    # 50MB超の場合は警告と進捗報告を有効化
    file_size_mb = path.stat().st_size / (1024 * 1024)
    report_progress = file_size_mb > 50
    if file_size_mb > 500:
        print(
            f"警告: {path.name} のサイズが {file_size_mb:.1f}MB を超えています。処理に時間がかかる場合があります。",
            file=sys.stderr,
        )
    enc = detect_encoding(path, encoding_override)
    return process_grep_lines(
        iter_grep_lines(path, enc),
        keyword,
        source_dir,
        stats,
        report_progress=report_progress,
        path_name=path.name,
        encoding_override=encoding_override,
    )


# ---------------------------------------------------------------------------
# F-02: UsageClassifier
# ---------------------------------------------------------------------------

def get_ast(
    filepath: str,
    source_dir: Path,
    *,
    encoding_override: str | None = None,
) -> object | None:
    """Javaファイルを解析してASTを返す。キャッシュを利用して再解析を省略する。

    Args:
        filepath:          Javaファイルのパス（相対または絶対）
        source_dir:        Javaソースのルートディレクトリ
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        javalang の CompilationUnit、またはパースエラー時は None
    """
    if not _JAVALANG_AVAILABLE:
        return None

    cache_key = str(filepath)
    if cache_key in _ast_cache:
        return _ast_cache[cache_key]

    # キャッシュ上限に達した場合、最古エントリを削除
    if len(_ast_cache) >= _MAX_AST_CACHE_SIZE:
        oldest = next(iter(_ast_cache))
        del _ast_cache[oldest]
        _ast_line_index.pop(oldest, None)
        _method_starts_cache.pop(oldest, None)

    # source_dir / filepath または filepath 単体で試みる
    candidate = Path(filepath)
    if not candidate.is_absolute():
        candidate = source_dir / filepath

    if not candidate.exists():
        _ast_cache[cache_key] = None
        return None

    try:
        source = candidate.read_text(encoding=detect_encoding(candidate, encoding_override), errors="replace")
        tree = javalang.parse.parse(source)
        _ast_cache[cache_key] = tree
    except Exception:
        # javalang.parser.JavaSyntaxError を含む全例外をフォールバック扱い
        _ast_cache[cache_key] = None

    return _ast_cache[cache_key]


def _get_or_build_ast_index(
    filepath: str, tree: object
) -> dict[int, tuple[str | None, str | None]]:
    """ASTを走査して行番号→(usage_type, scope)インデックスを構築・キャッシュする。

    一度構築すればO(1)ルックアップになり、同一ファイルへの繰り返し走査を排除する。
    """
    if not _JAVALANG_AVAILABLE:
        return {}
    if filepath in _ast_line_index:
        return _ast_line_index[filepath]

    usage_by_line: dict[int, str] = {}
    scope_by_line: dict[int, str] = {}

    for _, node in tree:
        if not hasattr(node, "position") or node.position is None:
            continue
        line = node.position.line
        u: str | None = None
        s: str | None = None

        if isinstance(node, javalang.tree.Annotation):
            u = UsageType.ANNOTATION.value
        elif isinstance(node, javalang.tree.FieldDeclaration):
            modifiers = getattr(node, "modifiers", set()) or set()
            u = (UsageType.CONSTANT.value
                 if ("static" in modifiers and "final" in modifiers)
                 else UsageType.VARIABLE.value)
            s = "class"
        elif isinstance(node, javalang.tree.LocalVariableDeclaration):
            u = UsageType.VARIABLE.value
            s = "method"
        elif isinstance(node, (javalang.tree.IfStatement, javalang.tree.WhileStatement)):
            u = UsageType.CONDITION.value
        elif isinstance(node, javalang.tree.ReturnStatement):
            u = UsageType.RETURN.value
        elif isinstance(node, (javalang.tree.MethodInvocation, javalang.tree.ClassCreator)):
            u = UsageType.ARGUMENT.value

        # 最初にマッチしたノードを優先（ASTトラバーサル順）
        if u is not None and line not in usage_by_line:
            usage_by_line[line] = u
        if s is not None and line not in scope_by_line:
            scope_by_line[line] = s

    all_lines = set(usage_by_line) | set(scope_by_line)
    index = {ln: (usage_by_line.get(ln), scope_by_line.get(ln)) for ln in all_lines}
    _ast_line_index[filepath] = index
    return index


def classify_usage_regex(code: str) -> str:
    """正規表現で使用タイプを分類する（フォールバック専用）。

    優先度順に評価: アノテーション > 定数定義 > 条件判定 >
                   return文 > 変数代入 > メソッド引数 > その他

    Args:
        code: 分類対象のコード行（前後の空白はtrim済みを推奨）

    Returns:
        UsageType の value 文字列（7種のいずれか）
    """
    stripped = code.strip()
    for pattern, usage_type in USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return UsageType.OTHER.value


def classify_usage(
    code: str,
    filepath: str,
    lineno: int,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> str:
    """コード行を解析し、使用タイプ文字列を返す。

    javalangによるAST解析を試み、パースエラーの場合は
    正規表現フォールバックで継続する。

    Args:
        code:              分類対象のコード行（前後の空白はtrim済み）
        filepath:          Javaファイルのパス（AST解析用）
        lineno:            対象行の行番号（AST解析用）
        source_dir:        Javaソースのルートディレクトリ
        stats:             処理統計（フォールバック件数の記録用）
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        UsageType の value 文字列（7種のいずれか）
    """
    tree = get_ast(filepath, source_dir, encoding_override=encoding_override)

    if tree is None:
        # AST解析失敗またはjavalang未インストール → 正規表現フォールバック
        if _JAVALANG_AVAILABLE:
            stats.fallback_files.add(filepath)  # setなので重複は自動的に無視
        return classify_usage_regex(code)

    # ASTが利用可能な場合はノードの行番号からタイプを判定
    try:
        usage = _classify_by_ast(tree, lineno, filepath)
        if usage is not None:
            return usage
    except Exception:
        # AST走査中の予期しない例外 → フォールバック対象として記録して継続
        stats.fallback_files.add(filepath)

    # AST解析で判定できなかった場合は正規表現フォールバック
    return classify_usage_regex(code)


def _classify_by_ast(tree: object, lineno: int, filepath: str) -> str | None:
    """ASTインデックスから使用タイプをO(1)で返す。

    Args:
        tree:     javalang の CompilationUnit
        lineno:   対象行の行番号
        filepath: ASTインデックスのキャッシュキー

    Returns:
        UsageType の value 文字列、または判定不能の場合は None
    """
    if not _JAVALANG_AVAILABLE:
        return None
    index = _get_or_build_ast_index(filepath, tree)
    entry = index.get(lineno)
    return entry[0] if entry else None


# ---------------------------------------------------------------------------
# F-03: IndirectTracker
# ---------------------------------------------------------------------------

# フィールド宣言判定用パターン
_FIELD_DECL_PATTERN = re.compile(
    r'^(private|protected|public|static|final|\s)*\s+\w[\w<>\[\]]*\s+\w+\s*[=;]'
)


def determine_scope(
    usage_type: str,
    code: str,
    filepath: str = "",
    source_dir: Path | None = None,
    lineno: int = 0,
    *,
    encoding_override: str | None = None,
) -> str:
    """変数の種類に応じた追跡スコープを返す。

    javalang が利用可能な場合は AST の FieldDeclaration / LocalVariableDeclaration
    ノードで判定するため、パッケージプライベートフィールド（修飾子なし）も正しく
    "class" と判定できる。AST が使えない場合は正規表現フォールバック。

    Args:
        usage_type:        使用タイプ文字列（UsageType.value）
        code:              変数定義のコード行
        filepath:          Javaファイルのパス（AST判定に使用。省略時はフォールバック）
        source_dir:        Javaソースのルートディレクトリ（AST判定に使用）
        lineno:            対象行の行番号（AST判定に使用）
        encoding_override: 文字コード強制指定（省略時は自動検出）

    Returns:
        "project"（定数）/ "class"（フィールド）/ "method"（ローカル変数）
    """
    if usage_type == UsageType.CONSTANT.value:
        return "project"

    # ASTインデックスでO(1)判定（FieldDeclaration/LocalVariableDeclaration）
    if filepath and source_dir and lineno and _JAVALANG_AVAILABLE:
        tree = get_ast(filepath, source_dir, encoding_override=encoding_override)
        if tree is not None:
            try:
                index = _get_or_build_ast_index(filepath, tree)
                entry = index.get(lineno)
                if entry and entry[1] is not None:
                    return entry[1]
            except Exception:
                pass

    # ASTが使えない場合は正規表現フォールバック
    stripped = code.strip()
    if _FIELD_DECL_PATTERN.match(stripped):
        return "class"
    return "method"


def extract_variable_name(code: str, usage_type: str) -> str | None:  # noqa: ARG001
    """定数/変数の名前をコード行から抽出する。

    左辺（= より前）の最後の識別子を変数名とみなす。
    例: "public static final String CODE = ..." → "CODE"
    例: "String msg = CODE;" → "msg"
    例: "private String type;" → "type"

    Args:
        code:       変数定義のコード行
        usage_type: 使用タイプ文字列（現在は未使用だがインターフェース上受け取る）

    Returns:
        変数名文字列、または抽出できない場合は None
    """
    stripped = code.strip().rstrip(';')
    # = の左辺のみを対象にする
    decl_part = stripped.split('=')[0].strip()
    # 最後のトークン（識別子）が変数名
    tokens = decl_part.split()
    if len(tokens) >= 2:
        # 末尾トークンから記号を除去して返す
        name = tokens[-1].strip('[];(){}<>')
        if name.isidentifier():
            return name
    return None


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


def _get_method_starts(
    filepath: str,
    source_dir: Path,
    *,
    encoding_override: str | None = None,
) -> list[int]:
    """ファイルの全メソッド開始行をキャッシュ付きで返す（内部ヘルパー）。

    同一ファイルに対する繰り返し呼び出しでASTフィルタリングを省略する。
    """
    if filepath in _method_starts_cache:
        return _method_starts_cache[filepath]

    tree = get_ast(filepath, source_dir, encoding_override=encoding_override)
    if tree is None:
        _method_starts_cache[filepath] = []
        return []

    method_starts: list[int] = []
    try:
        for _, method_decl in tree.filter(javalang.tree.MethodDeclaration):
            if method_decl.position:
                method_starts.append(method_decl.position.line)
        method_starts.sort()
    except Exception:
        method_starts = []

    _method_starts_cache[filepath] = method_starts
    return method_starts


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
    if not _JAVALANG_AVAILABLE:
        return None

    # キャッシュ済みメソッド開始行を取得（AST再フィルタリングを省略）
    method_starts = _get_method_starts(filepath, source_dir, encoding_override=encoding_override)
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
        usage_type = classify_usage(
            code=code,
            filepath=filepath_for_record,
            lineno=current_lineno,
            source_dir=source_dir,
            stats=stats,
            encoding_override=encoding_override,
        )
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


def _get_java_files(source_dir: Path) -> list[Path]:
    """source_dir 配下の .java ファイルリストをキャッシュ付きで返す。

    rglob は呼び出しごとにディスクスキャンを行うため、同一 source_dir に対しては
    1回だけ実行してキャッシュする。_batch_track_constants / _batch_track_getters /
    track_constant / track_getter_calls で共有することで I/O を大幅に削減する。
    """
    key = str(source_dir)
    if key not in _java_files_cache:
        _java_files_cache[key] = sorted(source_dir.rglob("*.java"))
    return _java_files_cache[key]


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
    if _JAVALANG_AVAILABLE:
        cache_key = str(class_file)
        # in 演算子でキー存在確認（.get() はNone値と未設定の区別ができないため）
        if cache_key not in _ast_cache:
            try:
                source = class_file.read_text(encoding=detect_encoding(class_file, encoding_override), errors="replace")
                _ast_cache[cache_key] = javalang.parse.parse(source)
            except Exception:
                _ast_cache[cache_key] = None

        tree = _ast_cache[cache_key]
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
    if _JAVALANG_AVAILABLE:
        cache_key = str(class_file)
        if cache_key not in _ast_cache:
            try:
                source = class_file.read_text(encoding=detect_encoding(class_file, encoding_override), errors="replace")
                _ast_cache[cache_key] = javalang.parse.parse(source)
            except Exception:
                _ast_cache[cache_key] = None

        tree = _ast_cache[cache_key]
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
    """プロジェクト全体でsetter呼び出し箇所を検索・AST分類する。"""
    pattern = re.compile(r'\b' + re.escape(setter_name) + r'\s*\(')
    records: list[GrepRecord] = []

    for java_file in _get_java_files(source_dir):
        filepath_abs = str(java_file)
        lines = cached_file_lines(Path(filepath_abs), detect_encoding(Path(filepath_abs), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if not pattern.search(line):
                continue
            usage_type = classify_usage(
                code=line,
                filepath=filepath_abs,
                lineno=i,
                source_dir=source_dir,
                stats=stats,
                encoding_override=encoding_override,
            )
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
    """プロジェクト全体でgetter呼び出し箇所を検索・AST分類する。

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
            usage_type = classify_usage(
                code=code,
                filepath=filepath_str,
                lineno=i,
                source_dir=source_dir,
                stats=stats,
                encoding_override=encoding_override,
            )
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
    pattern_str: str,
    const_tasks: dict[str, list[GrepRecord]],
    getter_tasks: dict[str, list[GrepRecord]],
    setter_tasks: dict[str, list[GrepRecord]],
) -> list[GrepRecord]:
    """ProcessPool worker: 渡されたファイル群を 1 パススキャンしてレコードを返す。

    pickle 経由で worker に渡せるよう、引数は basic 型 / NamedTuple / Path のみ。
    pattern オブジェクトの代わりに pattern 文字列を受け取り、worker 内で再コンパイルする。

    注意: stats は worker プロセス内ではローカルなため、ここでは更新しない
    （並列モードでは stats 追跡はしない）。
    """
    combined = re.compile(pattern_str)
    # worker プロセス内専用の ProcessStats（呼び出し元へは伝播しない）。
    local_stats = ProcessStats()
    records: list[GrepRecord] = []
    for java_file in files:
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = cached_file_lines(java_file, detect_encoding(java_file, encoding_override), local_stats)
        if not lines:
            continue
        for i, line in enumerate(lines, start=1):
            for m in combined.finditer(line):
                code = line.strip()
                usage_type = classify_usage(
                    code=code, filepath=filepath_str, lineno=i,
                    source_dir=source_dir, stats=local_stats,
                    encoding_override=encoding_override,
                )
                gd = m.groupdict()
                const_name = gd.get("const")
                getter_name = gd.get("getter")
                setter_name = gd.get("setter")
                if const_name:
                    for origin in const_tasks[const_name]:
                        if filepath_str == origin.filepath and str(i) == origin.lineno:
                            continue
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.INDIRECT.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=const_name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                elif getter_name:
                    for origin in getter_tasks[getter_name]:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.GETTER.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=getter_name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                elif setter_name:
                    for origin in setter_tasks[setter_name]:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.SETTER.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=setter_name, src_file=origin.filepath, src_lineno=origin.lineno,
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

    parts: list[str] = []
    if const_tasks:
        parts.append(r"\b(?P<const>" + "|".join(re.escape(k) for k in const_tasks) + r")\b(?!\s*\()")
    if getter_tasks:
        parts.append(r"\b(?P<getter>" + "|".join(re.escape(k) for k in getter_tasks) + r")\s*\(")
    if setter_tasks:
        parts.append(r"\b(?P<setter>" + "|".join(re.escape(k) for k in setter_tasks) + r")\s*\(")
    pattern_str = "|".join(parts)

    # 並列実行: ファイル数が十分多く、workers が 2 以上の場合。
    if workers >= 2 and len(java_files) >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [java_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(
                    _scan_files_for_combined, chunk, source_dir, encoding_override,
                    pattern_str, const_tasks, getter_tasks, setter_tasks,
                )
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        return results

    # 直列実行（従来通り）: stats を更新し、進捗ログも出す。
    combined = re.compile(pattern_str)
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
            for m in combined.finditer(line):
                code = line.strip()
                usage_type = classify_usage(
                    code=code, filepath=filepath_str, lineno=i,
                    source_dir=source_dir, stats=stats,
                    encoding_override=encoding_override,
                )
                gd = m.groupdict()
                const_name = gd.get("const")
                getter_name = gd.get("getter")
                setter_name = gd.get("setter")
                if const_name:
                    for origin in const_tasks[const_name]:
                        if filepath_str == origin.filepath and str(i) == origin.lineno:
                            continue
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.INDIRECT.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=const_name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                elif getter_name:
                    for origin in getter_tasks[getter_name]:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.GETTER.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=getter_name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                elif setter_name:
                    for origin in setter_tasks[setter_name]:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.SETTER.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=setter_name, src_file=origin.filepath, src_lineno=origin.lineno,
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

    combined = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in tasks) + r")\b"
    )
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
            for m in combined.finditer(line):
                matched_name = m.group(1)
                origins = tasks.get(matched_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage(
                    code=code,
                    filepath=filepath_str,
                    lineno=i,
                    source_dir=source_dir,
                    stats=stats,
                    encoding_override=encoding_override,
                )
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

    combined = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in tasks) + r")\s*\("
    )
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
            for m in combined.finditer(line):
                getter_name = m.group(1)
                origins = tasks.get(getter_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage(
                    code=code,
                    filepath=filepath_str,
                    lineno=i,
                    source_dir=source_dir,
                    stats=stats,
                    encoding_override=encoding_override,
                )
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

    combined = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in tasks) + r")\s*\("
    )
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
            for m in combined.finditer(line):
                setter_name = m.group(1)
                origins = tasks.get(setter_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage(
                    code=code,
                    filepath=filepath_str,
                    lineno=i,
                    source_dir=source_dir,
                    stats=stats,
                    encoding_override=encoding_override,
                )
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


# ---------------------------------------------------------------------------
# F-06: Reporter
# ---------------------------------------------------------------------------

def print_report(stats: ProcessStats, processed_files: list[str]) -> None:
    """処理サマリを標準出力に出力する。全ファイル処理完了後に1回呼び出す。

    Args:
        stats:           処理統計
        processed_files: 処理した .grep ファイル名のリスト
    """
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


# ---------------------------------------------------------------------------
# CLI: argparse + main()
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
    return parser


def main() -> None:
    """エントリーポイント。argparse でオプションを解析し、全処理を統括する。"""
    parser = build_parser()
    args = parser.parse_args()

    encoding_override: str | None = args.encoding

    source_dir = Path(args.source_dir)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    # 入力ディレクトリの検証
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

    # .grep ファイルを検出
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
            keyword = grep_path.stem  # 拡張子なしのファイル名 = 検索文言

            # 第1段階: 直接参照の取得と分類
            file_size_mb = grep_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 500:
                print(
                    f"警告: {grep_path.name} のサイズが {file_size_mb:.1f}MB を超えています。処理に時間がかかる場合があります。",
                    file=sys.stderr,
                )
            enc = detect_encoding(grep_path, encoding_override)
            direct_records = process_grep_lines(
                iter_grep_lines(grep_path, enc),
                keyword,
                source_dir,
                stats,
                report_progress=file_size_mb > 50,
                path_name=grep_path.name,
                encoding_override=encoding_override,
            )
            all_records: list[GrepRecord] = list(direct_records)

            # 第2・第3段階: 間接参照・getter経由参照の追跡
            # プロジェクト全体スキャンはバッチ化して1パスに削減
            project_scope_tasks: dict[str, list[GrepRecord]] = {}
            getter_tasks: dict[str, list[GrepRecord]] = {}
            setter_tasks: dict[str, list[GrepRecord]] = {}

            for record in direct_records:
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
                    encoding_override=encoding_override,
                )

                if scope == "project":
                    # バッチ追跡リストに積む（後でまとめて1パススキャン）
                    project_scope_tasks.setdefault(var_name, []).append(record)

                elif scope == "class":
                    # 第2段階: フィールドを同一クラス内で追跡
                    class_file = _resolve_java_file(record.filepath, source_dir)
                    if class_file:
                        indirect = track_field(
                            var_name, class_file, record, source_dir, stats,
                            encoding_override=encoding_override,
                        )
                        all_records.extend(indirect)

                        # getter/setter名を収集してバッチ追跡リストに積む
                        for getter_name in find_getter_names(
                            var_name, class_file, encoding_override=encoding_override,
                        ):
                            getter_tasks.setdefault(getter_name, []).append(record)
                        for setter_name in find_setter_names(
                            var_name, class_file, encoding_override=encoding_override,
                        ):
                            setter_tasks.setdefault(setter_name, []).append(record)

                elif scope == "method":
                    # 第2段階: ローカル変数を同一メソッド内で追跡
                    method_scope = _get_method_scope(
                        record.filepath, source_dir, int(record.lineno),
                        encoding_override=encoding_override,
                    )
                    if method_scope:
                        all_records.extend(
                            track_local(
                                var_name, method_scope, record, source_dir, stats,
                                encoding_override=encoding_override,
                            )
                        )

            # 定数・getter・setter の事前フィルタを1回の rglob で共有し、
            # 1 パスで定数/getter/setter を統合追跡する。
            if project_scope_tasks or getter_tasks or setter_tasks:
                all_java_names = list(dict.fromkeys(
                    list(project_scope_tasks.keys())
                    + list(getter_tasks.keys())
                    + list(setter_tasks.keys())
                ))
                java_candidates = grep_filter_files(
                    all_java_names, source_dir, [".java"], label="Java追跡",
                )
                all_records.extend(_batch_track_combined(
                    const_tasks=project_scope_tasks,
                    getter_tasks=getter_tasks,
                    setter_tasks=setter_tasks,
                    source_dir=source_dir, stats=stats, file_list=java_candidates,
                    encoding_override=encoding_override,
                ))

            # 出力
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


if __name__ == "__main__":
    main()
