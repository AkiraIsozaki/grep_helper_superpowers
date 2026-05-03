import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.ts import classify_usage as classify_usage_ts
from grep_helper.model import ProcessStats
from grep_helper.tsv_output import write_tsv
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import ts as _ts_handler
from grep_helper.file_cache import _file_lines_cache_clear


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _ts_handler, keyword=keyword, stats=stats)


class TestClassifyUsageTs(unittest.TestCase):
    """TestClassifyUsageTs: classify_usage(ts) の分類ラベル返り値を観察するテスト。
    E2E (TestE2ETs) は関数引数/const定数定義のみ通過するため、
    変数代入/条件判定/return文/デコレータ/その他 の分岐は本クラスでのみ保証される。
    """

    def test_const定数定義として分類されること(self):
        self.assertEqual(classify_usage_ts('const STATUS = "TARGET"'), "const定数定義")

    def test_let宣言は変数代入として分類されること(self):
        self.assertEqual(classify_usage_ts('let x = STATUS'), "変数代入(let/var)")

    def test_var宣言は変数代入として分類されること(self):
        self.assertEqual(classify_usage_ts('var x = STATUS'), "変数代入(let/var)")

    def test_if文の比較は条件判定として分類されること(self):
        self.assertEqual(classify_usage_ts('if (code === STATUS)'), "条件判定")

    def test_switch文は条件判定として分類されること(self):
        self.assertEqual(classify_usage_ts('switch (STATUS)'), "条件判定")

    def test_return文として分類されること(self):
        self.assertEqual(classify_usage_ts('return STATUS'), "return文")

    def test_デコレータ記法が分類されること(self):
        self.assertEqual(classify_usage_ts('@Component'), "デコレータ")

    def test_関数呼び出しの引数として分類されること(self):
        self.assertEqual(classify_usage_ts('process(STATUS)'), "関数引数")

    def test_該当しない行はその他として分類されること(self):
        self.assertEqual(classify_usage_ts('STATUS'), "その他")


class TestE2ETs(unittest.TestCase):
    """TestE2ETs: process_grep_file → write_tsv の TypeScript 経路全体の TSV 出力を観察するテスト。
    grep 行パース・分類・TSV 整形を含む統合経路の回帰検出を担う。
    """

    TESTS_DIR = Path(__file__).parent / "ts"

    def test_TARGETに対するE2E解析結果が期待TSVと一致すること(self):
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
