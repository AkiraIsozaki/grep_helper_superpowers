"""KPI 計測スクリプト measure_kpi.py の単体テスト。

プロジェクトのテスト方針（古典学派・ブラックボックス起点・WHATを検証・
日本語メソッド名・TDD）に従う。
"""
import sys
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


if __name__ == "__main__":
    unittest.main()
