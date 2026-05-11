"""TSV 出力（外部ソート対応）。"""
from __future__ import annotations

import csv
import heapq
import tempfile
from pathlib import Path

from grep_helper.model import GrepRecord

_TSV_HEADERS = [
    "文言", "参照種別", "使用タイプ", "ファイルパス", "行番号", "コード行",
    "参照元変数名", "参照元ファイル", "参照元行番号",
]

_EXTERNAL_SORT_THRESHOLD = 1_000_000


def write_tsv(records: list[GrepRecord], output_path: Path) -> None:
    """GrepRecordのリストをUTF-8 BOM付きTSVに出力する（ソート済み）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _sort_key(r: GrepRecord) -> tuple:
        """GrepRecord を決定的に並べるためのキー。tie を避けるため 5 タプル。"""
        lineno_int = int(r.lineno) if r.lineno.isdigit() else 0
        return (r.keyword, r.filepath, lineno_int, r.ref_type, r.usage_type)

    def _row_sort_key(row: list[str]) -> tuple:
        """外部マージソート用の行キー。_sort_key と同じ並び。"""
        lineno_int = int(row[4]) if row[4].isdigit() else 0
        # 列順: 0=keyword, 1=ref_type, 2=usage_type, 3=filepath, 4=lineno
        return (row[0], row[3], lineno_int, row[1], row[2])

    if len(records) < _EXTERNAL_SORT_THRESHOLD:
        records.sort(key=_sort_key)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(_TSV_HEADERS)
            for r in records:
                writer.writerow([
                    r.keyword, r.ref_type, r.usage_type, r.filepath,
                    r.lineno, r.code, r.src_var, r.src_file, r.src_lineno,
                ])
        return

    _CHUNK_SIZE = 500_000
    tmp_paths: list[Path] = []
    tmp_dir = output_path.parent
    try:
        for i in range(0, len(records), _CHUNK_SIZE):
            chunk = records[i:i + _CHUNK_SIZE]
            chunk.sort(key=_sort_key)
            fd, tmp_str = tempfile.mkstemp(
                suffix=".tmp", prefix=f".{output_path.stem}_chunk_", dir=tmp_dir,
            )
            tmp_path = Path(tmp_str)
            tmp_paths.append(tmp_path)
            with open(fd, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, delimiter="\t")
                for r in chunk:
                    w.writerow([
                        r.keyword, r.ref_type, r.usage_type, r.filepath,
                        r.lineno, r.code, r.src_var, r.src_file, r.src_lineno,
                    ])
            del chunk
        del records
        handles = [open(p, encoding="utf-8", newline="") for p in tmp_paths]
        readers = [csv.reader(h, delimiter="\t") for h in handles]
        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(_TSV_HEADERS)
                for row in heapq.merge(*readers, key=_row_sort_key):
                    writer.writerow(row)
        finally:
            for h in handles:
                h.close()
    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)
