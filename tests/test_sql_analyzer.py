import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_sql as aq


class TestClassifyUsageSql(unittest.TestCase):
    def test_exception(self):
        self.assertEqual(
            aq.classify_usage_sql("RAISE_APPLICATION_ERROR(-20001, 'TARGET');"),
            "例外・エラー処理"
        )
    def test_variable_definition(self):
        self.assertEqual(aq.classify_usage_sql("v_code := 'TARGET';"), "定数・変数定義")
    def test_constant_definition(self):
        self.assertEqual(
            aq.classify_usage_sql("c_val CONSTANT VARCHAR2(10) := 'TARGET';"),
            "定数・変数定義"
        )
    def test_where(self):
        self.assertEqual(
            aq.classify_usage_sql("WHERE code = 'TARGET'"), "WHERE条件"
        )
    def test_decode(self):
        self.assertEqual(
            aq.classify_usage_sql("DECODE(code, 'TARGET', 'OK')"), "比較・DECODE"
        )
    def test_case_when(self):
        self.assertEqual(
            aq.classify_usage_sql("CASE WHEN code = 'TARGET' THEN 1 END"), "比較・DECODE"
        )
    def test_insert(self):
        self.assertEqual(
            aq.classify_usage_sql("INSERT INTO t VALUES ('TARGET')"), "INSERT/UPDATE値"
        )
    def test_update(self):
        self.assertEqual(
            aq.classify_usage_sql("UPDATE t SET code = 'TARGET'"), "INSERT/UPDATE値"
        )
    def test_select(self):
        self.assertEqual(
            aq.classify_usage_sql("SELECT 'TARGET' FROM dual"), "SELECT/INTO"
        )
    def test_other(self):
        self.assertEqual(aq.classify_usage_sql("TARGET"), "その他")


class TestExtractSqlVariableName(unittest.TestCase):
    def test_simple_assignment(self):
        self.assertEqual(
            aq.extract_sql_variable_name("v_code := 'TARGET';"), "v_code"
        )
    def test_type_declaration(self):
        self.assertEqual(
            aq.extract_sql_variable_name("l_val VARCHAR2(10) := 'TARGET';"), "l_val"
        )
    def test_no_match(self):
        self.assertIsNone(aq.extract_sql_variable_name("WHERE code = 'TARGET'"))


if __name__ == "__main__":
    unittest.main()
