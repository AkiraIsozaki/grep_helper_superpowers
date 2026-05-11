"""dispatcher.main のインクリメンタル TSV 書き出しテスト。

WHAT 観察: 各 keyword の TSV がディスク上に出現するタイミングを
on_handler_complete を fake で駆動して確定的に検証する（OS スケジューラ依存を排除）。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.model import GrepRecord, ProcessStats, RefType


class TestDispatcherIncrementalWrite(unittest.TestCase):
    """全 handler 完了時点で各 keyword の TSV が書き出される。"""

    def _setup_dirs(self, tmp: Path) -> tuple[Path, Path, Path]:
        src = tmp / "src"; src.mkdir()
        inp = tmp / "input"; inp.mkdir()
        out = tmp / "output"; out.mkdir()
        (src / "a.sql").write_text("SELECT 'A' FROM t;\n")
        (inp / "A.grep").write_text("a.sql:1:SELECT 'A' FROM t;\n")
        (inp / "B.grep").write_text("a.sql:1:SELECT 'A' FROM t;\n")
        return src, inp, out

    def test_全handler完了後に全keywordのTSVが出揃う(self):
        from grep_helper import dispatcher
        with tempfile.TemporaryDirectory() as tmp:
            src, inp, out = self._setup_dirs(Path(tmp))
            argv = [
                "analyze_all.py",
                "--source-dir", str(src),
                "--input-dir", str(inp),
                "--output-dir", str(out),
            ]
            with patch.object(sys, "argv", argv):
                rc = dispatcher.main()
            self.assertEqual(rc, 0)
            self.assertTrue((out / "A.tsv").exists())
            self.assertTrue((out / "B.tsv").exists())

    def test_handler_namesが空でも直接分類のみで全keywordのTSVが出揃う(self):
        """全 handler が batch_track_indirect を持たない縁ケース。
        _all_handlers() を fake で空にして dispatcher.main を呼ぶ。
        """
        from grep_helper import dispatcher
        with tempfile.TemporaryDirectory() as tmp:
            src, inp, out = self._setup_dirs(Path(tmp))
            argv = [
                "analyze_all.py",
                "--source-dir", str(src),
                "--input-dir", str(inp),
                "--output-dir", str(out),
            ]
            with patch.object(dispatcher, "_all_handlers", lambda: iter([])), \
                 patch.object(sys, "argv", argv):
                rc = dispatcher.main()
            self.assertEqual(rc, 0)
            self.assertTrue((out / "A.tsv").exists())
            self.assertTrue((out / "B.tsv").exists())

    def test_同じ入力で3回実行しても全TSVがバイト一致する(self):
        """決定的ソートにより、handler 並列順序が違っても出力は同じ。"""
        from grep_helper import dispatcher
        with tempfile.TemporaryDirectory() as tmp:
            src, inp, out1 = self._setup_dirs(Path(tmp))
            out2 = Path(tmp) / "output2"; out2.mkdir()
            out3 = Path(tmp) / "output3"; out3.mkdir()
            for out in (out1, out2, out3):
                argv = [
                    "analyze_all.py",
                    "--source-dir", str(src),
                    "--input-dir", str(inp),
                    "--output-dir", str(out),
                    "--handler-workers", "2",
                ]
                with patch.object(sys, "argv", argv):
                    rc = dispatcher.main()
                self.assertEqual(rc, 0)
            self.assertEqual(
                (out1 / "A.tsv").read_bytes(),
                (out2 / "A.tsv").read_bytes(),
            )
            self.assertEqual(
                (out2 / "A.tsv").read_bytes(),
                (out3 / "A.tsv").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
