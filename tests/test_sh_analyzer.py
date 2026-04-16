import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_sh as ash


class TestClassifyUsageSh(unittest.TestCase):
    def test_export(self):
        self.assertEqual(ash.classify_usage_sh('export TARGET_VAR="TARGET"'), "環境変数エクスポート")
    def test_setenv_csh(self):
        self.assertEqual(ash.classify_usage_sh("setenv MY_VAR TARGET"), "環境変数エクスポート")
    def test_variable_assignment(self):
        self.assertEqual(ash.classify_usage_sh('MY_VAR="TARGET"'), "変数代入")
    def test_set_csh(self):
        self.assertEqual(ash.classify_usage_sh("set MY_VAR = TARGET"), "変数代入")
    def test_condition_if(self):
        self.assertEqual(ash.classify_usage_sh('if [ "$MY_VAR" = "TARGET" ]; then'), "条件判定")
    def test_condition_case(self):
        self.assertEqual(ash.classify_usage_sh("case $MY_VAR in"), "条件判定")
    def test_echo(self):
        self.assertEqual(ash.classify_usage_sh('echo "TARGET"'), "echo/print出力")
    def test_printf(self):
        self.assertEqual(ash.classify_usage_sh('printf "%s\n" "TARGET"'), "echo/print出力")
    def test_command_argument(self):
        self.assertEqual(ash.classify_usage_sh("grep TARGET file.txt"), "コマンド引数")
    def test_other(self):
        self.assertEqual(ash.classify_usage_sh("TARGET"), "その他")


class TestExtractShVariableName(unittest.TestCase):
    def test_simple_assignment(self):
        self.assertEqual(ash.extract_sh_variable_name('MY_VAR="TARGET"'), "MY_VAR")
    def test_export_assignment(self):
        self.assertEqual(ash.extract_sh_variable_name('export MY_VAR="TARGET"'), "MY_VAR")
    def test_set_csh(self):
        self.assertEqual(ash.extract_sh_variable_name("set MY_VAR = TARGET"), "MY_VAR")
    def test_setenv_csh(self):
        self.assertEqual(ash.extract_sh_variable_name("setenv MY_VAR TARGET"), "MY_VAR")
    def test_no_match(self):
        self.assertIsNone(ash.extract_sh_variable_name("grep TARGET file.txt"))


if __name__ == "__main__":
    unittest.main()
