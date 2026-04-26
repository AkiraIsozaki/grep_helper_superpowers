import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_plsql as ap
import analyze_common


class TestClassifyUsagePlsql(unittest.TestCase):
    def test_CONSTANT宣言は定数_変数宣言に分類される(self):
        """CONSTANT付きの宣言行が「定数/変数宣言」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql('v_status CONSTANT VARCHAR2(10) := TARGET;'), "定数/変数宣言")

    def test_代入文は定数_変数宣言に分類される(self):
        """変数への代入(:=)行が「定数/変数宣言」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql('v_code := TARGET;'), "定数/変数宣言")

    def test_WHEN_THEN節はEXCEPTION処理に分類される(self):
        """WHEN ... THEN形式の例外ハンドラ行が「EXCEPTION処理」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql('WHEN TARGET THEN'), "EXCEPTION処理")

    def test_RAISE文はEXCEPTION処理に分類される(self):
        """RAISE文が「EXCEPTION処理」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql('RAISE TARGET_ERROR;'), "EXCEPTION処理")

    def test_IF条件式は条件判定に分類される(self):
        """IF文の条件式が「条件判定」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql('IF v_status = TARGET THEN'), "条件判定")

    def test_CASE_WHEN節は条件判定に分類される(self):
        """CASE WHEN形式の条件分岐が「条件判定」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql('CASE WHEN v = TARGET'), "条件判定")

    def test_CURSOR定義はカーソル定義に分類される(self):
        """CURSOR ... IS SELECT 形式の宣言が「カーソル定義」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql('CURSOR c_target IS SELECT * FROM t WHERE code = TARGET'), "カーソル定義")

    def test_INSERT文はINSERT_UPDATE値に分類される(self):
        """INSERT文のVALUES句が「INSERT/UPDATE値」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql("INSERT INTO t(code) VALUES(TARGET)"), "INSERT/UPDATE値")

    def test_UPDATE_SET句はINSERT_UPDATE値に分類される(self):
        """UPDATE文のSET句が「INSERT/UPDATE値」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql("UPDATE t SET code = TARGET"), "INSERT/UPDATE値")

    def test_WHERE句はWHERE条件に分類される(self):
        """WHERE句のキーワード使用が「WHERE条件」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql("WHERE code = TARGET"), "WHERE条件")

    def test_どの分類にも該当しない行はその他に分類される(self):
        """既知のパターンに当てはまらない行が「その他」として分類されることを確認"""
        self.assertEqual(ap.classify_usage_plsql("TARGET"), "その他")


class TestE2EPlsql(unittest.TestCase):
    """E2E統合テスト: PL/SQL フィクスチャでツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "plsql"

    def test_TARGETキーワードのE2E実行で期待TSVと一致する(self):
        """TARGETフィクスチャに対してprocess_grep_fileを実行し、出力TSVが期待値と完全一致することを確認"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        analyze_common._file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ap.ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = ap.process_grep_file(grep_path, keyword, src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            ap.write_tsv(list(direct_records), output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


if __name__ == "__main__":
    unittest.main()
