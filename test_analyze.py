"""analyze.py のユニットテスト・統合テスト。

実行方法:
    python -m unittest discover -v
    python -m unittest test_analyze.TestGrepParser
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import analyze
from analyze import (
    GrepRecord,
    ProcessStats,
    RefType,
    UsageType,
    _ast_cache,
    _get_method_scope,
    _resolve_java_file,
    _search_in_lines,
    build_parser,
    classify_usage,
    classify_usage_regex,
    determine_scope,
    extract_variable_name,
    find_getter_names,
    parse_grep_line,
    print_report,
    process_grep_file,
    track_constant,
    track_field,
    track_getter_calls,
    track_local,
    write_tsv,
)


# ---------------------------------------------------------------------------
# TestGrepParser
# ---------------------------------------------------------------------------

class TestGrepParser(unittest.TestCase):
    """F-01: parse_grep_line() のテスト。"""

    def test_parse_valid_line_returns_dict(self):
        """正常なgrep行をパースできること。"""
        line = 'src/main/java/Constants.java:10:    public static final String CODE = "TARGET";'
        result = parse_grep_line(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["filepath"], "src/main/java/Constants.java")
        self.assertEqual(result["lineno"], "10")
        self.assertIn("CODE", result["code"])

    def test_parse_binary_notice_line_returns_none(self):
        """バイナリ通知行はNoneを返すこと。"""
        line = "Binary file src/main/resources/logo.png matches"
        self.assertIsNone(parse_grep_line(line))

    def test_parse_empty_line_returns_none(self):
        """空行・空白のみの行はNoneを返すこと。"""
        self.assertIsNone(parse_grep_line(""))
        self.assertIsNone(parse_grep_line("   "))
        self.assertIsNone(parse_grep_line("\n"))

    def test_parse_windows_path_handled(self):
        """Windowsパス（C:\\...）でも正しくパースできること。"""
        line = r"C:\project\src\Constants.java:42:    String s = CODE;"
        result = parse_grep_line(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["lineno"], "42")
        self.assertIn("CODE", result["code"])

    def test_parse_invalid_format_returns_none(self):
        """区切り文字がない不正行はNoneを返すこと。"""
        self.assertIsNone(parse_grep_line("no colon separator here"))

    def test_parse_code_is_stripped(self):
        """コード行の前後の空白がtrimされること。"""
        line = "Foo.java:5:    int x = 1;   "
        result = parse_grep_line(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "int x = 1;")


# ---------------------------------------------------------------------------
# TestUsageClassifier
# ---------------------------------------------------------------------------

class TestUsageClassifier(unittest.TestCase):
    """F-02: classify_usage_regex() の7種分類テスト。"""

    def test_classify_annotation(self):
        """アノテーション行を正しく分類すること。"""
        self.assertEqual(classify_usage_regex('@RequestMapping("TARGET")'), "アノテーション")

    def test_classify_constant_definition(self):
        """static final定数定義を正しく分類すること。"""
        code = 'public static final String CODE = "TARGET";'
        self.assertEqual(classify_usage_regex(code), "定数定義")

    def test_classify_condition_if(self):
        """if文を正しく分類すること。"""
        self.assertEqual(classify_usage_regex('if (x.equals(CODE)) {'), "条件判定")

    def test_classify_condition_equals(self):
        """.equals() を含む行を条件判定と分類すること（returnより優先）。"""
        # 優先度: 条件判定（.equals）> return文 のため、条件判定になる
        self.assertEqual(classify_usage_regex('return a.equals(CODE);'), "条件判定")

    def test_classify_condition_not_equals(self):
        """!= を含む行を条件判定と分類すること。"""
        self.assertEqual(classify_usage_regex('if (x != CODE) {'), "条件判定")

    def test_classify_return(self):
        """return文を正しく分類すること。"""
        self.assertEqual(classify_usage_regex('return CODE;'), "return文")

    def test_classify_variable_assignment(self):
        """変数代入を正しく分類すること。"""
        self.assertEqual(classify_usage_regex('String msg = CODE;'), "変数代入")

    def test_classify_method_argument(self):
        """メソッド引数を正しく分類すること。"""
        self.assertEqual(classify_usage_regex('someService.process(CODE);'), "メソッド引数")

    def test_classify_comment_as_other(self):
        """コメント行を「その他」に分類すること。"""
        self.assertEqual(classify_usage_regex('// TARGET はここで使われる'), "その他")

    def test_classify_annotation_takes_priority_over_constant(self):
        """アノテーションが定数定義より優先されること。"""
        # @SomeAnnotation(static final がある行でもアノテーション優先)
        code = '@Value("${static.final.code}")'
        self.assertEqual(classify_usage_regex(code), "アノテーション")


# ---------------------------------------------------------------------------
# TestTsvWriter
# ---------------------------------------------------------------------------

class TestTsvWriter(unittest.TestCase):
    """F-05: write_tsv() のテスト。"""

    def setUp(self):
        """テスト用の一時ディレクトリを使用。"""
        import tempfile
        self.tmp_dir = tempfile.mkdtemp()
        self.output_path = Path(self.tmp_dir) / "test.tsv"

    def tearDown(self):
        """一時ファイルを削除。"""
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_record(self, keyword="KW", lineno="10", filepath="A.java",
                     ref_type=None, usage_type=None):
        return GrepRecord(
            keyword=keyword,
            ref_type=ref_type or RefType.DIRECT.value,
            usage_type=usage_type or UsageType.CONSTANT.value,
            filepath=filepath,
            lineno=lineno,
            code=f'String x = "{keyword}";',
        )

    def test_write_tsv_creates_file(self):
        """TSVファイルが生成されること。"""
        write_tsv([self._make_record()], self.output_path)
        self.assertTrue(self.output_path.exists())

    def test_write_tsv_utf8_bom_encoding(self):
        """UTF-8 BOM付きで出力されること（Excelで文字化けしない）。"""
        write_tsv([self._make_record()], self.output_path)
        raw = self.output_path.read_bytes()
        # UTF-8 BOM は EF BB BF
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'), "BOMが先頭にない")

    def test_write_tsv_header_columns(self):
        """ヘッダー行が9列正しく出力されること。"""
        write_tsv([self._make_record()], self.output_path)
        with open(self.output_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader)
        expected = ["文言", "参照種別", "使用タイプ", "ファイルパス", "行番号",
                    "コード行", "参照元変数名", "参照元ファイル", "参照元行番号"]
        self.assertEqual(header, expected)

    def test_write_tsv_sort_order_numeric_lineno(self):
        """行番号が数値順にソートされること（"10" < "9" のバグがないこと）。"""
        records = [
            self._make_record(lineno="10"),
            self._make_record(lineno="9"),
            self._make_record(lineno="2"),
        ]
        write_tsv(records, self.output_path)
        with open(self.output_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader)  # ヘッダーをスキップ
            rows = list(reader)
        linenos = [r[4] for r in rows]
        self.assertEqual(linenos, ["2", "9", "10"])

    def test_write_tsv_sort_order_keyword_then_filepath(self):
        """文言 → ファイルパス → 行番号の順にソートされること。"""
        records = [
            self._make_record(keyword="ZZZ", filepath="B.java", lineno="1"),
            self._make_record(keyword="AAA", filepath="C.java", lineno="1"),
            self._make_record(keyword="AAA", filepath="A.java", lineno="1"),
        ]
        write_tsv(records, self.output_path)
        with open(self.output_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader)
            rows = list(reader)
        keywords = [r[0] for r in rows]
        filepaths = [r[3] for r in rows]
        self.assertEqual(keywords, ["AAA", "AAA", "ZZZ"])
        self.assertEqual(filepaths[:2], ["A.java", "C.java"])

    def test_write_tsv_output_dir_autocreated(self):
        """output/ ディレクトリが存在しなくても自動作成されること。"""
        nested_path = Path(self.tmp_dir) / "new_dir" / "sub" / "out.tsv"
        write_tsv([self._make_record()], nested_path)
        self.assertTrue(nested_path.exists())


# ---------------------------------------------------------------------------
# TestIndirectTracker
# ---------------------------------------------------------------------------

class TestIndirectTracker(unittest.TestCase):
    """F-03: determine_scope() / extract_variable_name() のテスト。"""

    def test_determine_scope_constant_returns_project(self):
        """定数定義は project スコープになること。"""
        self.assertEqual(
            determine_scope(UsageType.CONSTANT.value, 'public static final String CODE = "X";'),
            "project",
        )

    def test_determine_scope_field_returns_class(self):
        """アクセス修飾子付きフィールドは class スコープになること。"""
        self.assertEqual(
            determine_scope(UsageType.VARIABLE.value, 'private String type = "X";'),
            "class",
        )

    def test_determine_scope_local_variable_returns_method(self):
        """ローカル変数は method スコープになること（正規表現フォールバック）。"""
        # AST 未使用（filepath 省略）の場合は正規表現で判定される
        result = determine_scope(UsageType.VARIABLE.value, 'String msg = CODE;')
        # 修飾子なしのローカル変数は正規表現では method になる
        self.assertEqual(result, "method")

    def test_determine_scope_package_private_field_returns_class(self):
        """パッケージプライベートフィールド（修飾子なし）が class スコープになること。"""
        java_dir = Path(__file__).parent / "tests" / "fixtures" / "java"
        if not java_dir.exists():
            self.skipTest("フィクスチャが存在しません。")
        # Entity.java の `private String type = "SAMPLE";`（行8）は class スコープ
        result = determine_scope(
            UsageType.VARIABLE.value,
            'private String type = "SAMPLE";',
            "tests/fixtures/java/Entity.java",
            java_dir,
            8,
        )
        self.assertEqual(result, "class")

    def test_extract_variable_name_static_final(self):
        """static final 定数名を正しく抽出できること。"""
        code = 'public static final String CODE = "TARGET";'
        self.assertEqual(extract_variable_name(code, UsageType.CONSTANT.value), "CODE")

    def test_extract_variable_name_simple_assignment(self):
        """シンプルな変数代入から変数名を抽出できること。"""
        code = 'String msg = CODE;'
        self.assertEqual(extract_variable_name(code, UsageType.VARIABLE.value), "msg")

    def test_extract_variable_name_private_field(self):
        """private フィールドから変数名を抽出できること。"""
        code = 'private String type;'
        self.assertEqual(extract_variable_name(code, UsageType.VARIABLE.value), "type")

    def test_extract_variable_name_invalid_returns_none(self):
        """変数宣言でない行（条件文など）は None を返すこと。"""
        result = extract_variable_name('if (x.equals(CODE)) {', UsageType.CONDITION.value)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TestReporter
# ---------------------------------------------------------------------------

class TestReporter(unittest.TestCase):
    """F-06: print_report() のテスト。"""

    def _capture_report(self, stats: ProcessStats, files: list) -> str:
        """print_report() の標準出力をキャプチャして返す。"""
        from io import StringIO
        from unittest.mock import patch
        with patch('sys.stdout', new_callable=StringIO) as mock_out:
            print_report(stats, files)
            return mock_out.getvalue()

    def test_print_report_outputs_summary(self):
        """処理サマリが標準出力に出力されること。"""
        stats = ProcessStats(total_lines=10, valid_lines=8, skipped_lines=2)
        output = self._capture_report(stats, ["SAMPLE.grep"])
        self.assertIn("処理完了", output)
        self.assertIn("SAMPLE.grep", output)
        self.assertIn("10", output)
        self.assertIn("8", output)
        self.assertIn("2", output)

    def test_print_report_shows_fallback_files(self):
        """ASTフォールバックしたファイルが表示されること。"""
        stats = ProcessStats(fallback_files=["Foo.java", "Bar.java"])
        output = self._capture_report(stats, [])
        self.assertIn("ASTフォールバック", output)
        self.assertIn("Foo.java", output)
        self.assertIn("Bar.java", output)

    def test_print_report_shows_encoding_errors(self):
        """エンコーディングエラーのファイルが表示されること。"""
        stats = ProcessStats(encoding_errors=["Baz.java"])
        output = self._capture_report(stats, [])
        self.assertIn("エンコーディングエラー", output)
        self.assertIn("Baz.java", output)

    def test_print_report_no_optional_sections_when_empty(self):
        """フォールバック・エンコーディングエラーが0件のとき任意セクションが出力されないこと。"""
        stats = ProcessStats(total_lines=5, valid_lines=5, skipped_lines=0)
        output = self._capture_report(stats, ["X.grep"])
        self.assertNotIn("ASTフォールバック", output)
        self.assertNotIn("エンコーディングエラー", output)


# ---------------------------------------------------------------------------
# TestIntegration
# ---------------------------------------------------------------------------

class TestIntegration(unittest.TestCase):
    """E2E統合テスト。フィクスチャを使って直接参照の出力を検証する。"""

    FIXTURES_DIR = Path(__file__).parent / "tests" / "fixtures"

    def setUp(self):
        """フィクスチャの存在確認。"""
        if not self.FIXTURES_DIR.exists():
            self.skipTest("tests/fixtures/ が存在しません。統合テストをスキップします。")

    def test_full_flow_produces_expected_tsv(self):
        """直接参照がTSVに正しく出力されることを確認。"""
        import subprocess
        import tempfile

        input_dir = self.FIXTURES_DIR / "input"
        java_dir = self.FIXTURES_DIR / "java"
        expected_tsv = self.FIXTURES_DIR / "expected" / "SAMPLE.tsv"

        if not input_dir.exists() or not java_dir.exists() or not expected_tsv.exists():
            self.skipTest("統合テスト用フィクスチャが不完全です。")

        with tempfile.TemporaryDirectory() as tmp_out:
            project_root = Path(__file__).parent
            result = subprocess.run(
                [
                    sys.executable, str(project_root / "analyze.py"),
                    "--source-dir", str(java_dir),
                    "--input-dir", str(input_dir),
                    "--output-dir", tmp_out,
                ],
                capture_output=True,
                text=True,
                cwd=str(project_root),
            )
            self.assertEqual(result.returncode, 0, f"analyze.py が失敗しました:\n{result.stderr}")

            actual_tsv = Path(tmp_out) / "SAMPLE.tsv"
            self.assertTrue(actual_tsv.exists(), "出力TSVが生成されませんでした。")

            # 期待TSVと比較（ヘッダー行 + データ行）
            with open(expected_tsv, encoding="utf-8-sig", newline="") as f:
                expected_rows = list(csv.reader(f, delimiter="\t"))
            with open(actual_tsv, encoding="utf-8-sig", newline="") as f:
                actual_rows = list(csv.reader(f, delimiter="\t"))

            self.assertEqual(
                actual_rows[0], expected_rows[0],
                "ヘッダー行が一致しません。"
            )

            def normalize(row: list[str]) -> list[str]:
                """末尾の空文字列を除去して列数を正規化する。"""
                while row and row[-1] == "":
                    row = row[:-1]
                return row

            normalized_actual = [normalize(r) for r in actual_rows]
            # 期待する直接参照行（ヘッダー除く）が実際の出力に含まれることを確認
            # 間接参照追加により行数が増える場合があるため、行ごとに存在チェックする
            for expected_row in expected_rows[1:]:
                self.assertIn(
                    normalize(expected_row), normalized_actual,
                    f"期待する行が出力に含まれていません: {expected_row}",
                )


# ---------------------------------------------------------------------------
# TestProcessGrepFile
# ---------------------------------------------------------------------------

class TestProcessGrepFile(unittest.TestCase):
    """F-01: process_grep_file() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        _ast_cache.clear()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        _ast_cache.clear()

    def _write_grep(self, lines: list[str]) -> Path:
        p = Path(self.tmp_dir) / "KW.grep"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_valid_line_creates_record(self):
        """有効なgrep行からGrepRecordが生成されること。"""
        path = self._write_grep([
            "tests/fixtures/java/Constants.java:9:    public static final String SAMPLE_CODE = \"SAMPLE\";"
        ])
        stats = ProcessStats()
        records = process_grep_file(path, "KW", self.JAVA_DIR, stats)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].keyword, "KW")
        self.assertEqual(records[0].ref_type, RefType.DIRECT.value)
        self.assertEqual(stats.valid_lines, 1)

    def test_empty_line_skipped(self):
        """空行はスキップされ、skipped_lines が増加すること。"""
        path = self._write_grep([""])
        stats = ProcessStats()
        records = process_grep_file(path, "KW", self.JAVA_DIR, stats)
        self.assertEqual(len(records), 0)
        self.assertEqual(stats.skipped_lines, 1)

    def test_binary_line_skipped(self):
        """バイナリ通知行はスキップされること。"""
        path = self._write_grep(["Binary file foo.class matches"])
        stats = ProcessStats()
        records = process_grep_file(path, "KW", self.JAVA_DIR, stats)
        self.assertEqual(len(records), 0)
        self.assertEqual(stats.skipped_lines, 1)

    def test_multiple_lines_processed(self):
        """複数行が全て処理されること。"""
        path = self._write_grep([
            "tests/fixtures/java/Constants.java:9:    public static final String SAMPLE_CODE = \"SAMPLE\";",
            "tests/fixtures/java/Constants.java:13:        if (value.equals(SAMPLE_CODE)) {",
            "",
        ])
        stats = ProcessStats()
        records = process_grep_file(path, "KW", self.JAVA_DIR, stats)
        self.assertEqual(len(records), 2)
        self.assertEqual(stats.total_lines, 3)
        self.assertEqual(stats.valid_lines, 2)
        self.assertEqual(stats.skipped_lines, 1)

    def test_nonexistent_java_file_falls_back_to_regex(self):
        """存在しないJavaファイルでもフォールバックして処理が継続すること。"""
        path = self._write_grep([
            "nonexistent/Foo.java:5:    return CODE;"
        ])
        stats = ProcessStats()
        records = process_grep_file(path, "KW", self.JAVA_DIR, stats)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].usage_type, "return文")


