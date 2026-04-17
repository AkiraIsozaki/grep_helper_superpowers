# analyze_c.py
"""純C grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv

_C_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'#\s*define\b'),                               "#define定数定義"),
    (re.compile(r'\bif\s*\(|strcmp\s*\(|strncmp\s*\(|switch\s*\('), "条件判定"),
    (re.compile(r'\breturn\b'),                                 "return文"),
    (re.compile(r'\b\w+\s*(?:\[[^\]]*\])?\s*=(?!=)'),          "変数代入"),
    (re.compile(r'\w+\s*\('),                                   "関数引数"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


def _get_cached_lines(filepath: str | Path, stats: ProcessStats | None = None) -> list[str]:
    key = str(filepath)
    if key not in _file_cache:
        if len(_file_cache) >= _MAX_FILE_CACHE:
            _file_cache.pop(next(iter(_file_cache)))
        try:
            _file_cache[key] = Path(filepath).read_text(
                encoding="cp932", errors="replace"
            ).splitlines()
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
    return resolved if resolved.exists() else None


def classify_usage_c(code: str) -> str:
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


def extract_define_name(code: str) -> str | None:
    """#define からマクロ名を抽出する。値のない #define は None を返す。"""
    m = _DEFINE_PAT.match(code)
    return m.group(1) if m else None


def track_define(
    var_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """#define マクロ名の使用箇所を src_dir 配下の .c/.h/.pc ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    def_file = _resolve_source_file(record.filepath, src_dir)

    src_files = (sorted(src_dir.rglob("*.c"))
                 + sorted(src_dir.rglob("*.h"))
                 + sorted(src_dir.rglob("*.pc")))
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = _get_cached_lines(src_file, stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage_c(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=var_name,
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
) -> list[GrepRecord]:
    """C変数名の使用箇所を同一ファイル内でスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
    try:
        filepath_str = str(candidate.relative_to(src_dir))
    except ValueError:
        filepath_str = str(candidate)

    lines = _get_cached_lines(candidate, stats)
    for i, line in enumerate(lines, 1):
        if i == def_lineno:
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_c(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=var_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


def process_grep_file(
    path: Path,
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """grepファイル全行を処理し、直接参照レコードを返す。"""
    records: list[GrepRecord] = []
    with open(path, encoding="cp932", errors="replace") as f:
        for line in f:
            stats.total_lines += 1
            parsed = parse_grep_line(line)
            if parsed is None:
                stats.skipped_lines += 1
                continue
            records.append(GrepRecord(
                keyword=keyword,
                ref_type=RefType.DIRECT.value,
                usage_type=classify_usage_c(parsed["code"]),
                filepath=parsed["filepath"],
                lineno=parsed["lineno"],
                code=parsed["code"],
            ))
            stats.valid_lines += 1
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="純C grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="C ソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
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
            direct_records = process_grep_file(grep_path, keyword, source_dir, stats)
            all_records: list[GrepRecord] = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = extract_define_name(record.code)
                    if var_name:
                        all_records.extend(track_define(var_name, source_dir, record, stats))
                elif record.usage_type == "変数代入":
                    # 純Cでは strcpy/sprintf は「関数引数」に分類されるため
                    # Pro*C の extract_host_var_name 相当のフォールバックは不要
                    var_name = extract_variable_name_c(record.code)
                    if var_name:
                        candidate = _resolve_source_file(record.filepath, source_dir)
                        if candidate:
                            all_records.extend(
                                track_variable(var_name, candidate,
                                               int(record.lineno), source_dir, record, stats)
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
