import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_kotlin as ak
import analyze_common


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
            analyze_common._file_lines_cache_clear()
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
            analyze_common._file_lines_cache_clear()
            results = ak.track_const("STATUS", src, record, stats)
            self.assertEqual(results, [])


class TestE2EKotlin(unittest.TestCase):
    """E2E統合テスト: Kotlin フィクスチャでツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "kotlin"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        analyze_common._file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ak.ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = ak.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "const定数定義":
                    const_name = ak.extract_const_name(record.code)
                    if const_name:
                        all_records.extend(ak.track_const(const_name, src_dir, record, stats))

            output_path = output_dir / "TARGET.tsv"
            ak.write_tsv(all_records, output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


if __name__ == "__main__":
    unittest.main()
