"""source_files の _read_based_find / grep_filter_files テスト。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.source_files import _read_based_find


class TestReadBasedFind(unittest.TestCase):
    """1MB チャンク + prepend オーバーラップでバイト列を検索する。"""

    def test_パターンが先頭で見つかる(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"FOO" + b"X" * 100)
            self.assertTrue(_read_based_find(p, [b"FOO"], chunk_size=8))

    def test_パターンが末尾で見つかる(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"X" * 100 + b"BAR")
            self.assertTrue(_read_based_find(p, [b"BAR"], chunk_size=8))

    def test_パターンがチャンク境界をまたいでも見つかる(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            # chunk_size=8、パターン長 7 → overlap=6。
            # 1 チャンク目: bytes 0..7 (= "X"*6 + "BI")
            # 2 チャンク目: bytes 8..15 (= "GNAME" + "X"*3)
            # prepend overlap で 2 チャンク目処理時に "BI" + "GNAME"... が連結される
            p.write_bytes(b"X" * 6 + b"BIGNAME" + b"X" * 3)
            self.assertTrue(_read_based_find(p, [b"BIGNAME"], chunk_size=8))

    def test_複数パターンのいずれか1つでもヒットすればtrue(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"only ALPHA here")
            self.assertTrue(_read_based_find(p, [b"BETA", b"ALPHA"], chunk_size=64))

    def test_どのパターンもヒットしないとfalse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"only ALPHA here")
            self.assertFalse(_read_based_find(p, [b"BETA", b"GAMMA"], chunk_size=64))

    def test_空ファイルではfalse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"")
            self.assertFalse(_read_based_find(p, [b"X"], chunk_size=8))

    def test_1バイトパターンも検出できる(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"X" * 100 + b"Y")
            self.assertTrue(_read_based_find(p, [b"Y"], chunk_size=8))


if __name__ == "__main__":
    unittest.main()
