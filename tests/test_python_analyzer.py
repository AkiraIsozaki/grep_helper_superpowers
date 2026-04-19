import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_python as ap


class TestClassifyUsagePython(unittest.TestCase):
    def test_assignment(self):
        self.assertEqual(ap.classify_usage_python('STATUS = "TARGET"'), "変数代入")

    def test_indented_assignment(self):
        self.assertEqual(ap.classify_usage_python('    x = STATUS'), "変数代入")

    def test_if_condition(self):
        self.assertEqual(ap.classify_usage_python('if code == STATUS:'), "条件判定")

    def test_elif_condition(self):
        self.assertEqual(ap.classify_usage_python('elif STATUS in values:'), "条件判定")

    def test_return(self):
        self.assertEqual(ap.classify_usage_python('return STATUS'), "return文")

    def test_decorator(self):
        self.assertEqual(ap.classify_usage_python('@property'), "デコレータ")

    def test_function_arg(self):
        self.assertEqual(ap.classify_usage_python('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(ap.classify_usage_python('STATUS'), "その他")


class TestE2EPython(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "python"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        ap._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ap.ProcessStats()
            grep_path = input_dir / "TARGET.grep"

            direct_records = ap.process_grep_file(grep_path, "TARGET", src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            ap.write_tsv(list(direct_records), output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