# ---------------------------------------------------------------------------
# TestGetAst
# ---------------------------------------------------------------------------

class TestGetAst(unittest.TestCase):
    """F-02: get_ast() とASTキャッシュのテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def test_valid_file_returns_tree(self):
        """有効なJavaファイルはASTツリーを返すこと。"""
        from analyze import get_ast, _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        tree = get_ast("Constants.java", self.JAVA_DIR)
        self.assertIsNotNone(tree)

    def test_nonexistent_file_returns_none(self):
        """存在しないファイルはNoneを返すこと。"""
        from analyze import get_ast
        result = get_ast("nonexistent/Foo.java", self.JAVA_DIR)
        self.assertIsNone(result)

    def test_cache_hit_avoids_reparse(self):
        """2回目の呼び出しはキャッシュから取得すること（再パース不要）。"""
        from analyze import get_ast, _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        filepath = "Constants.java"
        tree1 = get_ast(filepath, self.JAVA_DIR)
        tree2 = get_ast(filepath, self.JAVA_DIR)
        self.assertIs(tree1, tree2, "キャッシュから同一オブジェクトが返るべき")

    def test_nonexistent_file_cached_as_none(self):
        """存在しないファイルはNoneとしてキャッシュされること。"""
        from analyze import get_ast, _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        get_ast("ghost.java", self.JAVA_DIR)
        self.assertIn("ghost.java", _ast_cache)
        self.assertIsNone(_ast_cache["ghost.java"])


# ---------------------------------------------------------------------------
# TestClassifyUsage
# ---------------------------------------------------------------------------

class TestClassifyUsage(unittest.TestCase):
    """F-02: classify_usage() と _classify_by_ast() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def test_classify_usage_with_valid_file_constant(self):
        """ASTが使えるファイルで定数定義を正しく分類すること。"""
        from analyze import _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        stats = ProcessStats()
        result = classify_usage(
            code='public static final String SAMPLE_CODE = "SAMPLE";',
            filepath="Constants.java",
            lineno=9,
            source_dir=self.JAVA_DIR,
            stats=stats,
        )
        self.assertEqual(result, UsageType.CONSTANT.value)

    def test_classify_usage_with_valid_file_condition(self):
        """ASTが使えるファイルで条件判定を正しく分類すること。"""
        from analyze import _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        stats = ProcessStats()
        result = classify_usage(
            code="if (value.equals(SAMPLE_CODE)) {",
            filepath="Constants.java",
            lineno=13,
            source_dir=self.JAVA_DIR,
            stats=stats,
        )
        self.assertEqual(result, UsageType.CONDITION.value)

    def test_classify_usage_nonexistent_file_uses_fallback(self):
        """存在しないファイルは正規表現フォールバックで分類すること。"""
        stats = ProcessStats()
        result = classify_usage(
            code="return CODE;",
            filepath="ghost.java",
            lineno=1,
            source_dir=self.JAVA_DIR,
            stats=stats,
        )
        self.assertEqual(result, "return文")

    def test_classify_usage_return_statement(self):
        """ASTが使えるファイルでreturn文を正しく分類すること。"""
        from analyze import _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        stats = ProcessStats()
        result = classify_usage(
            code="return SAMPLE_CODE;",
            filepath="Constants.java",
            lineno=21,
            source_dir=self.JAVA_DIR,
            stats=stats,
        )
        self.assertEqual(result, UsageType.RETURN.value)

    def test_classify_usage_fallback_recorded_in_stats(self):
        """フォールバック発生時にstats.fallback_filesに記録されること。"""
        from analyze import _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        stats = ProcessStats()
        classify_usage(
            code="return CODE;",
            filepath="ghost.java",
            lineno=1,
            source_dir=self.JAVA_DIR,
            stats=stats,
        )
        self.assertIn("ghost.java", stats.fallback_files)


