import sys, unittest, tempfile, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_c as ac


class TestClassifyUsageC(unittest.TestCase):
    def test_define(self):
        self.assertEqual(ac.classify_usage_c('#define MAX_SIZE 100'), "#define定数定義")

    def test_define_with_spaces(self):
        self.assertEqual(ac.classify_usage_c('# define STATUS "value"'), "#define定数定義")

    def test_condition_if(self):
        self.assertEqual(ac.classify_usage_c('if (code == STATUS)'), "条件判定")

    def test_condition_strcmp(self):
        self.assertEqual(ac.classify_usage_c('strcmp(code, STATUS)'), "条件判定")

    def test_condition_strncmp(self):
        self.assertEqual(ac.classify_usage_c('strncmp(code, STATUS, 4)'), "条件判定")

    def test_condition_switch(self):
        self.assertEqual(ac.classify_usage_c('switch (code) {'), "条件判定")

    def test_return(self):
        self.assertEqual(ac.classify_usage_c('return STATUS;'), "return文")

    def test_variable_assignment(self):
        self.assertEqual(ac.classify_usage_c('char buf[32] = STATUS;'), "変数代入")

    def test_function_argument(self):
        self.assertEqual(ac.classify_usage_c('process(STATUS)'), "関数引数")

    def test_other(self):
        self.assertEqual(ac.classify_usage_c('STATUS'), "その他")

    def test_no_exec_sql(self):
        result = ac.classify_usage_c('EXEC SQL SELECT * FROM t;')
        self.assertNotEqual(result, "EXEC SQL文")


class TestExtractDefineName(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ac.extract_define_name('#define STATUS "value"'), "STATUS")

    def test_with_spaces_after_hash(self):
        self.assertEqual(ac.extract_define_name('# define STATUS "value"'), "STATUS")

    def test_no_match(self):
        self.assertIsNone(ac.extract_define_name('if (x == STATUS)'))

    def test_no_value(self):
        self.assertIsNone(ac.extract_define_name('#define STATUS'))


class TestExtractVariableNameC(unittest.TestCase):
    def test_char_array(self):
        self.assertEqual(ac.extract_variable_name_c('char buf[32];'), "buf")

    def test_int_with_assignment(self):
        self.assertEqual(ac.extract_variable_name_c('int count = 0;'), "count")

    def test_pointer(self):
        self.assertEqual(ac.extract_variable_name_c('char *ptr;'), "ptr")

    def test_no_match(self):
        self.assertIsNone(ac.extract_variable_name_c('if (x == 1)'))


if __name__ == "__main__":
    unittest.main()
