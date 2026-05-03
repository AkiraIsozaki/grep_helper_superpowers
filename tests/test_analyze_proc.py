"""analyze_proc.py のユニットテスト・統合テスト"""
from __future__ import annotations

from grep_helper.file_cache import _file_lines_cache_clear
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.model import ProcessStats
from grep_helper.tsv_output import write_tsv
from grep_helper.languages.proc import (
    classify_usage_proc,
)
from grep_helper.languages.proc_define_map import (
    _define_map_cache,
    _build_define_map,
)
from grep_helper.languages.proc_track import (
    extract_variable_name_proc,
    extract_define_name,
    extract_host_var_name,
    track_define,
    track_variable,
)
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import proc as _proc_handler


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _proc_handler, keyword=keyword, stats=stats)


# ---------------------------------------------------------------------------
# TestClassifyUsageProc
# ---------------------------------------------------------------------------

class TestClassifyUsageProc(unittest.TestCase):
    """TestClassifyUsageProc: classify_usage_proc() の 7 種類分類ラベルを観察するテスト。
    E2E は fixture 内出現パターンしかカバーしないため、return文 / 関数引数 / 大文字小文字混在 等の網羅は本クラスで保持する。
    """

    def test_EXEC_SQL文を分類できる(self):
        """EXEC SQL で始まる行は EXEC SQL文 と分類される"""
        self.assertEqual(classify_usage_proc("EXEC SQL SELECT * FROM t INTO :v;"), "EXEC SQL文")

    def test_EXEC_SQL文は大文字小文字を区別しない(self):
        """小文字の exec sql でも EXEC SQL文 として分類される"""
        self.assertEqual(classify_usage_proc("exec sql commit;"), "EXEC SQL文")

    def test_define定数定義を分類できる(self):
        """#define で始まる行は #define定数定義 と分類される"""
        self.assertEqual(classify_usage_proc('#define SAMPLE_CODE "TARGET"'), "#define定数定義")

    def test_define行は空白を含むハッシュでも分類できる(self):
        """# と define の間に空白があっても #define定数定義 として分類される"""
        self.assertEqual(classify_usage_proc('#  define MY_CONST 100'), "#define定数定義")

    def test_if文の条件判定を分類できる(self):
        """if 文中で比較に用いる行は条件判定として分類される"""
        self.assertEqual(classify_usage_proc("if (x == TARGET) {"), "条件判定")

    def test_strcmpを使った条件判定を分類できる(self):
        """strcmp による比較も条件判定として分類される"""
        self.assertEqual(classify_usage_proc('if (strcmp(buf, TARGET) == 0)'), "条件判定")

    def test_return文を分類できる(self):
        """return で始まる行は return文 と分類される"""
        self.assertEqual(classify_usage_proc("return TARGET;"), "return文")

    def test_変数代入を分類できる(self):
        """char 配列への代入文は変数代入として分類される"""
        self.assertEqual(classify_usage_proc("char localVar[] = TARGET;"), "変数代入")

    def test_関数引数を分類できる(self):
        """関数呼び出し引数として渡される行は関数引数として分類される"""
        self.assertEqual(classify_usage_proc("process(TARGET);"), "関数引数")

    def test_未分類はその他になる(self):
        """どのパターンにも合致しない行はその他として分類される"""
        self.assertEqual(classify_usage_proc("TARGET"), "その他")


# ---------------------------------------------------------------------------
# TestExtractDefineName
# ---------------------------------------------------------------------------

class TestExtractDefineName(unittest.TestCase):
    """TestExtractDefineName: extract_define_name() の戻り値（定数名 or None）を観察するテスト。
    E2E は #define 値あり経路のみで、値なし／非 #define の None 返却までは保証されないため保持する。
    """

    def test_define名を基本パターンから抽出できる(self):
        """#define <name> <value> から定数名を取り出せる"""
        self.assertEqual(extract_define_name('#define SAMPLE_CODE "TARGET"'), "SAMPLE_CODE")

    def test_ハッシュとdefineの間の空白を許容する(self):
        """# と define の間に空白があっても定数名を抽出できる"""
        self.assertEqual(extract_define_name('#  define MY_CONST 100'), "MY_CONST")

    def test_define以外の行ではNoneを返す(self):
        """#define 以外のコードからは定数名を抽出しない"""
        self.assertIsNone(extract_define_name("int x = 0;"))

    def test_値のないdefineではNoneを返す(self):
        """#define NAME（値なし）はスペースがないのでNoneを返す"""
        self.assertIsNone(extract_define_name("#define NAME"))

    def test_数値リテラルを伴うdefineを抽出できる(self):
        """数値値を持つ #define からも定数名を抽出できる"""
        self.assertEqual(extract_define_name("#define MAX_LEN 256"), "MAX_LEN")