# ---------------------------------------------------------------------------
# TestResolveJavaFile
# ---------------------------------------------------------------------------

class TestResolveJavaFile(unittest.TestCase):
    """F-03 内部: _resolve_java_file() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def test_relative_path_resolves(self):
        """相対パス（source_dir基準）が解決されること。"""
        result = _resolve_java_file("Constants.java", self.JAVA_DIR)
        self.assertIsNotNone(result)
        self.assertTrue(result.exists())

    def test_absolute_path_resolves(self):
        """絶対パスが解決されること。"""
        abs_path = str((self.JAVA_DIR / "Constants.java").resolve())
        result = _resolve_java_file(abs_path, self.JAVA_DIR)
        self.assertIsNotNone(result)

    def test_nonexistent_relative_returns_none(self):
        """存在しない相対パスはNoneを返すこと。"""
        result = _resolve_java_file("ghost/Missing.java", self.JAVA_DIR)
        self.assertIsNone(result)

    def test_nonexistent_absolute_returns_none(self):
        """存在しない絶対パスはNoneを返すこと。"""
        result = _resolve_java_file("/nonexistent/path/Foo.java", self.JAVA_DIR)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TestGetMethodScope
# ---------------------------------------------------------------------------

class TestGetMethodScope(unittest.TestCase):
    """F-03 内部: _get_method_scope() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def test_line_in_method_returns_range(self):
        """メソッド内の行番号を渡すと (start, end) タプルが返ること。"""
        from analyze import _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        # Constants.java: isSample メソッドは12行目から始まる（source_dir基準の相対パス）
        result = _get_method_scope("Constants.java", self.JAVA_DIR, 13)
        self.assertIsNotNone(result)
        start, end = result
        self.assertLessEqual(start, 13)
        self.assertGreaterEqual(end, 13)

    def test_nonexistent_file_returns_none(self):
        """存在しないファイルはNoneを返すこと。"""
        result = _get_method_scope("ghost.java", self.JAVA_DIR, 5)
        self.assertIsNone(result)

    def test_line_before_any_method_returns_none(self):
        """メソッドより前の行はNoneを返すこと。"""
        from analyze import _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        result = _get_method_scope("Constants.java", self.JAVA_DIR, 1)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TestSearchInLines
