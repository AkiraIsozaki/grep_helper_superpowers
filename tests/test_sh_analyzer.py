import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.sh import classify_usage as classify_usage_sh, extract_sh_variable_name


class TestClassifyUsageSh(unittest.TestCase):
    """TestClassifyUsageSh: classify_usage の sh コード行→使用タイプ分類結果を観察するテスト。
    sh 言語の E2E 駆動テストが現状無いため、公開 API の分類仕様を本クラスで保証する。
    """
    def test_export文を環境変数エクスポートとして分類する(self):
        self.assertEqual(classify_usage_sh('export TARGET_VAR="TARGET"'), "環境変数エクスポート")
    def test_csh_setenv文を環境変数エクスポートとして分類する(self):
        self.assertEqual(classify_usage_sh("setenv MY_VAR TARGET"), "環境変数エクスポート")
    def test_通常の変数代入を変数代入として分類する(self):
        self.assertEqual(classify_usage_sh('MY_VAR="TARGET"'), "変数代入")
    def test_csh_set文を変数代入として分類する(self):
        self.assertEqual(classify_usage_sh("set MY_VAR = TARGET"), "変数代入")
    def test_if文を条件判定として分類する(self):
        self.assertEqual(classify_usage_sh('if [ "$MY_VAR" = "TARGET" ]; then'), "条件判定")
    def test_case文を条件判定として分類する(self):
        self.assertEqual(classify_usage_sh("case $MY_VAR in"), "条件判定")
    def test_echoをecho_print出力として分類する(self):
        self.assertEqual(classify_usage_sh('echo "TARGET"'), "echo/print出力")
    def test_printfをecho_print出力として分類する(self):
        self.assertEqual(classify_usage_sh('printf "%s\n" "TARGET"'), "echo/print出力")
    def test_コマンド引数として分類する(self):
        self.assertEqual(classify_usage_sh("grep TARGET file.txt"), "コマンド引数")
    def test_該当しないものはその他として分類する(self):
        self.assertEqual(classify_usage_sh("TARGET"), "その他")


class TestExtractShVariableName(unittest.TestCase):
    """TestExtractShVariableName: extract_sh_variable_name の代入文→変数名抽出を観察するテスト。
    sh 言語の E2E 駆動テストが現状無いため、公開 API の抽出仕様を本クラスで保証する。
    """
    def test_単純な代入から変数名を抽出する(self):
        self.assertEqual(extract_sh_variable_name('MY_VAR="TARGET"'), "MY_VAR")
    def test_export付き代入から変数名を抽出する(self):
        self.assertEqual(extract_sh_variable_name('export MY_VAR="TARGET"'), "MY_VAR")
    def test_csh_set文から変数名を抽出する(self):
        self.assertEqual(extract_sh_variable_name("set MY_VAR = TARGET"), "MY_VAR")
    def test_csh_setenv文から変数名を抽出する(self):
        self.assertEqual(extract_sh_variable_name("setenv MY_VAR TARGET"), "MY_VAR")
    def test_変数代入でない行ではNoneを返す(self):
        self.assertIsNone(extract_sh_variable_name("grep TARGET file.txt"))


if __name__ == "__main__":
    unittest.main()
