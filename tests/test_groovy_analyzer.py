import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_groovy as ag
import analyze_common


class TestClassifyUsageGroovy(unittest.TestCase):
    def test_static_final(self):
        self.assertEqual(ag.classify_usage_groovy('static final String STATUS = "TARGET"'), "static final定数定義")

    def test_def_assignment(self):
        self.assertEqual(ag.classify_usage_groovy('def code = STATUS'), "変数代入")

    def test_typed_assignment(self):
        self.assertEqual(ag.classify_usage_groovy('String x = STATUS'), "変数代入")

    def test_if_condition(self):
        self.assertEqual(ag.classify_usage_groovy('if (code == STATUS)'), "条件判定")

    def test_switch_condition(self):
        self.assertEqual(ag.classify_usage_groovy('switch (STATUS)'), "条件判定")

    def test_return(self):
        self.assertEqual(ag.classify_usage_groovy('return STATUS'), "return文")

    def test_annotation(self):
        self.assertEqual(ag.classify_usage_groovy('@Canonical'), "アノテーション")

    def test_method_arg(self):
        self.assertEqual(ag.classify_usage_groovy('process(STATUS)'), "メソッド引数")

    def test_other(self):
        self.assertEqual(ag.classify_usage_groovy('STATUS'), "その他")


class TestExtractStaticFinalName(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ag.extract_static_final_name('static final String STATUS = "TARGET"'), "STATUS")

    def test_with_access_modifier(self):
        self.assertEqual(ag.extract_static_final_name('public static final String CODE = "TARGET"'), "CODE")

    def test_no_match(self):
        self.assertIsNone(ag.extract_static_final_name('def x = STATUS'))


class TestIsClassLevelField(unittest.TestCase):
    def test_private_field(self):
        self.assertTrue(ag.is_class_level_field('private String type = STATUS'))

    def test_protected_field(self):
        self.assertTrue(ag.is_class_level_field('protected int count = 0'))

    def test_public_field(self):
        self.assertTrue(ag.is_class_level_field('public String name = "x"'))

    def test_def_field(self):
        self.assertTrue(ag.is_class_level_field('def code = STATUS'))

    def test_local_var_not_field(self):
        self.assertFalse(ag.is_class_level_field('    def code = STATUS'))


class TestFindGetterNamesGroovy(unittest.TestCase):
    def test_convention(self):
        names = ag.find_getter_names_groovy("type", [
            "String getType() {",
            "    return this.type",
            "}",
        ])
        self.assertIn("getType", names)

    def test_non_standard_getter(self):
        names = ag.find_getter_names_groovy("type", [
            "String fetchType() {",
            "    return type",
            "}",
        ])
        self.assertIn("fetchType", names)


class TestFindSetterNamesGroovy(unittest.TestCase):
    def test_convention(self):
        names = ag.find_setter_names_groovy("type", [
            "void setType(String v) {",
            "    this.type = v",
            "}",
        ])
        self.assertIn("setType", names)

    def test_non_standard_setter(self):
        names = ag.find_setter_names_groovy("type", [
            "void assignType(String v) {",
            "    type = v",
            "}",
        ])
        self.assertIn("assignType", names)


class TestTrackStaticFinalGroovy(unittest.TestCase):
    def test_finds_usages_in_groovy_files(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Codes.groovy").write_text('static final String STATUS = "TARGET"\n')
            (src / "Service.groovy").write_text('if (code == STATUS) { return }\n')
            from analyze_common import GrepRecord, ProcessStats, RefType
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="static final定数定義",
                filepath=str(src / "Codes.groovy"),
                lineno="1",
                code='static final String STATUS = "TARGET"',
            )
            stats = ProcessStats()
            analyze_common._file_lines_cache_clear()
            results = ag.track_static_final_groovy("STATUS", src, record, stats)
            self.assertTrue(any("Service.groovy" in r.filepath for r in results))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))


class TestE2EGroovy(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "groovy"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        analyze_common._file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ag.ProcessStats()
            grep_path = input_dir / "TARGET.grep"
            keyword = "TARGET"

            direct_records = ag.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "static final定数定義":
                    const_name = ag.extract_static_final_name(record.code)
                    if const_name:
                        all_records.extend(ag.track_static_final_groovy(const_name, src_dir, record, stats))

            output_path = output_dir / "TARGET.tsv"
            ag.write_tsv(all_records, output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
