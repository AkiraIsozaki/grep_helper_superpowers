# analyze_proc.py
"""Pro*C grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, parse_grep_line, write_tsv
from analyze_c import classify_usage_c, _collect_define_aliases

# ---------------------------------------------------------------------------
# 使用タイプ分類パターン（優先度順）
# ---------------------------------------------------------------------------

_PROC_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bEXEC\s+SQL\b', re.IGNORECASE), "EXEC SQL文"),
    (re.compile(r'#\s*define\b'),                  "#define定数定義"),
    (re.compile(r'\bif\s*\(|strcmp\s*\(|strncmp\s*\('), "条件判定"),
    (re.compile(r'\breturn\b'),                    "return文"),
    (re.compile(r'\b\w+\s*(?:\[[^\]]*\])?\s*=(?!=)'), "変数代入"),
    (re.compile(r'\w+\s*\('),                      "関数引数"),
]

# ---------------------------------------------------------------------------
# ファイル行キャッシュ
# ---------------------------------------------------------------------------

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800
_define_map_cache: dict[tuple[str, str], dict[str, str]] = {}


def _get_cached_lines(
    filepath: str | Path,
    stats: ProcessStats | None = None,
    encoding_override: str | None = None,
) -> list[str]:
    path = Path(filepath)
    enc = detect_encoding(path, encoding_override)
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            _file_cache[key] = path.read_text(encoding=enc, errors="replace").splitlines()
        except Exception:
            if stats is not None:
                stats.encoding_errors.add(key)
            _file_cache[key] = []
    return _file_cache[key]


def _resolve_source_file(filepath: str, src_dir: Path) -> Path | None:
    """ファイルパスを解決する。CWD相対→src_dir相対の順で試みる。"""
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    if resolved.exists():
        return resolved
    return None


# ---------------------------------------------------------------------------
# 使用タイプ分類
# ---------------------------------------------------------------------------

def classify_usage_proc(code: str) -> str:
    """Pro*Cコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PROC_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def _classify_for_filepath(code: str, filepath: str) -> str:
    """ファイルパスの拡張子に基づいて適切な分類関数を呼び出す。"""
    ext = Path(filepath).suffix.lower()
    if ext in ('.c', '.h'):
        return classify_usage_c(code)
    return classify_usage_proc(code)


# ---------------------------------------------------------------------------
# 変数名・マクロ名抽出
# ---------------------------------------------------------------------------

_C_TYPES_PAT = re.compile(
    r'\b(?:char|int|short|long|float|double|unsigned|signed|struct|void'
    r'|SQLCHAR|SQLINT|VARCHAR)\b\s*\**\s*(\w+)'
)


def extract_variable_name_proc(code: str) -> str | None:
    """C変数宣言から変数名を抽出する（型名の後の識別子）。"""
    m = _C_TYPES_PAT.search(code)
    return m.group(1) if m else None


_DEFINE_PAT = re.compile(r'#\s*define\s+(\w+)\s+')
_DEFINE_ALIAS_PAT = re.compile(r'#\s*define\s+(\w+)\s+(\w+)\s*$')


