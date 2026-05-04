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
    """TestClassifyUsagePerl: classify_usage_perl の分類ラベル返り値を観察するテスト。
    各分類種別の個別ケースは E2E に包摂されないため本クラスで保持する。
    """

    def test_use_constant定義を分類できる(self):
        """use constant の定義行を「use constant定義」に分類する"""
        self.assertEqual(classify_usage_perl('use constant STATUS => "TARGET";'), "use constant定義")

    def test_スカラー変数への代入を変数代入と判定する(self):
        """裸のスカラー代入を「変数代入」に分類する"""
        self.assertEqual(classify_usage_perl('$code = STATUS;'), "変数代入")

    def test_my宣言付き代入を変数代入と判定する(self):
        self.assertEqual(classify_usage_perl('my $x = STATUS;'), "変数代入")

    def test_our宣言付き代入を変数代入と判定する(self):
        self.assertEqual(classify_usage_perl('our $x = STATUS;'), "変数代入")

    def test_if文の条件式を条件判定と判定する(self):
        self.assertEqual(classify_usage_perl('if ($code eq STATUS)'), "条件判定")

    def test_unless文の条件式を条件判定と判定する(self):
        self.assertEqual(classify_usage_perl('unless ($x == STATUS)'), "条件判定")

    def test_print文をprint_say出力と判定する(self):
        self.assertEqual(classify_usage_perl('print STATUS;'), "print/say出力")

    def test_say文をprint_say出力と判定する(self):
        self.assertEqual(classify_usage_perl('say STATUS;'), "print/say出力")

    def test_printf文をprint_say出力と判定する(self):
        self.assertEqual(classify_usage_perl('printf "%s", STATUS;'), "print/say出力")

    def test_関数呼び出しの実引数を関数引数と判定する(self):
        """関数呼び出しの引数位置にある利用を「関数引数」に分類する"""
        self.assertEqual(classify_usage_perl('process(STATUS)'), "関数引数")

    def test_該当パターンに合致しない場合はその他と判定する(self):
        """既知パターンに合致しない単独利用を「その他」に分類する"""
        self.assertEqual(classify_usage_perl('STATUS'), "その他")

    def test_use_Module_qwのインポート宣言はその他と判定する(self):
        """use Sample qw(STATUS); はインポート宣言なので関数呼び出しではなくその他に分類する"""
        self.assertEqual(classify_usage_perl('use Sample qw(STATUS_CODE);'), "その他")


class TestE2EPerl(unittest.TestCase):
    """TestE2EPerl: process_grep_file (Perl) の全体パイプライン出力を観察するテスト。
    fixture ファイルを用いた入出力一致確認で回帰を防ぐ。
    """

    TESTS_DIR = Path(__file__).parent / "perl"

    def test_E2EでTARGET定数の解析結果が期待TSVと一致する(self):
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


