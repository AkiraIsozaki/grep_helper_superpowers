import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.plsql import classify_usage as classify_usage_plsql
from grep_helper.model import ProcessStats
from grep_helper.tsv_output import write_tsv
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import plsql as _plsql_handler
from grep_helper.file_cache import _file_lines_cache_clear


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _plsql_handler, keyword=keyword, stats=stats)


class TestClassifyUsagePlsql(unittest.TestCase):
    """TestClassifyUsagePlsql: classify_usage の分類ルール網羅を観察するテスト。
    E2E は4分類のみカバーし、EXCEPTION処理・カーソル定義・その他は未カバー。
    """

    def test_CONSTANT宣言は定数_変数宣言に分類される(self):
        self.assertEqual(classify_usage_plsql('v_status CONSTANT VARCHAR2(10) := TARGET;'), "定数/変数宣言")

    def test_代入文は定数_変数宣言に分類される(self):
        self.assertEqual(classify_usage_plsql('v_code := TARGET;'), "定数/変数宣言")

    def test_WHEN_THEN節はEXCEPTION処理に分類される(self):
        self.assertEqual(classify_usage_plsql('WHEN TARGET THEN'), "EXCEPTION処理")

    def test_RAISE文はEXCEPTION処理に分類される(self):
        self.assertEqual(classify_usage_plsql('RAISE TARGET_ERROR;'), "EXCEPTION処理")

    def test_IF条件式は条件判定に分類される(self):
        self.assertEqual(classify_usage_plsql('IF v_status = TARGET THEN'), "条件判定")

    def test_CASE_WHEN節は条件判定に分類される(self):
        self.assertEqual(classify_usage_plsql('CASE WHEN v = TARGET'), "条件判定")

    def test_CURSOR定義はカーソル定義に分類される(self):
        self.assertEqual(classify_usage_plsql('CURSOR c_target IS SELECT * FROM t WHERE code = TARGET'), "カーソル定義")

    def test_INSERT文はINSERT_UPDATE値に分類される(self):
        self.assertEqual(classify_usage_plsql("INSERT INTO t(code) VALUES(TARGET)"), "INSERT/UPDATE値")

    def test_UPDATE_SET句はINSERT_UPDATE値に分類される(self):
        self.assertEqual(classify_usage_plsql("UPDATE t SET code = TARGET"), "INSERT/UPDATE値")

    def test_WHERE句はWHERE条件に分類される(self):
        self.assertEqual(classify_usage_plsql("WHERE code = TARGET"), "WHERE条件")

    def test_どの分類にも該当しない行はその他に分類される(self):
        self.assertEqual(classify_usage_plsql("TARGET"), "その他")


class TestE2EPlsql(unittest.TestCase):
    """E2E統合テスト: PL/SQL フィクスチャでツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "plsql"

    def test_TARGETキーワードのE2E実行で期待TSVと一致する(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        _file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = _process_grep_file(grep_path, keyword, src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            write_tsv(list(direct_records), output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


from grep_helper.languages.plsql import (
    extract_plsql_constant_name,
    track_plsql_constant,
    batch_track_indirect as batch_track_indirect_plsql,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractPlsqlConstantName(unittest.TestCase):
    """TestExtractPlsqlConstantName: extract_plsql_constant_name の抽出有無を観察する。"""

    def test_constant宣言から名前を抽出する(self):
        self.assertEqual(extract_plsql_constant_name('c_x CONSTANT VARCHAR2(8) := \'777\';'), "c_x")

    def test_大文字混在のCONSTANT宣言から名前を抽出する(self):
        self.assertEqual(extract_plsql_constant_name('C_X Constant Number := 1;'), "C_X")

    def test_インデント付き宣言からも抽出する(self):
        self.assertEqual(extract_plsql_constant_name('    c_y CONSTANT NUMBER := 5;'), "c_y")

    def test_constantキーワード無しの変数宣言は抽出しない(self):
        self.assertIsNone(extract_plsql_constant_name('v_count NUMBER := 0;'))

    def test_条件判定行は抽出しない(self):
        self.assertIsNone(extract_plsql_constant_name('IF p_input = c_x THEN'))


class TestTrackPlsqlConstant(unittest.TestCase):
    """TestTrackPlsqlConstant: track_plsql_constant の間接参照検出と定義行除外を観察する。"""

    def test_別pkbファイルでの参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('PACKAGE BODY sample IS\n  c_x CONSTANT NUMBER := 777;\nEND;\n')
            (src / "other.pkb").write_text('IF p_input = sample.c_x THEN\n  NULL;\nEND IF;\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="定数/変数宣言",
                filepath=str(src / "sample.pkb"),
                lineno="2",
                code='  c_x CONSTANT NUMBER := 777;',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_plsql_constant("c_x", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("other.pkb" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_大文字小文字を区別せず参照を検出する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('  C_X CONSTANT NUMBER := 1;\n')
            (src / "other.pkb").write_text('  RETURN c_x;\n')
            record = GrepRecord(
                keyword="1",
                ref_type=RefType.DIRECT.value,
                usage_type="定数/変数宣言",
                filepath=str(src / "sample.pkb"),
                lineno="1",
                code='  C_X CONSTANT NUMBER := 1;',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_plsql_constant("C_X", src, record, stats)
            self.assertTrue(any("other.pkb" in r.filepath for r in results))


class TestBatchTrackIndirectPlsql(unittest.TestCase):
    """TestBatchTrackIndirectPlsql: batch_track_indirect の起点フィルタ・集約を観察する。"""

    def test_constantキーワードのレコードのみ起点となる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('  c_x CONSTANT NUMBER := 777;\n')
            (src / "other.pkb").write_text('  IF p = sample.c_x THEN NULL; END IF;\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="定数/変数宣言",
                    filepath=str(src / "sample.pkb"),
                    lineno="1",
                    code='  c_x CONSTANT NUMBER := 777;',
                ),
                GrepRecord(
                    keyword="0",
                    ref_type=RefType.DIRECT.value,
                    usage_type="定数/変数宣言",
                    filepath=str(src / "sample.pkb"),
                    lineno="2",
                    code='  v_count NUMBER := 0;',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_plsql(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("other.pkb" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_同一行に複数の参照がある場合は出現回数分のレコードを返す(self):
        """multi-emit 一貫性の観察: 一行に c_x が2回現れる場合、間接レコードも
        2件返す（python/ts/perl/kotlin と同じ挙動）。1行1emit にすると
        言語間で出力件数の意味が揃わなくなる。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('  c_x CONSTANT NUMBER := 777;\n')
            (src / "other.pkb").write_text('  IF c_x = 1 OR c_x = 2 THEN NULL; END IF;\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="定数/変数宣言",
                    filepath=str(src / "sample.pkb"),
                    lineno="1",
                    code='  c_x CONSTANT NUMBER := 777;',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_plsql(records, src, None, workers=1)
            other_pkb_results = [r for r in results if "other.pkb" in r.filepath]
            self.assertEqual(len(other_pkb_results), 2)

    def test_workers_2と1で同じレコード集合を返す(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('  c_x CONSTANT NUMBER := 777;\n')
            (src / "a.pkb").write_text('  IF p = sample.c_x THEN NULL; END IF;\n')
            (src / "b.pkb").write_text('  RETURN sample.c_x;\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="定数/変数宣言",
                    filepath=str(src / "sample.pkb"),
                    lineno="1",
                    code='  c_x CONSTANT NUMBER := 777;',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect_plsql(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect_plsql(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))


if __name__ == "__main__":
    unittest.main()
