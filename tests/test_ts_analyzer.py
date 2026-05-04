import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.ts import classify_usage as classify_usage_ts
from grep_helper.model import ProcessStats
from grep_helper.tsv_output import write_tsv
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import ts as _ts_handler
from grep_helper.file_cache import _file_lines_cache_clear


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _ts_handler, keyword=keyword, stats=stats)


class TestClassifyUsageTs(unittest.TestCase):
    """TestClassifyUsageTs: classify_usage(ts) の分類ラベル返り値を観察するテスト。
    E2E (TestE2ETs) は関数引数/const定数定義のみ通過するため、
    変数代入/条件判定/return文/デコレータ/その他 の分岐は本クラスでのみ保証される。
    """

    def test_const定数定義として分類されること(self):
        self.assertEqual(classify_usage_ts('const STATUS = "TARGET"'), "const定数定義")

    def test_let宣言は変数代入として分類されること(self):
        self.assertEqual(classify_usage_ts('let x = STATUS'), "変数代入(let/var)")

    def test_var宣言は変数代入として分類されること(self):
        self.assertEqual(classify_usage_ts('var x = STATUS'), "変数代入(let/var)")

    def test_if文の比較は条件判定として分類されること(self):
        self.assertEqual(classify_usage_ts('if (code === STATUS)'), "条件判定")

    def test_switch文は条件判定として分類されること(self):
        self.assertEqual(classify_usage_ts('switch (STATUS)'), "条件判定")

    def test_return文として分類されること(self):
        self.assertEqual(classify_usage_ts('return STATUS'), "return文")

    def test_デコレータ記法が分類されること(self):
        self.assertEqual(classify_usage_ts('@Component'), "デコレータ")

    def test_関数呼び出しの引数として分類されること(self):
        self.assertEqual(classify_usage_ts('process(STATUS)'), "関数引数")

    def test_該当しない行はその他として分類されること(self):
        self.assertEqual(classify_usage_ts('STATUS'), "その他")


class TestE2ETs(unittest.TestCase):
    """TestE2ETs: process_grep_file → write_tsv の TypeScript 経路全体の TSV 出力を観察するテスト。
    grep 行パース・分類・TSV 整形を含む統合経路の回帰検出を担う。
    """

    TESTS_DIR = Path(__file__).parent / "ts"

    def test_TARGETに対するE2E解析結果が期待TSVと一致すること(self):
        src_dir       = self.TESTS_DIR / "src"
        input_dir     = self.TESTS_DIR / "input"
        expected_path = self.TESTS_DIR / "expected" / "TARGET.tsv"

        self.assertTrue(src_dir.exists())
        self.assertTrue(expected_path.exists())

        _file_lines_cache_clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ProcessStats()
            grep_path = input_dir / "TARGET.grep"

            direct_records = _process_grep_file(grep_path, "TARGET", src_dir, stats)
            output_path = output_dir / "TARGET.tsv"
            write_tsv(list(direct_records), output_path)

            actual   = output_path.read_text(encoding="utf-8-sig").splitlines()
            expected = expected_path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(actual, expected)


from grep_helper.languages.ts import (
    extract_const_name as extract_const_name_ts,
    track_const as track_const_ts,
    batch_track_indirect as batch_track_indirect_ts,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractConstNameTs(unittest.TestCase):
    """TestExtractConstNameTs: extract_const_name の抽出有無を観察するテスト。"""

    def test_const宣言から定数名を抽出する(self):
        self.assertEqual(extract_const_name_ts('const STATUS_CODE = "777";'), "STATUS_CODE")

    def test_export_constから定数名を抽出する(self):
        self.assertEqual(extract_const_name_ts('export const STATUS_CODE = "777";'), "STATUS_CODE")

    def test_型注釈付きconstから名前を抽出する(self):
        self.assertEqual(extract_const_name_ts('const COUNT: number = 5;'), "COUNT")

    def test_let宣言からは抽出しない(self):
        self.assertIsNone(extract_const_name_ts('let x = STATUS_CODE;'))

    def test_var宣言からは抽出しない(self):
        self.assertIsNone(extract_const_name_ts('var x = STATUS_CODE;'))

    def test_分割代入は抽出しない(self):
        self.assertIsNone(extract_const_name_ts('const { a, b } = obj;'))


class TestTrackConstTs(unittest.TestCase):
    """TestTrackConstTs: track_const_ts の間接参照検出と定義行除外を観察する。"""

    def test_別tsファイルでの参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            (src / "service.ts").write_text('if (x === STATUS_CODE) { return; }\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "constants.ts"),
                lineno="1",
                code='const STATUS_CODE = "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_const_ts("STATUS_CODE", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.ts" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_定義行自身は間接レコードに含まれない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "constants.ts"),
                lineno="1",
                code='const STATUS_CODE = "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_const_ts("STATUS_CODE", src, record, stats)
            self.assertEqual(results, [])


class TestBatchTrackIndirectTs(unittest.TestCase):
    """TestBatchTrackIndirectTs: batch_track_indirect の起点フィルタ・集約を観察する。"""

    def test_const定数定義のレコードのみ起点となる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            (src / "service.ts").write_text('if (x === STATUS_CODE) { return; }\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="const定数定義",
                    filepath=str(src / "constants.ts"),
                    lineno="1",
                    code='const STATUS_CODE = "777";',
                ),
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入(let/var)",
                    filepath=str(src / "service.ts"),
                    lineno="1",
                    code='let local = STATUS_CODE;',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_ts(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.ts" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_別言語ファイルのレコードは起点にならない(self):
        """detect_handler ゲートの観察: .kt ファイル由来のレコードは
        usage_type が ts の起点条件に合致しても起点にしない。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Constants.kt").write_text('const STATUS_CODE = "777";\n')
            (src / "service.ts").write_text('if (x === STATUS_CODE) { return; }\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="const定数定義",
                    filepath=str(src / "Constants.kt"),
                    lineno="1",
                    code='const STATUS_CODE = "777";',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_ts(records, src, None, workers=1)
            self.assertEqual(results, [])

    def test_workers_2と1で同じレコード集合を返す(self):
        """Linux fork 前提の並列テスト。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            (src / "service.ts").write_text('if (x === STATUS_CODE) { return; }\n')
            (src / "worker.ts").write_text('process(STATUS_CODE);\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="const定数定義",
                    filepath=str(src / "constants.ts"),
                    lineno="1",
                    code='const STATUS_CODE = "777";',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect_ts(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect_ts(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))


if __name__ == "__main__":
    unittest.main()
