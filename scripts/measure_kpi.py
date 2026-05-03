"""KPI ゴールデンセット計測スクリプト。

使い方:
    python scripts/measure_kpi.py --lang java
    python scripts/measure_kpi.py --lang all

詳細は docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md を参照。
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple


class Record(NamedTuple):
    """期待TSV / actual TSV からロードしたレコード（grep_helper.model.GrepRecord 互換の9カラム）。"""
    keyword:    str
    ref_type:   str
    usage_type: str
    filepath:   str
    lineno:     str
    code:       str
    src_var:    str = ""
    src_file:   str = ""
    src_lineno: str = ""


@dataclass
class ComparisonResult:
    """compare() の出力。KPI 値と diff 詳細を保持する。"""
    expected_total: int
    matched_rows: int
    classified_correctly: int
    coverage_rate: float
    classification_accuracy: float
    missing_rows: list[Record] = field(default_factory=list)
    false_positives: list[Record] = field(default_factory=list)
    misclassified: list[tuple[Record, Record]] = field(default_factory=list)
    detail_diffs: list[tuple[Record, Record]] = field(default_factory=list)


def load_expected_tsv(path: Path) -> list[Record]:
    """期待TSV をパースして Record 列を返す。UTF-8 BOM・タブ区切り・9カラム。"""
    return _load_tsv(path)


def load_actual_tsv(path: Path) -> list[Record]:
    """actual TSV をパースして Record 列を返す。スキーマは expected と同じ。"""
    return _load_tsv(path)


def _load_tsv(path: Path) -> list[Record]:
    records: list[Record] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader, None)  # ヘッダをスキップ
        for row in reader:
            # 9カラム未満ならパディング
            padded = list(row) + [""] * max(0, 9 - len(row))
            records.append(Record(
                keyword=padded[0],
                ref_type=padded[1],
                usage_type=padded[2],
                filepath=padded[3],
                lineno=padded[4],
                code=padded[5],
                src_var=padded[6],
                src_file=padded[7],
                src_lineno=padded[8],
            ))
    return records


def compare(expected: list[Record], actual: list[Record]) -> ComparisonResult:
    """expected と actual を突合し、網羅率・分類精度・diff を算出する。

    マッチング基準キー = (filepath, lineno)。
    網羅率: matched_rows / expected_total
    分類精度: classified_correctly / matched_rows
    """
    expected_by_key: dict[tuple[str, str], Record] = {(r.filepath, r.lineno): r for r in expected}
    actual_by_key: dict[tuple[str, str], Record] = {(r.filepath, r.lineno): r for r in actual}

    matched_keys = expected_by_key.keys() & actual_by_key.keys()
    missing_keys = expected_by_key.keys() - actual_by_key.keys()

    expected_total = len(expected)
    matched_rows = len(matched_keys)

    classified_correctly = 0
    misclassified: list[tuple[Record, Record]] = []
    for key in matched_keys:
        exp = expected_by_key[key]
        act = actual_by_key[key]
        if exp.ref_type == act.ref_type and exp.usage_type == act.usage_type:
            classified_correctly += 1
        else:
            misclassified.append((exp, act))

    fp_keys = actual_by_key.keys() - expected_by_key.keys()
    false_positives = [actual_by_key[k] for k in fp_keys]

    coverage_rate = matched_rows / expected_total if expected_total > 0 else 1.0
    classification_accuracy = (
        classified_correctly / matched_rows if matched_rows > 0 else 0.0
    )

    return ComparisonResult(
        expected_total=expected_total,
        matched_rows=matched_rows,
        classified_correctly=classified_correctly,
        coverage_rate=coverage_rate,
        classification_accuracy=classification_accuracy,
        missing_rows=[expected_by_key[k] for k in missing_keys],
        false_positives=false_positives,
        misclassified=misclassified,
        detail_diffs=[],  # Task 9
    )
