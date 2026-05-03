"""KPI ゴールデンセット計測スクリプト。

使い方:
    python scripts/measure_kpi.py --lang java
    python scripts/measure_kpi.py --lang all

詳細は docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md を参照。
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
