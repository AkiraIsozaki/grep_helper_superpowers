"""analyze_proc.py のユニットテスト・統合テスト"""
from __future__ import annotations

import csv
import analyze_common
import os
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールをインポート
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_proc as ap


# ---------------------------------------------------------------------------
# TestParseGrepLine
# ---------------------------------------------------------------------------

class TestParseGrepLine(unittest.TestCase):
    """parse_grep_line() のテスト"""

    def test_通常のgrep行をパースできる(self):
        """ファイルパス:行番号:コード形式の標準的なgrep行を正しく分解できる"""
        result = ap.parse_grep_line("src/sample.pc:42:    EXEC SQL FETCH cur INTO :hostVar;")
        self.assertIsNotNone(result)
        self.assertEqual(result["filepath"], "src/sample.pc")
        self.assertEqual(result["lineno"], "42")
        self.assertEqual(result["code"], "EXEC SQL FETCH cur INTO :hostVar;")

    def test_Windowsパスを含む行をパースできる(self):
        """ドライブレター付きのWindowsパス（C:\\...）でも行番号を抽出できる"""
        result = ap.parse_grep_line(r"C:\project\sample.pc:10:char buf[256];")
        self.assertIsNotNone(result)
        self.assertEqual(result["lineno"], "10")

    def test_バイナリファイル通知行はNoneを返す(self):
        """grep のバイナリファイル一致通知行（Binary file ... matches）はパース対象外"""
        result = ap.parse_grep_line("Binary file ./obj/sample.o matches")
        self.assertIsNone(result)

    def test_空行はNoneを返す(self):
        """空文字列はパースできずNoneを返す"""
        result = ap.parse_grep_line("")
        self.assertIsNone(result)

    def test_空白のみの行はNoneを返す(self):
        """空白と改行だけの行はパース対象外"""
        result = ap.parse_grep_line("   \n")
        self.assertIsNone(result)

    def test_行番号が数値でない場合はNoneを返す(self):
        """行番号位置に非数値が来た行は無効としてNoneを返す"""
        result = ap.parse_grep_line("src/sample.pc:no_number:code")
        self.assertIsNone(result)

    def test_コード部分の前後空白がトリムされる(self):
        """コード列の前後の空白文字は除去される"""
        result = ap.parse_grep_line("src/sample.pc:1:    int x = 0;    ")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "int x = 0;")


# ---------------------------------------------------------------------------
# TestClassifyUsageProc
# ---------------------------------------------------------------------------

class TestClassifyUsageProc(unittest.TestCase):
    """classify_usage_proc() の7種テスト"""

    def test_EXEC_SQL文を分類できる(self):
        """EXEC SQL で始まる行は EXEC SQL文 と分類される"""
        self.assertEqual(ap.classify_usage_proc("EXEC SQL SELECT * FROM t INTO :v;"), "EXEC SQL文")

    def test_EXEC_SQL文は大文字小文字を区別しない(self):
        """小文字の exec sql でも EXEC SQL文 として分類される"""
        self.assertEqual(ap.classify_usage_proc("exec sql commit;"), "EXEC SQL文")

    def test_define定数定義を分類できる(self):
        """#define で始まる行は #define定数定義 と分類される"""
        self.assertEqual(ap.classify_usage_proc('#define SAMPLE_CODE "TARGET"'), "#define定数定義")

    def test_define行は空白を含むハッシュでも分類できる(self):
        """# と define の間に空白があっても #define定数定義 として分類される"""
        self.assertEqual(ap.classify_usage_proc('#  define MY_CONST 100'), "#define定数定義")

    def test_if文の条件判定を分類できる(self):
        """if 文中で比較に用いる行は条件判定として分類される"""
        self.assertEqual(ap.classify_usage_proc("if (x == TARGET) {"), "条件判定")

    def test_strcmpを使った条件判定を分類できる(self):
        """strcmp による比較も条件判定として分類される"""
        self.assertEqual(ap.classify_usage_proc('if (strcmp(buf, TARGET) == 0)'), "条件判定")

    def test_return文を分類できる(self):
        """return で始まる行は return文 と分類される"""
        self.assertEqual(ap.classify_usage_proc("return TARGET;"), "return文")

    def test_変数代入を分類できる(self):
        """char 配列への代入文は変数代入として分類される"""
        self.assertEqual(ap.classify_usage_proc("char localVar[] = TARGET;"), "変数代入")

    def test_関数引数を分類できる(self):
        """関数呼び出し引数として渡される行は関数引数として分類される"""
        self.assertEqual(ap.classify_usage_proc("process(TARGET);"), "関数引数")

    def test_未分類はその他になる(self):
        """どのパターンにも合致しない行はその他として分類される"""
        self.assertEqual(ap.classify_usage_proc("TARGET"), "その他")


# ---------------------------------------------------------------------------
# TestExtractDefineName
# ---------------------------------------------------------------------------

class TestExtractDefineName(unittest.TestCase):
    """extract_define_name() のテスト"""

    def test_define名を基本パターンから抽出できる(self):
        """#define <name> <value> から定数名を取り出せる"""
        self.assertEqual(ap.extract_define_name('#define SAMPLE_CODE "TARGET"'), "SAMPLE_CODE")

    def test_ハッシュとdefineの間の空白を許容する(self):
        """# と define の間に空白があっても定数名を抽出できる"""
        self.assertEqual(ap.extract_define_name('#  define MY_CONST 100'), "MY_CONST")

    def test_define以外の行ではNoneを返す(self):
        """#define 以外のコードからは定数名を抽出しない"""
        self.assertIsNone(ap.extract_define_name("int x = 0;"))

    def test_値のないdefineではNoneを返す(self):
        """#define NAME（値なし）はスペースがないのでNoneを返す"""
        # #define NAME（値なし）はスペースがないのでNone
        self.assertIsNone(ap.extract_define_name("#define NAME"))

    def test_数値リテラルを伴うdefineを抽出できる(self):
        """数値値を持つ #define からも定数名を抽出できる"""
        self.assertEqual(ap.extract_define_name("#define MAX_LEN 256"), "MAX_LEN")


