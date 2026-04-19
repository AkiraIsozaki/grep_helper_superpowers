import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_dotnet as ad


class TestClassifyUsageDotnet(unittest.TestCase):
    def test_cs_const(self):
        self.assertEqual(ad.classify_usage_dotnet('public const string STATUS = "TARGET";'), "定数定義(Const/readonly)")

    def test_cs_readonly(self):
        self.assertEqual(ad.classify_usage_dotnet('public static readonly string ALIAS = STATUS;'), "定数定義(Const/readonly)")

    def test_vb_const(self):
        self.assertEqual(ad.classify_usage_dotnet('Const STATUS As String = "TARGET"'), "定数定義(Const/readonly)")

    def test_cs_var_assignment(self):
        self.assertEqual(ad.classify_usage_dotnet('string code = STATUS;'), "変数代入")

    def test_cs_var_keyword(self):
        self.assertEqual(ad.classify_usage_dotnet('var x = STATUS;'), "変数代入")

    def test_vb_dim(self):
        self.assertEqual(ad.classify_usage_dotnet('Dim x As String = STATUS'), "変数代入")

    def test_cs_if(self):
        self.assertEqual(ad.classify_usage_dotnet('if (code == STATUS)'), "条件判定")

    def test_vb_if(self):
        self.assertEqual(ad.classify_usage_dotnet('If code = STATUS Then'), "条件判定")

    def test_cs_return(self):
        self.assertEqual(ad.classify_usage_dotnet('return STATUS;'), "return文")

    def test_vb_return(self):
        self.assertEqual(ad.classify_usage_dotnet('Return STATUS'), "return文")

    def test_cs_attribute(self):
        self.assertEqual(ad.classify_usage_dotnet('[Obsolete]'), "属性(Attribute)")

    def test_vb_attribute(self):
        self.assertEqual(ad.classify_usage_dotnet('<Serializable>'), "属性(Attribute)")

    def test_method_arg(self):
        self.assertEqual(ad.classify_usage_dotnet('Process(STATUS)'), "メソッド引数")

    def test_other(self):
        self.assertEqual(ad.classify_usage_dotnet('STATUS'), "その他")


class TestExtractConstNameDotnet(unittest.TestCase):
    def test_cs_const(self):
        self.assertEqual(ad.extract_const_name_dotnet('public const string STATUS = "TARGET";'), "STATUS")

    def test_cs_public_static_readonly(self):
        self.assertEqual(ad.extract_const_name_dotnet('public static readonly string ALIAS = STATUS;'), "ALIAS")

    def test_cs_private_static_readonly(self):
        self.assertEqual(ad.extract_const_name_dotnet('private static readonly int COUNT = 1;'), "COUNT")

    def test_vb_const(self):
        self.assertEqual(ad.extract_const_name_dotnet('Const STATUS As String = "TARGET"'), "STATUS")

    def test_no_match(self):
        self.assertIsNone(ad.extract_const_name_dotnet('string x = STATUS;'))


class TestTrackConstDotnet(unittest.TestCase):
    def test_finds_usages_in_cs_and_vb(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Codes.cs").write_text('public const string STATUS = "TARGET";\n')
            (src / "Service.cs").write_text('if (code == STATUS) { return; }\n')
            (src / "Module.vb").write_text('Dim x As String = STATUS\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="定数定義(Const/readonly)",
                filepath=str(src / "Codes.cs"),
                lineno="1",
                code='public const string STATUS = "TARGET";',
            )
            stats = ProcessStats()
            ad._file_cache.clear()
            results = ad.track_const_dotnet("STATUS", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.cs" in fp for fp in filepaths))
            self.assertTrue(any("Module.vb" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_skips_definition_line(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Codes.cs").write_text('public const string STATUS = "TARGET";\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="定数定義(Const/readonly)",
                filepath=str(src / "Codes.cs"),
                lineno="1",
                code='public const string STATUS = "TARGET";',
            )
            stats = ProcessStats()
            ad._file_cache.clear()
            results = ad.track_const_dotnet("STATUS", src, record, stats)
            self.assertEqual(results, [])


class TestE2EDotnet(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "dotnet"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        ad._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ad.ProcessStats()
            grep_path = input_dir / "TARGET.grep"
            keyword = "TARGET"

            direct_records = ad.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "定数定義(Const/readonly)":
                    const_name = ad.extract_const_name_dotnet(record.code)
                    if const_name:
                        all_records.extend(ad.track_const_dotnet(const_name, src_dir, record, stats))

            output_path = output_dir / "TARGET.tsv"
            ad.write_tsv(all_records, output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
