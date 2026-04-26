import sys, unittest, tempfile, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.c import (
    classify_usage as classify_usage_c,
    extract_define_name,
    extract_variable_name_c,
    _build_define_map,
    _collect_define_aliases,
    _define_map_cache,
    _build_reverse_define_map,
    _get_reverse_define_map,
    track_define,
    track_variable,
)
import grep_helper.languages.c as _c_mod
from grep_helper.model import ProcessStats
from grep_helper.tsv_output import write_tsv
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import c as _c_handler
from grep_helper.file_cache import _file_lines_cache_clear


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _c_handler, keyword=keyword, stats=stats)


class TestClassifyUsageC(unittest.TestCase):
    def test_define定数定義を分類できる(self):
        """#define 行が「#define定数定義」に分類されることを確認する。"""
        self.assertEqual(classify_usage_c('#define MAX_SIZE 100'), "#define定数定義")

    def test_hashとdefineの間に空白がある場合も分類できる(self):
        """# define のように空白があっても #define定数定義 と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('# define STATUS "value"'), "#define定数定義")

    def test_if文を条件判定として分類できる(self):
        """if (...) 形式が「条件判定」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('if (code == STATUS)'), "条件判定")

    def test_strcmp呼び出しを条件判定として分類できる(self):
        """strcmp 呼び出しが「条件判定」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('strcmp(code, STATUS)'), "条件判定")

    def test_strncmp呼び出しを条件判定として分類できる(self):
        """strncmp 呼び出しが「条件判定」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('strncmp(code, STATUS, 4)'), "条件判定")

    def test_switch文を条件判定として分類できる(self):
        """switch 文が「条件判定」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('switch (code) {'), "条件判定")

    def test_return文を分類できる(self):
        """return 文が「return文」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('return STATUS;'), "return文")

    def test_変数代入を分類できる(self):
        """配列宣言+代入が「変数代入」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('char buf[32] = STATUS;'), "変数代入")

    def test_関数引数を分類できる(self):
        """関数呼び出しの引数として渡される場合「関数引数」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('process(STATUS)'), "関数引数")

    def test_その他の出現を分類できる(self):
        """単独識別子はどれにも該当せず「その他」と分類されることを確認する。"""
        self.assertEqual(classify_usage_c('STATUS'), "その他")

    def test_EXEC_SQL文はC側では分類されない(self):
        """C アナライザは EXEC SQL 行を「EXEC SQL文」として分類しないことを確認する。"""
        result = classify_usage_c('EXEC SQL SELECT * FROM t;')
        self.assertNotEqual(result, "EXEC SQL文")


class TestExtractDefineName(unittest.TestCase):
    def test_define行から定数名を抽出できる(self):
        """通常の #define 行から定数名を取り出せることを確認する。"""
        self.assertEqual(extract_define_name('#define STATUS "value"'), "STATUS")

    def test_hashの後に空白があっても定数名を抽出できる(self):
        """# define のように空白があっても定数名を取り出せることを確認する。"""
        self.assertEqual(extract_define_name('# define STATUS "value"'), "STATUS")

    def test_define以外の行ではNoneを返す(self):
        """#define ではない行に対しては None を返すことを確認する。"""
        self.assertIsNone(extract_define_name('if (x == STATUS)'))

    def test_値を持たないdefineではNoneを返す(self):
        """値が指定されていない #define 行に対しては None を返すことを確認する。"""
        self.assertIsNone(extract_define_name('#define STATUS'))


class TestExtractVariableNameC(unittest.TestCase):
    def test_char配列宣言から変数名を抽出できる(self):
        """char buf[32]; から変数名 buf を抽出できることを確認する。"""
        self.assertEqual(extract_variable_name_c('char buf[32];'), "buf")

    def test_int宣言と代入から変数名を抽出できる(self):
        """int count = 0; から変数名 count を抽出できることを確認する。"""
        self.assertEqual(extract_variable_name_c('int count = 0;'), "count")

    def test_ポインタ宣言から変数名を抽出できる(self):
        """char *ptr; から変数名 ptr を抽出できることを確認する。"""
        self.assertEqual(extract_variable_name_c('char *ptr;'), "ptr")

    def test_変数宣言ではない行ではNoneを返す(self):
        """変数宣言でない行に対しては None を返すことを確認する。"""
        self.assertIsNone(extract_variable_name_c('if (x == 1)'))


