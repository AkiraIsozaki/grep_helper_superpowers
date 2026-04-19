import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_kotlin as ak


class TestClassifyUsageKotlin(unittest.TestCase):
    def test_const_val(self):
        self.assertEqual(ak.classify_usage_kotlin('const val STATUS = "TARGET"'), "const定数定義")

    def test_val_assignment(self):
        self.assertEqual(ak.classify_usage_kotlin('val code = STATUS'), "変数代入")

    def test_var_assignment(self):
        self.assertEqual(ak.classify_usage_kotlin('var code = STATUS'), "変数代入")

    def test_if_condition(self):
        self.assertEqual(ak.classify_usage_kotlin('if (code == STATUS)'), "条件判定")

    def test_when_condition(self):
        self.assertEqual(ak.classify_usage_kotlin('when (status)'), "条件判定")

    def test_return(self):
        self.assertEqual(ak.classify_usage_kotlin('return STATUS'), "return文")

    def test_annotation(self):
        self.assertEqual(ak.classify_usage_kotlin('@Suppress("unused")'), "アノテーション")

    def test_function_arg(self):
        self.assertEqual(ak.classify_usage_kotlin('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(ak.classify_usage_kotlin('STATUS'), "その他")


class TestExtractConstName(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ak.extract_const_name('const val STATUS = "TARGET"'), "STATUS")

    def test_no_const(self):
        self.assertIsNone(ak.extract_const_name('val code = "TARGET"'))

    def test_no_match(self):
        self.assertIsNone(ak.extract_const_name('if (x == STATUS)'))


class TestTrackConst(unittest.TestCase):
    def test_finds_usages_in_kt_files(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Constants.kt").write_text('const val STATUS = "TARGET"\n')
            (src / "Service.kt").write_text('if (code == STATUS) { return true }\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "Constants.kt"),
                lineno="1",
                code='const val STATUS = "TARGET"',
            )
            stats = ProcessStats()
            ak._file_cache.clear()
            results = ak.track_const("STATUS", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.kt" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_skips_definition_line(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Constants.kt").write_text('const val STATUS = "TARGET"\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "Constants.kt"),
                lineno="1",
                code='const val STATUS = "TARGET"',
            )
            stats = ProcessStats()
            ak._file_cache.clear()
            results = ak.track_const("STATUS", src, record, stats)
            self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