# ---------------------------------------------------------------------------

class TestSearchInLines(unittest.TestCase):
    """F-03 内部: _search_in_lines() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def _make_origin(self, filepath="A.java", lineno="5"):
        return GrepRecord(
            keyword="KW",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.CONSTANT.value,
            filepath=filepath,
            lineno=lineno,
            code="code",
        )

    def test_finds_matching_line(self):
        """変数名を含む行がGrepRecordとして返ること。"""
        lines = [
            "// some comment",
            "String x = MY_VAR;",
            "int y = 0;",
        ]
        origin = self._make_origin()
        stats = ProcessStats()
        records = _search_in_lines(
            lines=lines,
            var_name="MY_VAR",
            start_line=1,
            origin=origin,
            source_dir=self.JAVA_DIR,
            ref_type=RefType.INDIRECT.value,
            stats=stats,
            filepath_for_record="Some.java",
        )
        self.assertEqual(len(records), 1)
        self.assertIn("MY_VAR", records[0].code)
        self.assertEqual(records[0].ref_type, RefType.INDIRECT.value)

    def test_skips_origin_line(self):
        """origin と同じファイル・行番号の行はスキップされること。"""
        lines = ["String x = MY_VAR;"]
        origin = self._make_origin(filepath="A.java", lineno="1")
        stats = ProcessStats()
        records = _search_in_lines(
            lines=lines,
            var_name="MY_VAR",
            start_line=1,
            origin=origin,
            source_dir=self.JAVA_DIR,
            ref_type=RefType.INDIRECT.value,
            stats=stats,
            filepath_for_record="A.java",
        )
        self.assertEqual(len(records), 0)

    def test_word_boundary_only(self):
        """変数名が単語境界でマッチすること（部分一致しないこと）。"""
        lines = ["MY_VARIABLE_EXTRA = 1;", "MY_VAR = 2;"]
        origin = self._make_origin()
        stats = ProcessStats()
        records = _search_in_lines(
            lines=lines,
            var_name="MY_VAR",
            start_line=1,
            origin=origin,
            source_dir=self.JAVA_DIR,
            ref_type=RefType.INDIRECT.value,
            stats=stats,
            filepath_for_record="B.java",
        )
        # MY_VARIABLE_EXTRA には MY_VAR が単語境界でマッチしない
        # MY_VAR = 2; にはマッチする
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].lineno, "2")


# ---------------------------------------------------------------------------
# TestTrackConstant
# ---------------------------------------------------------------------------

class TestTrackConstant(unittest.TestCase):
    """F-03: track_constant() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def test_finds_usages_in_project(self):
        """定数名がプロジェクト全体から検索されること。"""
        origin = GrepRecord(
            keyword="SAMPLE",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.CONSTANT.value,
            filepath=str(self.JAVA_DIR / "Constants.java"),
            lineno="9",
            code='public static final String SAMPLE_CODE = "SAMPLE";',
        )
        stats = ProcessStats()
        records = track_constant("SAMPLE_CODE", self.JAVA_DIR, origin, stats)
        # Constants.java 内と Service.java 内に使用箇所がある
        filepaths = [r.filepath for r in records]
        self.assertTrue(
            any("Constants.java" in fp or "Service.java" in fp for fp in filepaths),
            f"期待するファイルが見つかりません: {filepaths}",
        )

    def test_returns_indirect_ref_type(self):
        """返されるレコードの参照種別が '間接' であること。"""
        origin = GrepRecord(
            keyword="SAMPLE",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.CONSTANT.value,
            filepath=str(self.JAVA_DIR / "Constants.java"),
            lineno="9",
            code='public static final String SAMPLE_CODE = "SAMPLE";',
        )
        stats = ProcessStats()
        records = track_constant("SAMPLE_CODE", self.JAVA_DIR, origin, stats)
        for r in records:
            self.assertEqual(r.ref_type, RefType.INDIRECT.value)


# ---------------------------------------------------------------------------
# TestTrackField
# ---------------------------------------------------------------------------

