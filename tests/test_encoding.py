"""detect_encoding のキャッシュ挙動テスト。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.encoding import detect_encoding, _encoding_cache_clear


class TestEncodingCache(unittest.TestCase):
    def setUp(self):
        _encoding_cache_clear()

    def test_同じパスを2回呼ぶとファイル変更後も古い結果が返る(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes("こんにちは世界".encode("cp932"))
            first = detect_encoding(p)

            p.write_bytes(b"Hello world Hello world")
            second = detect_encoding(p)

            self.assertEqual(second, first,
                             "キャッシュが効けば 2 回目は 1 回目と同じ結果のはず")

    def test_override指定時はキャッシュを使わずそのまま返す(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"hello")
            self.assertEqual(detect_encoding(p, "utf-8"), "utf-8")
            self.assertEqual(detect_encoding(p, "shift_jis"), "shift_jis")

    def test_存在しないパスでもcp932にフォールバックする(self):
        result = detect_encoding(Path("/nonexistent/path/zzz"))
        self.assertEqual(result, "cp932")

    def test_クリア後はキャッシュが効かなくなる(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes("こんにちは世界".encode("cp932"))
            first = detect_encoding(p)

            p.write_bytes(("Hello world " * 50).encode("utf-8"))
            cached = detect_encoding(p)
            self.assertEqual(cached, first, "クリア前はキャッシュ通り")

            _encoding_cache_clear()
            re_detected = detect_encoding(p)
            self.assertNotEqual(re_detected, first,
                                "クリア後は新ファイル内容に対して chardet が再走するはず")


if __name__ == "__main__":
    unittest.main()
