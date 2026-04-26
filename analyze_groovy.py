# analyze_groovy.py
"""Groovy grep結果 自動分類・使用箇所洗い出しツール。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from collections.abc import Iterable

from analyze_common import GrepRecord, ProcessStats, RefType, cached_file_lines, detect_encoding, iter_grep_lines, parse_grep_line, write_tsv

_GROOVY_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bstatic\s+final\b'),                                              "static final定数定義"),
    (re.compile(r'\bdef\s+\w+\s*=|[\w<>\[\]]+\s+\w+\s*='),                          "変数代入"),
    (re.compile(r'\bif\s*\(|\bswitch\s*\(|==|!=|\.equals\s*\('),                    "条件判定"),
    (re.compile(r'\breturn\b'),                                                       "return文"),
    (re.compile(r'@\w+'),                                                             "アノテーション"),
    (re.compile(r'\w+\s*\('),                                                         "メソッド引数"),
]

_GROOVY_EXTENSIONS = (".groovy", ".gvy")

_STATIC_FINAL_PAT = re.compile(
    r'\bstatic\s+final\s+\w[\w<>]*\s+(\w+)\s*='
)
_CLASS_FIELD_PAT = re.compile(
    r'^(?:(?:private|protected|public)\s+\w[\w<>]*\s+\w+\s*[=;]|def\s+\w+\s*[=;])'
)
_GETTER_RETURN_PAT = re.compile(r'\breturn\s+(?:this\.)?(\w+)')
_SETTER_ASSIGN_PAT = re.compile(r'(?:this\.)?(\w+)\s*=\s*\w+')
_METHOD_DEF_PAT    = re.compile(r'\b(?:def|void|\w+)\s+(\w+)\s*\(')



def classify_usage_groovy(code: str) -> str:
    """Groovyコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _GROOVY_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


def extract_static_final_name(code: str) -> str | None:
    """static final 定義から定数名を抽出する。"""
    m = _STATIC_FINAL_PAT.search(code)
    return m.group(1) if m else None


def is_class_level_field(code: str) -> bool:
    """クラスレベルのフィールド宣言かどうかを判定する（インデントなしの行）。"""
    return bool(_CLASS_FIELD_PAT.match(code.strip())) and not code.startswith((' ', '\t'))


def find_getter_names_groovy(field_name: str, class_lines: list[str]) -> list[str]:
    """正規表現でgetterメソッド名候補を返す（2方式）。"""
    candidates = ["get" + field_name[0].upper() + field_name[1:]]
    current_method: str | None = None

    for line in class_lines:
        m = _METHOD_DEF_PAT.search(line)
        if m and '{' in line:
            current_method = m.group(1)
        if current_method and _GETTER_RETURN_PAT.search(line):
            rm = _GETTER_RETURN_PAT.search(line)
            if rm and rm.group(1) == field_name:
                candidates.append(current_method)

    return list(set(candidates))


def find_setter_names_groovy(field_name: str, class_lines: list[str]) -> list[str]:
    """正規表現でsetterメソッド名候補を返す（2方式）。"""
    candidates = ["set" + field_name[0].upper() + field_name[1:]]
    current_method: str | None = None

    for line in class_lines:
        m = _METHOD_DEF_PAT.search(line)
        if m and '{' in line:
            current_method = m.group(1)
        if current_method and _SETTER_ASSIGN_PAT.search(line):
            am = _SETTER_ASSIGN_PAT.search(line)
            if am and am.group(1) == field_name:
                candidates.append(current_method)

    return list(set(candidates))


def track_static_final_groovy(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """static final 定数の使用箇所を src_dir 配下の .groovy/.gvy ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = Path(record.filepath)

    src_files: list[Path] = []
    for ext in _GROOVY_EXTENSIONS:
        src_files.extend(sorted(src_dir.rglob(f"*{ext}")))

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
                    usage_type=classify_usage_groovy(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=const_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def track_field_groovy(
    field_name: str,
    src_file: Path,
    record: GrepRecord,
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """同一ファイル内でフィールド使用箇所を追跡する。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(field_name) + r'\b')
    lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)

    try:
        filepath_str = str(src_file.relative_to(src_dir))
    except ValueError:
        filepath_str = str(src_file)

    for i, line in enumerate(lines, 1):
        if i == int(record.lineno):
            continue
        if pattern.search(line):
            results.append(GrepRecord(
                keyword=record.keyword,
                ref_type=RefType.INDIRECT.value,
                usage_type=classify_usage_groovy(line.strip()),
                filepath=filepath_str,
                lineno=str(i),
                code=line.strip(),
                src_var=field_name,
                src_file=record.filepath,
                src_lineno=record.lineno,
            ))
    return results


def _batch_track_getter_setter_groovy(
    getter_tasks: dict[str, list[GrepRecord]],
    setter_tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """getter/setter をプロジェクト全体に対して1パスで一括スキャンする。"""
    all_tasks = {**getter_tasks, **setter_tasks}
    if not all_tasks:
        return []

    combined = re.compile(
        r'\b(' + '|'.join(re.escape(k) for k in all_tasks) + r')\s*\('
    )
    results: list[GrepRecord] = []

    src_files: list[Path] = []
    for ext in _GROOVY_EXTENSIONS:
        src_files.extend(sorted(src_dir.rglob(f"*{ext}")))

    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                method_name = m.group(1)
                if method_name in getter_tasks:
                    for origin in getter_tasks[method_name]:
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.GETTER.value,
                            usage_type=classify_usage_groovy(line.strip()),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=line.strip(),
                            src_var=method_name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
                if method_name in setter_tasks:
                    for origin in setter_tasks[method_name]:
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.SETTER.value,
                            usage_type=classify_usage_groovy(line.strip()),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=line.strip(),
                            src_var=method_name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
    return results


def _resolve_groovy_file(filepath: str, src_dir: Path) -> Path | None:
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if candidate.exists():
        return candidate
    resolved = src_dir / filepath
    return resolved if resolved.exists() else None


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
            usage_type=classify_usage_groovy(parsed["code"]),
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
    parser = argparse.ArgumentParser(description="Groovy grep結果 自動分類・使用箇所洗い出しツール")
    parser.add_argument("--source-dir", required=True, help="Groovyソースのルートディレクトリ")
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

            getter_tasks: dict[str, list[GrepRecord]] = {}
            setter_tasks: dict[str, list[GrepRecord]] = {}

            for record in direct_records:
                if record.usage_type == "static final定数定義":
                    const_name = extract_static_final_name(record.code)
                    if const_name:
                        all_records.extend(
                            track_static_final_groovy(const_name, source_dir, record, stats, args.encoding)
                        )
                elif record.usage_type == "変数代入" and is_class_level_field(record.code):
                    field_name_match = re.search(r'(\w+)\s*[=;]', record.code.strip())
                    if field_name_match:
                        fname = field_name_match.group(1)
                        src_file = _resolve_groovy_file(record.filepath, source_dir)
                        if src_file:
                            all_records.extend(
                                track_field_groovy(fname, src_file, record, source_dir, stats, args.encoding)
                            )
                            lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), args.encoding), stats)
                            for g in find_getter_names_groovy(fname, lines):
                                getter_tasks.setdefault(g, []).append(record)
                            for s in find_setter_names_groovy(fname, lines):
                                setter_tasks.setdefault(s, []).append(record)

            all_records.extend(
                _batch_track_getter_setter_groovy(getter_tasks, setter_tasks, source_dir, stats, args.encoding)
            )

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
