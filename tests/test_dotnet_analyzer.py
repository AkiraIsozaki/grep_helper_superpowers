import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_dotnet as ad
import analyze_common


class TestClassifyUsageDotnet(unittest.TestCase):
    def test_CSのconst定義を定数定義として分類する(self):
        """C# の const 宣言が定数定義(Const/readonly)に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('public const string STATUS = "TARGET";'), "定数定義(Const/readonly)")

    def test_CSのstatic_readonlyを定数定義として分類する(self):
        """C# の static readonly 宣言が定数定義(Const/readonly)に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('public static readonly string ALIAS = STATUS;'), "定数定義(Const/readonly)")

    def test_VBのConst定義を定数定義として分類する(self):
        """VB の Const 宣言が定数定義(Const/readonly)に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('Const STATUS As String = "TARGET"'), "定数定義(Const/readonly)")

    def test_CSの型付き変数代入を変数代入として分類する(self):
        """C# の型指定付き変数代入が変数代入に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('string code = STATUS;'), "変数代入")

    def test_CSのvarキーワード代入を変数代入として分類する(self):
        """C# の var キーワードによる代入が変数代入に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('var x = STATUS;'), "変数代入")

    def test_VBのDim宣言を変数代入として分類する(self):
        """VB の Dim 宣言が変数代入に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('Dim x As String = STATUS'), "変数代入")

    def test_CSのif文を条件判定として分類する(self):
        """C# の if 文が条件判定に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('if (code == STATUS)'), "条件判定")

    def test_VBのIf文を条件判定として分類する(self):
        """VB の If 文が条件判定に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('If code = STATUS Then'), "条件判定")

    def test_CSのreturn文をreturn文として分類する(self):
        """C# の return 文が return 文に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('return STATUS;'), "return文")

    def test_VBのReturn文をreturn文として分類する(self):
        """VB の Return 文が return 文に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('Return STATUS'), "return文")

    def test_CSの角括弧Attribute記法を属性として分類する(self):
        """C# の [Attribute] 記法が属性(Attribute)に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('[Obsolete]'), "属性(Attribute)")

    def test_VBの山括弧Attribute記法を属性として分類する(self):
        """VB の <Attribute> 記法が属性(Attribute)に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('<Serializable>'), "属性(Attribute)")

    def test_メソッド呼び出しの引数をメソッド引数として分類する(self):
        """メソッド呼び出しの引数として渡されたケースがメソッド引数に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('Process(STATUS)'), "メソッド引数")

    def test_どの分類にも該当しない場合はその他になる(self):
        """既知パターンに当てはまらない記述がその他に分類されることを確認"""
        self.assertEqual(ad.classify_usage_dotnet('STATUS'), "その他")


class TestExtractConstNameDotnet(unittest.TestCase):
    def test_CSのconst宣言から定数名を抽出する(self):
        """C# の const 宣言から定数名 STATUS が抽出されることを確認"""
        self.assertEqual(ad.extract_const_name_dotnet('public const string STATUS = "TARGET";'), "STATUS")

    def test_CSのpublic_static_readonlyから定数名を抽出する(self):
        """C# の public static readonly 宣言から定数名 ALIAS が抽出されることを確認"""
        self.assertEqual(ad.extract_const_name_dotnet('public static readonly string ALIAS = STATUS;'), "ALIAS")

    def test_CSのprivate_static_readonlyから定数名を抽出する(self):
        """C# の private static readonly 宣言から定数名 COUNT が抽出されることを確認"""
        self.assertEqual(ad.extract_const_name_dotnet('private static readonly int COUNT = 1;'), "COUNT")

    def test_VBのConst宣言から定数名を抽出する(self):
        """VB の Const 宣言から定数名 STATUS が抽出されることを確認"""
        self.assertEqual(ad.extract_const_name_dotnet('Const STATUS As String = "TARGET"'), "STATUS")

    def test_定義以外の行からはNoneを返す(self):
        """定数定義に該当しない行に対しては None が返されることを確認"""
        self.assertIsNone(ad.extract_const_name_dotnet('string x = STATUS;'))


class TestTrackConstDotnet(unittest.TestCase):
    def test_CSとVBの両方で定数の利用箇所を検出する(self):
        """.cs と .vb の両方から間接参照の利用箇所を検出することを確認"""
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
            analyze_common._file_lines_cache_clear()
            results = ad.track_const_dotnet("STATUS", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.cs" in fp for fp in filepaths))
            self.assertTrue(any("Module.vb" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_定義行自体は追跡結果から除外される(self):
        """定数定義行そのものは間接参照として返却されないことを確認"""
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
            analyze_common._file_lines_cache_clear()
            results = ad.track_const_dotnet("STATUS", src, record, stats)
            self.assertEqual(results, [])


class TestE2EDotnet(unittest.TestCase):
    TESTS_DIR = Path(__file__).parent / "dotnet"

    def test_TARGETキーワードのE2E解析結果が期待TSVと一致する(self):
        """.NET 解析の E2E パイプラインで生成される TSV が期待ファイルと一致することを確認"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        analyze_common._file_lines_cache_clear()

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
