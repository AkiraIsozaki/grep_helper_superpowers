import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAhoCorasick(unittest.TestCase):
    def test_basic_match(self):
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["he", "she", "his", "hers"])
        result = sorted(ac.findall("ushers"))
        self.assertEqual(result, [(1, "she"), (2, "he"), (2, "hers")])

    def test_no_overlap_loss(self):
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["abc", "bc", "c"])
        result = sorted(ac.findall("abc"))
        self.assertEqual(result, [(0, "abc"), (1, "bc"), (2, "c")])

    def test_empty_input(self):
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["foo"])
        self.assertEqual(list(ac.findall("")), [])

    def test_word_boundary_helper(self):
        from aho_corasick import AhoCorasick
        ac = AhoCorasick(["FOO"])
        result = list(ac.findall_word_boundary("FOO_BAR FOO BAZ", word_chars="abcdefghijklmnopqrstuvwxyz_"))
        # FOO_BAR は _ で続くので除外、" FOO " はマッチ
        self.assertEqual(result, [(8, "FOO")])


if __name__ == "__main__":
    unittest.main()
