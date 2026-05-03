"""KPI 計測スクリプト measure_kpi.py の単体テスト。

プロジェクトのテスト方針（古典学派・ブラックボックス起点・WHATを検証・
日本語メソッド名・TDD）に従う。
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# scripts/ を import path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import measure_kpi


class TestRecord(unittest.TestCase):
    """Record は期待TSV / actual TSV をパースしたあとの軽量レコード。"""

    def test_Recordは9カラムの値を保持する(self):
        r = measure_kpi.Record(
            keyword="K", ref_type="直接", usage_type="その他",
            filepath="f.sql", lineno="1", code="c",
            src_var="", src_file="", src_lineno="",
        )
        self.assertEqual(r.keyword, "K")
        self.assertEqual(r.lineno, "1")
        self.assertEqual(r.src_var, "")


class TestComparisonResult(unittest.TestCase):
    """ComparisonResult は KPI 値と diff 詳細を持つ。"""

    def test_空のresultは網羅率も精度も0で初期化される(self):
        result = measure_kpi.ComparisonResult(
            expected_total=0, matched_rows=0, classified_correctly=0,
            coverage_rate=0.0, classification_accuracy=0.0,
            missing_rows=[], false_positives=[], misclassified=[], detail_diffs=[],
        )
        self.assertEqual(result.expected_total, 0)
        self.assertEqual(result.coverage_rate, 0.0)


class TestLoadTsv(unittest.TestCase):
    """load_expected_tsv / load_actual_tsv は UTF-8 BOM 付きタブ区切り TSV をパースする。"""

    def _write_tsv(self, path: Path, rows: list[list[str]]) -> None:
        headers = ["文言", "参照種別", "使用タイプ", "ファイルパス", "行番号", "コード行",
                   "参照元変数名", "参照元ファイル", "参照元行番号"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(headers)
            for r in rows:
                w.writerow(r)

    def test_BOM付きTSVをパースしてRecord列を返す(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.tsv"
            self._write_tsv(p, [
                ["K", "直接", "その他", "f.sql", "10", "code1", "", "", ""],
                ["K", "間接", "条件判定", "g.sql", "20", "code2", "V", "f.sql", "10"],
            ])
            records = measure_kpi.load_expected_tsv(p)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].keyword, "K")
            self.assertEqual(records[0].lineno, "10")
            self.assertEqual(records[1].src_var, "V")

    def test_空ファイルヘッダのみは空リストを返す(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.tsv"
            self._write_tsv(p, [])
            records = measure_kpi.load_expected_tsv(p)
            self.assertEqual(records, [])

    def test_load_actual_tsvもload_expected_tsvと同じ動作(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.tsv"
            self._write_tsv(p, [["K", "直接", "その他", "f.sql", "1", "c", "", "", ""]])
            self.assertEqual(
                measure_kpi.load_actual_tsv(p),
                measure_kpi.load_expected_tsv(p),
            )


def _rec(filepath: str, lineno: str, ref_type: str = "直接", usage: str = "その他", keyword: str = "K") -> "measure_kpi.Record":
    return measure_kpi.Record(
        keyword=keyword, ref_type=ref_type, usage_type=usage,
        filepath=filepath, lineno=lineno, code="c",
    )


class TestCompareCoverage(unittest.TestCase):
    """compare() の網羅率: (file, line) ベースで expected が actual に含まれる割合。"""

    def test_完全一致なら網羅率は1_0(self):
        expected = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        actual = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertEqual(result.matched_rows, 2)

    def test_片方だけ取りこぼすと網羅率は0_5(self):
        expected = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        actual = [_rec("f.sql", "1")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 0.5)
        self.assertEqual(result.matched_rows, 1)
        self.assertEqual(len(result.missing_rows), 1)
        self.assertEqual(result.missing_rows[0].lineno, "2")


class TestCompareClassificationAccuracy(unittest.TestCase):
    """compare() の分類精度: matched 行のうち (参照種別, 使用タイプ) も一致する割合。"""

    def test_全行で分類が一致すると精度は1_0(self):
        expected = [_rec("f.sql", "1", ref_type="直接", usage="定数定義")]
        actual = [_rec("f.sql", "1", ref_type="直接", usage="定数定義")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.classification_accuracy, 1.0)
        self.assertEqual(result.classified_correctly, 1)

    def test_使用タイプが違うと誤分類として記録される(self):
        expected = [_rec("f.sql", "1", usage="定数定義"), _rec("f.sql", "2", usage="条件判定")]
        actual = [_rec("f.sql", "1", usage="定数定義"), _rec("f.sql", "2", usage="その他")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.classification_accuracy, 0.5)
        self.assertEqual(len(result.misclassified), 1)
        exp_rec, act_rec = result.misclassified[0]
        self.assertEqual(exp_rec.usage_type, "条件判定")
        self.assertEqual(act_rec.usage_type, "その他")

    def test_参照種別が違うと誤分類として記録される(self):
        expected = [_rec("f.sql", "1", ref_type="直接")]
        actual = [_rec("f.sql", "1", ref_type="間接")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.classification_accuracy, 0.0)
        self.assertEqual(len(result.misclassified), 1)


class TestCompareFalsePositive(unittest.TestCase):
    """compare() の FP: actual のみに存在する行は false_positives に入る（KPI不算入）。"""

    def test_actualのみに存在する行はfalse_positivesに入る(self):
        expected = [_rec("f.sql", "1")]
        actual = [_rec("f.sql", "1"), _rec("g.sql", "5")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(len(result.false_positives), 1)
        self.assertEqual(result.false_positives[0].filepath, "g.sql")

    def test_FP件数は網羅率と分類精度に影響しない(self):
        expected = [_rec("f.sql", "1")]
        actual = [_rec("f.sql", "1"), _rec("g.sql", "5"), _rec("h.sql", "9")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertEqual(result.classification_accuracy, 1.0)
        self.assertEqual(len(result.false_positives), 2)


class TestCompareEdgeCases(unittest.TestCase):
    """compare() のゼロ除算エッジケース。spec §ゼロ除算エッジケース に準拠。"""

    def test_期待TSVが空なら網羅率は1_0扱い(self):
        result = measure_kpi.compare([], [])
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertEqual(result.expected_total, 0)

    def test_全件取りこぼしなら網羅率も精度も0_0(self):
        expected = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        actual = []
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 0.0)
        self.assertEqual(result.classification_accuracy, 0.0)
        self.assertEqual(result.matched_rows, 0)


if __name__ == "__main__":
    unittest.main()
