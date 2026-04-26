"""Java 使用タイプ分類層。

UsageType Enum、regex パターン、AST ベース分類、スコープ判定、変数名抽出を提供する。
依存: java_ast のみ（java_track には依存しない）。
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from grep_helper.languages import java_ast

# Re-export from java_ast so that consumers can import from java_classify or java_ast
from grep_helper.languages.java_ast import (  # noqa: F401
    USAGE_PATTERNS as USAGE_PATTERNS,
    classify_usage_regex as classify_usage_regex,
)

# ---------------------------------------------------------------------------
# UsageType
# ---------------------------------------------------------------------------


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
# フィールド宣言判定用パターン
# ---------------------------------------------------------------------------

_FIELD_DECL_PATTERN = re.compile(
    r'^(private|protected|public|static|final|\s)*\s+\w[\w<>\[\]]*\s+\w+\s*[=;]'
)


# ---------------------------------------------------------------------------
# 分類関数
# ---------------------------------------------------------------------------


def _classify_by_ast(tree: object, lineno: int, filepath: str) -> str | None:
    """ASTインデックスから使用タイプをO(1)で返す。

    Args:
        tree:     javalang の CompilationUnit
        lineno:   対象行の行番号
        filepath: ASTインデックスのキャッシュキー

    Returns:
        UsageType の value 文字列、または判定不能の場合は None
    """
    if not java_ast._JAVALANG_AVAILABLE:
        return None
    index = java_ast._get_or_build_ast_index(filepath, tree)
    entry = index.get(lineno)
    return entry[0] if entry else None


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
    if filepath and source_dir and lineno and java_ast._JAVALANG_AVAILABLE:
        tree = java_ast.get_ast(filepath, source_dir, encoding_override=encoding_override)
        if tree is not None:
            try:
                index = java_ast._get_or_build_ast_index(filepath, tree)
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
