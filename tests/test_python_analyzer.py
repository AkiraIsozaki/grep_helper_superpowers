import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.languages.python import classify_usage as classify_usage_python
from grep_helper.model import ProcessStats
from grep_helper.tsv_output import write_tsv
from grep_helper.pipeline import process_grep_file as _pgf
from grep_helper.languages import python as _python_handler
from grep_helper.file_cache import _file_lines_cache_clear


def _process_grep_file(path, keyword, source_dir, stats):
    return _pgf(path, source_dir, _python_handler, keyword=keyword, stats=stats)


class TestClassifyUsagePython(unittest.TestCase):
    """TestClassifyUsagePython: classify_usage(python) の分類ラベル返り値を観察するテスト。
    E2E (TestE2EPython) は変数代入/条件判定のみ通過するため、
    return文/デコレータ/関数引数/その他 の分岐は本クラスでのみ保証される。
    """

    def test_単純な変数代入を変数代入と分類する(self):
        self.assertEqual(classify_usage_python('STATUS = "TARGET"'), "変数代入")

    def test_インデント付き代入も変数代入と分類する(self):
        self.assertEqual(classify_usage_python('    x = STATUS'), "変数代入")

    def test_if文の比較式を条件判定と分類する(self):
        self.assertEqual(classify_usage_python('if code == STATUS:'), "条件判定")

    def test_elif文のin式を条件判定と分類する(self):
        self.assertEqual(classify_usage_python('elif STATUS in values:'), "条件判定")

    def test_return文をreturn文と分類する(self):
        self.assertEqual(classify_usage_python('return STATUS'), "return文")

    def test_decoratorをデコレータと分類する(self):
        self.assertEqual(classify_usage_python('@property'), "デコレータ")

    def test_関数呼び出しの引数を関数引数と分類する(self):
        self.assertEqual(classify_usage_python('process(STATUS)'), "関数引数")

    def test_該当しない行はその他と分類する(self):
        self.assertEqual(classify_usage_python('STATUS'), "その他")


class TestE2EPython(unittest.TestCase):
    """TestE2EPython: process_grep_file → write_tsv の Python 経路全体の TSV 出力を観察するテスト。
    grep 行パース・分類・TSV 整形を含む統合経路の回帰検出を担う。
    """

    TESTS_DIR = Path(__file__).parent / "python"

    def test_TARGETシンボルのE2E解析結果が期待TSVと一致する(self):
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


from grep_helper.languages.python import (
    extract_module_const_name,
    track_module_const,
    batch_track_indirect,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractModuleConstName(unittest.TestCase):
    """TestExtractModuleConstName: extract_module_const_name の抽出有無を観察するテスト。
    None 返却（小文字代入や非代入行）の WHAT は E2E TSV からは観察できないため keep。
    """

    def test_全大文字定数定義から名前を抽出する(self):
        self.assertEqual(extract_module_const_name('STATUS_CODE = "777"'), "STATUS_CODE")

    def test_型注釈付き全大文字定数定義から名前を抽出する(self):
        self.assertEqual(extract_module_const_name('MAX_RETRY: int = 5'), "MAX_RETRY")

    def test_インデント付き全大文字定数からも名前を抽出する(self):
        self.assertEqual(extract_module_const_name('    MY_CONST = 1'), "MY_CONST")

    def test_小文字シングルトンからは抽出しない(self):
        self.assertIsNone(extract_module_const_name('app = Flask(__name__)'))

    def test_小文字インデントなし代入からは抽出しない(self):
        self.assertIsNone(extract_module_const_name('db = SQLAlchemy()'))

    def test_dunder名は抽出しない(self):
        self.assertIsNone(extract_module_const_name('__all__ = ["x"]'))

    def test_等価比較は抽出しない(self):
        self.assertIsNone(extract_module_const_name('if x == STATUS_CODE:'))

    def test_非代入行は抽出しない(self):
        self.assertIsNone(extract_module_const_name('return STATUS_CODE'))


class TestTrackModuleConst(unittest.TestCase):
    """TestTrackModuleConst: track_module_const の間接参照検出と定義行除外を観察するテスト。"""

    def test_別ファイルでの参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            (src / "service.py").write_text('if x == STATUS_CODE:\n    pass\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(src / "constants.py"),
                lineno="1",
                code='STATUS_CODE = "777"',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_module_const("STATUS_CODE", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.py" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_定義行自身は間接レコードに含まれない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(src / "constants.py"),
                lineno="1",
                code='STATUS_CODE = "777"',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_module_const("STATUS_CODE", src, record, stats)
            self.assertEqual(results, [])


class TestBatchTrackIndirectPython(unittest.TestCase):
    """TestBatchTrackIndirectPython: batch_track_indirect の起点フィルタ・集約を観察するテスト。
    主要な公開 API のブラックボックステスト。
    """

    def test_変数代入usage_typeのレコードのみ起点となる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            (src / "service.py").write_text('if x == STATUS_CODE:\n    pass\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "constants.py"),
                    lineno="1",
                    code='STATUS_CODE = "777"',
                ),
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="条件判定",
                    filepath=str(src / "service.py"),
                    lineno="1",
                    code='if x == STATUS_CODE:',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.py" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_小文字シングルトンは起点にならない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "app_init.py").write_text('app = Flask(__name__)\n')
            (src / "service.py").write_text('app.run()\n')
            records = [
                GrepRecord(
                    keyword="app",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "app_init.py"),
                    lineno="1",
                    code='app = Flask(__name__)',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect(records, src, None, workers=1)
            self.assertEqual(results, [])

    def test_workers_2と1で同じレコード集合を返す(self):
        """Linux fork 前提の並列テスト（spawn 環境はスコープ外）。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            (src / "service.py").write_text('if x == STATUS_CODE:\n    pass\n')
            (src / "worker.py").write_text('process(STATUS_CODE)\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "constants.py"),
                    lineno="1",
                    code='STATUS_CODE = "777"',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))


if __name__ == "__main__":
    unittest.main()
