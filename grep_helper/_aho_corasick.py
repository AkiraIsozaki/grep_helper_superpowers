"""Pure Python Aho-Corasick (オフライン環境フォールバック用)。

pyahocorasick が利用可能ならそちらを優先することを呼び出し側に推奨する。
"""
from __future__ import annotations

from collections import deque
from typing import Iterable, Iterator


class AhoCorasick:
    def __init__(self, patterns: Iterable[str]) -> None:
        self._goto: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._out: list[list[str]] = [[]]
        for p in patterns:
            self._add(p)
        self._build_fail()

    def _add(self, pattern: str) -> None:
        node = 0
        for ch in pattern:
            nxt = self._goto[node].get(ch)
            if nxt is None:
                self._goto.append({})
                self._fail.append(0)
                self._out.append([])
                nxt = len(self._goto) - 1
                self._goto[node][ch] = nxt
            node = nxt
        self._out[node].append(pattern)

    def _build_fail(self) -> None:
        q: deque[int] = deque()
        for ch, child in self._goto[0].items():
            self._fail[child] = 0
            q.append(child)
        while q:
            r = q.popleft()
            for ch, u in self._goto[r].items():
                q.append(u)
                state = self._fail[r]
                while state and ch not in self._goto[state]:
                    state = self._fail[state]
                next_state = self._goto[state].get(ch, 0)
                self._fail[u] = next_state if next_state != u else 0
                self._out[u].extend(self._out[self._fail[u]])

    def findall(self, text: str) -> Iterator[tuple[int, str]]:
        state = 0
        for i, ch in enumerate(text):
            while state and ch not in self._goto[state]:
                state = self._fail[state]
            state = self._goto[state].get(ch, 0)
            for pat in self._out[state]:
                yield (i - len(pat) + 1, pat)

    def findall_word_boundary(self, text: str, word_chars: str) -> Iterator[tuple[int, str]]:
        wset = set(word_chars)
        for pos, pat in self.findall(text):
            left_ok = pos == 0 or text[pos - 1] not in wset
            right = pos + len(pat)
            right_ok = right == len(text) or text[right] not in wset
            if left_ok and right_ok:
                yield (pos, pat)
