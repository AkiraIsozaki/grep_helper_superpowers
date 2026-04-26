import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_python as ap
import analyze_common


class TestClassifyUsagePython(unittest.TestCase):
    def test_単純な変数代入を変数代入と分類する(self):
        """シンボルを右辺に持つ代入文が変数代入と判定されること"""
        self.assertEqual(ap.classify_usage_python('STATUS = "TARGET"'), "変数代入")

    def test_インデント付き代入も変数代入と分類する(self):
        """先頭にインデントがある代入文も変数代入と判定されること"""
        self.assertEqual(ap.classify_usage_python('    x = STATUS'), "変数代入")

    def test_if文の比較式を条件判定と分類する(self):
        """if文の等価比較が条件判定として扱われること"""
        self.assertEqual(ap.classify_usage_python('if code == STATUS:'), "条件判定")

    def test_elif文のin式を条件判定と分類する(self):
        """elif文の包含チェックが条件判定として扱われること"""
        self.assertEqual(ap.classify_usage_python('elif STATUS in values:'), "条件判定")

    def test_return文をreturn文と分類する(self):
        """return文に出現するシンボルがreturn文と判定されること"""
        self.assertEqual(ap.classify_usage_python('return STATUS'), "return文")

    def test_decoratorをデコレータと分類する(self):
        """@で始まる行がデコレータと判定されること"""
        self.assertEqual(ap.classify_usage_python('@property'), "デコレータ")

    def test_関数呼び出しの引数を関数引数と分類する(self):
        """関数呼び出しに渡されたシンボルが関数引数と判定されること"""
        self.assertEqual(ap.classify_usage_python('process(STATUS)'), "関数引数")

    def test_該当しない行はその他と分類する(self):
        """どの分類にも合致しない行がその他と判定されること"""
        self.assertEqual(ap.classify_usage_python('STATUS'), "その他")


class TestE2EPython(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "python"

    def test_TARGETシンボルのE2E解析結果が期待TSVと一致する(self):
        """grep入力からTSVを生成しゴールデンファイルと一致することを検証する"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        analyze_common._file_lines_cache_clear()

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
