"""tsv_output の決定的ソート 5 タプル化テスト。"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.model import GrepRecord, RefType
from grep_helper.tsv_output import write_tsv


class TestWriteTsvDeterministicOrder(unittest.TestCase):
    """同一 (keyword, filepath, lineno) で複数 ref_type / usage_type が出るとき、
    アルファベット順で決定的に並ぶ。
    """

    def _read_rows(self, path: Path) -> list[list[str]]:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader)  # ヘッダ
            return list(reader)

    def test_同一file_line_で複数ref_typeがあるとref_type順に並ぶ(self):
        records = [
            GrepRecord(keyword="K", ref_type=RefType.SETTER.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="x"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "K.tsv"
            write_tsv(records, out)
            rows = self._read_rows(out)
            self.assertEqual(len(rows), 2)
            # 同じ入力を 2 回ソートしても順序が変わらない (決定性)
            with tempfile.TemporaryDirectory() as tmp2:
                out2 = Path(tmp2) / "K.tsv"
                write_tsv(list(reversed(records)), out2)
                rows2 = self._read_rows(out2)
                self.assertEqual(rows, rows2)

    def test_同一file_line_ref_typeで複数usage_typeがあるとusage_type順に並ぶ(self):
        records = [
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UB",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="y"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "K.tsv"
            write_tsv(records, out)
            rows = self._read_rows(out)
            self.assertEqual([r[2] for r in rows], ["UA", "UB"])

    def test_異なる挿入順で書き出しても結果TSVがバイト一致する(self):
        base = [
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.SETTER.value, usage_type="UB",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.GETTER.value, usage_type="UA",
                       filepath="b.java", lineno="5", code="y"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            write_tsv(list(base), t / "a.tsv")
            write_tsv(list(reversed(base)), t / "b.tsv")
            self.assertEqual((t / "a.tsv").read_bytes(), (t / "b.tsv").read_bytes())


if __name__ == "__main__":
    unittest.main()