def _build_define_map(
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> dict[str, str]:
    """src_dir配下の全ソースから #define NAME IDENTIFIER 形式のマップを構築する。"""
    cache_key = (str(src_dir), encoding_override or "")
    if cache_key in _define_map_cache:
        return _define_map_cache[cache_key]
    define_map: dict[str, str] = {}
    pc_files = (sorted(src_dir.rglob("*.pc"))
                + sorted(src_dir.rglob("*.c"))
                + sorted(src_dir.rglob("*.h")))
    for pc_file in pc_files:
        for line in _get_cached_lines(pc_file, stats, encoding_override):
            m = _DEFINE_ALIAS_PAT.match(line.strip())
            if m:
                define_map[m.group(1)] = m.group(2)
    _define_map_cache[cache_key] = define_map
    return define_map


def extract_define_name(code: str) -> str | None:
    """#define からマクロ名を抽出する。値のない #define は None を返す。"""
    m = _DEFINE_PAT.match(code)
    return m.group(1) if m else None


def extract_host_var_name(code: str) -> str | None:
    """ホスト変数名を抽出する（strcpy / EXEC SQL INTO / 単純代入）。"""
    m = re.match(r'\s*str(?:n?cpy)\s*\(\s*(\w+)', code)
    if m:
        return m.group(1)
    m = re.match(r'\s*sprintf\s*\(\s*(\w+)', code)
    if m:
        return m.group(1)
    m = re.search(r'\bINTO\s*:(\w+)', code, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.match(r'\s*(\w+)\s*=\s*"', code)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 間接参照追跡
# ---------------------------------------------------------------------------

def track_define(
    var_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """#define マクロ名の使用箇所を src_dir 配下の全 .pc/.c/.h ファイルでスキャンする（多段解決）。"""
    results: list[GrepRecord] = []
    def_file = _resolve_source_file(record.filepath, src_dir)

    pc_files = (sorted(src_dir.rglob("*.pc"))
                + sorted(src_dir.rglob("*.c"))
                + sorted(src_dir.rglob("*.h")))

    define_map = _build_define_map(src_dir, stats, encoding_override)
    aliases = _collect_define_aliases(var_name, define_map)
    scan_names = [var_name] + aliases

    for scan_name in scan_names:
        pattern = re.compile(r'\b' + re.escape(scan_name) + r'\b')
        for pc_file in pc_files:
            try:
                filepath_str = str(pc_file.relative_to(src_dir))
            except ValueError:
                filepath_str = str(pc_file)

            lines = _get_cached_lines(pc_file, stats, encoding_override)
            for i, line in enumerate(lines, 1):
                if (scan_name == var_name
                        and def_file is not None
                        and pc_file.resolve() == def_file.resolve()
                        and i == int(record.lineno)):
                    continue
                if pattern.search(line):
                    results.append(GrepRecord(
                        keyword=record.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=_classify_for_filepath(line.strip(), str(pc_file)),
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

    lines = _get_cached_lines(candidate, stats, encoding_override)
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_proc(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


# ---------------------------------------------------------------------------
# grep ファイル処理
# ---------------------------------------------------------------------------

def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """grepファイル全行を処理し、直接参照レコードを返す。"""
    records: list[GrepRecord] = []
    enc = detect_encoding(path, encoding_override)
    with open(path, encoding=enc, errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=_classify_for_filepath(parsed["code"], parsed["filepath"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pro*C grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="Pro*Cソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None, help="文字コード強制指定（省略時は自動検出）")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"エラー: --source-dir が存在しません: {source_dir}", file=sys.stderr)
        sys.exit(1)
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"エラー: --input-dir が存在しません: {input_dir}", file=sys.stderr)
        sys.exit(1)

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print("エラー: grep結果ファイルがありません", file=sys.stderr)
        sys.exit(1)

    stats = ProcessStats()
    processed_files: list[str] = []
    try:
        for grep_path in grep_files:
            keyword = grep_path.stem
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats, args.encoding)
            all_records: list[GrepRecord] = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = extract_define_name(record.code)
                    if var_name:
                        all_records.extend(track_define(var_name, source_dir, record, stats, args.encoding))
                elif record.usage_type == "変数代入":
                    var_name = extract_variable_name_proc(record.code)
                    if not var_name:
                        var_name = extract_host_var_name(record.code)
                    if var_name:
                        candidate = _resolve_source_file(record.filepath, source_dir)
                        if candidate:
                            all_records.extend(
                                track_variable(var_name, candidate,
                                               int(record.lineno), source_dir, record, stats, args.encoding)
                            )

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} "
                  f"(直接: {direct_count} 件, 間接: {indirect_count} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}"
          f"  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
