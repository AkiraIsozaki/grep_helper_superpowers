"""KPI ゴールデンセット計測スクリプト。

使い方:
    python scripts/measure_kpi.py --lang java
    python scripts/measure_kpi.py --lang all

詳細は docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md を参照。
"""
from __future__ import annotations

import argparse
import csv
import datetime
import importlib
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, TypedDict

# プロジェクトルートを sys.path に追加（直接 python scripts/measure_kpi.py 実行に対応）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grep_helper.pipeline import run_full_pipeline  # noqa: E402


class LangSpec(TypedDict):
    """言語仕様の型定義。LangSpec値のキー名をタイプチェック時に検証する。"""
    module: str
    usage_types: list[str]
    min_per_type: int
    reference_kinds_required: list[str]


LANG_SPECS: dict[str, LangSpec] = {
    "java": {
        "module": "grep_helper.languages.java",
        "usage_types": [
            "アノテーション", "定数定義", "変数代入", "条件判定",
            "return文", "メソッド引数", "その他",
        ],
        "min_per_type": 10,  # Java 深堀り
        "reference_kinds_required": [
            "直接", "間接", "間接（getter経由）", "間接（setter経由）",
        ],
    },
    "c": {
        "module": "grep_helper.languages.c",
        "usage_types": [
            "#define定数定義", "条件判定", "return文",
            "変数代入", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "proc": {
        "module": "grep_helper.languages.proc",
        "usage_types": [
            "EXEC SQL文", "#define定数定義", "条件判定", "return文",
            "変数代入", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "sql": {
        "module": "grep_helper.languages.sql",
        "usage_types": [
            "例外・エラー処理", "定数・変数定義", "WHERE条件",
            "比較・DECODE", "INSERT/UPDATE値", "SELECT/INTO", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "sh": {
        "module": "grep_helper.languages.sh",
        "usage_types": [
            "環境変数エクスポート", "変数代入", "条件判定",
            "echo/print出力", "コマンド引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "kotlin": {
        "module": "grep_helper.languages.kotlin",
        "usage_types": [
            "const定数定義", "変数代入", "条件判定", "return文",
            "アノテーション", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "plsql": {
        "module": "grep_helper.languages.plsql",
        "usage_types": [
            "定数/変数宣言", "EXCEPTION処理", "条件判定",
            "カーソル定義", "INSERT/UPDATE値", "WHERE条件", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "ts": {
        "module": "grep_helper.languages.ts",
        "usage_types": [
            "const定数定義", "変数代入(let/var)", "条件判定", "return文",
            "デコレータ", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "python": {
        "module": "grep_helper.languages.python",
        "usage_types": [
            "変数代入", "条件判定", "return文", "デコレータ",
            "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "perl": {
        "module": "grep_helper.languages.perl",
        "usage_types": [
            "use constant定義", "変数代入", "条件判定",
            "print/say出力", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "dotnet": {
        "module": "grep_helper.languages.dotnet",
        "usage_types": [
            "定数定義(Const/readonly)", "変数代入", "条件判定", "return文",
            "属性(Attribute)", "メソッド引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "groovy": {
        "module": "grep_helper.languages.groovy",
        "usage_types": [
            "static final定数定義", "変数代入", "条件判定", "return文",
            "アノテーション", "メソッド引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": [
            "直接", "間接", "間接（getter経由）", "間接（setter経由）",
        ],
    },
}


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

    マッチング基準キー = (filepath, lineno, ref_type)。
    spec §出力フォーマット 比較ロジック の指示に従い、同一 (file, line) に
    複数行（直接 + 間接（setter経由）など）が来ても重複潰しが起きないよう
    ref_type を2次キーに含める。
    網羅率: matched_rows / expected_total
    分類精度: classified_correctly / matched_rows
    """
    expected_by_key: dict[tuple[str, str, str], Record] = {(r.filepath, r.lineno, r.ref_type): r for r in expected}
    actual_by_key: dict[tuple[str, str, str], Record] = {(r.filepath, r.lineno, r.ref_type): r for r in actual}

    matched_keys = expected_by_key.keys() & actual_by_key.keys()
    missing_keys = expected_by_key.keys() - actual_by_key.keys()

    expected_total = len(expected)
    matched_rows = len(matched_keys)

    classified_correctly = 0
    misclassified: list[tuple[Record, Record]] = []
    for key in matched_keys:
        exp = expected_by_key[key]
        act = actual_by_key[key]
        # キーで ref_type は既に一致。残る usage_type のみ比較する。
        if exp.usage_type == act.usage_type:
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


def run(argv: list[str] | None = None) -> int:
    """CLI エントリポイント。

    Returns:
        0: 計測完了（しきい値割れでも 0）
        1: 入力エラー（ディレクトリ欠損、ペアリング不一致、未対応 lang）
        2: 実行時例外
    """
    parser = argparse.ArgumentParser(description="KPI ゴールデンセット計測スクリプト")
    parser.add_argument("--lang", required=True, help="計測対象言語（または all）")
    parser.add_argument("--samples-dir", default="tests/golden", help="ゴールデンセットのルート")
    parser.add_argument("--output-dir", default="output/kpi", help="レポート出力先")
    parser.add_argument("--quiet", action="store_true", help="stdout サマリを抑制")
    args = parser.parse_args(argv)

    samples_dir = Path(args.samples_dir)
    output_dir = Path(args.output_dir)

    if args.lang == "all":
        return _run_all(samples_dir, output_dir, quiet=args.quiet)
    if args.lang not in LANG_SPECS:
        print(f"エラー: 未対応の --lang: {args.lang}", file=sys.stderr)
        return 1

    try:
        return _run_single(args.lang, samples_dir, output_dir, quiet=args.quiet)
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    except Exception:
        print("予期しないエラー:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 2


def _run_single(lang: str, samples_dir: Path, output_dir: Path, *, quiet: bool) -> int:
    """単一言語の KPI 計測。Step 5 (Task 20) で _run_all から呼ばれる形に再利用する。"""
    spec = LANG_SPECS[lang]
    lang_dir = samples_dir / lang
    inputs_dir = lang_dir / "inputs"
    expected_dir = lang_dir / "expected"
    src_dir = lang_dir / "src"

    if not lang_dir.is_dir():
        raise FileNotFoundError(f"言語ディレクトリが存在しません: {lang_dir}")
    if not inputs_dir.is_dir() or not expected_dir.is_dir() or not src_dir.is_dir():
        raise FileNotFoundError(f"inputs/expected/src いずれかが存在しません: {lang_dir}")

    # ペアリング検証
    grep_files = sorted(inputs_dir.glob("*.grep"))
    expected_files = {p.stem for p in expected_dir.glob("*.tsv")}
    actual_stems = {p.stem for p in grep_files}
    if actual_stems != expected_files:
        raise FileNotFoundError(
            f"inputs/expected の対応不一致: only-input={actual_stems - expected_files}, "
            f"only-expected={expected_files - actual_stems}"
        )

    handler = importlib.import_module(spec["module"])

    # 各 grep ファイルを処理
    aggregated = ComparisonResult(
        expected_total=0, matched_rows=0, classified_correctly=0,
        coverage_rate=0.0, classification_accuracy=0.0,
    )
    per_file: list[tuple[str, ComparisonResult]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_full_pipeline(
            source_dir=src_dir,
            input_dir=inputs_dir,
            output_dir=tmp_path,
            handler=handler,
            workers=1,
        )
        for grep_path in grep_files:
            stem = grep_path.stem
            actual = load_actual_tsv(tmp_path / f"{stem}.tsv")
            expected = load_expected_tsv(expected_dir / f"{stem}.tsv")
            res = compare(expected, actual)
            per_file.append((stem, res))
            aggregated.expected_total += res.expected_total
            aggregated.matched_rows += res.matched_rows
            aggregated.classified_correctly += res.classified_correctly
            aggregated.missing_rows.extend(res.missing_rows)
            aggregated.false_positives.extend(res.false_positives)
            aggregated.misclassified.extend(res.misclassified)

    aggregated.coverage_rate = (
        aggregated.matched_rows / aggregated.expected_total
        if aggregated.expected_total > 0 else 1.0
    )
    aggregated.classification_accuracy = (
        aggregated.classified_correctly / aggregated.matched_rows
        if aggregated.matched_rows > 0 else 0.0
    )

    # 分布チェック（全 expected を改めてロード）
    all_expected: list[Record] = []
    for grep_path in grep_files:
        all_expected.extend(load_expected_tsv(expected_dir / f"{grep_path.stem}.tsv"))
    distribution_warnings = assert_coverage_distribution(all_expected, spec)

    # レポート出力
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{lang}-{timestamp}.md"
    report_path.write_text(
        format_detail_report(aggregated, lang=lang, timestamp=timestamp),
        encoding="utf-8",
    )

    if not quiet:
        print(f"=== KPI 計測結果 ({lang}) ===")
        for stem, res in per_file:
            print(f"\n[{stem}.grep]")
            print(format_summary(res))
        print(f"\n=== 合計 ({lang}) ===")
        print(format_summary(aggregated))
        if distribution_warnings:
            print("\nサンプル分布警告:")
            for w in distribution_warnings:
                print(f"  - {w}")
        print(f"\n詳細レポート: {report_path}")

    return 0


def _run_all(samples_dir: Path, output_dir: Path, *, quiet: bool) -> int:
    """全12言語ぶん順次実行。失敗時は続行、最終 exit code は max(0, 1, 2)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_lines: list[str] = [f"# KPI 計測サマリ — {timestamp}", ""]
    summary_lines.append("| 言語 | 状態 | 備考 |")
    summary_lines.append("|---|---|---|")
    final_code = 0

    for lang in LANG_SPECS.keys():
        try:
            code = _run_single(lang, samples_dir, output_dir, quiet=quiet)
            if code == 0:
                summary_lines.append(f"| {lang} | 成功 | (詳細レポート: {lang}-{timestamp}*.md) |")
            else:
                summary_lines.append(f"| {lang} | エラー (exit {code}) | - |")
                final_code = max(final_code, code)
        except FileNotFoundError as e:
            summary_lines.append(f"| {lang} | 未整備 | {e} |")
            if not quiet:
                print(f"[{lang}] 未整備: {e}", file=sys.stderr)
            final_code = max(final_code, 1)
        except Exception as e:
            summary_lines.append(f"| {lang} | 例外 | {type(e).__name__}: {e} |")
            if not quiet:
                print(f"[{lang}] 例外: {type(e).__name__}: {e}", file=sys.stderr)
            final_code = max(final_code, 2)

    summary_path = output_dir / f"_summary-{timestamp}.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    if not quiet:
        print(f"\nサマリレポート: {summary_path}")

    return final_code


if __name__ == "__main__":
    raise SystemExit(run())
