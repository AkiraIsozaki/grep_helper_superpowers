# Test Style Rework — Pilot (test_common.py) 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tests/test_common.py` を WHAT 検証スタイル（古典派 TDD）に書き直し、ガイドラインの 7 翻訳パターン (A〜G) のうち A〜F を実適用、G は試験翻訳スパイクとして所見化する。

**Architecture:** 単一ファイル `tests/test_common.py` のテストを、メソッドごとに「グリーン確認 → 書き換え → グリーン確認 → 手動 mutation スポットチェック → コミット」のリズムで書き換える。書き直し対象でないクラスはそのままだが docstring 削除のみ実施。production コード (`grep_helper/`) は変更しない（mutation チェック時のみ一時的にコメントアウトし戻す）。

**Tech Stack:** Python 3, `unittest`, optional `pytest` for runner ergonomics.

**Reference Spec:** `docs/superpowers/specs/2026-05-03-test-style-rework-design.md`

---

## File Structure

- **Modify:** `tests/test_common.py`（メイン対象）
- **Touch (一時的・コミットしない):** `grep_helper/file_cache.py`（mutation スポットチェックのみ）
- **Modify (Task 9 のみ):** `docs/superpowers/specs/2026-05-03-test-style-rework-design.md`（試験翻訳の所見追記）

---

## 棚卸し（Task 1 で参照）

| クラス | テスト | 扱い |
|---|---|---|
| TestCommonImports | 5 個 | パターン F のみ（docstring 削除） |
| TestGrepFilterFiles | 8 個 | パターン F のみ |
| TestDetectEncodingStreaming | 2 個 | パターン D（Whitebox 移送） |
| TestIterGrepLines | 2 個 | パターン E（型 assertion 削除＋smoke test 追加） |
| TestIterSourceFiles | 2 個 | パターン F のみ |
| TestResolveFileCached | 3 個 | パターン F のみ（既に振る舞い検証） |
| TestCachedFileLines | 3 個 | パターン A・B 適用 |
| TestBatchScannerSelector | 3 個 | パターン C（1 個保持・2 個 Whitebox 移送） |

---

### Task 1: ベースライン確認

**Files:**
- Verify only: `tests/test_common.py`

- [ ] **Step 1: 現状の test_common.py がグリーンであることを確認**

```bash
python -m unittest tests.test_common -v
```

Expected: すべて OK。失敗があったらここで止め、原因を報告する（このプラン外の問題）。

- [ ] **Step 2: 全体テストもグリーンであることを確認**

```bash
python -m unittest discover -v 2>&1 | tail -5
```

Expected: 末尾に `OK` を含むサマリ。

---

### Task 2: パターン F — メソッド docstring の一括削除

**Files:**
- Modify: `tests/test_common.py` 全体

- [ ] **Step 1: メソッドの docstring を全て削除**

`tests/test_common.py` 内の **テストメソッド** (`def test_...(self):` で始まるもの) 直下の docstring（"""..."""）を全て削除する。例：

Before:
```python
def test_GrepRecordのフィールドが正しく設定される(self):
    """GrepRecord 生成時に keyword が設定され src_var が空文字となる。"""
    r = GrepRecord("kw", "直接", "その他", "f.sql", "1", "code")
```

After:
```python
def test_GrepRecordのフィールドが正しく設定される(self):
    r = GrepRecord("kw", "直接", "その他", "f.sql", "1", "code")
```

**注意：** クラス直下の docstring（`class TestXxx(unittest.TestCase):` 直下）は残す（spec 規約）。ただしこの段階ではどのクラスにも触らない（後続 Task で必要なら追加・更新する）。

- [ ] **Step 2: 削除後のグリーン確認**

```bash
python -m unittest tests.test_common -v
```

Expected: すべて OK（docstring 削除はテスト挙動を変えない）。

- [ ] **Step 3: コミット**

