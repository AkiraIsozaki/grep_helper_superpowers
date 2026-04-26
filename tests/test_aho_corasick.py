import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAhoCorasick(unittest.TestCase):
    def test_基本的な複数パターンマッチが期待通りの位置と語を返す(self):
        """複数パターンを与えて findall が全マッチ (位置, 語) を返すことを確認する"""
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["he", "she", "his", "hers"])
        result = sorted(ac.findall("ushers"))
        self.assertEqual(result, [(1, "she"), (2, "he"), (2, "hers")])

    def test_重なり合うパターンが取りこぼされず全て検出される(self):
        """部分文字列を含むパターン群でも重複マッチを欠落させずに返すことを確認する"""
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["abc", "bc", "c"])
        result = sorted(ac.findall("abc"))
        self.assertEqual(result, [(0, "abc"), (1, "bc"), (2, "c")])

    def test_空文字列を入力した場合はマッチが空になる(self):
        """空入力に対して findall が空リストを返すことを確認する"""
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["foo"])
        self.assertEqual(list(ac.findall("")), [])

    def test_単語境界ヘルパーが識別子内のマッチを除外する(self):
        """findall_word_boundary が単語文字に隣接するマッチを除外し、独立した語のみ返すことを確認する"""
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["FOO"])
        result = list(ac.findall_word_boundary("FOO_BAR FOO BAZ", word_chars="abcdefghijklmnopqrstuvwxyz_"))
        # FOO_BAR は _ で続くので除外、" FOO " はマッチ
        self.assertEqual(result, [(8, "FOO")])


if __name__ == "__main__":
    unittest.main()
