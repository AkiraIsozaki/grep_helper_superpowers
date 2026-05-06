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


class TestGrepFilterFilesUseMmap(unittest.TestCase):
    """use_mmap=True/False は同一の結果ファイルリストを返す。"""

    def setUp(self):
        from grep_helper.source_files import _source_files_cache_clear
        _source_files_cache_clear()

    def _make_src(self, tmp: Path) -> Path:
        from grep_helper.source_files import _source_files_cache_clear
        _source_files_cache_clear()
        src = tmp / "src"
        src.mkdir()
        (src / "a.java").write_text("class A { String NAME = \"hit\"; }\n")
        (src / "b.java").write_text("class B { /* nothing */ }\n")
        (src / "c.java").write_text("public static final String FOO = \"hit\";\n")
        return src

    def test_use_mmap_TrueとFalseで結果ファイルリストが一致する(self):
        from grep_helper.source_files import grep_filter_files
        with tempfile.TemporaryDirectory() as tmp:
            src = self._make_src(Path(tmp))
            with_mmap = grep_filter_files(["NAME", "FOO"], src, [".java"], use_mmap=True)
            from grep_helper.source_files import _source_files_cache_clear
            _source_files_cache_clear()
            without_mmap = grep_filter_files(["NAME", "FOO"], src, [".java"], use_mmap=False)
            self.assertEqual(
                [str(p) for p in with_mmap],
                [str(p) for p in without_mmap],
            )

    def test_use_mmap_Falseでも空ファイルはスキップされる(self):
        from grep_helper.source_files import grep_filter_files
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "empty.java").write_bytes(b"")
            (src / "hit.java").write_text("FOO")
            result = grep_filter_files(["FOO"], src, [".java"], use_mmap=False)
            self.assertEqual([p.name for p in result], ["hit.java"])

    def test_空patternsならcandidatesがそのまま返る(self):
        from grep_helper.source_files import grep_filter_files
        with tempfile.TemporaryDirectory() as tmp:
            src = self._make_src(Path(tmp))
            # 非 ASCII 名前のみだと patterns が空になる経路
            result = grep_filter_files(["日本語識別子"], src, [".java"], use_mmap=True)
            # ASCII でないので patterns は空 → candidates 全件
            self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
