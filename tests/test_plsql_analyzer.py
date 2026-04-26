import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_plsql as ap
import analyze_common


class TestClassifyUsagePlsql(unittest.TestCase):
    def test_constant_declaration(self):
        self.assertEqual(ap.classify_usage_plsql('v_status CONSTANT VARCHAR2(10) := TARGET;'), "定数/変数宣言")

    def test_assignment(self):
        self.assertEqual(ap.classify_usage_plsql('v_code := TARGET;'), "定数/変数宣言")

    def test_exception_when_then(self):
        self.assertEqual(ap.classify_usage_plsql('WHEN TARGET THEN'), "EXCEPTION処理")

    def test_exception_raise(self):
        self.assertEqual(ap.classify_usage_plsql('RAISE TARGET_ERROR;'), "EXCEPTION処理")

    def test_if_condition(self):
        self.assertEqual(ap.classify_usage_plsql('IF v_status = TARGET THEN'), "条件判定")

    def test_case_when(self):
        self.assertEqual(ap.classify_usage_plsql('CASE WHEN v = TARGET'), "条件判定")

    def test_cursor_definition(self):
        self.assertEqual(ap.classify_usage_plsql('CURSOR c_target IS SELECT * FROM t WHERE code = TARGET'), "カーソル定義")

    def test_insert(self):
        self.assertEqual(ap.classify_usage_plsql("INSERT INTO t(code) VALUES(TARGET)"), "INSERT/UPDATE値")

    def test_update_set(self):
        self.assertEqual(ap.classify_usage_plsql("UPDATE t SET code = TARGET"), "INSERT/UPDATE値")

    def test_where(self):
        self.assertEqual(ap.classify_usage_plsql("WHERE code = TARGET"), "WHERE条件")

    def test_other(self):
        self.assertEqual(ap.classify_usage_plsql("TARGET"), "その他")


class TestE2EPlsql(unittest.TestCase):
    """E2E統合テスト: PL/SQL フィクスチャでツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "plsql"

    def test_e2e_target(self):
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
