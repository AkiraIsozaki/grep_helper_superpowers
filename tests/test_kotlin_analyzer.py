import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.kotlin import (
    classify_usage as classify_usage_kotlin,
    extract_const_name,
    track_const,
)
from grep_helper.model import GrepRecord, ProcessStats, RefType
from grep_helper.tsv_output import write_tsv
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import kotlin as _kotlin_handler
from grep_helper.file_cache import _file_lines_cache_clear


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _kotlin_handler, keyword=keyword, stats=stats)


class TestClassifyUsageKotlin(unittest.TestCase):
    def test_const_val宣言はconst定数定義に分類される(self):
        """const val 宣言がconst定数定義として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('const val STATUS = "TARGET"'), "const定数定義")

    def test_val代入は変数代入に分類される(self):
        """val による代入が変数代入として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('val code = STATUS'), "変数代入")

    def test_var代入は変数代入に分類される(self):
        """var による代入が変数代入として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('var code = STATUS'), "変数代入")

    def test_if文は条件判定に分類される(self):
        """if 式が条件判定として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('if (code == STATUS)'), "条件判定")

    def test_when文は条件判定に分類される(self):
        """when 式が条件判定として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('when (status)'), "条件判定")

    def test_return文はreturn文に分類される(self):
        """return 文が return文として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('return STATUS'), "return文")

    def test_アノテーション行はアノテーションに分類される(self):
        """@付きの行がアノテーションとして分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('@Suppress("unused")'), "アノテーション")

    def test_関数呼び出し引数は関数引数に分類される(self):
        """関数呼び出し時の引数が関数引数として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('process(STATUS)'), "関数引数")

    def test_該当しない記述はその他に分類される(self):
        """いずれにも該当しない記述がその他として分類されることを確認"""
        self.assertEqual(classify_usage_kotlin('STATUS'), "その他")


class TestExtractConstName(unittest.TestCase):
    def test_const_val宣言から定数名を抽出できる(self):
        """const val 宣言行から定数名を正しく抽出することを確認"""
        self.assertEqual(extract_const_name('const val STATUS = "TARGET"'), "STATUS")

    def test_constなしのvalからは抽出されない(self):
        """const なしの val 宣言からは定数名を抽出しないことを確認"""
        self.assertIsNone(extract_const_name('val code = "TARGET"'))

    def test_宣言以外の行からは抽出されない(self):
        """宣言ではない行からは定数名を抽出しないことを確認"""
        self.assertIsNone(extract_const_name('if (x == STATUS)'))


class TestTrackConst(unittest.TestCase):
    def test_ktファイル内の定数利用箇所を検出できる(self):
        """track_const が .kt ファイル内の定数利用箇所を間接参照として検出することを確認"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Constants.kt").write_text('const val STATUS = "TARGET"\n')
            (src / "Service.kt").write_text('if (code == STATUS) { return true }\n')
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "Constants.kt"),
                lineno="1",
                code='const val STATUS = "TARGET"',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_const("STATUS", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.kt" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_定義行自身は結果に含まれない(self):
        """track_const が定数の定義行自身を結果に含めないことを確認"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Constants.kt").write_text('const val STATUS = "TARGET"\n')
            record = GrepRecord(
                keyword="TARGET",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "Constants.kt"),
                lineno="1",
                code='const val STATUS = "TARGET"',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_const("STATUS", src, record, stats)
            self.assertEqual(results, [])


class TestE2EKotlin(unittest.TestCase):
    """E2E統合テスト: Kotlin フィクスチャでツールを実行し、期待TSVと比較する"""

    TESTS_DIR = Path(__file__).parent / "kotlin"

    def test_kotlinフィクスチャのE2E出力が期待TSVと一致する(self):
        """Kotlin フィクスチャに対する解析結果のTSVが期待値と一致することを確認"""
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
                if record.usage_type == "const定数定義":
                    const_name = extract_const_name(record.code)
                    if const_name:
                        all_records.extend(track_const(const_name, src_dir, record, stats))

            output_path = output_dir / "TARGET.tsv"
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