class TestBuildDefineMap(unittest.TestCase):
    def test_単純なdefineエイリアスを収集できる(self):
        """#define ALIAS TARGET 形式から ALIAS->TARGET のマップが作られることを確認する。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define ALIAS TARGET\n')
            stats = ProcessStats()
            dm = _build_define_map(src, stats)
            self.assertEqual(dm.get("ALIAS"), "TARGET")

    def test_文字列リテラル値のdefineは無視される(self):
        """値が文字列リテラルの #define はエイリアスマップに含まれないことを確認する。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define STATUS "value"\n')
            stats = ProcessStats()
            dm = _build_define_map(src, stats)
            self.assertNotIn("STATUS", dm)

    def test_定義マップが同一src_dirに対してキャッシュされる(self):
        """同一 src_dir への2回目の呼び出しはキャッシュを返す（同一オブジェクト）。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define ALIAS TARGET\n')
            stats = ProcessStats()
            _define_map_cache.clear()
            dm1 = _build_define_map(src, stats)
            dm2 = _build_define_map(src, stats)
            self.assertIs(dm1, dm2)

    def test_定義マップキャッシュがエンコーディング別に分かれる(self):
        """encoding が異なる場合は別キャッシュエントリになる。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "a.c").write_text('#define ALIAS TARGET\n')
            stats = ProcessStats()
            _define_map_cache.clear()
            dm1 = _build_define_map(src, stats, encoding_override=None)
            dm2 = _build_define_map(src, stats, encoding_override="utf-8")
            # 異なるエンコーディング指定は別キャッシュエントリ（別オブジェクト）
            self.assertIsNot(dm1, dm2)


class TestCollectDefineAliases(unittest.TestCase):
    def test_2段階のdefineチェーンを辿れる(self):
        """B->A, C->B のような連鎖を辿って A のエイリアス集合に B と C を含むことを確認する。"""
        define_map = {"B": "A", "C": "B"}
        aliases = _collect_define_aliases("A", define_map)
        self.assertIn("B", aliases)
        self.assertIn("C", aliases)

    def test_循環参照があっても無限ループしない(self):
        """A と B が相互参照していても収集が打ち切られ、件数が制限内に収まることを確認する。"""
        define_map = {"B": "A", "A": "B"}
        aliases = _collect_define_aliases("A", define_map)
        self.assertLessEqual(len(aliases), 10)

    def test_該当エイリアスがない場合は空リストを返す(self):
        """対象キーワードへ向かう #define が存在しない場合は空リストを返すことを確認する。"""
        define_map = {"X": "Y"}
        aliases = _collect_define_aliases("A", define_map)
        self.assertEqual(aliases, [])


class TestE2EC(unittest.TestCase):
    """E2E統合テスト: sample.c でツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "c"

    def test_TARGETキーワードのE2E出力が期待TSVと一致する(self):
        """sample.c に対し TARGET キーワードで解析した結果が期待 TSV と完全一致することを確認する。"""
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists(), f"src_dir が存在しない: {src_dir}")
        self.assertTrue(expected_path.exists(), f"expected TSV が存在しない: {expected_path}")

        _file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ProcessStats()
            keyword = "TARGET"
            grep_path = input_dir / "TARGET.grep"

            direct_records = _process_grep_file(grep_path, keyword, src_dir, stats)
            all_records = list(direct_records)

            for record in direct_records:
                if record.usage_type == "#define定数定義":
                    var_name = extract_define_name(record.code)
                    if var_name:
                        all_records.extend(track_define(var_name, src_dir, record, stats))
                elif record.usage_type == "変数代入":
                    var_name = extract_variable_name_c(record.code)
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

            actual_lines   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected_lines = expected_path.read_text(encoding="utf-8-sig").splitlines()

            self.assertEqual(
                actual_lines, expected_lines,
                f"出力TSVが期待値と一致しない\n"
                f"実際行数: {len(actual_lines)}, 期待行数: {len(expected_lines)}"
            )


class TestDefineMapWithReverse(unittest.TestCase):
    def test_エイリアス収集でreverseマップが再構築されない(self):
        """_collect_define_aliases を多数回呼んでも reverse 構築は 1 回。"""
        _define_map_cache.clear()
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.h").write_text("#define A1 X\n#define A2 X\n", encoding="utf-8")
            stats = ProcessStats()
            _build_define_map(p, stats)
            calls = {"n": 0}
            orig = _c_mod._build_reverse_define_map  # 新規 API
            def counter(m):
                calls["n"] += 1
                return orig(m)
            _c_mod._build_reverse_define_map = counter
            try:
                for _ in range(50):
                    _collect_define_aliases(
                        "X",
                        _build_define_map(p, stats),
                        reverse=_c_mod._get_reverse_define_map(p, None),
                    )
                self.assertEqual(calls["n"], 0,
                    "reverse map はキャッシュから取得されるはずで、再構築されない")
            finally:
                _c_mod._build_reverse_define_map = orig


if __name__ == "__main__":
    unittest.main()
