"""シェルスクリプト grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType

EXTENSIONS: tuple[str, ...] = (".sh", ".bash")
SHEBANGS: tuple[str, ...] = ("sh", "bash", "csh", "tcsh", "ksh", "ksh93")

_SH_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bexport\b|\bsetenv\b'), "環境変数エクスポート"),
    (re.compile(r'^\s*(?:set\s+)?\w+\s*=(?!=)|^\s*\w+\s*=(?!=)'), "変数代入"),
    (re.compile(r'\bif\s*\[|\bcase\b|[!=]=|\b-eq\b|\b-ne\b|\b-lt\b|\b-gt\b|\b-le\b|\b-ge\b'),
     "条件判定"),
    (re.compile(r'\becho\b|\bprint\b|\bprintf\b'), "echo/print出力"),
    (re.compile(r'^\s*\w+\s+\S'), "コマンド引数"),
]

_SH_VAR_PATTERNS = [
    re.compile(r'^\s*(?:export\s+)?(\w+)\s*='),   # VAR= or export VAR=
    re.compile(r'^\s*set\s+(\w+)\s*='),            # CSH: set VAR=
    re.compile(r'^\s*setenv\s+(\w+)\s+'),          # CSH: setenv VAR value
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """シェルスクリプトコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _SH_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_sh_variable_name(code: str) -> str | None:
    """シェルスクリプトの代入文から変数名を抽出する。"""
    for pattern in _SH_VAR_PATTERNS:
        m = pattern.match(code)
        if m:
            return m.group(1)
    return None


def track_sh_variable(
    var_name: str,
    filepath: Path,
    def_lineno: int,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """シェル変数名の使用箇所を同一ファイル内でスキャンする（$VAR / ${VAR}）。"""
    from grep_helper.file_cache import cached_file_lines
    from grep_helper.encoding import detect_encoding

    results: list[GrepRecord] = []
    # $VAR または ${VAR} の出現を検索
    pattern = re.compile(r'\$\{?' + re.escape(var_name) + r'\}?(?=\b|[^a-zA-Z0-9_]|$)')
    try:
        filepath_str = str(filepath.relative_to(src_dir))
    except ValueError:
        filepath_str = str(filepath)

    lines = cached_file_lines(Path(filepath), detect_encoding(Path(filepath), encoding_override), stats)
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


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """直接参照レコードから sh 変数代入・エクスポートを追跡して間接参照を返す。"""
    from grep_helper.source_files import resolve_file_cached

    results: list[GrepRecord] = []
    stats = ProcessStats()
    for record in direct_records:
        if Path(record.filepath).suffix.lower() not in EXTENSIONS and \
                not _is_sh_shebang(record.filepath, src_dir):
            continue
        if record.usage_type in ("変数代入", "環境変数エクスポート"):
            var_name = extract_sh_variable_name(record.code)
            if var_name:
                candidate = resolve_file_cached(record.filepath, src_dir)
                if candidate:
                    results.extend(track_sh_variable(
                        var_name, candidate, int(record.lineno),
                        src_dir, record, stats, encoding,
                    ))
    return results


def _is_sh_shebang(filepath: str, src_dir: Path) -> bool:
    """拡張子なしのファイルがシェルスクリプトのシェバンを持つか確認する。"""
    if Path(filepath).suffix:
        return False
    from grep_helper.source_files import resolve_file_cached
    candidate = resolve_file_cached(filepath, src_dir)
    if candidate is None:
        return False
    try:
        first = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        import re as _re
        m = _re.match(r'^#!\s*(?:.*/)?(?:env\s+)?(\S+)', first)
        return bool(m and m.group(1).lower() in SHEBANGS)
    except Exception:
        return False