```bash
git add tests/test_common.py
git commit -m "$(cat <<'EOF'
test(test_common): drop redundant method docstrings (pattern F)

メソッド名が日本語で WHAT を表現しているため docstring は冗長。
spec パターン F に従い一括削除。クラス docstring は据え置き。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: TestCachedFileLines にパターン A 適用 — キャッシュ hit を振る舞いで観察

**Files:**
- Modify: `tests/test_common.py` の `TestCachedFileLines.test_サイズ上限内ならキャッシュされる`

**WHAT 契約:** ファイルを書き換えても、キャッシュ済みなら古い値が返る（自動無効化しない契約）。

- [ ] **Step 1: 該当テスト単体のベースライン確認**

```bash
python -m unittest tests.test_common.TestCachedFileLines.test_サイズ上限内ならキャッシュされる -v
```

Expected: OK。

- [ ] **Step 2: テストを書き直す**

`tests/test_common.py` の `TestCachedFileLines.test_サイズ上限内ならキャッシュされる` を以下に置換：

```python
def test_キャッシュ済みファイルは書き換えても古い値が返る(self):
    from grep_helper.file_cache import cached_file_lines, _file_lines_cache_clear
    _file_lines_cache_clear()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.txt"
        p.write_text("first\n", encoding="utf-8")
        first = cached_file_lines(p, "utf-8")
        p.write_text("second\n", encoding="utf-8")
        second = cached_file_lines(p, "utf-8")
        self.assertEqual(first, ["first"])
        self.assertEqual(second, ["first"])  # キャッシュ hit で古い値
```

旧テスト本体（`assertIn(str(p), _file_lines_cache)` のあった箇所）は完全置き換えする。`_file_lines_cache` のインポートは他のテストで残っていれば触らない。

- [ ] **Step 3: 書き直し後のグリーン確認**

```bash
python -m unittest tests.test_common.TestCachedFileLines -v
```

Expected: OK（同クラス内すべて）。

- [ ] **Step 4: 手動 mutation スポットチェック — production 1 行コメントアウト**

`grep_helper/file_cache.py` の **38〜40 行目**（cache lookup ブロック）を一時的にコメントアウトする：

Before (file_cache.py:38-40):
```python
    if key in _file_lines_cache:
        _file_lines_cache.move_to_end(key)
        return _file_lines_cache[key]
```

After (mutation):
```python
    # if key in _file_lines_cache:
    #     _file_lines_cache.move_to_end(key)
    #     return _file_lines_cache[key]
```

その状態で：
```bash
python -m unittest tests.test_common.TestCachedFileLines.test_キャッシュ済みファイルは書き換えても古い値が返る -v
```

Expected: **FAIL**（cache hit が消えて常に再読込されるため、`second == ["second"]` になり assertion 失敗）。

- [ ] **Step 5: production を元に戻す**

`grep_helper/file_cache.py` を元に戻す（コメントアウトを解除）。

```bash
git diff grep_helper/file_cache.py
```

Expected: 差分なし。

- [ ] **Step 6: コミット**

```bash
git add tests/test_common.py
git commit -m "$(cat <<'EOF'
test(test_common): pattern A — observe cache hit via source mutation

旧: assertIn(str(p), _file_lines_cache) — 内部 dict の peek
新: ファイルを書き換えても古い値が返る — 自動無効化なし契約を WHAT として観察

Equivalence: cache lookup を 1 行コメントアウトすると新テストは赤くなる（手動 mutation 確認済み）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: TestCachedFileLines にパターン B 適用 — 退避を振る舞いで観察

**Files:**
- Modify: `tests/test_common.py` の `TestCachedFileLines.test_合計サイズが上限超過で古いものを破棄する`

**WHAT 契約:** 容量上限を超えると、初期エントリのうち**少なくとも 1 つ**は再読込される（退避ポリシー非依存）。

- [ ] **Step 1: ベースライン確認**

```bash
python -m unittest tests.test_common.TestCachedFileLines.test_合計サイズが上限超過で古いものを破棄する -v
```

Expected: OK。

- [ ] **Step 2: テストを書き直す**

`TestCachedFileLines.test_合計サイズが上限超過で古いものを破棄する` を以下に置換：

