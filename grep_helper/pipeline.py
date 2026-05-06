"""共通パイプライン: grep行 → handler.classify_usage → GrepRecord 変換。"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

from grep_helper.encoding import detect_encoding
from grep_helper.grep_input import iter_grep_lines, parse_grep_line
from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType


def process_grep_file(
    grep_path: Path,
    src_dir: Path,
    handler: ModuleType,
    *,
    keyword: str | None = None,
    encoding: str | None = None,
    stats: ProcessStats | None = None,
) -> list[GrepRecord]:
    """grep ファイルを 1 本処理し、handler.classify_usage で分類した直接参照レコードを返す。

    handler は ``classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str``
    を持つモジュール（duck typing）。
    """
    if keyword is None:
        keyword = grep_path.stem
    if stats is None:
        stats = ProcessStats()
    enc = detect_encoding(grep_path, encoding)

    records: list[GrepRecord] = []
    for line in iter_grep_lines(grep_path, enc):
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        try:
            lineno_int = int(parsed["lineno"])
        except ValueError:
            lineno_int = 0
        ctx = ClassifyContext(
            filepath=parsed["filepath"],
            lineno=lineno_int,
            source_dir=src_dir,
            stats=stats,
            encoding_override=encoding,
        )
        usage = handler.classify_usage(parsed["code"], ctx=ctx)
        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=usage,
            filepath=parsed["filepath"],
            lineno=parsed["lineno"],
            code=parsed["code"],
        ))
        stats.valid_lines += 1
    return records


def run_full_pipeline(
    source_dir: Path,
    input_dir: Path,
    output_dir: Path,
    handler: ModuleType,
    *,
    encoding: str | None = None,
    workers: int = 1,
    use_mmap: bool = True,
    stats: ProcessStats | None = None,
) -> list[str]:
    """input_dir/*.grep を処理し、output_dir/<stem>.tsv を書き出す（in-process 完全版）。

    3 フェーズ:
      1. 全 grep ファイルの直接分類を先に終わらせる
      2. ハンドラの間接追跡を 1 回だけ呼ぶ
      3. 戻り値を keyword で振り分けて TSV 出力

    Returns: 処理した grep ファイル名のリスト（出力 TSV を実際に書いたもののみ）。
    """
    import sys as _sys  # noqa: PLC0415

    from grep_helper.tsv_output import write_tsv  # noqa: PLC0415

    if stats is None:
        stats = ProcessStats()

    output_dir.mkdir(parents=True, exist_ok=True)

    grep_files = sorted(input_dir.glob("*.grep"))
    direct_by_keyword: dict[str, list[GrepRecord]] = {}
    processed_files: list[str] = []

    # フェーズ 1: 直接分類（個別 grep の例外は他に巻き込まない）
    for grep_path in grep_files:
        keyword = grep_path.stem
        try:
            direct = process_grep_file(
                grep_path, source_dir, handler,
                keyword=keyword, encoding=encoding, stats=stats,
            )
        except Exception as exc:
            print(
                f"  警告: {grep_path.name} の直接分類で例外 ({exc!r}) - スキップして継続",
                file=_sys.stderr, flush=True,
            )
            continue
        direct_by_keyword[keyword] = direct
        processed_files.append(grep_path.name)

    if not direct_by_keyword:
        return processed_files

    # フェーズ 2: 間接追跡を 1 回だけ
    indirect_fn = getattr(handler, "batch_track_indirect", None)
    indirect_by_keyword: dict[str, list[GrepRecord]] = {}
    if indirect_fn is not None:
        all_direct: list[GrepRecord] = []
        for records in direct_by_keyword.values():
            all_direct.extend(records)
        indirect_all = indirect_fn(
            all_direct, source_dir, encoding,
            workers=workers, use_mmap=use_mmap,
        )
        for rec in indirect_all:
            indirect_by_keyword.setdefault(rec.keyword, []).append(rec)

    # フェーズ 3: keyword で振り分けて TSV 出力
    for keyword, direct_records in direct_by_keyword.items():
        indirect_records = indirect_by_keyword.get(keyword, [])
        all_records = list(direct_records) + list(indirect_records)
        output_path = output_dir / f"{keyword}.tsv"
        write_tsv(all_records, output_path)

    return processed_files
