# grep-helper 性能改善 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 60GB ソース・GB級 grep ファイル規模で OOM を回避し、実行時間を 5〜10倍級で短縮する。

**Architecture:**
- I/O 層をストリーミング化し、grep ファイル全体読み込みと encoding 検出時の全件読み込みを排除する。
- 共通インフラ `analyze_common.py` に rglob 結果・file 行・encoding・file 解決の共通 LRU キャッシュを集約し、言語横断で再利用する。
- バッチスキャンを「定数 + getter + setter」のワンパスに統合し、`_encoding_override` モジュールグローバルを引数化して並列化に備える。
- 仕上げに `multiprocessing` でファイル並列化し、キーワード数が多い場合に Aho-Corasick を使う。

**Tech Stack:** Python 3.7+, pytest, javalang, chardet (任意), multiprocessing, pyahocorasick (任意)

**Implementation Order:** Phase A → B → C → D → E → F → G。各フェーズは独立に出荷可能で、Phase A だけでも OOM は解消する。

---

## Phase A: ストリーミング化（OOM 即時回避）

### Task A1: `detect_encoding` を 4KB ストリーミング読み込みに修正

**Files:**
- Modify: `analyze_common.py:65-78`
- Test: `tests/test_common.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_common.py` のクラス `TestGrepFilterFiles` の前（ファイル末尾の手前）に追加:

```python
class TestDetectEncodingStreaming(unittest.TestCase):
    def test_does_not_call_read_bytes(self):
        """巨大ファイルでも先頭 4KB だけ読む（read_bytes は使わない）。"""
        from analyze_common import detect_encoding
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_bytes(b"hello world\n" * 100)
            def boom(self):
                raise AssertionError("read_bytes should not be called")
            with patch.object(Path, "read_bytes", boom):
                enc = detect_encoding(p)
                self.assertIsInstance(enc, str)

    def test_reads_at_most_4kb(self):
        """4096 バイト以下しか read しない。"""
        from analyze_common import detect_encoding
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
            import analyze_common
            with unittest.mock.patch.object(analyze_common, "open", tracking_open, create=True):
                detect_encoding(p)
            self.assertTrue(all(n <= 4096 for n in sizes), sizes)
```

ファイル冒頭の import に `import unittest.mock` を足す。

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
python -m pytest tests/test_common.py::TestDetectEncodingStreaming -v
```

期待: `test_does_not_call_read_bytes` が AssertionError で失敗する（現実装は `path.read_bytes()` を呼ぶ）。

- [ ] **Step 3: 最小実装**

`analyze_common.py:65-78` の `detect_encoding` を以下に置換:

```python
def detect_encoding(path: Path, override: str | None = None) -> str:
    """ファイルの文字コードを検出する。overrideがあればそのまま返す。

    巨大ファイル対策として先頭 4096 バイトのみを読む。
    """
    if override is not None:
        return override
    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
    except OSError:
        return "cp932"
    if not _CHARDET_AVAILABLE:
        return "cp932"
    result = _chardet.detect(raw)
    if result and result.get("confidence", 0) >= 0.6 and result.get("encoding"):
        return result["encoding"]
    return "cp932"
```

- [ ] **Step 4: テスト全件実行**

```bash
python -m pytest tests/test_common.py -v
```

期待: 全 PASS。

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "perf: detect_encoding を先頭 4KB ストリーミング読み込みに変更"
```

---

### Task A2: 共通の grep 行ストリーミングヘルパーを追加

**Files:**
- Modify: `analyze_common.py` (関数追加)
- Test: `tests/test_common.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_common.py` 末尾に追加:

```python
class TestIterGrepLines(unittest.TestCase):
    def test_yields_lines_without_loading_all(self):
        """iter_grep_lines はジェネレータで返る（list 化されない）。"""
        from analyze_common import iter_grep_lines
        import types
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_text("a:1:foo\nb:2:bar\n", encoding="utf-8")
            it = iter_grep_lines(p, "utf-8")
            self.assertIsInstance(it, types.GeneratorType)
            self.assertEqual(list(it), ["a:1:foo", "b:2:bar"])

    def test_handles_decode_errors(self):
        """不正バイトは errors=replace で継続。"""
        from analyze_common import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_bytes(b"good\n\xff\xfe\xfd\nmore\n")
            self.assertEqual(list(iter_grep_lines(p, "utf-8")), ["good", "���", "more"])
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
python -m pytest tests/test_common.py::TestIterGrepLines -v
```

期待: `ImportError: cannot import name 'iter_grep_lines'`。

- [ ] **Step 3: 最小実装**

`analyze_common.py` の `parse_grep_line` の直前に追加:

```python
def iter_grep_lines(path: Path, encoding: str):
    """grep 結果ファイルを 1 行ずつジェネレータで返す。

    巨大ファイル対策。改行は除去済み。
    """
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        for line in f:
            yield line.rstrip("\n").rstrip("\r")
```

- [ ] **Step 4: テスト実行で PASS 確認**

```bash
python -m pytest tests/test_common.py::TestIterGrepLines -v
```

