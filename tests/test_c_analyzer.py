import sys, unittest, tempfile, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_c as ac
import analyze_common


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


class TestBuildDefineMap(unittest.TestCase):
    def test_single_define_alias(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define ALIAS TARGET\n')
            stats = ac.ProcessStats()
            dm = ac._build_define_map(src, stats)
            self.assertEqual(dm.get("ALIAS"), "TARGET")

    def test_ignores_string_literal(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define STATUS "value"\n')
            stats = ac.ProcessStats()
            dm = ac._build_define_map(src, stats)
            self.assertNotIn("STATUS", dm)

    def test_build_define_map_is_cached(self):
        """同一 src_dir への2回目の呼び出しはキャッシュを返す（同一オブジェクト）。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define ALIAS TARGET\n')
            stats = ac.ProcessStats()
            ac._define_map_cache.clear()
            dm1 = ac._build_define_map(src, stats)
            dm2 = ac._build_define_map(src, stats)
            self.assertIs(dm1, dm2)

    def test_build_define_map_cache_keyed_by_encoding(self):
        """encoding が異なる場合は別キャッシュエントリになる。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define ALIAS TARGET\n')
            stats = ac.ProcessStats()
            ac._define_map_cache.clear()
            dm1 = ac._build_define_map(src, stats, encoding_override=None)
            dm2 = ac._build_define_map(src, stats, encoding_override="utf-8")
            # 異なるエンコーディング指定は別キャッシュエントリ（別オブジェクト）
            self.assertIsNot(dm1, dm2)


class TestCollectDefineAliases(unittest.TestCase):
    def test_two_level_chain(self):
        define_map = {"B": "A", "C": "B"}
        aliases = ac._collect_define_aliases("A", define_map)
        self.assertIn("B", aliases)
        self.assertIn("C", aliases)

    def test_circular_reference_guard(self):
        define_map = {"B": "A", "A": "B"}
        aliases = ac._collect_define_aliases("A", define_map)
        self.assertLessEqual(len(aliases), 10)

    def test_no_aliases(self):
        define_map = {"X": "Y"}
        aliases = ac._collect_define_aliases("A", define_map)
        self.assertEqual(aliases, [])


class TestE2EC(unittest.TestCase):
    """E2E統合テスト: sample.c でツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "c"

    def test_e2e_target(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        analyze_common._file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ac.ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = ac.process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = ac.extract_define_name(record.code)
                    if var_name:
                        all_records.extend(ac.track_define(var_name, src_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = ac.extract_variable_name_c(record.code)
                    if var_name:
                        candidate = Path(record.filepath)
                        if not candidate.is_absolute():
                            candidate = src_dir / record.filepath
                        if candidate.exists():
                            all_records.extend(
                                ac.track_variable(var_name, candidate,
                                                  int(record.lineno), src_dir, record, stats)
                            )

            output_path = output_dir / "TARGET.tsv"
            ac.write_tsv(all_records, output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


class TestDefineMapWithReverse(unittest.TestCase):
    def test_collect_aliases_reuses_reverse_map(self):
        """_collect_define_aliases を多数回呼んでも reverse 構築は 1 回。"""
        import analyze_c
        from analyze_c import _collect_define_aliases, _build_define_map, _define_map_cache
        _define_map_cache.clear()
        from analyze_common import ProcessStats
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.h").write_text("#define A1 X\n#define A2 X\n", encoding="utf-8")
            stats = ProcessStats()
            _build_define_map(p, stats)
            calls = {"n": 0}
            orig = analyze_c._build_reverse_define_map  # 新規 API
            def counter(m):
                calls["n"] += 1
                return orig(m)
            analyze_c._build_reverse_define_map = counter
            try:
                for _ in range(50):
                    _collect_define_aliases(
                        "X",
                        _build_define_map(p, stats),
                        reverse=analyze_c._get_reverse_define_map(p, None),
                    )
                self.assertEqual(calls["n"], 0,
                    "reverse map はキャッシュから取得されるはずで、再構築されない")
            finally:
                analyze_c._build_reverse_define_map = orig


if __name__ == "__main__":
    unittest.main()