```python
def test_容量上限を超えると古いエントリが追い出されて再読込される(self):
    from grep_helper.file_cache import (
        cached_file_lines,
        _file_lines_cache_clear,
        set_file_lines_cache_limit,
    )
    _file_lines_cache_clear()
    set_file_lines_cache_limit(100)  # 100 byte 上限
    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            early = []
            for i in range(3):
                f = p / f"early{i}.txt"
                f.write_text("X" * 50, encoding="utf-8")
                cached_file_lines(f, "utf-8")
                early.append(f)
            for i in range(5):  # 容量上限を確実に超過
                f = p / f"later{i}.txt"
                f.write_text("X" * 50, encoding="utf-8")
                cached_file_lines(f, "utf-8")
            # 初期エントリの中身を書き換え、再読込が起きていることを観察
            re_read = []
            for f in early:
                f.write_text("CHANGED", encoding="utf-8")
                if cached_file_lines(f, "utf-8") == ["CHANGED"]:
                    re_read.append(f)
            self.assertGreaterEqual(len(re_read), 1)
    finally:
        set_file_lines_cache_limit(256 * 1024 * 1024)  # 復元
```

旧テストの `_file_lines_cache` peek 部分は完全に置き換える。

- [ ] **Step 3: 書き直し後のグリーン確認**

```bash
python -m unittest tests.test_common.TestCachedFileLines -v
```

Expected: OK。

- [ ] **Step 4: 手動 mutation スポットチェック**

`grep_helper/file_cache.py` の **50〜52 行目**（eviction ループ）を一時的にコメントアウトする：

Before (file_cache.py:50-52):
```python
    while _file_lines_cache_bytes > _file_lines_cache_limit and len(_file_lines_cache) > 1:
        _, old_lines = _file_lines_cache.popitem(last=False)
        _file_lines_cache_bytes -= _estimate_lines_bytes(old_lines)
```

After (mutation):
```python
    # while _file_lines_cache_bytes > _file_lines_cache_limit and len(_file_lines_cache) > 1:
    #     _, old_lines = _file_lines_cache.popitem(last=False)
    #     _file_lines_cache_bytes -= _estimate_lines_bytes(old_lines)
```

その状態で：
```bash
python -m unittest tests.test_common.TestCachedFileLines.test_容量上限を超えると古いエントリが追い出されて再読込される -v
```

Expected: **FAIL**（退避が起きないため、書き換え後も古い値（"X"*50）が返り続け、`re_read` が空になり `assertGreaterEqual(1)` で落ちる）。

- [ ] **Step 5: production を元に戻す**

```bash
git diff grep_helper/file_cache.py
```

Expected: 差分なし。

- [ ] **Step 6: コミット**

```bash
git add tests/test_common.py
git commit -m "$(cat <<'EOF'
test(test_common): pattern B — observe eviction via re-read after capacity exceed

旧: assertLessEqual(len(_file_lines_cache), 3) — dict サイズで判定
新: 上限超過後、初期エントリのうち少なくとも 1 つは再読込される — 退避ポリシー非依存

Equivalence: eviction loop を 3 行コメントアウトすると新テストは赤くなる（手動 mutation 確認済み）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: TestIterGrepLines にパターン E 適用 — 型 assertion 削除＋streaming smoke test

**Files:**
- Modify: `tests/test_common.py` の `TestIterGrepLines` クラス

**WHAT 契約:** 行が改行除去されて順番に取り出せる。加えて、巨大入力でも先頭少数行だけ消費して break しても妥当な時間で完了する（ストリーミング）。

- [ ] **Step 1: ベースライン確認**

```bash
python -m unittest tests.test_common.TestIterGrepLines -v
```

Expected: OK。

- [ ] **Step 2: 既存 2 テストの型 assertion を削除し命名を WHAT に揃える**

`TestIterGrepLines` クラス内を以下で置換（既存 2 テストの本体を残しつつ assertion を整理する）：

```python
class TestIterGrepLines(unittest.TestCase):
    def test_grep行を順序通りに取り出せる(self):
        from grep_helper.grep_input import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_text("a:1:foo\nb:2:bar\n", encoding="utf-8")
            self.assertEqual(list(iter_grep_lines(p, "utf-8")), ["a:1:foo", "b:2:bar"])

    def test_デコードエラーを置換して継続する(self):
        from grep_helper.grep_input import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_bytes(b"good\n\xff\xfe\xfd\nmore\n")
            self.assertEqual(list(iter_grep_lines(p, "utf-8")), ["good", "���", "more"])
