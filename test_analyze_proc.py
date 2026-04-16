"""analyze_proc.py のユニットテスト・統合テスト"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールをインポート
sys.path.insert(0, str(Path(__file__).parent))
import analyze_proc as ap


# ---------------------------------------------------------------------------
# TestParseGrepLine
# ---------------------------------------------------------------------------

class TestParseGrepLine(unittest.TestCase):
    """parse_grep_line() のテスト"""

    def test_normal_line(self):
        result = ap.parse_grep_line("src/sample.pc:42:    EXEC SQL FETCH cur INTO :hostVar;")
        self.assertIsNotNone(result)
        self.assertEqual(result["filepath"], "src/sample.pc")
        self.assertEqual(result["lineno"], "42")
        self.assertEqual(result["code"], "EXEC SQL FETCH cur INTO :hostVar;")

    def test_windows_path(self):
        result = ap.parse_grep_line(r"C:\project\sample.pc:10:char buf[256];")
        self.assertIsNotNone(result)
        self.assertEqual(result["lineno"], "10")

    def test_binary_notification_line(self):
        result = ap.parse_grep_line("Binary file ./obj/sample.o matches")
        self.assertIsNone(result)

    def test_empty_line(self):
        result = ap.parse_grep_line("")
        self.assertIsNone(result)

    def test_whitespace_only_line(self):
        result = ap.parse_grep_line("   \n")
        self.assertIsNone(result)

    def test_no_lineno(self):
        result = ap.parse_grep_line("src/sample.pc:no_number:code")
        self.assertIsNone(result)

    def test_code_is_stripped(self):
        result = ap.parse_grep_line("src/sample.pc:1:    int x = 0;    ")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "int x = 0;")


# ---------------------------------------------------------------------------
# TestClassifyUsageProc
# ---------------------------------------------------------------------------

class TestClassifyUsageProc(unittest.TestCase):
    """classify_usage_proc() の7種テスト"""

    def test_exec_sql(self):
        self.assertEqual(ap.classify_usage_proc("EXEC SQL SELECT * FROM t INTO :v;"), "EXEC SQL文")

    def test_exec_sql_case_insensitive(self):
        self.assertEqual(ap.classify_usage_proc("exec sql commit;"), "EXEC SQL文")

    def test_define(self):
        self.assertEqual(ap.classify_usage_proc('#define SAMPLE_CODE "TARGET"'), "#define定数定義")

    def test_define_with_spaces(self):
        self.assertEqual(ap.classify_usage_proc('#  define MY_CONST 100'), "#define定数定義")

    def test_condition_if(self):
        self.assertEqual(ap.classify_usage_proc("if (x == TARGET) {"), "条件判定")

    def test_condition_strcmp(self):
        self.assertEqual(ap.classify_usage_proc('if (strcmp(buf, TARGET) == 0)'), "条件判定")

    def test_return(self):
        self.assertEqual(ap.classify_usage_proc("return TARGET;"), "return文")

    def test_variable_assignment(self):
        self.assertEqual(ap.classify_usage_proc("char localVar[] = TARGET;"), "変数代入")

    def test_function_argument(self):
        self.assertEqual(ap.classify_usage_proc("process(TARGET);"), "関数引数")

    def test_other(self):
        self.assertEqual(ap.classify_usage_proc("TARGET"), "その他")


# ---------------------------------------------------------------------------
# TestExtractDefineName
# ---------------------------------------------------------------------------

class TestExtractDefineName(unittest.TestCase):
    """extract_define_name() のテスト"""

    def test_basic(self):
        self.assertEqual(ap.extract_define_name('#define SAMPLE_CODE "TARGET"'), "SAMPLE_CODE")

    def test_with_spaces_after_hash(self):
        self.assertEqual(ap.extract_define_name('#  define MY_CONST 100'), "MY_CONST")

    def test_no_match(self):
        self.assertIsNone(ap.extract_define_name("int x = 0;"))

    def test_no_value(self):
        # #define NAME（値なし）はスペースがないのでNone
        self.assertIsNone(ap.extract_define_name("#define NAME"))

    def test_with_value(self):
        self.assertEqual(ap.extract_define_name("#define MAX_LEN 256"), "MAX_LEN")


# ---------------------------------------------------------------------------
# TestExtractVariableNameProc
# ---------------------------------------------------------------------------

class TestExtractVariableNameProc(unittest.TestCase):
    """extract_variable_name_proc() のテスト"""

    def test_char_array_with_assignment(self):
        self.assertEqual(ap.extract_variable_name_proc('char localVar[] = "TARGET";'), "localVar")

    def test_char_array_size(self):
        self.assertEqual(ap.extract_variable_name_proc("char hostVar[256];"), "hostVar")

    def test_int_assignment(self):
        self.assertEqual(ap.extract_variable_name_proc("int count = 0;"), "count")

    def test_pointer(self):
        self.assertEqual(ap.extract_variable_name_proc("char *ptr = NULL;"), "ptr")

    def test_no_match(self):
        self.assertIsNone(ap.extract_variable_name_proc("EXEC SQL COMMIT;"))


# ---------------------------------------------------------------------------
# TestWriteTsv
# ---------------------------------------------------------------------------

class TestWriteTsv(unittest.TestCase):
    """write_tsv() の列数・エンコード・ソート順テスト"""

    def _make_record(self, keyword, ref_type, filepath, lineno, code,
                     src_var="", src_file="", src_lineno=""):
        return ap.GrepRecord(
            keyword=keyword,
            ref_type=ref_type,
            usage_type="その他",
            filepath=filepath,
            lineno=lineno,
            code=code,
            src_var=src_var,
            src_file=src_file,
            src_lineno=src_lineno,
        )

    def test_column_count(self):
        records = [self._make_record("KW", "直接", "a.pc", "1", "code")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            ap.write_tsv(records, out)
            with open(out, encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter="\t")
                header = next(reader)
                self.assertEqual(len(header), 9)
                row = next(reader)
                self.assertEqual(len(row), 9)

    def test_utf8_bom(self):
        records = [self._make_record("KW", "直接", "a.pc", "1", "code")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            ap.write_tsv(records, out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'), "UTF-8 BOMで始まること")

    def test_sort_order(self):
        records = [
            self._make_record("KW", "直接", "b.pc", "10", "code b"),
            self._make_record("KW", "直接", "a.pc", "20", "code a20"),
            self._make_record("KW", "直接", "a.pc", "5", "code a5"),
        ]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            ap.write_tsv(records, out)
            with open(out, encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter="\t")
                next(reader)  # header
                rows = list(reader)
            # a.pc:5 → a.pc:20 → b.pc:10 の順
            self.assertEqual(rows[0][3], "a.pc")
            self.assertEqual(rows[0][4], "5")
            self.assertEqual(rows[1][3], "a.pc")
            self.assertEqual(rows[1][4], "20")
            self.assertEqual(rows[2][3], "b.pc")


# ---------------------------------------------------------------------------
# TestE2EProc（統合テスト）
# ---------------------------------------------------------------------------

class TestE2EProc(unittest.TestCase):
    """E2E統合テスト: サンプルファイル群でツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "tests" / "proc"

    def test_e2e_target(self):
        """TARGET.grep を処理し、expected/TARGET.tsv と全行一致することを確認する"""
        src_dir = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(input_dir.exists(), f"input_dir が存在しない: {input_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        # キャッシュをリセット（テスト間の汚染防止）
        ap._file_cache.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # main() の内側のロジックを直接呼び出す
            stats = ap.ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = ap.process_grep_file(grep_path, keyword, src_dir, stats)
            classified = [r._replace(usage_type=ap.classify_usage_proc(r.code))
                          for r in direct_records]
            direct_records = classified
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = ap.extract_define_name(record.code)
                    if var_name:
                        all_records.extend(ap.track_define(var_name, src_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = ap.extract_variable_name_proc(record.code)
                    if not var_name:
                        var_name = ap.extract_host_var_name(record.code)
                    if var_name:
                        candidate = Path(record.filepath)
                        if not candidate.is_absolute():
                            candidate = src_dir / record.filepath
                        if candidate.exists():
                            all_records.extend(
                                ap.track_variable(var_name, candidate,
                                                  int(record.lineno), src_dir, record, stats)
                            )

            output_path = output_dir / "TARGET.tsv"
            ap.write_tsv(all_records, output_path)

            # 実際の出力と期待値を比較
            actual_lines = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


if __name__ == "__main__":
    unittest.main()
