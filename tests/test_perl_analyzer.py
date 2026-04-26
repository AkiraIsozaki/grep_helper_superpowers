import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.perl import classify_usage as classify_usage_perl
from grep_helper.model import ProcessStats
from grep_helper.tsv_output import write_tsv
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import perl as _perl_handler
from grep_helper.file_cache import _file_lines_cache_clear


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _perl_handler, keyword=keyword, stats=stats)


class TestClassifyUsagePerl(unittest.TestCase):
    def test_use_constant定義を分類できる(self):
        """use constant の定義行を「use constant定義」に分類する"""
        self.assertEqual(classify_usage_perl('use constant STATUS => "TARGET";'), "use constant定義")

    def test_スカラー変数への代入を変数代入と判定する(self):
        """裸のスカラー代入を「変数代入」に分類する"""
        self.assertEqual(classify_usage_perl('$code = STATUS;'), "変数代入")

    def test_my宣言付き代入を変数代入と判定する(self):
        """my 宣言を伴う代入を「変数代入」に分類する"""
        self.assertEqual(classify_usage_perl('my $x = STATUS;'), "変数代入")

    def test_our宣言付き代入を変数代入と判定する(self):
        """our 宣言を伴う代入を「変数代入」に分類する"""
        self.assertEqual(classify_usage_perl('our $x = STATUS;'), "変数代入")

    def test_if文の条件式を条件判定と判定する(self):
        """if 文での比較を「条件判定」に分類する"""
        self.assertEqual(classify_usage_perl('if ($code eq STATUS)'), "条件判定")

    def test_unless文の条件式を条件判定と判定する(self):
        """unless 文での比較を「条件判定」に分類する"""
        self.assertEqual(classify_usage_perl('unless ($x == STATUS)'), "条件判定")

    def test_print文をprint_say出力と判定する(self):
        """print 文を「print/say出力」に分類する"""
        self.assertEqual(classify_usage_perl('print STATUS;'), "print/say出力")

    def test_say文をprint_say出力と判定する(self):
        """say 文を「print/say出力」に分類する"""
        self.assertEqual(classify_usage_perl('say STATUS;'), "print/say出力")

    def test_printf文をprint_say出力と判定する(self):
        """printf 文を「print/say出力」に分類する"""
        self.assertEqual(classify_usage_perl('printf "%s", STATUS;'), "print/say出力")

    def test_関数呼び出しの実引数を関数引数と判定する(self):
        """関数呼び出しの引数位置にある利用を「関数引数」に分類する"""
        self.assertEqual(classify_usage_perl('process(STATUS)'), "関数引数")

    def test_該当パターンに合致しない場合はその他と判定する(self):
        """既知パターンに合致しない単独利用を「その他」に分類する"""
        self.assertEqual(classify_usage_perl('STATUS'), "その他")


class TestE2EPerl(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "perl"

    def test_E2EでTARGET定数の解析結果が期待TSVと一致する(self):
        """grep 入力から TARGET 定数を解析した TSV が期待出力と一致することを E2E で検証する"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        _file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ProcessStats()
            grep_path = input_dir / "TARGET.grep"

            direct_records = _process_grep_file(grep_path, "TARGET", src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            write_tsv(list(direct_records), output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
