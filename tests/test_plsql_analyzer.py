import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_plsql as ap


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


if __name__ == "__main__":
    unittest.main()