```

- [ ] **Step 3: ストリーミング smoke test を 1 本追加**

同 `TestIterGrepLines` クラスの末尾に以下を追加：

```python
    def test_巨大ファイルでも先頭数行だけ消費して短時間で返る(self):
        import itertools, time
        from grep_helper.grep_input import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "huge.grep"
            # 数十 MB 相当を生成 (1MB × 30 行 / line)
            with open(p, "w", encoding="utf-8") as f:
                for i in range(300_000):
                    f.write(f"src/file.py:{i}:line content here\n")
            t0 = time.monotonic()
            head = list(itertools.islice(iter_grep_lines(p, "utf-8"), 5))
            elapsed = time.monotonic() - t0
            self.assertEqual(len(head), 5)
            self.assertEqual(head[0], "src/file.py:0:line content here")
            self.assertLess(elapsed, 2.0, f"ストリーミングが効いていない疑い: {elapsed:.3f}s")
```

注：閾値は緩く 2 秒。CI 環境でも余裕で通る想定。フレーキー化したら値を上げる。

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest tests.test_common.TestIterGrepLines -v
```

Expected: 3 テストすべて OK。smoke test は数百 ms で完了するはず。

- [ ] **Step 5: 手動 mutation スポットチェックは省略**

streaming smoke test は実装契約（generator-ness）を観察するもので、対応する production 1 行を機械的に特定しにくい。`grep_input.py:16-18` の `for line in f: yield ...` を `return list(f)` 等に置換すれば赤くなるが、本検証はオプション。**コミットメッセージにその旨を明記**して飛ばす。

- [ ] **Step 6: コミット**

```bash
git add tests/test_common.py
git commit -m "$(cat <<'EOF'
test(test_common): pattern E — drop type assertion, add streaming smoke test

旧: assertIsInstance(it, GeneratorType) — 型 instance を HOW として検証
新: 行順序の WHAT のみ assertion + 巨大入力で先頭数行を 2 秒以内に取り出せる smoke test

iter_grep_lines という関数名がストリーミング契約を公開している。
型 assertion 削除で契約が消えないよう smoke test を 1 本残す。

Mutation チェックは省略（streaming は単一行に局所化された契約ではないため）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: TestBatchScannerSelector にパターン C 適用 — 1 個保持・2 個 Whitebox 移送

**Files:**
- Modify: `tests/test_common.py` の `TestBatchScannerSelector`、新規 `TestBatchScannerSelectorWhitebox`

**WHAT 契約:** 1 〜 数百パターンのいずれでも同じマッチ結果が返る。**バックエンド名は内部最適化**で、Whitebox 側で別途固定する。

- [ ] **Step 1: ベースライン確認**

```bash
python -m unittest tests.test_common.TestBatchScannerSelector -v
```

Expected: OK。

- [ ] **Step 2: TestBatchScannerSelector の内容を以下に置換**

旧：3 テスト（うち 2 つは backend assertion）。
新：findall の振る舞いを 1〜数百パターンの代表点で検証する WHAT テスト。

```python
class TestBatchScannerSelector(unittest.TestCase):
    def test_findallが単語境界でマッチする(self):
        from grep_helper.scanner import build_batch_scanner
        scanner = build_batch_scanner(["FOO"])
        line = "x = FOO + FOOBAR;"
        results = [name for _, name in scanner.findall(line)]
        self.assertEqual(results, ["FOO"])

    def test_数パターンでも数百パターンでも同じマッチ結果になる(self):
        from grep_helper.scanner import build_batch_scanner
        small = build_batch_scanner(["A", "B", "C"])
        large_patterns = [f"NAME{i:04d}" for i in range(200)] + ["A", "B", "C"]
        large = build_batch_scanner(large_patterns)
        line = "use A and B and C here"
        small_hits = sorted(name for _, name in small.findall(line))
        large_hits = sorted(name for _, name in large.findall(line) if name in {"A","B","C"})
        self.assertEqual(small_hits, ["A", "B", "C"])
        self.assertEqual(large_hits, ["A", "B", "C"])