from grep_helper.languages.perl import (
    extract_perl_constant_name,
    extract_perl_our_name,
    extract_perl_constant_hash_names,
    track_perl_constant,
    batch_track_indirect as batch_track_indirect_perl,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractPerlConstantName(unittest.TestCase):
    """TestExtractPerlConstantName: extract_perl_constant_name の抽出有無を観察する。"""

    def test_use_constantから定数名を抽出する(self):
        self.assertEqual(extract_perl_constant_name('use constant STATUS_CODE => "777";'), "STATUS_CODE")

    def test_use_constantのハッシュ形式は単体抽出ではNoneを返す(self):
        self.assertIsNone(extract_perl_constant_name('use constant {A => 1, B => 2};'))

    def test_非constant行はNoneを返す(self):
        self.assertIsNone(extract_perl_constant_name('our $FOO = "x";'))


class TestExtractPerlOurName(unittest.TestCase):
    """TestExtractPerlOurName: extract_perl_our_name の抽出有無を観察する。"""

    def test_our宣言から変数名を抽出する(self):
        self.assertEqual(extract_perl_our_name('our $FOO = "x";'), "FOO")

    def test_my宣言からは抽出しない(self):
        self.assertIsNone(extract_perl_our_name('my $FOO = "x";'))

    def test_use_constant行からは抽出しない(self):
        self.assertIsNone(extract_perl_our_name('use constant FOO => "x";'))


class TestExtractPerlConstantHashNames(unittest.TestCase):
    """TestExtractPerlConstantHashNames: ハッシュ形式から複数キー抽出を観察する。"""

    def test_use_constantのハッシュ形式から複数の名前を抽出する(self):
        names = extract_perl_constant_hash_names('use constant {A => 1, B => 2, C => 3};')
        self.assertEqual(set(names), {"A", "B", "C"})

    def test_単一形式のuse_constantからは空リストを返す(self):
        self.assertEqual(extract_perl_constant_hash_names('use constant FOO => "x";'), [])

    def test_非use_constant行からは空リストを返す(self):
        self.assertEqual(extract_perl_constant_hash_names('our $FOO = "x";'), [])


class TestTrackPerlConstant(unittest.TestCase):
    """TestTrackPerlConstant: track_perl_constant の間接参照検出と定義行除外を観察する。"""

    def test_別pmファイルでの定数参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('package Sample;\nuse constant STATUS_CODE => "777";\n1;\n')
            (src / "Service.pm").write_text('if ($x eq STATUS_CODE) { return 1; }\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="use constant定義",
                filepath=str(src / "Sample.pm"),
                lineno="2",
                code='use constant STATUS_CODE => "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_perl_constant("STATUS_CODE", src, record, stats, kind="bareword")
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.pm" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_our_scalar変数の参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('package Sample;\nour $FOO = "777";\n1;\n')
            (src / "Service.pm").write_text('print $FOO;\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(src / "Sample.pm"),
                lineno="2",
                code='our $FOO = "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_perl_constant("FOO", src, record, stats, kind="scalar")
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.pm" in fp for fp in filepaths))


class TestBatchTrackIndirectPerl(unittest.TestCase):
    """TestBatchTrackIndirectPerl: batch_track_indirect の起点フィルタ・集約を観察する。"""

    def test_use_constantとour両方のレコードから間接追跡する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text(
                'package Sample;\n'
                'use constant STATUS_CODE => "777";\n'
                'our $FOO = "x";\n'
                '1;\n'
            )
            (src / "Service.pm").write_text(
                'if ($x eq STATUS_CODE) { return 1; }\n'
                'print $Sample::FOO;\n'
            )
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="use constant定義",
                    filepath=str(src / "Sample.pm"),
                    lineno="2",
                    code='use constant STATUS_CODE => "777";',
                ),
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "Sample.pm"),
                    lineno="3",
                    code='our $FOO = "x";',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_perl(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.pm" in fp for fp in filepaths))

    def test_our_scalar変数のbatch経由参照を間接レコードに記録する(self):
        """scalar batch 経路の回帰テスト: bare names + $ post-filter で
        `print $FOO;` のような行も正しく拾えること（過去 build_batch_scanner に
        `$FOO` を直接渡すと regex 境界の都合で取り逃していた）。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('package Sample;\nour $FOO = "777";\n1;\n')
            (src / "Service.pm").write_text('print $FOO;\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "Sample.pm"),
                    lineno="2",
                    code='our $FOO = "777";',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_perl(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.pm" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_my宣言は起点にならない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('my $LOCAL = "x";\n')
            (src / "other.pm").write_text('print $LOCAL;\n')
            records = [
                GrepRecord(
                    keyword="x",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "Sample.pm"),
                    lineno="1",
                    code='my $LOCAL = "x";',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_perl(records, src, None, workers=1)
            self.assertEqual(results, [])

    def test_workers_2と1で同じレコード集合を返す(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('use constant STATUS_CODE => "777";\n')
            (src / "Service.pm").write_text('if ($x eq STATUS_CODE) { return 1; }\n')
            (src / "Worker.pm").write_text('do_notify(STATUS_CODE);\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="use constant定義",
                    filepath=str(src / "Sample.pm"),
                    lineno="1",
                    code='use constant STATUS_CODE => "777";',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect_perl(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect_perl(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))


if __name__ == "__main__":
    unittest.main()
