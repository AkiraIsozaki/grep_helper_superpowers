"""バッチスキャナ（Aho-Corasick / regex）。"""
from __future__ import annotations

import re


class _BatchScanner:
    def __init__(self, patterns: list[str], backend: str, impl):
        self.patterns = patterns
        self.backend = backend
        self._impl = impl

    def findall(self, line: str):
        if self.backend == "regex":
            for m in self._impl.finditer(line):
                yield (m.start(), m.group(1))
        else:
            yield from self._impl.findall_word_boundary(
                line, word_chars="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
            )


def build_batch_scanner(patterns: list[str], threshold: int = 100) -> _BatchScanner:
    """名前リストから「単語境界一致」スキャナを作る。

    パターン数が閾値以上なら Aho-Corasick を使う（pyahocorasick または pure Python）。
    閾値未満は再来通りの combined regex。
    """
    if len(patterns) >= threshold:
        try:
            import ahocorasick as _pyaho  # type: ignore[import-not-found]
            ac = _pyaho.Automaton()
            for p in patterns:
                ac.add_word(p, p)
            ac.make_automaton()

            class _Wrap:
                def findall_word_boundary(self, line, word_chars):
                    wset = set(word_chars)
                    for end, p in ac.iter(line):
                        start = end - len(p) + 1
                        left = start == 0 or line[start - 1] not in wset
                        right = end + 1 == len(line) or line[end + 1] not in wset
                        if left and right:
                            yield (start, p)
            return _BatchScanner(patterns, "ahocorasick", _Wrap())
        except ImportError:
            from grep_helper._aho_corasick import AhoCorasick  # type: ignore[import-not-found]
            return _BatchScanner(patterns, "ahocorasick", AhoCorasick(patterns))
    combined = re.compile(r"\b(" + "|".join(re.escape(p) for p in patterns) + r")\b")
    return _BatchScanner(patterns, "regex", combined)
