"""run_full_pipeline の最小契約テスト。

handler を渡すと、grep ファイル群を処理して output_dir に <stem>.tsv を書く。
in-process 呼び出しで argparse を介さない。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile

from grep_helper.languages import sql as sql_handler  # 既存ハンドラを借りる
from grep_helper.pipeline import run_full_pipeline


class TestRunFullPipeline(unittest.TestCase):
    """run_full_pipeline は in-process で呼べる完全パイプライン。"""

    def test_grepファイルを与えると同名のtsvが出力される(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            input_dir = tmp_path / "input"
            output_dir = tmp_path / "output"
            src_dir.mkdir()
            input_dir.mkdir()
            sample_sql = src_dir / "sample.sql"
            sample_sql.write_text("SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8")
            grep_path = input_dir / "A.grep"
            grep_path.write_text("src/sample.sql:1:SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8")

            run_full_pipeline(
                source_dir=src_dir,
                input_dir=input_dir,
                output_dir=output_dir,
                handler=sql_handler,
                workers=1,
            )

            self.assertTrue((output_dir / "A.tsv").exists())


class TestRunFullPipelineAggregation(unittest.TestCase):
    """集約処理 (E-2): 複数 grep を 1 回の間接追跡で処理しても、
    grep ごとに 1 本ずつ処理した場合と完全一致の TSV が出る。
    """

    def test_複数grepでも単独処理と同じTSVが出力される(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            src_dir.mkdir()
            (src_dir / "sample.sql").write_text(
                "SELECT * FROM t WHERE x = 'A';\n"
                "SELECT * FROM t WHERE x = 'B';\n",
                encoding="utf-8",
            )

            # 集約: 同じ input_dir に 2 grep
            input_combined = tmp_path / "input_combined"
            input_combined.mkdir()
            (input_combined / "A.grep").write_text(
                "src/sample.sql:1:SELECT * FROM t WHERE x = 'A';\n",
                encoding="utf-8",
            )
            (input_combined / "B.grep").write_text(
                "src/sample.sql:2:SELECT * FROM t WHERE x = 'B';\n",
                encoding="utf-8",
            )
            output_combined = tmp_path / "output_combined"
            run_full_pipeline(
                source_dir=src_dir, input_dir=input_combined,
                output_dir=output_combined, handler=sql_handler, workers=1,
            )

            # 単独: 1 grep ずつ別 input_dir で実行
            output_solo = tmp_path / "output_solo"
            output_solo.mkdir()
            for stem, body in [("A", "1:SELECT * FROM t WHERE x = 'A';"),
                               ("B", "2:SELECT * FROM t WHERE x = 'B';")]:
                input_solo = tmp_path / f"input_{stem}"
                input_solo.mkdir()
                (input_solo / f"{stem}.grep").write_text(
                    f"src/sample.sql:{body}\n", encoding="utf-8",
                )
                run_full_pipeline(
                    source_dir=src_dir, input_dir=input_solo,
                    output_dir=output_solo, handler=sql_handler, workers=1,
                )

            # 比較: A.tsv / B.tsv の中身が一致
            for keyword in ("A", "B"):
                combined = (output_combined / f"{keyword}.tsv").read_bytes()
                solo = (output_solo / f"{keyword}.tsv").read_bytes()
                self.assertEqual(combined, solo,
                                 f"{keyword}.tsv が集約/単独で一致しない")

    def test_1つのgrepが読めなくても他のgrepは処理される(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            src_dir.mkdir()
            (src_dir / "sample.sql").write_text(
                "SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8",
            )
            input_dir = tmp_path / "input"
            input_dir.mkdir()
            # A.grep は正常
            (input_dir / "A.grep").write_text(
                "src/sample.sql:1:SELECT * FROM t WHERE x = 'A';\n",
                encoding="utf-8",
            )
            # B.grep は読み取り時に IsADirectoryError を起こすディレクトリ
            (input_dir / "B.grep").mkdir()

            output_dir = tmp_path / "output"
            run_full_pipeline(
                source_dir=src_dir, input_dir=input_dir,
                output_dir=output_dir, handler=sql_handler, workers=1,
            )
            # A.tsv は正常に生成されているはず
            self.assertTrue((output_dir / "A.tsv").exists())
            # B.tsv は失敗して未生成 or 空でもよい（仕様: 個別 grep 失敗は他に巻き込まない）


if __name__ == "__main__":
    unittest.main()
