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


if __name__ == "__main__":
    unittest.main()
