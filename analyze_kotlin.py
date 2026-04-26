# analyze_kotlin.py
"""Kotlin grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from collections.abc import Iterable

from analyze_common import GrepRecord, ProcessStats, RefType, detect_encoding, iter_grep_lines, parse_grep_line, resolve_file_cached, write_tsv

_KOTLIN_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\s+val\s+\w+\s*='),              "const定数定義"),
    (re.compile(r'\b(?:val|var)\s+\w+\s*='),              "変数代入"),
    (re.compile(r'\bif\s*\(|\bwhen\s*\('),                "条件判定"),
    (re.compile(r'\breturn\b'),                            "return文"),
    (re.compile(r'@\w+'),                                  "アノテーション"),
    (re.compile(r'\w+\s*\('),                              "関数引数"),
]

_file_cache: dict[str, list[str]] = {}
_MAX_FILE_CACHE = 800


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


def classify_usage_kotlin(code: str) -> str:
    """Kotlinコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _KOTLIN_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_CONST_VAL_PAT = re.compile(r'\bconst\s+val\s+(\w+)\s*=')


def extract_const_name(code: str) -> str | None:
    """const val 定義から定数名を抽出する。"""
    m = _CONST_VAL_PAT.search(code)
    return m.group(1) if m else None


def track_const(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """const val 定数の使用箇所を src_dir 配下の .kt/.kts ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = sorted(src_dir.rglob("*.kt")) + sorted(src_dir.rglob("*.kts"))
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = _get_cached_lines(src_file, stats, encoding_override)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage_kotlin(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=const_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def process_grep_lines(
    lines: Iterable[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """grepファイル行イテラブルを処理し、直接参照レコードを返す。"""
    records: list[GrepRecord] = []
    for line in lines:
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=classify_usage_kotlin(parsed["code"]),
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
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """grepファイル全行を処理し、直接参照レコードを返す。後方互換ラッパー。"""
    enc = detect_encoding(path, encoding_override)
    return process_grep_lines(iter_grep_lines(path, enc), keyword, source_dir, stats)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kotlin grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="Kotlinソースのルートディレクトリ")
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
            enc = detect_encoding(grep_path, args.encoding)
            direct_records = process_grep_lines(iter_grep_lines(grep_path, enc), keyword, source_dir, stats)
            all_records: list[GrepRecord] = list(direct_records)

            for record in direct_records:
                if record.usage_type == "const定数定義":
                    const_name = extract_const_name(record.code)
                    if const_name:
                        all_records.extend(track_const(const_name, source_dir, record, stats, args.encoding))

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
