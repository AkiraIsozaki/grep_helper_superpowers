import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.sh import classify_usage as classify_usage_sh, extract_sh_variable_name


class TestClassifyUsageSh(unittest.TestCase):
    def test_export文を環境変数エクスポートとして分類する(self):
        """export 構文が環境変数エクスポートに分類されることを検証"""
        self.assertEqual(classify_usage_sh('export TARGET_VAR="TARGET"'), "環境変数エクスポート")
    def test_csh_setenv文を環境変数エクスポートとして分類する(self):
        """csh の setenv 構文が環境変数エクスポートに分類されることを検証"""
        self.assertEqual(classify_usage_sh("setenv MY_VAR TARGET"), "環境変数エクスポート")
    def test_通常の変数代入を変数代入として分類する(self):
        """通常の VAR=VALUE 形式が変数代入に分類されることを検証"""
        self.assertEqual(classify_usage_sh('MY_VAR="TARGET"'), "変数代入")
    def test_csh_set文を変数代入として分類する(self):
        """csh の set 構文が変数代入に分類されることを検証"""
        self.assertEqual(classify_usage_sh("set MY_VAR = TARGET"), "変数代入")
    def test_if文を条件判定として分類する(self):
        """if 構文が条件判定に分類されることを検証"""
        self.assertEqual(classify_usage_sh('if [ "$MY_VAR" = "TARGET" ]; then'), "条件判定")
    def test_case文を条件判定として分類する(self):
        """case 構文が条件判定に分類されることを検証"""
        self.assertEqual(classify_usage_sh("case $MY_VAR in"), "条件判定")
    def test_echoをecho_print出力として分類する(self):
        """echo 文が echo/print 出力に分類されることを検証"""
        self.assertEqual(classify_usage_sh('echo "TARGET"'), "echo/print出力")
    def test_printfをecho_print出力として分類する(self):
        """printf 文が echo/print 出力に分類されることを検証"""
        self.assertEqual(classify_usage_sh('printf "%s\n" "TARGET"'), "echo/print出力")
    def test_コマンド引数として分類する(self):
        """コマンドの引数として現れるトークンがコマンド引数に分類されることを検証"""
        self.assertEqual(classify_usage_sh("grep TARGET file.txt"), "コマンド引数")
    def test_該当しないものはその他として分類する(self):
        """どのパターンにも該当しない場合にその他へ分類されることを検証"""
        self.assertEqual(classify_usage_sh("TARGET"), "その他")


class TestExtractShVariableName(unittest.TestCase):
    def test_単純な代入から変数名を抽出する(self):
        """VAR="..." 形式から変数名 VAR を抽出できることを検証"""
        self.assertEqual(extract_sh_variable_name('MY_VAR="TARGET"'), "MY_VAR")
    def test_export付き代入から変数名を抽出する(self):
        """export VAR="..." 形式から変数名 VAR を抽出できることを検証"""
        self.assertEqual(extract_sh_variable_name('export MY_VAR="TARGET"'), "MY_VAR")
    def test_csh_set文から変数名を抽出する(self):
        """csh の set VAR = ... 形式から変数名を抽出できることを検証"""
        self.assertEqual(extract_sh_variable_name("set MY_VAR = TARGET"), "MY_VAR")
    def test_csh_setenv文から変数名を抽出する(self):
        """csh の setenv VAR ... 形式から変数名を抽出できることを検証"""
        self.assertEqual(extract_sh_variable_name("setenv MY_VAR TARGET"), "MY_VAR")
    def test_変数代入でない行ではNoneを返す(self):
        """変数代入以外の行では None が返ることを検証"""
        self.assertIsNone(extract_sh_variable_name("grep TARGET file.txt"))


if __name__ == "__main__":
    unittest.main()