class TestBuildDefineMapProcWhitebox(unittest.TestCase):
    """TestBuildDefineMapProcWhitebox: _build_define_map のキャッシュ実装契約を観察するテスト。
    キャッシュキーは (src_dir, encoding) で構成され、同一キーなら同一オブジェクトを再利用する。
    実装変更時は本クラスも同期更新が必要。
    """

    def test_define_mapは同一src_dirに対してキャッシュされる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.pc").write_text('#define ALIAS TARGET\n')
            stats = ProcessStats()
            _define_map_cache.clear()
            dm1 = _build_define_map(src, stats)
            dm2 = _build_define_map(src, stats)
            self.assertIs(dm1, dm2)

    def test_define_mapキャッシュはエンコーディング別に分かれる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.pc").write_text('#define ALIAS TARGET\n')
            stats = ProcessStats()
            _define_map_cache.clear()
            dm1 = _build_define_map(src, stats, encoding_override=None)
            dm2 = _build_define_map(src, stats, encoding_override="utf-8")
            self.assertIsNot(dm1, dm2)


# ---------------------------------------------------------------------------
# TestExtractVariableNameProc
# ---------------------------------------------------------------------------

class TestExtractVariableNameProc(unittest.TestCase):
    """TestExtractVariableNameProc: extract_variable_name_proc() の変数名抽出を観察するテスト。
    char[] / char[N] / int / ポインタ / 非変数宣言 の各分岐を網羅し、E2E fixture 外の形状を保証する。
    """

    def test_代入を伴うchar配列の変数名を抽出できる(self):
        """char foo[] = "..." 形式から変数名を抽出できる"""
        self.assertEqual(extract_variable_name_proc('char localVar[] = "TARGET";'), "localVar")

    def test_サイズ指定付きchar配列の変数名を抽出できる(self):
        """char foo[256]; 形式から変数名を抽出できる"""
        self.assertEqual(extract_variable_name_proc("char hostVar[256];"), "hostVar")

    def test_int代入文の変数名を抽出できる(self):
        """int 型変数の宣言と初期化から変数名を抽出できる"""
        self.assertEqual(extract_variable_name_proc("int count = 0;"), "count")

    def test_ポインタ変数の変数名を抽出できる(self):
        """char *ptr 形式のポインタ宣言から変数名を抽出できる"""
        self.assertEqual(extract_variable_name_proc("char *ptr = NULL;"), "ptr")

    def test_変数宣言以外ではNoneを返す(self):
        """EXEC SQL 文など変数宣言でない行ではNoneを返す"""
        self.assertIsNone(extract_variable_name_proc("EXEC SQL COMMIT;"))


# ---------------------------------------------------------------------------
# TestE2EProc（統合テスト）
# ---------------------------------------------------------------------------

class TestE2EProc(unittest.TestCase):
    """TestE2EProc: TARGET fixture 群を Pro*C パイプラインに通し期待 TSV と完全一致を観察するゴールデンテスト。
    classify_usage_proc / extract_define_name / track_define / track_variable / write_tsv の統合契約を本クラスが代表する。
    """

    TESTS_DIR = Path(__file__).parent / "proc"

    def test_E2E_TARGETサンプルが期待TSVと完全一致する(self):
        """TARGET.grep を処理し、expected/TARGET.tsv と全行一致することを確認する"""
        src_dir = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(input_dir.exists(), f"input_dir が存在しない: {input_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        _file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            stats = ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = _process_grep_file(grep_path, keyword, src_dir, stats)
            classified = [r._replace(usage_type=classify_usage_proc(r.code))
                          for r in direct_records]
            direct_records = classified
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = extract_define_name(record.code)
                    if var_name:
                        all_records.extend(track_define(var_name, src_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = extract_variable_name_proc(record.code)
                    if not var_name:
                        var_name = extract_host_var_name(record.code)
                    if var_name:
                        candidate = Path(record.filepath)
                        if not candidate.is_absolute():
                            candidate = src_dir / record.filepath
                        if candidate.exists():
                            all_records.extend(
                                track_variable(var_name, candidate,
                                               int(record.lineno), src_dir, record, stats)
                            )

            output_path = output_dir / "TARGET.tsv"
            write_tsv(all_records, output_path)

            actual_lines = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


class TestE2EMixed(unittest.TestCase):
    """TestE2EMixed: .c と .pc が混在する MIXVAL fixture を処理し期待 TSV と完全一致を観察するゴールデンテスト。
    _classify_for_filepath による拡張子ディスパッチの統合契約を本クラスが代表する。
    """

    TESTS_DIR = Path(__file__).parent / "proc"

    def test_E2E_MIXVAL混在サンプルが期待TSVと完全一致する(self):
        """MIXVAL.grep を処理し、expected/MIXVAL.tsv と全行一致することを確認する"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "MIXVAL.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        _file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ProcessStats()
            keyword = "MIXVAL"
            grep_path = input_dir / "MIXVAL.grep"

            direct_records = _process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = extract_define_name(record.code)
                    if var_name:
                        all_records.extend(track_define(var_name, src_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = extract_variable_name_proc(record.code)
                    if not var_name:
                        var_name = extract_host_var_name(record.code)
                    if var_name:
                        candidate = Path(record.filepath)
                        if not candidate.is_absolute():
                            candidate = src_dir / record.filepath
                        if candidate.exists():
                            all_records.extend(
                                track_variable(var_name, candidate,
                                               int(record.lineno), src_dir, record, stats)
                            )

            output_path = output_dir / "MIXVAL.tsv"
            write_tsv(all_records, output_path)

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


if __name__ == "__main__":
    unittest.main()
