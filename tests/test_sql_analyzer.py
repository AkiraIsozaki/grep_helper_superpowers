import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.sql import classify_usage as classify_usage_sql, extract_sql_variable_name


class TestClassifyUsageSql(unittest.TestCase):
    """TestClassifyUsageSql: classify_usage の SQL コード行→使用タイプ分類を観察するテスト。
    SQL 言語の E2E 駆動テストが現状無いため、公開 API の分類仕様を本クラスで保証する。
    """
    def test_例外エラー処理を分類できる(self):
        """RAISE_APPLICATION_ERROR を含む行が「例外・エラー処理」に分類されること"""
        self.assertEqual(
            classify_usage_sql("RAISE_APPLICATION_ERROR(-20001, 'TARGET');"),
            "例外・エラー処理"
        )
    def test_変数代入を定数変数定義に分類できる(self):
        self.assertEqual(classify_usage_sql("v_code := 'TARGET';"), "定数・変数定義")
    def test_CONSTANT宣言を定数変数定義に分類できる(self):
        self.assertEqual(
            classify_usage_sql("c_val CONSTANT VARCHAR2(10) := 'TARGET';"),
            "定数・変数定義"
        )
    def test_WHERE条件を分類できる(self):
        """WHERE 句を含む行が「WHERE条件」に分類されること"""
        self.assertEqual(
            classify_usage_sql("WHERE code = 'TARGET'"), "WHERE条件"
        )
    def test_DECODE式を比較DECODEに分類できる(self):
        self.assertEqual(
            classify_usage_sql("DECODE(code, 'TARGET', 'OK')"), "比較・DECODE"
        )
    def test_CASE_WHEN式を比較DECODEに分類できる(self):
        self.assertEqual(
            classify_usage_sql("CASE WHEN code = 'TARGET' THEN 1 END"), "比較・DECODE"
        )
    def test_INSERT文をINSERT_UPDATE値に分類できる(self):
        self.assertEqual(
            classify_usage_sql("INSERT INTO t VALUES ('TARGET')"), "INSERT/UPDATE値"
        )
    def test_UPDATE文をINSERT_UPDATE値に分類できる(self):
        self.assertEqual(
            classify_usage_sql("UPDATE t SET code = 'TARGET'"), "INSERT/UPDATE値"
        )
    def test_SELECT文をSELECT_INTOに分類できる(self):
        self.assertEqual(
            classify_usage_sql("SELECT 'TARGET' FROM dual"), "SELECT/INTO"
        )
    def test_該当しない場合はその他に分類される(self):
        self.assertEqual(classify_usage_sql("TARGET"), "その他")


class TestExtractSqlVariableName(unittest.TestCase):
    """TestExtractSqlVariableName: extract_sql_variable_name の代入文→変数名抽出を観察するテスト。
    SQL 言語の E2E 駆動テストが現状無いため、公開 API の抽出仕様を本クラスで保証する。
    """
    def test_単純な代入文から変数名を抽出できる(self):
        """`v_code := ...` から変数名 v_code を取り出せること"""
        self.assertEqual(
            extract_sql_variable_name("v_code := 'TARGET';"), "v_code"
        )
    def test_型宣言付き代入から変数名を抽出できる(self):
        """VARCHAR2 など型宣言を伴う代入から変数名を取り出せること"""
        self.assertEqual(
            extract_sql_variable_name("l_val VARCHAR2(10) := 'TARGET';"), "l_val"
        )
    def test_変数定義でない場合はNoneを返す(self):
        """WHERE 句のような非変数定義行では None が返ること"""
        self.assertIsNone(extract_sql_variable_name("WHERE code = 'TARGET'"))


if __name__ == "__main__":
    unittest.main()