```

- [ ] **Step 3: 同ファイル末尾に Whitebox クラスを追加**

`tests/test_common.py` の末尾（`if __name__ == "__main__":` の直前）に以下を追加：

```python
class TestBatchScannerSelectorWhitebox(unittest.TestCase):
    """build_batch_scanner のバックエンド選択は内部最適化の実装契約。
    public な振る舞い（マッチ結果）はパターン数に依らず同一だが、
    性能劣化の早期検知のため backend 名を固定する。リファクタ時に同期更新が必要。
    """

    def test_パターン数が閾値以上ならahocorasickバックエンドが選ばれる(self):
        from grep_helper.scanner import build_batch_scanner
        scanner = build_batch_scanner([f"NAME{i:04d}" for i in range(200)])
        self.assertEqual(scanner.backend, "ahocorasick")

    def test_パターン数が閾値未満ならregexバックエンドが選ばれる(self):
        from grep_helper.scanner import build_batch_scanner
        scanner = build_batch_scanner(["A", "B", "C"])
        self.assertEqual(scanner.backend, "regex")
```

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest tests.test_common -v
```

Expected: すべて OK。新クラス含めグリーン。

- [ ] **Step 5: コミット**

```bash
git add tests/test_common.py
git commit -m "$(cat <<'EOF'
test(test_common): pattern C — keep findall WHAT, isolate backend selection to Whitebox

旧: scanner.backend == "ahocorasick" / "regex" を直接 assert
新:
- TestBatchScannerSelector: findall の振る舞い (WHAT) のみ検証
- TestBatchScannerSelectorWhitebox: backend 名を実装契約として固定

backend 名は内部最適化で、振る舞いとしては「両方とも同じマッチ結果」が WHAT。
性能劣化早期検知の必要性は隔離クラスで継続的に保証。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: TestDetectEncodingStreaming にパターン D 適用 — Whitebox 完全移送

**Files:**
- Modify: `tests/test_common.py` の `TestDetectEncodingStreaming` を削除、`TestDetectEncodingStreamingWhitebox` を末尾に追加

**WHAT 契約:** （振る舞いに翻訳できないため）`detect_encoding` が先頭 4096 byte のみ読む実装契約をホワイトボックスで固定する。

- [ ] **Step 1: ベースライン確認**

```bash
python -m unittest tests.test_common.TestDetectEncodingStreaming -v
```

Expected: OK。

- [ ] **Step 2: TestDetectEncodingStreaming クラスを削除**

`tests/test_common.py` から `class TestDetectEncodingStreaming(unittest.TestCase):` 全体（テスト 2 個含む）を削除する。

- [ ] **Step 3: ファイル末尾に TestDetectEncodingStreamingWhitebox を追加**

直前 Task で追加した `TestBatchScannerSelectorWhitebox` の **後ろ**に以下を追加（`if __name__ == "__main__":` の直前）。

中身は旧テストをそのまま移送する（インタラクション検証は Whitebox クラス内で許容される）。

```python
class TestDetectEncodingStreamingWhitebox(unittest.TestCase):
    """detect_encoding が先頭 4096 byte のみ読むという実装契約のテスト。
    巨大ファイルに対するメモリ・レイテンシ非機能要件を担保する。
    実装を変更したら本クラスも同期更新する必要がある。
    """

    def test_read_bytesを呼ばない(self):
        from grep_helper.encoding import detect_encoding
        from unittest.mock import patch
        # chardet のモデル遅延ロードが read_bytes を使うため、先に初期化しておく
        try:
            import chardet as _cd
            _cd.detect(b"warmup")
        except Exception:
            pass
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_bytes(b"hello world\n" * 100)
            orig_read_bytes = Path.read_bytes
            def boom(self_path):
                if str(self_path) == str(p):
                    raise AssertionError("read_bytes should not be called on target file")
                return orig_read_bytes(self_path)
            with patch.object(Path, "read_bytes", boom):
                enc = detect_encoding(p)
                self.assertIsInstance(enc, str)

    def test_最大4KBまでしか読まない(self):
        from grep_helper.encoding import detect_encoding
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "big.txt"
            p.write_bytes(b"A" * 100_000)
            sizes: list[int] = []
            real_open = open
            def tracking_open(*args, **kwargs):
                f = real_open(*args, **kwargs)
                orig_read = f.read
                def read(n=-1):
                    sizes.append(n if n >= 0 else 10**12)
                    return orig_read(n)
                f.read = read
                return f
            import grep_helper.encoding
            with unittest.mock.patch.object(grep_helper.encoding, "open", tracking_open, create=True):
                detect_encoding(p)
            self.assertTrue(len(sizes) > 0, "tracking_open was never called")
            self.assertTrue(all(n <= 4096 for n in sizes), sizes)
