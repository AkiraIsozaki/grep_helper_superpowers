import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_groovy as ag
import analyze_common


class TestClassifyUsageGroovy(unittest.TestCase):
    def test_static_final定数定義を分類できる(self):
        """static final宣言を「static final定数定義」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('static final String STATUS = "TARGET"'), "static final定数定義")

    def test_def宣言による変数代入を分類できる(self):
        """def宣言での代入を「変数代入」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('def code = STATUS'), "変数代入")

    def test_型付き変数代入を分類できる(self):
        """型付き変数（String x = ...）の代入を「変数代入」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('String x = STATUS'), "変数代入")

    def test_if文の条件式を分類できる(self):
        """if文での比較を「条件判定」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('if (code == STATUS)'), "条件判定")

    def test_switch文の条件式を分類できる(self):
        """switch文の条件を「条件判定」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('switch (STATUS)'), "条件判定")

    def test_return文を分類できる(self):
        """return文を「return文」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('return STATUS'), "return文")

    def test_アノテーションを分類できる(self):
        """@で始まるアノテーションを「アノテーション」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('@Canonical'), "アノテーション")

    def test_メソッド引数としての利用を分類できる(self):
        """メソッド呼び出しの引数を「メソッド引数」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('process(STATUS)'), "メソッド引数")

    def test_該当しない場合はその他に分類する(self):
        """どのパターンにも一致しない場合「その他」として分類することを確認"""
        self.assertEqual(ag.classify_usage_groovy('STATUS'), "その他")


class TestExtractStaticFinalName(unittest.TestCase):
    def test_基本的なstatic_final宣言から名前を抽出する(self):
        """static final宣言から定数名を取り出せることを確認"""
        self.assertEqual(ag.extract_static_final_name('static final String STATUS = "TARGET"'), "STATUS")

    def test_アクセス修飾子付きstatic_finalから名前を抽出する(self):
        """publicなどの修飾子があってもstatic final定数名を抽出できることを確認"""
        self.assertEqual(ag.extract_static_final_name('public static final String CODE = "TARGET"'), "CODE")

    def test_static_finalでない場合はNoneを返す(self):
        """static final宣言でない行ではNoneを返すことを確認"""
        self.assertIsNone(ag.extract_static_final_name('def x = STATUS'))


class TestIsClassLevelField(unittest.TestCase):
    def test_privateフィールドをクラスレベルと判定する(self):
        """private修飾子付きの宣言をクラスレベルフィールドと判定することを確認"""
        self.assertTrue(ag.is_class_level_field('private String type = STATUS'))

    def test_protectedフィールドをクラスレベルと判定する(self):
        """protected修飾子付きの宣言をクラスレベルフィールドと判定することを確認"""
        self.assertTrue(ag.is_class_level_field('protected int count = 0'))

    def test_publicフィールドをクラスレベルと判定する(self):
        """public修飾子付きの宣言をクラスレベルフィールドと判定することを確認"""
        self.assertTrue(ag.is_class_level_field('public String name = "x"'))

    def test_def宣言をクラスレベルフィールドと判定する(self):
        """def宣言をクラスレベルフィールドと判定することを確認"""
        self.assertTrue(ag.is_class_level_field('def code = STATUS'))

    def test_インデント付きdefはローカル変数と判定する(self):
        """インデントされたdef宣言はクラスレベルフィールドではないと判定することを確認"""
        self.assertFalse(ag.is_class_level_field('    def code = STATUS'))


class TestFindGetterNamesGroovy(unittest.TestCase):
    def test_命名規則に従ったgetterを検出する(self):
        """getXxx形式の標準的なgetterを検出できることを確認"""
        names = ag.find_getter_names_groovy("type", [
            "String getType() {",
            "    return this.type",
            "}",
        ])
        self.assertIn("getType", names)

    def test_非標準名のgetterも検出する(self):
        """fetchXxxなど命名規則に沿わないgetterも本体から検出できることを確認"""
        names = ag.find_getter_names_groovy("type", [
            "String fetchType() {",
            "    return type",
            "}",
        ])
        self.assertIn("fetchType", names)


class TestFindSetterNamesGroovy(unittest.TestCase):
    def test_命名規則に従ったsetterを検出する(self):
        """setXxx形式の標準的なsetterを検出できることを確認"""
        names = ag.find_setter_names_groovy("type", [
            "void setType(String v) {",
            "    this.type = v",
            "}",
        ])
        self.assertIn("setType", names)

    def test_非標準名のsetterも検出する(self):
        """assignXxxなど命名規則に沿わないsetterも本体から検出できることを確認"""
        names = ag.find_setter_names_groovy("type", [
            "void assignType(String v) {",
            "    type = v",
            "}",
        ])
        self.assertIn("assignType", names)


class TestTrackStaticFinalGroovy(unittest.TestCase):
    def test_groovyファイル内のstatic_final利用箇所を追跡できる(self):
        """static final定数の利用箇所を他のGroovyファイルから間接参照として検出できることを確認"""
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

    def test_TARGETキーワードのE2E解析結果が期待TSVと一致する(self):
        """grep入力からの一連の解析パイプラインの出力TSVが期待ファイルと一致することを確認"""
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
