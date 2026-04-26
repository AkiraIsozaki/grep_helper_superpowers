# analyze_dotnet.py
"""C# / VB.NET grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from collections.abc import Iterable

from analyze_common import GrepRecord, ProcessStats, RefType, cached_file_lines, detect_encoding, iter_grep_lines, iter_source_files, parse_grep_line, write_tsv

_DOTNET_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\b|\bConst\b|\breadonly\b'),                           "定数定義(Const/readonly)"),
    (re.compile(r'\b(?:var|string|int|String)\s+\w+\s*=|\bDim\b.*='),          "変数代入"),
    (re.compile(r'\bif\s*\(|\bIf\b|==|!=|<>|\.Equals\s*\('),                  "条件判定"),
    (re.compile(r'\breturn\b|\bReturn\b'),                                       "return文"),
    (re.compile(r'^\s*\[[\w]+|^\s*<[\w]+'),                                     "属性(Attribute)"),
    (re.compile(r'\w+\s*\('),                                                    "メソッド引数"),
]

_DOTNET_EXTENSIONS = (".cs", ".vb")

_CS_CONST_PATS = [
    re.compile(r'\bconst\s+\w[\w<>]*\s+(\w+)\s*='),
    re.compile(r'\bpublic\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*='),
    re.compile(r'\bprivate\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*='),
]
_VB_CONST_PAT = re.compile(r'\bConst\s+(\w+)\s+As\b')


def classify_usage_dotnet(code: str) -> str:
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

    src_files = iter_source_files(src_dir, list(_DOTNET_EXTENSIONS))

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
                    usage_type=classify_usage_dotnet(line.strip()),
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
            usage_type=classify_usage_dotnet(parsed["code"]),
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
    parser = argparse.ArgumentParser(
        description="C#/VB.NET grep結果 自動分類・使用箇所洗い出しツール。"
                    "並列実行は analyze_all.py --workers を使用してください。"
    )
    parser.add_argument("--source-dir", required=True, help="C#/VB.NETソースのルートディレクトリ")
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
                if record.usage_type == "定数定義(Const/readonly)":
                    const_name = extract_const_name_dotnet(record.code)
                    if const_name:
                        all_records.extend(track_const_dotnet(const_name, source_dir, record, stats, args.encoding))

            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(all_records, output_path)
            processed_files.append(grep_path.name)
            direct_count   = len(direct_records)
            indirect_count = len(all_records) - direct_count
            print(f"  {grep_path.name} → {output_path} (直接: {direct_count} 件, 間接: {indirect_count} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}"
          f"  スキップ: {stats.skipped_lines}")


if __name__ == "__main__":
    main()