```

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest tests.test_common -v
```

Expected: すべて OK。`TestDetectEncodingStreaming` は消え、`TestDetectEncodingStreamingWhitebox` の 2 テストが OK。

- [ ] **Step 5: コミット**

```bash
git add tests/test_common.py
git commit -m "$(cat <<'EOF'
test(test_common): pattern D — isolate read-bytes interaction tests to Whitebox

旧: TestDetectEncodingStreaming にロンドン派的なインタラクション検証 2 件
新: TestDetectEncodingStreamingWhitebox に移送、クラス docstring で実装契約を明示

「呼ばれない」「4KB しか読まない」は性能契約。観察可能な振る舞いに翻訳できない
ため隔離クラス内に留める。spec パターン D の判定（タイミング NG・観察対象が曖昧）に該当。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: ホワイトボックス点検 — 不足ケースの追加（必要なら）

**Files:**
- Possibly modify: `tests/test_common.py`

**目的:** 書き直し後のテスト群を実装と突き合わせ、明らかに抜けている振る舞いがあれば**実装を知らないふりをして**ブラックボックス的にケースを足す。

- [ ] **Step 1: 各 production 関数の入力空間を整理する**

以下のリストを目で確認し、test_common.py に対応する WHAT テストがあるかチェックする。**実装の if 分岐を追わない**。「外から見て区別すべき入力カテゴリは何か」だけ考える。

| production | 観察すべき入力カテゴリ | 既存テスト |
|---|---|---|
| `parse_grep_line` | 正常 / バイナリ通知 / 空行 / 区切りなし / Windows パス / コード前後空白 | TestCommonImports に正常・バイナリ |
| `detect_encoding` | override あり / override なし & ASCII ファイル / 空ファイル / ファイル不在 | （Whitebox 側のみ。ブラックボックス側に**ゼロ**） |
| `cached_file_lines` | 初回読込 / 2 回目 hit / 上限超過退避 / エラーファイル | パターン A・B で 2 ケース。エラー系なし |
| `iter_grep_lines` | 通常 / 不正バイト / 空ファイル / 巨大ファイル | 3 ケースあり |
| `grep_filter_files` | マッチあり / マッチなし / 拡張子外 / 空 names / 空ファイル / 複数拡張子 / ソート / label | TestGrepFilterFiles に 8 ケース。十分 |
| `iter_source_files` | キャッシュ hit / 拡張子別キャッシュ | 2 ケースあり |
| `resolve_file_cached` | 相対 / 絶対 / 不在 / キャッシュ hit | 3 ケースあり |
| `build_batch_scanner` | 数パターン / 数百パターン / 単語境界 | パターン C で 2 ケース。十分 |

- [ ] **Step 2: 検出された穴を埋めるテストを追加**

判定の結果、以下が候補（実際にコードを読んで必要性を判断）：

**候補 1: `detect_encoding` のブラックボックス側 WHAT テスト（強く推奨）**

現状ブラックボックス側に 0 件、Whitebox 側のみ 2 件。WHAT が一切 public 検証されていない。同ファイル `TestDetectEncodingStreamingWhitebox` の前（または専用クラスとして）に以下を追加：

```python
class TestDetectEncoding(unittest.TestCase):
    def test_overrideを与えるとそのまま返る(self):
        from grep_helper.encoding import detect_encoding
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "any.txt"
            p.write_bytes(b"\xe3\x81\x82\xe3\x81\x84")
            self.assertEqual(detect_encoding(p, override="utf-16"), "utf-16")

    def test_存在しないファイルはcp932にフォールバックする(self):
        from grep_helper.encoding import detect_encoding
        result = detect_encoding(Path("/nonexistent/path/x.txt"))
        self.assertEqual(result, "cp932")