class TestTrackField(unittest.TestCase):
    """F-03: track_field() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def test_finds_field_usage_in_class(self):
        """フィールドが同一クラス内で見つかること。"""
        entity_file = self.JAVA_DIR / "Entity.java"
        if not entity_file.exists():
            self.skipTest("Entity.java フィクスチャが存在しません。")
        origin = GrepRecord(
            keyword="SAMPLE",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.VARIABLE.value,
            filepath=str(entity_file),
            lineno="8",
            code='private String type = "SAMPLE";',
        )
        stats = ProcessStats()
        records = track_field("type", entity_file, origin, self.JAVA_DIR, stats)
        # Entity.java には `return type;` がある
        codes = [r.code for r in records]
        self.assertTrue(
            any("type" in c for c in codes),
            f"'type' を含む行が見つかりません: {codes}",
        )

    def test_returns_indirect_ref_type(self):
        """返されるレコードの参照種別が '間接' であること。"""
        entity_file = self.JAVA_DIR / "Entity.java"
        if not entity_file.exists():
            self.skipTest("Entity.java フィクスチャが存在しません。")
        origin = GrepRecord(
            keyword="SAMPLE",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.VARIABLE.value,
            filepath=str(entity_file),
            lineno="8",
            code='private String type = "SAMPLE";',
        )
        stats = ProcessStats()
        records = track_field("type", entity_file, origin, self.JAVA_DIR, stats)
        for r in records:
            self.assertEqual(r.ref_type, RefType.INDIRECT.value)


# ---------------------------------------------------------------------------
# TestTrackLocal
# ---------------------------------------------------------------------------

class TestTrackLocal(unittest.TestCase):
    """F-03: track_local() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        _ast_cache.clear()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        _ast_cache.clear()

    def test_finds_local_var_within_scope(self):
        """ローカル変数がメソッドスコープ内で見つかること。"""
        # 一時Javaファイルを作成
        java_src = (
            "public class Tmp {\n"
            "    public void run() {\n"
            "        String msg = \"hello\";\n"
            "        System.out.println(msg);\n"
            "    }\n"
            "}\n"
        )
        java_file = Path(self.tmp_dir) / "Tmp.java"
        java_file.write_text(java_src, encoding="utf-8")
        java_dir = Path(self.tmp_dir)

        origin = GrepRecord(
            keyword="hello",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.VARIABLE.value,
            filepath=str(java_file),
            lineno="3",
            code='String msg = "hello";',
        )
        stats = ProcessStats()
        records = track_local("msg", (2, 5), origin, java_dir, stats)
        codes = [r.code for r in records]
        self.assertTrue(
            any("msg" in c for c in codes),
            f"'msg' を含む行が見つかりません: {codes}",
        )

    def test_nonexistent_file_returns_empty(self):
        """存在しないファイルは空リストを返すこと。"""
        origin = GrepRecord(
            keyword="KW",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.VARIABLE.value,
            filepath="ghost.java",
            lineno="3",
            code='String x = "KW";',
        )
        stats = ProcessStats()
        records = track_local("x", (2, 5), origin, Path(self.tmp_dir), stats)
        self.assertEqual(records, [])


# ---------------------------------------------------------------------------
# TestFindGetterNames
# ---------------------------------------------------------------------------

class TestFindGetterNames(unittest.TestCase):
    """F-04: find_getter_names() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def test_convention_based_getter(self):
        """命名規則によるgetter候補が含まれること。"""
        entity_file = self.JAVA_DIR / "Entity.java"
        if not entity_file.exists():
            self.skipTest("Entity.java フィクスチャが存在しません。")
        getters = find_getter_names("type", entity_file)
        self.assertIn("getType", getters)

    def test_ast_based_getter_detection(self):
        """Entity.javaの `return type;` から getType が見つかること。"""
        from analyze import _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        entity_file = self.JAVA_DIR / "Entity.java"
        if not entity_file.exists():
            self.skipTest("Entity.java フィクスチャが存在しません。")
        getters = find_getter_names("type", entity_file)
        self.assertIn("getType", getters)

    def test_no_duplicates_in_result(self):
        """重複したgetter名が含まれないこと。"""
        entity_file = self.JAVA_DIR / "Entity.java"
        if not entity_file.exists():
            self.skipTest("Entity.java フィクスチャが存在しません。")
        getters = find_getter_names("type", entity_file)
        self.assertEqual(len(getters), len(set(getters)))

    def test_nonexistent_file_returns_convention(self):
        """存在しないファイルでも命名規則のgetter候補は返ること。"""
        getters = find_getter_names("name", Path("/nonexistent/Foo.java"))
        self.assertIn("getName", getters)


# ---------------------------------------------------------------------------
# TestTrackGetterCalls
# ---------------------------------------------------------------------------

class TestTrackGetterCalls(unittest.TestCase):
    """F-04: track_getter_calls() のテスト。"""

    JAVA_DIR = Path(__file__).parent / "tests" / "fixtures" / "java"

    def setUp(self):
        _ast_cache.clear()

    def tearDown(self):
        _ast_cache.clear()

    def test_finds_getter_call_in_service(self):
        """Service.java の getType() 呼び出しが検出されること。"""
        service_file = self.JAVA_DIR / "Service.java"
        entity_file = self.JAVA_DIR / "Entity.java"
        if not service_file.exists() or not entity_file.exists():
            self.skipTest("フィクスチャが存在しません。")
        origin = GrepRecord(
            keyword="SAMPLE",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.VARIABLE.value,
            filepath=str(entity_file),
            lineno="8",
            code='private String type = "SAMPLE";',
        )
        stats = ProcessStats()
        records = track_getter_calls("getType", self.JAVA_DIR, origin, stats)
        filepaths = [r.filepath for r in records]
        self.assertTrue(
            any("Service.java" in fp for fp in filepaths),
            f"Service.java が見つかりません: {filepaths}",
        )

    def test_returns_getter_ref_type(self):
        """返されるレコードの参照種別が '間接（getter経由）' であること。"""
        entity_file = self.JAVA_DIR / "Entity.java"
        if not entity_file.exists():
            self.skipTest("Entity.java フィクスチャが存在しません。")
        origin = GrepRecord(
            keyword="SAMPLE",
            ref_type=RefType.DIRECT.value,
            usage_type=UsageType.VARIABLE.value,
            filepath=str(entity_file),
            lineno="8",
            code='private String type = "SAMPLE";',
        )
        stats = ProcessStats()
        records = track_getter_calls("getType", self.JAVA_DIR, origin, stats)
        for r in records:
            self.assertEqual(r.ref_type, RefType.GETTER.value)


# ---------------------------------------------------------------------------
# TestBuildParser
# ---------------------------------------------------------------------------

class TestBuildParser(unittest.TestCase):
    """CLI: build_parser() のテスト。"""

    def test_source_dir_required(self):
        """--source-dir が必須であること。"""
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_defaults(self):
        """デフォルト値が設定されること。"""
        parser = build_parser()
        args = parser.parse_args(["--source-dir", "/tmp/src"])
        self.assertEqual(args.source_dir, "/tmp/src")
        self.assertEqual(args.input_dir, "input")
        self.assertEqual(args.output_dir, "output")

    def test_all_options(self):
        """全オプションを指定できること。"""
        parser = build_parser()
        args = parser.parse_args([
            "--source-dir", "/src",
            "--input-dir", "/in",
            "--output-dir", "/out",
        ])
        self.assertEqual(args.source_dir, "/src")
        self.assertEqual(args.input_dir, "/in")
        self.assertEqual(args.output_dir, "/out")


# ---------------------------------------------------------------------------
# TestMain
# ---------------------------------------------------------------------------

class TestMain(unittest.TestCase):
    """main() のエンドツーエンドテスト。"""

    FIXTURES_DIR = Path(__file__).parent / "tests" / "fixtures"
    JAVA_DIR = FIXTURES_DIR / "java"
    INPUT_DIR = FIXTURES_DIR / "input"

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        _ast_cache.clear()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        _ast_cache.clear()

    def _run_main(self, args: list[str]) -> tuple[int, str, str]:
        """sys.argv を差し替えて main() を実行し (returncode, stdout, stderr) を返す。"""
        from io import StringIO
        from unittest.mock import patch
        out_buf = StringIO()
        err_buf = StringIO()
        with patch("sys.argv", ["analyze.py"] + args), \
                patch("sys.stdout", out_buf), \
                patch("sys.stderr", err_buf):
            try:
                analyze.main()
                returncode = 0
            except SystemExit as e:
                returncode = int(e.code) if e.code is not None else 0
        return returncode, out_buf.getvalue(), err_buf.getvalue()

    def test_main_success(self):
        """正常な引数で main() がゼロ終了し TSV を生成すること。"""
        if not self.INPUT_DIR.exists() or not self.JAVA_DIR.exists():
            self.skipTest("フィクスチャが存在しません。")
        rc, out, _ = self._run_main([
            "--source-dir", str(self.JAVA_DIR),
            "--input-dir", str(self.INPUT_DIR),
            "--output-dir", self.tmp_dir,
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((Path(self.tmp_dir) / "SAMPLE.tsv").exists())
        self.assertIn("処理完了", out)

    def test_main_invalid_source_dir_exits_1(self):
        """存在しない --source-dir で sys.exit(1) になること。"""
        rc, _, err = self._run_main([
            "--source-dir", "/nonexistent/dir",
            "--input-dir", str(self.INPUT_DIR),
            "--output-dir", self.tmp_dir,
        ])
        self.assertEqual(rc, 1)
        self.assertIn("source-dir", err)

    def test_main_invalid_input_dir_exits_1(self):
        """存在しない --input-dir で sys.exit(1) になること。"""
        rc, _, err = self._run_main([
            "--source-dir", str(self.JAVA_DIR),
            "--input-dir", "/nonexistent/input",
            "--output-dir", self.tmp_dir,
        ])
        self.assertEqual(rc, 1)
        self.assertIn("input-dir", err)

    def test_main_empty_input_dir_exits_1(self):
        """grep ファイルが 0 件の --input-dir で sys.exit(1) になること。"""
        empty_dir = Path(self.tmp_dir) / "empty_input"
        empty_dir.mkdir()
        rc, _, err = self._run_main([
            "--source-dir", str(self.JAVA_DIR),
            "--input-dir", str(empty_dir),
            "--output-dir", self.tmp_dir,
        ])
        self.assertEqual(rc, 1)
        self.assertIn("grep結果ファイルがありません", err)

    def test_main_processes_grep_file(self):
        """main() が grep ファイルを処理して直接参照を TSV に出力すること。"""
        if not self.INPUT_DIR.exists() or not self.JAVA_DIR.exists():
            self.skipTest("フィクスチャが存在しません。")
        rc, out, _ = self._run_main([
            "--source-dir", str(self.JAVA_DIR),
            "--input-dir", str(self.INPUT_DIR),
            "--output-dir", self.tmp_dir,
        ])
        self.assertEqual(rc, 0)
        tsv = Path(self.tmp_dir) / "SAMPLE.tsv"
        with open(tsv, encoding="utf-8-sig", newline="") as f:
            content = f.read()
        self.assertIn("SAMPLE", content)
        self.assertIn("直接", content)


# ---------------------------------------------------------------------------
# TestGetAstExceptionHandling
# ---------------------------------------------------------------------------

class TestGetAstExceptionHandling(unittest.TestCase):
    """get_ast() の例外処理テスト。"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        _ast_cache.clear()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        _ast_cache.clear()

    def test_invalid_java_syntax_returns_none(self):
        """構文エラーのあるJavaファイルはNoneを返しキャッシュされること。"""
        from analyze import get_ast, _JAVALANG_AVAILABLE
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        bad_file = Path(self.tmp_dir) / "Bad.java"
        bad_file.write_text("this is not valid java { { {", encoding="utf-8")
        java_dir = Path(self.tmp_dir)
        result = get_ast("Bad.java", java_dir)
        self.assertIsNone(result)
        self.assertIn("Bad.java", _ast_cache)
        self.assertIsNone(_ast_cache["Bad.java"])


