"""Java AST キャッシュ層。

javalang によるパース・インデックス構築・メソッド開始行キャッシュを提供する。
また、純粋正規表現による使用タイプ分類（classify_usage_regex）も提供する。
他の java_* モジュールはこのモジュールのみに依存する（DAG の最底層）。
"""
from __future__ import annotations

import re
from pathlib import Path

try:
    import javalang
    _JAVALANG_AVAILABLE = True
except ImportError:
    _JAVALANG_AVAILABLE = False

from grep_helper.encoding import detect_encoding

# ---------------------------------------------------------------------------
# 使用タイプ分類パターン（優先度順・モジュールレベルでプリコンパイル）
# ---------------------------------------------------------------------------

USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'@\w+\s*\('),                                  "アノテーション"),
    (re.compile(r'\bstatic\s+final\b'),                         "定数定義"),
    (re.compile(r'\bif\s*\(|\bwhile\s*\(|\.equals\s*\(|[!=]='), "条件判定"),
    (re.compile(r'\breturn\b'),                                  "return文"),
    (re.compile(r'\b\w[\w<>\[\]]*\s+\w+\s*='),                 "変数代入"),
    (re.compile(r'\w+\s*\('),                                    "メソッド引数"),
]

_OTHER_TYPE = "その他"


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
    return _OTHER_TYPE


# ---------------------------------------------------------------------------
# モジュールレベルキャッシュ（シングルトン）
# ---------------------------------------------------------------------------

# キャッシュ上限（大規模プロジェクトでのOOM防止）
_MAX_AST_CACHE_SIZE = 2000   # 60GB規模のソースに対応（~2-6GB使用。メモリ不足時は500〜1000に調整）

# None = javalang パースエラーが発生したファイル（フォールバック対象）
_ast_cache: dict[str, object | None] = {}

# AST行インデックス: filepath → {lineno: (usage_type | None, scope | None)}
# usage_type: UsageType.value, scope: "class" | "method" | None
_ast_line_index: dict[str, dict[int, tuple[str | None, str | None]]] = {}

# メソッド開始行キャッシュ: filepath → sorted list of method start line numbers
_method_starts_cache: dict[str, list[int]] = {}


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

    NOTE: UsageType の値文字列をここで直接文字列リテラルとして使う（循環インポート回避）。
    java_classify がここに依存するため、ここから java_classify をインポートしてはいけない。
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
            u = "アノテーション"
        elif isinstance(node, javalang.tree.FieldDeclaration):
            modifiers = getattr(node, "modifiers", set()) or set()
            u = ("定数定義"
                 if ("static" in modifiers and "final" in modifiers)
                 else "変数代入")
            s = "class"
        elif isinstance(node, javalang.tree.LocalVariableDeclaration):
            u = "変数代入"
            s = "method"
        elif isinstance(node, (javalang.tree.IfStatement, javalang.tree.WhileStatement)):
            u = "条件判定"
        elif isinstance(node, javalang.tree.ReturnStatement):
            u = "return文"
        elif isinstance(node, (javalang.tree.MethodInvocation, javalang.tree.ClassCreator)):
            u = "メソッド引数"

        # 最初にマッチしたノードを優先（ASTトラバーサル順）
        if u is not None and line not in usage_by_line:
            usage_by_line[line] = u
        if s is not None and line not in scope_by_line:
            scope_by_line[line] = s

    all_lines = set(usage_by_line) | set(scope_by_line)
    index = {ln: (usage_by_line.get(ln), scope_by_line.get(ln)) for ln in all_lines}
    _ast_line_index[filepath] = index
    return index


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