```

**候補 2: `cached_file_lines` のエラーファイル時の挙動**

read_text で例外が出るパス（権限なし等は環境依存なので避け、不在ファイルで観察）：

```python
class TestCachedFileLinesErrorPath(unittest.TestCase):
    def test_存在しないファイルは空リストを返す(self):
        from grep_helper.file_cache import cached_file_lines, _file_lines_cache_clear
        from grep_helper.model import ProcessStats
        _file_lines_cache_clear()
        stats = ProcessStats()
        result = cached_file_lines(Path("/nonexistent/x.txt"), "utf-8", stats)
        self.assertEqual(result, [])
        self.assertIn("/nonexistent/x.txt", stats.encoding_errors)
```

候補 1 と 2 のどちらか（または両方）を採用するかは、実際に読んで判断する。**全部採用するな** — 「明らかに不足」かどうかが基準。迷ったら**追加しない**（YAGNI）。

- [ ] **Step 3: 追加した各テストについて TDD 検証**

各追加に対して：
1. テスト単体実行 → 通る or 落ちる
2. 通れば既存実装が偶然カバーしている → そのまま採用
3. 落ちれば、production がそもそもその WHAT を満たしていない疑いがある → **コミットせず**ユーザーに報告（プラン外の発見）

```bash
python -m unittest tests.test_common -v
```

Expected: すべて OK（既存実装はこれらの WHAT を満たしているはず）。

- [ ] **Step 4: コミット**

追加が 1 件以上あった場合のみ：

```bash
git add tests/test_common.py
git commit -m "$(cat <<'EOF'
test(test_common): pattern step6 — fill obvious WHAT gaps in blackbox cases

ホワイトボックス点検で見えた穴を、実装を知らないふりでブラックボックス的に追加：
- detect_encoding に override / 不在ファイルの WHAT テスト
- (採用したら) cached_file_lines のエラーファイル時の WHAT テスト

すべて既存実装のもとでグリーン。原則 6（変更耐性）を満たしている。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

追加が 0 件の場合はコミット不要。Step 4 を飛ばして Task 9 へ。

---

### Task 9: パターン G 試験翻訳スパイク（コードは変更しない）

**Files:**
- Modify: `docs/superpowers/specs/2026-05-03-test-style-rework-design.md` （所見追記のみ）
- Read only: `tests/test_analyze.py:688-720`、`grep_helper/languages/java_track.py`、`tests/fixtures/java/`

**目的:** スイープ第一弾（test_analyze.py）でパターン G が機能するかを先行検証する。**コードは書き換えない。所見だけスペックに追記。**

- [ ] **Step 1: 試験翻訳の対象を読む**

```bash
sed -n '688,720p' tests/test_analyze.py
```

確認すべき点：
- `_get_method_scope` を直接呼んでいるか
- 引数アリティ（filepath, source_dir, lineno）
- assertion の中身

- [ ] **Step 2: 公開 API での代替経路を探す**

```bash
grep -nE "def (track_constant|track_field|track_local|find_getter)" grep_helper/languages/java_track.py
```

これらの公開関数が内部で `_get_method_scope` を呼んでいるかを 1 ファイル開いて確認：

