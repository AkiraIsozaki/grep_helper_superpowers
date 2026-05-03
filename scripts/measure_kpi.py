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


def assert_coverage_distribution(records: list[Record], lang_spec: dict) -> list[str]:
    """ゴールデンセットが lang_spec の網羅要件を満たすか検証し、警告メッセージ列を返す。

    Args:
        records:    期待TSV からロードしたレコード列
        lang_spec:  {"usage_types": [...], "min_per_type": int, "reference_kinds_required": [...]}

    Returns: 警告文字列のリスト。空なら OK。
    """
    warnings: list[str] = []
    usage_types = lang_spec["usage_types"]
    min_per_type = lang_spec["min_per_type"]
    ref_kinds = lang_spec["reference_kinds_required"]

    # 使用タイプの件数チェック
    counts: dict[str, int] = {ut: 0 for ut in usage_types}
    for r in records:
        if r.usage_type in counts:
            counts[r.usage_type] += 1
    for ut, c in counts.items():
        if c < min_per_type:
            warnings.append(
                f"使用タイプ「{ut}」: {c} 件 (要 {min_per_type} 件以上)"
            )

    # 参照種別の存在チェック
    seen_kinds = {r.ref_type for r in records}
    for kind in ref_kinds:
        if kind not in seen_kinds:
            warnings.append(f"参照種別「{kind}」のサンプルが1件もない")

    return warnings


# しきい値定数（spec §出力フォーマット 参照）
COVERAGE_THRESHOLD = 1.0
ACCURACY_THRESHOLD = 0.9


def format_summary(result: ComparisonResult) -> str:
    """ComparisonResult から stdout 用の短いサマリ文字列を生成する。
    完全一致のスナップショットは取らず、主要数値の存在で検証される設計。
    """
    cov_pct = result.coverage_rate * 100
    acc_pct = result.classification_accuracy * 100
    cov_label = "OK" if result.coverage_rate >= COVERAGE_THRESHOLD else "WARN"
    acc_label = "OK" if result.classification_accuracy >= ACCURACY_THRESHOLD else "WARN"

    lines = [
        f"網羅率: {result.matched_rows}/{result.expected_total} ({cov_pct:.1f}%) [{cov_label}]",
        f"分類精度: {result.classified_correctly}/{result.matched_rows} ({acc_pct:.1f}%) [{acc_label}]",
        f"false positive: {len(result.false_positives)}件 (KPI算入なし)",
    ]
    if result.missing_rows:
        lines.append(f"取りこぼし: {len(result.missing_rows)}件")
    if result.misclassified:
        lines.append(f"誤分類: {len(result.misclassified)}件")
    return "\n".join(lines)


def format_detail_report(result: ComparisonResult, *, lang: str = "", timestamp: str = "") -> str:
    """Markdown 詳細レポートを生成する。spec §詳細レポート の章構成に準拠。"""
    header = f"# KPI 計測レポート"
    if lang:
        header += f" ({lang})"
    if timestamp:
        header += f" — {timestamp}"

    parts = [header, "", "## サマリ", "", format_summary(result), ""]

    parts.append("## 取りこぼし行（網羅率を下げている要因）")
    if result.missing_rows:
        parts.append("| ファイルパス | 行番号 | 期待コード行 | 期待使用タイプ |")
        parts.append("|---|---|---|---|")
        for r in result.missing_rows:
            parts.append(f"| {r.filepath} | {r.lineno} | {r.code} | {r.usage_type} |")
    else:
        parts.append("（なし）")
    parts.append("")

    parts.append("## 誤分類行（分類精度を下げている要因）")
    if result.misclassified:
        parts.append("| ファイル | 行 | 期待 | 実際 |")
        parts.append("|---|---|---|---|")
        for exp, act in result.misclassified:
            parts.append(f"| {exp.filepath} | {exp.lineno} | {exp.ref_type}/{exp.usage_type} | {act.ref_type}/{act.usage_type} |")
    else:
        parts.append("（なし）")
    parts.append("")

    parts.append("## false positive（参考、KPI算入なし）")
    if result.false_positives:
        parts.append("| ファイル | 行 | 実際の使用タイプ |")
        parts.append("|---|---|---|")
        for r in result.false_positives:
            parts.append(f"| {r.filepath} | {r.lineno} | {r.usage_type} |")
    else:
        parts.append("（なし）")

    return "\n".join(parts) + "\n"