期待: 2 PASS。

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat(common): iter_grep_lines ストリーミングヘルパーを追加"
```

---

### Task A3: `process_grep_lines_all` を Iterable 受けに変更

**Files:**
- Modify: `analyze_all.py:134-163`
- Test: `tests/test_all_analyzer.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_all_analyzer.py` 末尾に追加:

```python
class TestProcessGrepLinesAllIterable(unittest.TestCase):
    def test_accepts_generator(self):
        """list ではなくジェネレータも受け取れる。"""
        from analyze_all import process_grep_lines_all
        from analyze_common import ProcessStats
        def gen():
            yield "Foo.java:1:public class Foo {}"
        stats = ProcessStats()
        records = process_grep_lines_all(gen(), "kw", Path("/tmp"), stats, None)
        self.assertEqual(len(records), 1)
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
python -m pytest tests/test_all_analyzer.py::TestProcessGrepLinesAllIterable -v
```

期待: 既存の型注釈 `list[str]` のままでも runtime では通る場合があるので、その場合は次の Step 3 のリファクタを単に行ってもよい。FAIL すれば普通に進める。

- [ ] **Step 3: 型を Iterable に変更**

`analyze_all.py:1-15` のインポート部に `from collections.abc import Iterable` を追加（`from collections.abc import Callable` の隣）。

`analyze_all.py:134` のシグネチャを以下に変更:

```python
def process_grep_lines_all(
    lines: Iterable[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
```

関数本体（143 行目以降）はそのまま `for line in lines:` で動くので変更不要。

- [ ] **Step 4: テスト全件実行**

```bash
python -m pytest tests/test_all_analyzer.py -v
```

期待: 全 PASS。

- [ ] **Step 5: コミット**

```bash
git add analyze_all.py tests/test_all_analyzer.py
git commit -m "refactor(all): process_grep_lines_all を Iterable 受けに変更"
```

---

### Task A4: `analyze_all.py` の main() を grep ストリーミング読み込みに置換

**Files:**
- Modify: `analyze_all.py:780-790` (main 内)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_all_analyzer.py` 末尾に追加:

```python
class TestMainStreaming(unittest.TestCase):
    def test_main_does_not_load_full_grep_file(self):
        """main は grep_path.read_text(...).splitlines() を使わない。"""
        import analyze_all, inspect
        src = inspect.getsource(analyze_all.main)
        self.assertNotIn("read_text(encoding=enc, errors=\"replace\").splitlines()", src)
        self.assertIn("iter_grep_lines", src)
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
python -m pytest tests/test_all_analyzer.py::TestMainStreaming -v
```

期待: FAIL（現状 read_text を使っている）。

- [ ] **Step 3: 実装**

`analyze_all.py:10-14` のインポートに `iter_grep_lines` を追加:

```python
from analyze_common import (
    GrepRecord, ProcessStats, RefType,
    detect_encoding, parse_grep_line, write_tsv,
    grep_filter_files, iter_grep_lines,
)
```

`analyze_all.py:781-789` 付近の main ループを以下に置換:

```python
        for grep_path in grep_files:
            print(f"  処理中: {grep_path.name} ...", file=sys.stderr, flush=True)
            keyword = grep_path.stem
            enc = detect_encoding(grep_path, args.encoding)

            direct_records = process_grep_lines_all(
                iter_grep_lines(grep_path, enc),
                keyword, source_dir, stats, args.encoding,
            )
```

- [ ] **Step 4: テスト全件実行**

```bash
python -m pytest tests/ -q
```

期待: 全 PASS。

- [ ] **Step 5: コミット**

```bash
git add analyze_all.py tests/test_all_analyzer.py
git commit -m "perf(all): main を grep ファイルのストリーミング読み込みに変更"
```

---

### Task A5: 他 13 アナライザの main() も同様に置換

**Files:**
- Modify: `analyze.py`, `analyze_kotlin.py`, `analyze_c.py`, `analyze_proc.py`, `analyze_sql.py`, `analyze_sh.py`, `analyze_ts.py`, `analyze_python.py`, `analyze_perl.py`, `analyze_dotnet.py`, `analyze_groovy.py`, `analyze_plsql.py`

- [ ] **Step 1: 該当箇所を一括検索**

```bash
grep -nH "read_text(encoding=enc.*splitlines()" analyze*.py
```

各ファイルの main() で grep ファイルを丸読みしている箇所を確認する。

- [ ] **Step 2: 各ファイルを修正**

各ファイルで:
1. `from analyze_common import ...` 行に `iter_grep_lines` を追加。
2. `raw_lines = grep_path.read_text(encoding=enc, errors="replace").splitlines()` を削除。
3. 続く `process_grep_lines(raw_lines, ...)` の引数を `iter_grep_lines(grep_path, enc)` に変更。
4. 各 `process_grep_lines` の型注釈を `lines: Iterable[str]` に変更し `from collections.abc import Iterable` を追加。

- [ ] **Step 3: 全テスト実行**

```bash
python -m pytest tests/ -q
```

期待: 全 PASS（既存テストは list を渡していて Iterable は list を含むので壊れない）。

- [ ] **Step 4: コミット**

```bash
git add analyze*.py
git commit -m "perf: 全アナライザ main を grep ファイル ストリーミング読み込みに統一"
```

---

## Phase B: 共通キャッシュインフラ（rglob/resolve/lines を集約）

### Task B1: `iter_source_files` 共通 rglob キャッシュを追加

**Files:**
- Modify: `analyze_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_common.py` 末尾に追加:

```python
class TestIterSourceFiles(unittest.TestCase):
    def test_caches_per_extension_set(self):
        """同じ (src_dir, extensions) は二度目はディスクを読まない。"""
        from analyze_common import iter_source_files, _source_files_cache_clear
        _source_files_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.java").write_text("x")
            (p / "b.kt").write_text("x")
            r1 = iter_source_files(p, [".java"])
            (p / "c.java").write_text("x")  # 後から追加
            r2 = iter_source_files(p, [".java"])
            self.assertEqual(r1, r2)         # 2 回目もキャッシュから返る
            self.assertEqual(len(r1), 1)     # b.java は無いので 1 件
            self.assertNotIn(p / "c.java", r2)

    def test_different_extensions_separate_cache(self):
        from analyze_common import iter_source_files, _source_files_cache_clear
        _source_files_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.java").write_text("x")
            (p / "b.kt").write_text("x")
            self.assertEqual(len(iter_source_files(p, [".java"])), 1)
            self.assertEqual(len(iter_source_files(p, [".kt"])), 1)
            self.assertEqual(len(iter_source_files(p, [".java", ".kt"])), 2)
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
python -m pytest tests/test_common.py::TestIterSourceFiles -v
```

期待: ImportError。

- [ ] **Step 3: 実装**

`analyze_common.py` の末尾（`grep_filter_files` の前）に追加:

```python
_source_files_cache: dict[tuple[str, tuple[str, ...]], list[Path]] = {}


def _source_files_cache_clear() -> None:
    """テスト用: source_files キャッシュをクリア。"""
    _source_files_cache.clear()


def iter_source_files(src_dir: Path, extensions: list[str]) -> list[Path]:
    """src_dir 配下で extensions のいずれかにマッチするファイル一覧を返す。

    rglob は呼び出し毎にディスクを再走査するため、(src_dir, extensions) 単位で
    キャッシュする。同一プロセス内で複数言語を横断して再利用される。
    """
    key = (str(src_dir), tuple(sorted(e.lower() for e in extensions)))
    cached = _source_files_cache.get(key)
    if cached is not None:
        return cached
    ext_set = set(key[1])
    result = sorted(f for f in src_dir.rglob("*") if f.suffix.lower() in ext_set)
    _source_files_cache[key] = result
    return result
```

- [ ] **Step 4: テスト PASS 確認**

```bash
python -m pytest tests/test_common.py::TestIterSourceFiles -v
```

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat(common): iter_source_files 共通 rglob キャッシュを追加"
```

---

### Task B2: `grep_filter_files` を `iter_source_files` ベースに置換

**Files:**
- Modify: `analyze_common.py:158-204`
- Test: 既存の `TestGrepFilterFiles`

- [ ] **Step 1: 既存テストの確認**

```bash
python -m pytest tests/test_common.py::TestGrepFilterFiles -v
```

期待: 全 PASS（リファクタ前ベースライン）。

- [ ] **Step 2: 実装**

`analyze_common.py:158-204` の `grep_filter_files` を以下に置換:

```python
def grep_filter_files(
    names: list[str],
    src_dir: Path,
    extensions: list[str],
    label: str = "",
) -> list[Path]:
    """mmap によるバイト列検索でスキャン対象ファイルを絞り込む。

    iter_source_files で取得した (キャッシュ済み) ファイルリストに対し
    mmap.find で names の含有を判定する。
    エラー時は安全側（スキャン対象に含める）でフォールバック。
    """
    candidates = iter_source_files(src_dir, extensions)
    patterns = [n.encode("ascii") for n in names if n.isascii()]
    if not patterns:
        return candidates

    result: list[Path] = []
    for f in candidates:
        try:
            if f.stat().st_size == 0:
                continue
            with open(f, "rb") as fh, \
                 mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                if any(mm.find(p) != -1 for p in patterns):
                    result.append(f)
        except (OSError, ValueError, mmap.error):
            result.append(f)

    if label:
        print(
            f"  [{label}] 事前フィルタ完了: {len(candidates)} → {len(result)} ファイルに絞り込み",
            file=sys.stderr, flush=True,
        )

    return result
```

- [ ] **Step 3: テスト実行**

```bash
python -m pytest tests/test_common.py -v
```

期待: 全 PASS（既存テストは順序依存があれば落ちる可能性あり、その場合は順序保持を確認）。

- [ ] **Step 4: コミット**

```bash
git add analyze_common.py
git commit -m "refactor(common): grep_filter_files を iter_source_files ベースに統合"
```

---

### Task B3: `resolve_file_cached` 共通ヘルパーを追加

**Files:**
- Modify: `analyze_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_common.py` 末尾に追加:

```python
class TestResolveFileCached(unittest.TestCase):
    def test_resolves_relative_to_src_dir(self):
        from analyze_common import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "sub").mkdir()
            f = p / "sub" / "x.txt"
            f.write_text("x")
            self.assertEqual(resolve_file_cached("sub/x.txt", p), f)

    def test_returns_none_for_missing(self):
        from analyze_common import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(resolve_file_cached("missing.txt", Path(d)))

    def test_caches_result(self):
        from analyze_common import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "x.txt"
            f.write_text("x")
            r1 = resolve_file_cached("x.txt", p)
            f.unlink()  # ファイル削除
            r2 = resolve_file_cached("x.txt", p)
            self.assertEqual(r1, r2)  # キャッシュから同じ結果が返る
```

- [ ] **Step 2: テスト実行で失敗を確認**

- [ ] **Step 3: 実装**

`analyze_common.py` の末尾に追加:

```python
_resolve_file_cache: dict[tuple[str, str], Path | None] = {}


def _resolve_file_cache_clear() -> None:
    """テスト用: resolve_file キャッシュをクリア。"""
    _resolve_file_cache.clear()


def resolve_file_cached(filepath: str, src_dir: Path) -> Path | None:
    """ファイルパスを解決する（CWD 相対 → src_dir 相対の順）。結果はキャッシュ。"""
    key = (filepath, str(src_dir))
    if key in _resolve_file_cache:
        return _resolve_file_cache[key]
    candidate = Path(filepath)
    result: Path | None
    if candidate.is_absolute():
        result = candidate if candidate.exists() else None
    elif candidate.exists():
        result = candidate
    else:
        resolved = src_dir / filepath
        result = resolved if resolved.exists() else None
    _resolve_file_cache[key] = result
    return result
```

- [ ] **Step 4: テスト PASS 確認**

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat(common): resolve_file_cached 共通キャッシュヘルパーを追加"
```

---

### Task B4: 各アナライザの `_resolve_file` / `_resolve_source_file` を `resolve_file_cached` に統一

**Files:**
- Modify: `analyze_all.py:220-228`, `analyze_c.py:45-53`, `analyze_proc.py` (同名関数), 他のアナライザ

- [ ] **Step 1: 該当箇所を確認**

```bash
grep -n "def _resolve_file\|def _resolve_source_file" analyze*.py
```

- [ ] **Step 2: 各ファイルで置換**

各ファイル内の `_resolve_file` / `_resolve_source_file` を削除し、呼び出し側を `resolve_file_cached` に変更する。
`analyze_common` の import に `resolve_file_cached` を追加する。

- [ ] **Step 3: 全テスト実行**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 4: コミット**

```bash
git add analyze*.py
git commit -m "refactor: 各アナライザの _resolve_file を共通 resolve_file_cached に統合"
```

---

### Task B5: バイトサイズベースの行キャッシュを共通化

**Files:**
- Modify: `analyze_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_common.py` 末尾に追加:

```python
class TestCachedFileLines(unittest.TestCase):
    def test_returns_lines(self):
        from analyze_common import cached_file_lines, _file_lines_cache_clear
        _file_lines_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_text("a\nb\nc\n", encoding="utf-8")
            self.assertEqual(cached_file_lines(p, "utf-8"), ["a", "b", "c"])

    def test_caches_within_size_limit(self):
        from analyze_common import cached_file_lines, _file_lines_cache_clear, _file_lines_cache
        _file_lines_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_text("a\n", encoding="utf-8")
            cached_file_lines(p, "utf-8")
            self.assertIn(str(p), _file_lines_cache)

    def test_evicts_when_total_size_exceeds_limit(self):
        """合計バイト数が上限を超えたら最古のエントリを破棄。"""
        from analyze_common import cached_file_lines, _file_lines_cache_clear, _file_lines_cache, set_file_lines_cache_limit
        _file_lines_cache_clear()
        set_file_lines_cache_limit(100)  # 100 byte 上限
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for i in range(5):
                f = p / f"f{i}.txt"
                f.write_text("X" * 50, encoding="utf-8")
                cached_file_lines(f, "utf-8")
            # 合計 250 byte 入れたら最初の 3 ファイル分は追い出されているはず
            self.assertLessEqual(len(_file_lines_cache), 3)
        set_file_lines_cache_limit(256 * 1024 * 1024)  # 復元
```

- [ ] **Step 2: テスト実行で失敗を確認**

- [ ] **Step 3: 実装**

`analyze_common.py` の末尾に追加:

```python
from collections import OrderedDict as _OrderedDict

_file_lines_cache: _OrderedDict[str, list[str]] = _OrderedDict()
_file_lines_cache_bytes: int = 0
_file_lines_cache_limit: int = 256 * 1024 * 1024  # 256MB


def _file_lines_cache_clear() -> None:
    global _file_lines_cache_bytes
    _file_lines_cache.clear()
    _file_lines_cache_bytes = 0


def set_file_lines_cache_limit(n_bytes: int) -> None:
    """テスト/チューニング用: キャッシュの合計バイト上限を変更する。"""
    global _file_lines_cache_limit
    _file_lines_cache_limit = n_bytes


def _estimate_lines_bytes(lines: list[str]) -> int:
    return sum(len(s) for s in lines) + 64 * len(lines)  # おおよその overhead


def cached_file_lines(
    path: Path,
    encoding: str,
    stats: ProcessStats | None = None,
) -> list[str]:
    """ファイルの行リストをサイズベース LRU キャッシュ経由で返す。"""
    global _file_lines_cache_bytes
    key = str(path)
    if key in _file_lines_cache:
        _file_lines_cache.move_to_end(key)
        return _file_lines_cache[key]
    try:
        lines = path.read_text(encoding=encoding, errors="replace").splitlines()
    except Exception:
        if stats is not None:
            stats.encoding_errors.add(key)
        lines = []
    size = _estimate_lines_bytes(lines)
    _file_lines_cache[key] = lines
    _file_lines_cache_bytes += size
    while _file_lines_cache_bytes > _file_lines_cache_limit and len(_file_lines_cache) > 1:
        old_key, old_lines = _file_lines_cache.popitem(last=False)
        _file_lines_cache_bytes -= _estimate_lines_bytes(old_lines)
    return lines
```

- [ ] **Step 4: テスト PASS 確認**

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat(common): cached_file_lines サイズベース LRU を追加"
```

---

### Task B6: 各アナライザの `_file_cache` / `_cached_read_lines` を `cached_file_lines` に統一

**Files:**
- Modify: `analyze.py:65-78,199-215`, `analyze_c.py:20-42`, `analyze_proc.py:30-52`, `analyze_all.py:231-246`

- [ ] **Step 1: 該当箇所をリスト化**

```bash
grep -nH "_file_cache\b\|_cached_read_lines\|_file_lines_cache\|_get_cached_lines\|_read_lines\b" analyze*.py
```

- [ ] **Step 2: 各ファイルでローカルキャッシュを削除し、共通 API に切り替え**

- `analyze.py:75-78,199-215` を削除し、`_cached_read_lines(filepath, stats)` の呼び出しを `cached_file_lines(Path(filepath), detect_encoding(Path(filepath), _encoding_override), stats)` に置き換える（次フェーズで encoding を引数化するので一旦これで OK）。
- `analyze_c.py:20-42` の `_file_cache` 関連を削除し、`_get_cached_lines(...)` を `cached_file_lines(Path(filepath), detect_encoding(Path(filepath), encoding_override), stats)` に置き換える。
- `analyze_proc.py:30-52` 同様。
- `analyze_all.py:231-246` の `_file_cache_all` / `_read_lines` を削除し、`_read_lines(src_file, encoding)` の呼び出しを `cached_file_lines(src_file, detect_encoding(src_file, encoding))` に置き換える。

- [ ] **Step 3: テスト実行**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 4: コミット**

```bash
git add analyze*.py
git commit -m "refactor: 各アナライザの行キャッシュを共通 cached_file_lines に統合"
```

---

## Phase C: トラッカー個別最適化

### Task C1: `_collect_define_aliases` の reverse map をキャッシュ

**Files:**
- Modify: `analyze_c.py:87-132`
- Test: `tests/test_c_analyzer.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_c_analyzer.py` 末尾に追加:

```python
class TestDefineMapWithReverse(unittest.TestCase):
    def test_build_define_map_returns_with_reverse(self):
        """_build_define_map は (forward, reverse) のタプルをキャッシュ。"""
        from analyze_c import _build_define_map, _define_map_cache
        _define_map_cache.clear()
        from analyze_common import ProcessStats
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.h").write_text("#define FOO BAR\n#define BAR BAZ\n", encoding="utf-8")
            stats = ProcessStats()
            forward = _build_define_map(p, stats)
            self.assertEqual(forward, {"FOO": "BAR", "BAR": "BAZ"})
            # reverse map がキャッシュ内部に格納されていること
            cached = next(iter(_define_map_cache.values()))
            self.assertIn("reverse", dir(cached) + list(cached.keys()) if isinstance(cached, dict) else dir(cached))
```

ただし内部実装に踏み込みすぎないよう、よりよい代替テストとしてパフォーマンス側を計測:

```python
    def test_collect_aliases_reuses_reverse_map(self):
        """_collect_define_aliases を多数回呼んでも reverse 構築は 1 回。"""
        import analyze_c
        from analyze_c import _collect_define_aliases, _build_define_map, _define_map_cache
        _define_map_cache.clear()
        from analyze_common import ProcessStats
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.h").write_text("#define A1 X\n#define A2 X\n", encoding="utf-8")
            stats = ProcessStats()
            _build_define_map(p, stats)
            calls = {"n": 0}
            orig = analyze_c._build_reverse_define_map  # 新規 API
            def counter(m):
                calls["n"] += 1
                return orig(m)
            analyze_c._build_reverse_define_map = counter
            try:
                for _ in range(50):
                    _collect_define_aliases("X", _build_define_map(p, stats))
                self.assertEqual(calls["n"], 0,
                    "reverse map はキャッシュから取得されるはずで、再構築されない")
            finally:
                analyze_c._build_reverse_define_map = orig
```

- [ ] **Step 2: テスト実行で失敗を確認**

期待: `_build_reverse_define_map` が無いので AttributeError。

- [ ] **Step 3: 実装**

`analyze_c.py:22` の型を変更:

```python
_define_map_cache: dict[tuple[str, str], tuple[dict[str, str], dict[str, list[str]]]] = {}
```

`analyze_c.py:87-106` を以下に置換:

```python
def _build_reverse_define_map(define_map: dict[str, str]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for k, v in define_map.items():
        reverse.setdefault(v, []).append(k)
    return reverse


def _build_define_map(
    src_dir: Path,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> dict[str, str]:
    """src_dir 配下の全ソースから #define NAME IDENTIFIER 形式のマップを構築する。
    内部キャッシュには forward と reverse map のタプルを保持する。
    """
    cache_key = (str(src_dir), encoding_override or "")
    cached = _define_map_cache.get(cache_key)
    if cached is not None:
        return cached[0]
    define_map: dict[str, str] = {}
    src_files = iter_source_files(src_dir, [".c", ".h", ".pc"])
    for src_file in src_files:
        enc = detect_encoding(src_file, encoding_override)
        for line in cached_file_lines(src_file, enc, stats):
            m = _DEFINE_ALIAS_PAT.match(line.strip())
            if m:
                define_map[m.group(1)] = m.group(2)
    _define_map_cache[cache_key] = (define_map, _build_reverse_define_map(define_map))
    return define_map


def _get_reverse_define_map(src_dir: Path, encoding_override: str | None) -> dict[str, list[str]]:
    cache_key = (str(src_dir), encoding_override or "")
    cached = _define_map_cache.get(cache_key)
    return cached[1] if cached is not None else {}
```

`_collect_define_aliases` を変更し、reverse を引数で受け取れるようにする:

```python
def _collect_define_aliases(
    var_name: str,
    define_map: dict[str, str],
    max_depth: int = 10,
    reverse: dict[str, list[str]] | None = None,
) -> list[str]:
    if reverse is None:
        reverse = _build_reverse_define_map(define_map)
    aliases: list[str] = []
    to_visit = [var_name]
    seen: set[str] = {var_name}
    for _ in range(max_depth):
        next_level: list[str] = []
        for name in to_visit:
            for k in reverse.get(name, []):
                if k not in seen:
                    aliases.append(k)
                    next_level.append(k)
                    seen.add(k)
        if not next_level:
            break
        to_visit = next_level
    return aliases
```

呼び出し側 (`analyze_c.py:152`, `analyze_proc.py:174`, `analyze_all.py:434/504`) で `reverse=_get_reverse_define_map(src_dir, encoding)` を渡す。

- [ ] **Step 4: 全テスト実行**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 5: コミット**

```bash
git add analyze_c.py analyze_proc.py analyze_all.py tests/test_c_analyzer.py
git commit -m "perf(c/proc): define reverse map をキャッシュし alias 解決を高速化"
```

---

### Task C2: Java 定数 / getter / setter のワンパス統合

**Files:**
- Modify: `analyze.py:932-1150`
- Test: `tests/test_analyze.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_analyze.py` 末尾に追加:

```python
class TestBatchTrackOnePass(unittest.TestCase):
    def test_one_pass_reads_each_file_once(self):
        """定数+getter+setter を 1 パスで処理する _batch_track_combined を提供。"""
        import analyze
        self.assertTrue(hasattr(analyze, "_batch_track_combined"))

    def test_combined_yields_all_kinds(self):
        """combined は constant / getter / setter のレコードを混合で返す。"""
        from analyze import _batch_track_combined
        from analyze_common import ProcessStats, GrepRecord
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "Foo.java").write_text(
                "public class Foo {\n"
                "  static final String CODE = \"x\";\n"
                "  String getCode() { return null; }\n"
                "  void setCode(String s) {}\n"
                "  void use() { String c = CODE; getCode(); setCode(\"y\"); }\n"
                "}\n",
                encoding="utf-8",
            )
            origin = GrepRecord("kw", "直接", "定数定義", "Foo.java", "2",
                                "static final String CODE = \"x\";")
            stats = ProcessStats()
            records = _batch_track_combined(
                const_tasks={"CODE": [origin]},
                getter_tasks={"getCode": [origin]},
                setter_tasks={"setCode": [origin]},
                source_dir=p, stats=stats, file_list=None,
            )
            ref_types = {(r.ref_type, r.src_var) for r in records}
            self.assertIn(("間接", "CODE"), ref_types)
            self.assertIn(("間接（getter経由）", "getCode"), ref_types)
            self.assertIn(("間接（setter経由）", "setCode"), ref_types)
```

- [ ] **Step 2: テスト実行で失敗を確認**

- [ ] **Step 3: 実装**

`analyze.py:932` 直前に新 API を追加:

```python
def _batch_track_combined(
    const_tasks: dict[str, list[GrepRecord]],
    getter_tasks: dict[str, list[GrepRecord]],
    setter_tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
) -> list[GrepRecord]:
    """定数 / getter / setter を 1 パスで一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする。
    """
    if not const_tasks and not getter_tasks and not setter_tasks:
        return []

    all_names = list(dict.fromkeys(
        list(const_tasks.keys()) + list(getter_tasks.keys()) + list(setter_tasks.keys())
    ))
    java_files = file_list if file_list is not None else grep_filter_files(
        all_names, source_dir, [".java"], label="Java追跡(統合)",
    )
    if not java_files:
        return []

    # 名前 → どのトラッカーで処理するか
    parts: list[str] = []
    if const_tasks:
        parts.append(r"\b(?P<const>" + "|".join(re.escape(k) for k in const_tasks) + r")\b(?!\s*\()")
    if getter_tasks:
        parts.append(r"\b(?P<getter>" + "|".join(re.escape(k) for k in getter_tasks) + r")\s*\(")
    if setter_tasks:
        parts.append(r"\b(?P<setter>" + "|".join(re.escape(k) for k in setter_tasks) + r")\s*\(")
    combined = re.compile("|".join(parts))

    records: list[GrepRecord] = []
    total = len(java_files)
    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            print(f"  [Java追跡] {idx}/{total} ファイル処理済み", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = _cached_read_lines(filepath_abs, stats)
        if not lines:
            continue
        for i, line in enumerate(lines, start=1):
            for m in combined.finditer(line):
                code = line.strip()
                usage_type = classify_usage(
                    code=code, filepath=filepath_str, lineno=i,
                    source_dir=source_dir, stats=stats,
                )
                gd = m.groupdict()
                const_name = gd.get("const")
                getter_name = gd.get("getter")
                setter_name = gd.get("setter")
                if const_name:
                    for origin in const_tasks[const_name]:
                        if filepath_str == origin.filepath and str(i) == origin.lineno:
                            continue
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.INDIRECT.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=const_name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                elif getter_name:
                    for origin in getter_tasks[getter_name]:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.GETTER.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=getter_name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
                elif setter_name:
                    for origin in setter_tasks[setter_name]:
                        records.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.SETTER.value,
                            usage_type=usage_type,
                            filepath=filepath_str, lineno=str(i), code=code,
                            src_var=setter_name, src_file=origin.filepath, src_lineno=origin.lineno,
                        ))
    return records
```

呼び出し側 (`analyze.py:1300-1322`, `analyze_all.py:711-726`) を `_batch_track_combined` の 1 回呼び出しに置換する（既存の 3 関数は当面 deprecated として残し、1 リリース後削除）。

- [ ] **Step 4: 全テスト実行**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 5: コミット**

```bash
git add analyze.py analyze_all.py tests/test_analyze.py
git commit -m "perf(java): 定数/getter/setter 追跡を 1 パスに統合し I/O を 1/3 に"
```

---

## Phase D: `_encoding_override` 引数化（並列化の前提）

### Task D1: `analyze.py` の `_encoding_override` モジュールグローバルを引数に置き換える

**Files:**
- Modify: `analyze.py` 全般 (約 30 箇所)
- Test: `tests/test_analyze.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_analyze.py` に追加:

```python
class TestNoModuleGlobalEncoding(unittest.TestCase):
    def test_no_encoding_override_module_global(self):
        """_encoding_override モジュールグローバルは廃止されている。"""
        import analyze
        self.assertFalse(hasattr(analyze, "_encoding_override"),
            "_encoding_override は引数化されたため削除されているべき")
```

- [ ] **Step 2: テスト実行で失敗を確認**

期待: FAIL（現在 `_encoding_override` は存在する）。

- [ ] **Step 3: 段階的に引数化**

a. `analyze.py` の `_encoding_override` 利用箇所を全列挙: `grep -n "_encoding_override" analyze.py`
b. `get_ast`, `_cached_read_lines`, `classify_usage`, `determine_scope`, `track_constant`, `track_field`, `track_local`, `track_getter_calls`, `track_setter_calls` 等のシグネチャに `encoding_override: str | None = None` を追加。
c. 関数内の `_encoding_override` 参照を引数に置換。
d. `analyze.py` 内の main や呼び出し側で `args.encoding` を渡す。
e. `analyze_all.py:118, 597` の `_java_mod._encoding_override = encoding` を削除し、引数として `classify_usage(..., encoding_override=encoding)` で渡す。
f. 最後にモジュール冒頭の `_encoding_override: str | None = None` を削除。

- [ ] **Step 4: 全テスト実行**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 5: コミット**

```bash
git add analyze.py analyze_all.py tests/test_analyze.py
git commit -m "refactor(analyze): _encoding_override を引数化（並列化の前提整備）"
```

---

## Phase E: ProcessPool による並列化

### Task E1: バッチトラッカーをファイル並列化

**Files:**
- Modify: `analyze.py:_batch_track_combined`, `analyze_all.py:_batch_track_*`
- Test: `tests/test_analyze.py`

- [ ] **Step 1: ベンチマーク（任意）**

実プロジェクトの grep 結果を 1 本投入し、実行時間を `time` で計測してベースラインを取る:

```bash
time python analyze_all.py --source-dir /path/to/big --input-dir input --output-dir output
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_analyze.py` に追加:

```python
class TestParallelBatchTrack(unittest.TestCase):
    def test_batch_track_combined_accepts_workers_arg(self):
        """並列ワーカー数を指定できる。"""
        import inspect, analyze
        sig = inspect.signature(analyze._batch_track_combined)
        self.assertIn("workers", sig.parameters)
```

- [ ] **Step 3: 実装**

`_batch_track_combined` に `workers: int = 1` 引数を追加。`workers > 1` のとき `concurrent.futures.ProcessPoolExecutor` でファイルを n 分割して各ワーカーに渡し、ワーカー側でローカル `cached_file_lines` を使って records を返し、メイン側で結合する。

ワーカー関数を定義:

```python
def _scan_files_for_combined(
    files: list[Path], combined_pattern: str, source_dir_str: str,
    encoding_override: str | None,
    const_keys: list[str], getter_keys: list[str], setter_keys: list[str],
    tasks_serialized: dict[str, list[tuple]],  # ピクル可能な形に
) -> list[tuple]:
    ...
```

ピクル化対応: GrepRecord は NamedTuple なのでピクル可能。

ファイル分割は `chunks = [files[i::workers] for i in range(workers)]`。

- [ ] **Step 4: 全テスト実行**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 5: 動作確認**

実プロジェクトで `--workers 4` を指定して動作とスピードを確認。

- [ ] **Step 6: コミット**

```bash
git add analyze.py analyze_all.py tests/test_analyze.py
git commit -m "perf: バッチトラッカーを ProcessPoolExecutor で並列化"
```

---

### Task E2: CLI に `--workers` を追加

**Files:**
- Modify: 全アナライザの `build_parser`

- [ ] **Step 1: 各 build_parser に追加**

`analyze_all.py:747-755` および他のアナライザの `build_parser` に:

```python
import os
parser.add_argument(
    "--workers", type=int, default=1,
    help=f"並列ワーカー数（デフォルト: 1, 推奨: {os.cpu_count() or 4}）",
)
```

main 関数内で `args.workers` を `_batch_track_combined(..., workers=args.workers)` 等に渡す。

- [ ] **Step 2: テスト実行**

```bash
python -m pytest tests/ -q
python analyze_all.py --help | grep workers
```

- [ ] **Step 3: README 更新**

`README.md` の引数表に `--workers` を追加。

- [ ] **Step 4: コミット**

```bash
git add analyze*.py README.md
git commit -m "feat(cli): --workers 並列ワーカー数オプションを追加"
```

---

## Phase F: Aho-Corasick 導入（オプション）

### Task F1: Pure Python Aho-Corasick 実装をフォールバックとして追加

**Files:**
- Create: `aho_corasick.py`
- Test: `tests/test_aho_corasick.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_aho_corasick.py` を新規作成:

```python
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
        # ヘルパーで境界マッチを 1 回だけ検出
        result = list(ac.findall_word_boundary("FOO_BAR FOO BAZ", word_chars="abcdefghijklmnopqrstuvwxyz_"))
        # FOO_BAR は _ で続くので除外、" FOO " はマッチ
        self.assertEqual(result, [(8, "FOO")])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テスト実行で失敗を確認**

期待: ImportError（`aho_corasick.py` 未作成）。

- [ ] **Step 3: 実装**

`aho_corasick.py` を新規作成:

```python
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
                self._fail[u] = self._goto[state].get(ch, 0) if self._goto[state].get(ch, 0) != u else 0
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
```

- [ ] **Step 4: テスト PASS 確認**

```bash
python -m pytest tests/test_aho_corasick.py -v
```

- [ ] **Step 5: コミット**

```bash
git add aho_corasick.py tests/test_aho_corasick.py
git commit -m "feat: Pure Python Aho-Corasick (オフライン環境フォールバック) を追加"
```

---

### Task F2: バッチトラッカーで Aho-Corasick を使うラッパー関数を追加

**Files:**
- Modify: `analyze_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_common.py` 末尾に追加:

```python
class TestBatchScannerSelector(unittest.TestCase):
    def test_uses_aho_corasick_for_many_patterns(self):
        """パターン数が閾値超えで Aho-Corasick が選択される。"""
        from analyze_common import build_batch_scanner
        scanner = build_batch_scanner([f"NAME{i:04d}" for i in range(200)])
        self.assertEqual(scanner.backend, "ahocorasick")

    def test_uses_regex_for_few_patterns(self):
        from analyze_common import build_batch_scanner
        scanner = build_batch_scanner(["A", "B", "C"])
        self.assertEqual(scanner.backend, "regex")

    def test_findall_word_boundary(self):
        from analyze_common import build_batch_scanner
        scanner = build_batch_scanner(["FOO"])
        line = "x = FOO + FOOBAR;"
        results = [name for _, name in scanner.findall(line)]
        self.assertEqual(results, ["FOO"])
```

- [ ] **Step 2: テスト実行で失敗を確認**

- [ ] **Step 3: 実装**

`analyze_common.py` 末尾に追加:

```python
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
            import ahocorasick as _pyaho
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
            from aho_corasick import AhoCorasick
            return _BatchScanner(patterns, "ahocorasick", AhoCorasick(patterns))
    combined = re.compile(r"\b(" + "|".join(re.escape(p) for p in patterns) + r")\b")
    return _BatchScanner(patterns, "regex", combined)
```

- [ ] **Step 4: テスト PASS 確認**

- [ ] **Step 5: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat(common): build_batch_scanner で Aho-Corasick / regex を自動選択"
```

---

### Task F3: 各バッチトラッカーで `build_batch_scanner` を使う

**Files:**
- Modify: `analyze.py:_batch_track_combined`, `analyze_all.py:_batch_track_*`

- [ ] **Step 1: 各バッチ関数の `combined = re.compile(...)` を `scanner = build_batch_scanner([...])` に置換**

`finditer(line)` の代わりに `scanner.findall(line)` を使う。各 (pos, name) について従来 `m.group(1)` の代わりに `name` を使う。

- [ ] **Step 2: 全テスト実行**

```bash
python -m pytest tests/ -q
```

- [ ] **Step 3: コミット**

```bash
git add analyze.py analyze_all.py
git commit -m "perf: バッチトラッカーで build_batch_scanner（AC自動選択）を採用"
```

---

## Phase G: ドキュメント整備

### Task G1: README と docs を更新

**Files:**
- Modify: `README.md`, `docs/architecture.md`, `docs/development-guidelines.md`

- [ ] **Step 1: README**

`README.md:104-112` の「大規模ソースディレクトリの場合」節を更新:

- `--workers` の使い方を追加。
- 「メモリ使用量はファイル行キャッシュ（既定 256MB）と AST キャッシュで制限される」と明記。

- [ ] **Step 2: docs/architecture.md / development-guidelines.md**

共通インフラに集約された次の API を記載:

- `iter_grep_lines(path, encoding)`
- `iter_source_files(src_dir, extensions)`
- `cached_file_lines(path, encoding, stats)`
- `resolve_file_cached(filepath, src_dir)`
- `build_batch_scanner(patterns)`

各言語アナライザは独自キャッシュを持たないことを述べる。

- [ ] **Step 3: コミット**

```bash
git add README.md docs/
git commit -m "docs: 性能改善に伴うキャッシュインフラと --workers の説明を追記"
```

---

## 完了チェック

- [ ] `python -m pytest tests/ -q` が全 PASS
- [ ] 実プロジェクト（60GB / GB級 grep）での動作確認
- [ ] メモリ使用量が想定上限（既定 256MB + AST + ワーカー × チャンク）に収まる
- [ ] `python analyze_all.py --help` に `--workers` が表示される
- [ ] `git log --oneline` で各タスクごとに 1 コミット

## ロールバック方針

各 Phase は独立してロールバック可能。途中で問題が発生したら直近フェーズの先頭コミットに `git revert` する。Phase A だけでも OOM 解消の効果があるため、最低でも Phase A まではマージする価値がある。
