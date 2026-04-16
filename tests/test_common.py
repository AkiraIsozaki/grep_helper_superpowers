import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv
import tempfile, csv

class TestCommonImports(unittest.TestCase):
    def test_grep_record_fields(self):
        r = GrepRecord("kw", "直接", "その他", "f.sql", "1", "code")
        self.assertEqual(r.keyword, "kw")
        self.assertEqual(r.src_var, "")

    def test_parse_grep_line_valid(self):
        result = parse_grep_line("src/sample.sql:10:WHERE code = 'A';")
        self.assertEqual(result["filepath"], "src/sample.sql")
        self.assertEqual(result["lineno"], "10")
        self.assertEqual(result["code"], "WHERE code = 'A';")

    def test_parse_grep_line_binary(self):
        self.assertIsNone(parse_grep_line("Binary file ./obj/sample.o matches"))

    def test_write_tsv_creates_bom(self):
        records = [GrepRecord("K", "直接", "その他", "f.sql", "1", "code")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            write_tsv(records, out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))

    def test_write_tsv_sort_direct_before_indirect(self):
        records = [
            GrepRecord("K", "間接", "その他", "b.sql", "5", "c",
                       src_var="V", src_file="a.sql", src_lineno="2"),
            GrepRecord("K", "直接", "その他", "a.sql", "2", "c"),
        ]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            write_tsv(records, out)
            with open(out, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter="\t"))[1:]
            self.assertEqual(rows[0][1], "直接")
            self.assertEqual(rows[1][1], "間接")

if __name__ == "__main__":
    unittest.main()
