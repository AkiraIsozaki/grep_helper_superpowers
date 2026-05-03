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


if __name__ == "__main__":
    unittest.main()
