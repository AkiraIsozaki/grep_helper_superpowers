import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_ts as at
import analyze_common


class TestClassifyUsageTs(unittest.TestCase):
    def test_const_def(self):
        self.assertEqual(at.classify_usage_ts('const STATUS = "TARGET"'), "const定数定義")

    def test_let_assignment(self):
        self.assertEqual(at.classify_usage_ts('let x = STATUS'), "変数代入(let/var)")

    def test_var_assignment(self):
        self.assertEqual(at.classify_usage_ts('var x = STATUS'), "変数代入(let/var)")

    def test_if_condition(self):
        self.assertEqual(at.classify_usage_ts('if (code === STATUS)'), "条件判定")

    def test_switch_condition(self):
        self.assertEqual(at.classify_usage_ts('switch (STATUS)'), "条件判定")

    def test_return(self):
        self.assertEqual(at.classify_usage_ts('return STATUS'), "return文")

    def test_decorator(self):
        self.assertEqual(at.classify_usage_ts('@Component'), "デコレータ")

    def test_function_arg(self):
        self.assertEqual(at.classify_usage_ts('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(at.classify_usage_ts('STATUS'), "その他")


class TestE2ETs(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "ts"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        analyze_common._file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = at.ProcessStats()
            grep_path = input_dir / "TARGET.grep"

            direct_records = at.process_grep_file(grep_path, "TARGET", src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            at.write_tsv(list(direct_records), output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