# ---------------------------------------------------------------------------
# TestIntenseE2E
# ---------------------------------------------------------------------------

class TestIntenseE2E(unittest.TestCase):
    """過激な統合テスト。

    重厚長大なマルチモジュール Java プロジェクトを模したフィクスチャを使い、
    GrepParser → UsageClassifier → IndirectTracker → GetterTracker → TsvWriter
    の全パイプラインを通して正確に動作することを検証する。

    javalang なしでも実行可能（正規表現フォールバックで全機能を検証）。
    """

    INTENSE_DIR = Path(__file__).parent / "tests" / "fixtures" / "intense"
    JAVA_DIR    = INTENSE_DIR / "java"
    GREP_DIR    = INTENSE_DIR / "grep"

    def setUp(self):
        import shutil as _shutil
        self._shutil = _shutil
        self.output_dir = Path(tempfile.mkdtemp())
        _ast_cache.clear()

    def tearDown(self):
        self._shutil.rmtree(self.output_dir, ignore_errors=True)
        _ast_cache.clear()

    # ------------------------------------------------------------------
    # ヘルパー
    # ------------------------------------------------------------------

    def _run_pipeline(
        self, grep_filename: str
    ) -> tuple[list[GrepRecord], list[GrepRecord], ProcessStats]:
        """指定 grep ファイルで全パイプラインを実行し (direct, all, stats) を返す。"""
        grep_path = self.GREP_DIR / grep_filename
        keyword   = grep_path.stem
        stats     = ProcessStats()

        direct_records = process_grep_file(grep_path, keyword, self.JAVA_DIR, stats)
        all_records: list[GrepRecord] = list(direct_records)

        for record in direct_records:
            if record.usage_type not in (UsageType.CONSTANT.value, UsageType.VARIABLE.value):
                continue

            var_name = extract_variable_name(record.code, record.usage_type)
            if not var_name:
                continue

            scope = determine_scope(
                record.usage_type, record.code,
                record.filepath, self.JAVA_DIR, int(record.lineno),
            )

            if scope == "project":
                all_records.extend(
                    track_constant(var_name, self.JAVA_DIR, record, stats)
                )
            elif scope == "class":
                class_file = _resolve_java_file(record.filepath, self.JAVA_DIR)
                if class_file:
                    indirect = track_field(var_name, class_file, record, self.JAVA_DIR, stats)
                    all_records.extend(indirect)
                    for getter_name in find_getter_names(var_name, class_file):
                        all_records.extend(
                            track_getter_calls(getter_name, self.JAVA_DIR, record, stats)
                        )
            elif scope == "method":
                method_scope = _get_method_scope(record.filepath, self.JAVA_DIR, int(record.lineno))
                if method_scope:
                    all_records.extend(
                        track_local(var_name, method_scope, record, self.JAVA_DIR, stats)
                    )

        return direct_records, all_records, stats

    def _run_main(self, extra_args: list[str]) -> tuple[int, str, str]:
        """sys.argv を差し替えて main() を実行し (returncode, stdout, stderr) を返す。"""
        from io import StringIO
        from unittest.mock import patch
        out_buf = StringIO()
        err_buf = StringIO()
        with patch("sys.argv", ["analyze.py"] + extra_args), \
                patch("sys.stdout", out_buf), \
                patch("sys.stderr", err_buf):
            try:
                analyze.main()
                returncode = 0
            except SystemExit as e:
                returncode = int(e.code) if e.code is not None else 0
        return returncode, out_buf.getvalue(), err_buf.getvalue()

    # ------------------------------------------------------------------
    # フィクスチャ存在チェック
    # ------------------------------------------------------------------

    def test_fixtures_exist(self):
        """フィクスチャディレクトリ・Java ファイル・grep ファイルが揃っていること。"""
        self.assertTrue(self.JAVA_DIR.exists(), f"JAVA_DIR が存在しない: {self.JAVA_DIR}")
        self.assertTrue(self.GREP_DIR.exists(), f"GREP_DIR が存在しない: {self.GREP_DIR}")

        expected_java_files = [
            "com/example/constants/AppConstants.java",
            "com/example/constants/ErrorCodes.java",
            "com/example/constants/MessageKeys.java",
            "com/example/domain/Order.java",
            "com/example/domain/OrderItem.java",
            "com/example/domain/OrderStatus.java",
            "com/example/service/OrderService.java",
            "com/example/service/ValidationService.java",
            "com/example/service/NotificationService.java",
            "com/example/repository/OrderRepository.java",
            "com/example/util/CodeConverter.java",
        ]
        for rel_path in expected_java_files:
            full = self.JAVA_DIR / rel_path
            self.assertTrue(full.exists(), f"Java フィクスチャが存在しない: {rel_path}")

        expected_grep_files = ["ORDER_TYPE_NORMAL.grep", "orderStatus.grep"]
        for gf in expected_grep_files:
            self.assertTrue((self.GREP_DIR / gf).exists(), f"grep ファイルが存在しない: {gf}")

    # ------------------------------------------------------------------
    # テスト1: 使用タイプの網羅
    # ------------------------------------------------------------------

    def test_direct_records_cover_all_usage_types(self):
        """ORDER_TYPE_NORMAL.grep から 6 種類以上の使用タイプが検出されること。

        期待する使用タイプ:
        - アノテーション (@ConditionalOnExpression 行)
        - 定数定義       (AppConstants.java の static final 行)
        - 条件判定       (if (...) 行、.equals() 行)
        - return文       (return findByOrderType(...) 行)
        - 変数代入       (String normalType = ... 行)
        - メソッド引数   (sendAlert(AppConstants.ORDER_TYPE_NORMAL) 行)
        - その他         (AppConstants.ORDER_TYPE_NORMAL, だけの行)
        """
        direct_records, _, _ = self._run_pipeline("ORDER_TYPE_NORMAL.grep")

        usage_types_found = {r.usage_type for r in direct_records}
        self.assertIn(UsageType.CONSTANT.value,   usage_types_found, "定数定義が見つからない")
        self.assertIn(UsageType.CONDITION.value,  usage_types_found, "条件判定が見つからない")
        self.assertIn(UsageType.RETURN.value,     usage_types_found, "return文が見つからない")
        self.assertIn(UsageType.VARIABLE.value,   usage_types_found, "変数代入が見つからない")
        self.assertIn(UsageType.ARGUMENT.value,   usage_types_found, "メソッド引数が見つからない")
        self.assertGreaterEqual(
            len(usage_types_found), 6,
            f"6種類以上を期待するが {len(usage_types_found)} 種類のみ: {usage_types_found}",
        )

    # ------------------------------------------------------------------
    # テスト2: バイナリ行・空行スキップ
    # ------------------------------------------------------------------

    def test_binary_and_empty_lines_skipped(self):
        """バイナリ行・空行が skipped_lines に計上され valid_lines に含まれないこと。

        ORDER_TYPE_NORMAL.grep:  バイナリ 3行 + 空行 2行 = 5行スキップ
        orderStatus.grep:        バイナリ 2行 + 空行 1行 = 3行スキップ
        """
        # ORDER_TYPE_NORMAL.grep の検証
        _, _, stats_n = self._run_pipeline("ORDER_TYPE_NORMAL.grep")
        self.assertGreater(stats_n.skipped_lines, 0, "スキップ行が 0 件")
        self.assertEqual(
            stats_n.total_lines,
            stats_n.valid_lines + stats_n.skipped_lines,
            "total = valid + skipped を満たさない",
        )

        # orderStatus.grep の検証
        _ast_cache.clear()
        _, _, stats_s = self._run_pipeline("orderStatus.grep")
        self.assertGreater(stats_s.skipped_lines, 0, "スキップ行が 0 件 (orderStatus)")

    # ------------------------------------------------------------------
    # テスト3: 定数の間接参照がプロジェクト全体で検出される
    # ------------------------------------------------------------------

    def test_indirect_constant_tracked_across_multiple_files(self):
        """ORDER_TYPE_NORMAL（static final 定数）の間接参照が複数の異なるファイルにわたって検出されること。

        AppConstants.java:12 が 'project' スコープとなり、
        track_constant() によって全 .java ファイルが検索される。
        """
        direct_records, all_records, _ = self._run_pipeline("ORDER_TYPE_NORMAL.grep")

        # 定数定義レコードが存在すること
        constant_records = [
            r for r in direct_records
            if r.usage_type == UsageType.CONSTANT.value
        ]
        self.assertGreater(len(constant_records), 0, "定数定義レコードが見つからない")

        # 間接参照レコードが存在すること
        indirect_records = [r for r in all_records if r.ref_type == RefType.INDIRECT.value]
        self.assertGreater(len(indirect_records), 0, "間接参照レコードが見つからない")

        # 間接参照が複数の異なるファイルにわたること
        indirect_filepaths = {r.filepath for r in indirect_records}
        self.assertGreater(
            len(indirect_filepaths), 3,
            f"間接参照ファイルが 3 件超を期待するが: {indirect_filepaths}",
        )

        # 間接参照に src_var="ORDER_TYPE_NORMAL" が設定されていること
        for r in indirect_records:
            self.assertEqual(r.src_var, "ORDER_TYPE_NORMAL", f"src_var が不正: {r}")

        # 間接参照の src_file がすべて AppConstants.java であること
        for r in indirect_records:
            self.assertIn("AppConstants.java", r.src_file, f"src_file が不正: {r}")

    # ------------------------------------------------------------------
    # テスト4: フィールドの間接参照が同一クラス内で検出される
    # ------------------------------------------------------------------

    def test_indirect_field_tracked_within_same_class(self):
        """orderStatus（private フィールド）の間接参照が Order.java クラス内で検出されること。

        Order.java:13 が 'class' スコープとなり、
        track_field() によって Order.java 内が検索される。
        """
        direct_records, all_records, _ = self._run_pipeline("orderStatus.grep")

        # フィールド定義レコードが存在すること
        field_records = [
            r for r in direct_records
            if r.usage_type == UsageType.VARIABLE.value
            and "orderStatus" in r.code
        ]
        self.assertGreater(len(field_records), 0, "変数代入（フィールド）レコードが見つからない")

        # 間接参照（フィールド経由）レコードが存在すること
        indirect_records = [r for r in all_records if r.ref_type == RefType.INDIRECT.value]
        self.assertGreater(len(indirect_records), 0, "間接参照レコードが見つからない")

        # 間接参照ファイルが Order.java を含むこと
        indirect_fps = [r.filepath for r in indirect_records]
        order_java_refs = [fp for fp in indirect_fps if "Order.java" in fp]
        self.assertGreater(len(order_java_refs), 0, "Order.java への間接参照が見つからない")

        # src_var="orderStatus" が設定されていること
        for r in indirect_records:
            self.assertEqual("orderStatus", r.src_var, f"src_var が不正: {r}")

    # ------------------------------------------------------------------
    # テスト5: getter 経由参照の検出
    # ------------------------------------------------------------------

    def test_getter_calls_detected(self):
        """orderStatus フィールドの getter 経由参照が検出されること。

        find_getter_names("orderStatus", Order.java) が 'getOrderStatus' を候補として返し、
        track_getter_calls() が ValidationService.java 内の呼び出しを検出する。
        """
        direct_records, all_records, _ = self._run_pipeline("orderStatus.grep")

        getter_records = [r for r in all_records if r.ref_type == RefType.GETTER.value]
        self.assertGreater(len(getter_records), 0, "getter 経由参照レコードが見つからない")

        # getter 名が getOrderStatus であること（命名規則由来）
        for r in getter_records:
            self.assertIn(
                "getOrderStatus", r.src_var,
                f"getter 名が期待と異なる: {r.src_var}",
            )

        # ValidationService.java で呼び出しが検出されること
        getter_fps = [r.filepath for r in getter_records]
        validation_refs = [fp for fp in getter_fps if "ValidationService.java" in fp]
        self.assertGreater(len(validation_refs), 0, "ValidationService.java での getter 呼び出しが未検出")

    # ------------------------------------------------------------------
    # テスト6: TSV ソート順の検証
    # ------------------------------------------------------------------

    def test_tsv_output_sorted_by_keyword_filepath_lineno(self):
        """TSV 出力が 文言 → ファイルパス → 行番号（昇順） でソートされること。"""
        direct_records, all_records, _ = self._run_pipeline("ORDER_TYPE_NORMAL.grep")

        output_path = self.output_dir / "ORDER_TYPE_NORMAL.tsv"
        write_tsv(all_records, output_path)
        self.assertTrue(output_path.exists(), "TSV ファイルが生成されない")

        with open(output_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            rows = list(reader)

        self.assertGreater(len(rows), 1, "TSV にデータ行がない")

        # ヘッダー確認
        header = rows[0]
        self.assertEqual(header[0], "文言")
        self.assertEqual(header[3], "ファイルパス")
        self.assertEqual(header[4], "行番号")

        # ソート順確認: (keyword, filepath, lineno) が昇順であること
        data_rows = rows[1:]
        prev_key = None
        for row in data_rows:
            keyword_col  = row[0]
            filepath_col = row[3]
            lineno_col   = int(row[4]) if row[4].isdigit() else 0
            current_key  = (keyword_col, filepath_col, lineno_col)
            if prev_key is not None:
                self.assertGreaterEqual(
                    current_key, prev_key,
                    f"ソート順が崩れている: {prev_key} → {current_key}",
                )
            prev_key = current_key

    # ------------------------------------------------------------------
    # テスト7: 処理統計の正確性
    # ------------------------------------------------------------------

    def test_stats_accurate(self):
        """処理統計（total, valid, skipped）が正確に集計されること。

        total_lines == valid_lines + skipped_lines が常に成立すること。
        両ファイルを処理しても統計が正確に累積されること。
        """
        grep_path_n = self.GREP_DIR / "ORDER_TYPE_NORMAL.grep"
        grep_path_s = self.GREP_DIR / "orderStatus.grep"
        stats = ProcessStats()

        process_grep_file(grep_path_n, "ORDER_TYPE_NORMAL", self.JAVA_DIR, stats)
        _ast_cache.clear()
        process_grep_file(grep_path_s, "orderStatus", self.JAVA_DIR, stats)

        # 基本不変条件
        self.assertEqual(
            stats.total_lines,
            stats.valid_lines + stats.skipped_lines,
            "total_lines != valid_lines + skipped_lines",
        )

        # バイナリ行・空行がスキップされていること
        # ORDER_TYPE_NORMAL.grep: バイナリ3行+空行2行=5
        # orderStatus.grep: バイナリ2行+空行1行=3
        self.assertGreaterEqual(stats.skipped_lines, 8, "スキップ行数が期待より少ない")

        # 有効行が十分存在すること
        # ORDER_TYPE_NORMAL: 15行, orderStatus: 18行
        self.assertGreaterEqual(stats.valid_lines, 25, "有効行数が期待より少ない")

    # ------------------------------------------------------------------
    # テスト8: 全体的な量と質（smoke test）
    # ------------------------------------------------------------------

    def test_indirect_records_exist_in_significant_volume(self):
        """間接参照が大量かつ複数ファイルにわたって検出されること（定数が広く参照されているため）。

        direct 参照は grep ファイルの行数に依存するが、indirect は実際の Java ファイルを
        全件検索するため、プロジェクト全体に定数が行き渡るほど多くなる。
        少なくとも 8 件以上、かつ 4 ファイル以上から検出されることを確認する。
        """
        direct_records, all_records, _ = self._run_pipeline("ORDER_TYPE_NORMAL.grep")

        indirect_records = [r for r in all_records if r.ref_type == RefType.INDIRECT.value]
        indirect_count   = len(indirect_records)
        indirect_files   = {r.filepath for r in indirect_records}

        self.assertGreaterEqual(
            indirect_count, 8,
            f"間接参照が 8 件以上を期待するが {indirect_count} 件のみ",
        )
        self.assertGreaterEqual(
            len(indirect_files), 4,
            f"間接参照が 4 ファイル以上を期待するが {len(indirect_files)} ファイルのみ: {indirect_files}",
        )

    # ------------------------------------------------------------------
    # テスト9: CLI 経由での E2E 実行
    # ------------------------------------------------------------------

    def test_full_cli_run_produces_tsv_files(self):
        """CLI（main()）を通じて 2 つの TSV ファイルが正常出力されること。

        - 終了コード 0
        - ORDER_TYPE_NORMAL.tsv および orderStatus.tsv が生成される
        - 各 TSV にヘッダー＋データ行が存在する
        - 'direct' 参照と 'indirect' 参照が両方含まれる（ORDER_TYPE_NORMAL）
        - stdout に '処理完了' が出力される
        """
        rc, out, err = self._run_main([
            "--source-dir", str(self.JAVA_DIR),
            "--input-dir",  str(self.GREP_DIR),
            "--output-dir", str(self.output_dir),
        ])
        self.assertEqual(rc, 0, f"main() が非ゼロ終了: {err}")

        # 両 TSV ファイルが生成されること
        tsv_n = self.output_dir / "ORDER_TYPE_NORMAL.tsv"
        tsv_s = self.output_dir / "orderStatus.tsv"
        self.assertTrue(tsv_n.exists(), "ORDER_TYPE_NORMAL.tsv が生成されない")
        self.assertTrue(tsv_s.exists(), "orderStatus.tsv が生成されない")

        # ORDER_TYPE_NORMAL.tsv の内容検証
        with open(tsv_n, encoding="utf-8-sig", newline="") as f:
            content_n = f.read()
        self.assertIn("ORDER_TYPE_NORMAL", content_n, "キーワードが TSV に含まれない")
        self.assertIn(RefType.DIRECT.value,   content_n, "直接参照が TSV に含まれない")
        self.assertIn(RefType.INDIRECT.value, content_n, "間接参照が TSV に含まれない")
        self.assertIn(UsageType.CONSTANT.value, content_n, "定数定義が TSV に含まれない")

        # orderStatus.tsv の内容検証
        with open(tsv_s, encoding="utf-8-sig", newline="") as f:
            content_s = f.read()
        self.assertIn("orderStatus", content_s, "キーワードが TSV に含まれない")
        self.assertIn(RefType.DIRECT.value, content_s, "直接参照が TSV に含まれない")

        # stdout に処理完了メッセージが出力されること
        self.assertIn("処理完了", out, "処理完了メッセージが stdout に出力されない")

        # stdout に両ファイルの処理件数が出力されること
        self.assertIn("ORDER_TYPE_NORMAL.grep", out)
        self.assertIn("orderStatus.grep", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