```bash
grep -n "_get_method_scope" grep_helper/languages/java_track.py
```

呼んでいれば「公開 API 経由（パターン G の a 案）」が成り立つ。

- [ ] **Step 3: E2E カバーを確認**

```bash
ls tests/fixtures/java/
ls tests/fixtures/expected/
```

`Constants.java`（13 行目）の振る舞いが E2E ゴールデンに含まれているなら「E2E カバーで削除（パターン G の b 案）」が成り立つ。

- [ ] **Step 4: 所見をまとめる**

以下のいずれかに着地するはず：
- a 案で十分 → スイープでは TestGetMethodScope 全体を `track_constant` 等の公開 API 経由テストへ統合可能
- b 案で十分 → E2E ゴールデンが該当パスを踏んでいれば削除可能
- c 案 → どうしても private を直接叩くテストが要るなら Whitebox に隔離

判定ロジックを spec の末尾に追加する。

- [ ] **Step 5: spec の末尾に「パイロットでのスパイク所見」セクションを追加**

`docs/superpowers/specs/2026-05-03-test-style-rework-design.md` の末尾（最後の表の後ろ）に以下を追加：

```markdown
## パイロットでのスパイク所見（パターン G）

`tests/test_analyze.py:688-720` の `TestGetMethodScope` を試験翻訳した結果：

- **対象**: `test_メソッド内の行番号からスタートとエンドのタプルが返る`
- **判定**: ［a / b / c のいずれかを記入］
- **理由**: ［例：`_get_method_scope` は `track_constant` 内部で呼ばれており、E2E ゴールデンで Constants.java の 13 行目振る舞いを検証済み。よって b 案（削除）が妥当］
- **スイープ第一弾への影響**: ［例：TestGetMethodScope クラス全体を削除可能。`_search_in_lines`、`_batch_track_*` も同様の判定が想定されるが、各クラス開始時に再判定する］
```

実際の判定内容を埋める（プレースホルダのまま残さない）。

- [ ] **Step 6: コミット**

spec ファイルだけをコミット：

```bash
git add docs/superpowers/specs/2026-05-03-test-style-rework-design.md
git commit -m "$(cat <<'EOF'
docs(specs): add pattern G spike findings from pilot

test_analyze.py:688-720 の TestGetMethodScope を試験翻訳した所見を追記。
スイープ第一弾の判定根拠とする。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: パイロット完了確認

**Files:**
- Verify only: `tests/`

- [ ] **Step 1: tests/ 全体のグリーン確認**

```bash
python -m unittest discover -v 2>&1 | tail -20
```

Expected: 末尾に `OK` を含むサマリ。失敗があれば該当テストを特定し、原因を報告する。

- [ ] **Step 2: 直近のコミット履歴を確認**

```bash
git log --oneline -10
```

Expected: Task 2〜9 のコミットが順に並んでいる（Task 8 は採否次第で 0〜1 コミット）。

- [ ] **Step 3: パイロットのまとめをユーザーに報告**

報告文に含める：
- 適用したパターン (F / A / B / E / C / D / 必要なら G スパイク所見)
- 追加した穴埋めテストの数（Task 8）
- 残ったホワイトボックスクラス（`TestBatchScannerSelectorWhitebox`、`TestDetectEncodingStreamingWhitebox`、必要なら他）
- 全体テストグリーン状態
- スイープ第一弾（`test_analyze.py`）への準備が整った旨

これでパイロット完了。スイープに進むかは別判断。

---

## 自己レビュー結果

- Spec の 7 パターン (A〜G) はすべて Task に対応：F=Task 2, A=Task 3, B=Task 4, E=Task 5, C=Task 6, D=Task 7, G=Task 9
- ホワイトボックス点検（spec の Step 6）は Task 8 に対応
- 等価性検証の手動 mutation スポットチェックは Task 3・4 に Step 4・5 として組み込み
- パイロット完了の全体グリーン確認は Task 10 Step 1 に対応
- production コードへの変更は無し（mutation チェックは git diff で復元確認）