class TestBuildDefineMapProc(unittest.TestCase):
    """_build_define_map() のキャッシュテスト"""

    def test_define_mapは同一src_dirに対してキャッシュされる(self):
        """同一 src_dir への2回目の呼び出しはキャッシュを返す（同一オブジェクト）"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.pc").write_text('#define ALIAS TARGET\n')
            stats = ap.ProcessStats()
            ap._define_map_cache.clear()
            dm1 = ap._build_define_map(src, stats)
            dm2 = ap._build_define_map(src, stats)
            self.assertIs(dm1, dm2)

    def test_define_mapキャッシュはエンコーディング別に分かれる(self):
        """encoding が異なる場合は別キャッシュエントリになる"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.pc").write_text('#define ALIAS TARGET\n')
            stats = ap.ProcessStats()
            ap._define_map_cache.clear()
            dm1 = ap._build_define_map(src, stats, encoding_override=None)
            dm2 = ap._build_define_map(src, stats, encoding_override="utf-8")
            self.assertIsNot(dm1, dm2)


# ---------------------------------------------------------------------------
# TestExtractVariableNameProc
# ---------------------------------------------------------------------------

class TestExtractVariableNameProc(unittest.TestCase):
    """extract_variable_name_proc() のテスト"""

    def test_代入を伴うchar配列の変数名を抽出できる(self):
        """char foo[] = "..." 形式から変数名を抽出できる"""
        self.assertEqual(ap.extract_variable_name_proc('char localVar[] = "TARGET";'), "localVar")

    def test_サイズ指定付きchar配列の変数名を抽出できる(self):
        """char foo[256]; 形式から変数名を抽出できる"""
        self.assertEqual(ap.extract_variable_name_proc("char hostVar[256];"), "hostVar")

    def test_int代入文の変数名を抽出できる(self):
        """int 型変数の宣言と初期化から変数名を抽出できる"""
        self.assertEqual(ap.extract_variable_name_proc("int count = 0;"), "count")

    def test_ポインタ変数の変数名を抽出できる(self):
        """char *ptr 形式のポインタ宣言から変数名を抽出できる"""
        self.assertEqual(ap.extract_variable_name_proc("char *ptr = NULL;"), "ptr")

    def test_変数宣言以外ではNoneを返す(self):
        """EXEC SQL 文など変数宣言でない行ではNoneを返す"""
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

    def test_TSV出力の列数が9列であること(self):
        """ヘッダ行とデータ行の両方が 9 列で出力される"""
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

    def test_TSV出力がUTF8_BOMで始まること(self):
        """write_tsv は Excel 互換のため UTF-8 BOM 付きで書き出す"""
        records = [self._make_record("KW", "直接", "a.pc", "1", "code")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            ap.write_tsv(records, out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'), "UTF-8 BOMで始まること")

    def test_TSV出力がファイルパスと行番号でソートされる(self):
        """ファイルパス昇順、同一ファイル内では行番号昇順で並ぶ"""
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

    TESTS_DIR = Path(__file__).parent / "proc"

    def test_E2E_TARGETサンプルが期待TSVと完全一致する(self):
        """TARGET.grep を処理し、expected/TARGET.tsv と全行一致することを確認する"""
        src_dir = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(input_dir.exists(), f"input_dir が存在しない: {input_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        # キャッシュをリセット（テスト間の汚染防止）
        analyze_common._file_lines_cache_clear()

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


class TestDispatch(unittest.TestCase):
    """拡張子ベースのディスパッチテスト"""

    def test_拡張子cではEXEC_SQL文として分類されない(self):
        """.c ファイルでは EXEC SQL が 'EXEC SQL文' に分類されない（その他になる）"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'src/main.c')
        self.assertEqual(result, "その他")

    def test_拡張子pcではEXEC_SQL文として分類される(self):
        """.pc ファイルでは EXEC SQL が 'EXEC SQL文' に分類される"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'src/main.pc')
        self.assertEqual(result, "EXEC SQL文")

    def test_ヘッダファイルはC分類器を使う(self):
        """.h ファイルは C 分類を使う（その他になる）"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'include/config.h')
        self.assertEqual(result, "その他")

    def test_未知拡張子はProCがデフォルトとなる(self):
        """未知拡張子はデフォルトで Pro*C 分類（後方互換）"""
        result = ap._classify_for_filepath('EXEC SQL SELECT * FROM t;', 'src/main.xyz')
        self.assertEqual(result, "EXEC SQL文")


class TestE2EMixed(unittest.TestCase):
    """混在E2Eテスト: .c と .pc が混在する grep ファイルの処理"""

    TESTS_DIR = Path(__file__).parent / "proc"

    def test_E2E_MIXVAL混在サンプルが期待TSVと完全一致する(self):
        """MIXVAL.grep を処理し、expected/MIXVAL.tsv と全行一致することを確認する"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "MIXVAL.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        analyze_common._file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ap.ProcessStats()
            keyword = "MIXVAL"
            grep_path = input_dir / "MIXVAL.grep"

            direct_records = ap.process_grep_file(grep_path, keyword, src_dir, stats)
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

            output_path = output_dir / "MIXVAL.tsv"
            ap.write_tsv(all_records, output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


if __name__ == "__main__":
    unittest.main()
