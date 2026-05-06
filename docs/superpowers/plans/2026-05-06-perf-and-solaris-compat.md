# Perf 改善 + Solaris 10 / Python 3.7 互換 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `grep_helper/` の重複作業を削る軽量な性能改善（encoding キャッシュ、間接追跡の集約化、mmap フォールバック）と、出荷先 Solaris 10 + Python 3.7 ランタイムでの実行を可能にする互換ガードを 1 本にまとめて実装する。KPI ゴールデンセットで before/after の網羅率と速度を比較する。

**Architecture:** 3 フェーズ パイプライン構造（grep ごとの直接分類 → 全量集約 → ハンドラごとの間接追跡 1 回 → keyword 振り分け & TSV 書き出し）。`detect_encoding` のプロセス内 dict キャッシュ。`mmap` 失敗時は prepend 方式の `_read_based_find` にファイル単位でフォールバック。Python 3.7 互換は ruff `target-version = "py37"` + `flake8-future-annotations` で構文ガード。

**Tech Stack:** Python 3.7+ ランタイム（Solaris 10）、Python 3.12 dev container、ruff、pytest 9、`pyahocorasick`（pure Python フォールバックあり）、`chardet`、`javalang`、既存の KPI ゴールデンセット（`tests/golden/`）と `scripts/measure_kpi.py`。

**Reference spec:** `docs/superpowers/specs/2026-05-06-perf-and-solaris-compat-design.md`

---

## File Structure

実装で触るファイル:

| ファイル | 責務 | Task |
|---|---|---|
| `pyproject.toml` | ruff 設定（py37 + FA） | 1 |
| `requirements.txt` | Python バージョン要件コメント | 1 |
| `requirements-dev.txt` | dev 依存の Python 要件コメント | 1 |
| `grep_helper/encoding.py` | `detect_encoding` + `_encoding_cache` | 2 |
| `grep_helper/source_files.py` | `_read_based_find` 追加、`grep_filter_files(use_mmap=...)` | 3, 4 |
| `grep_helper/languages/*.py` (12 ハンドラ) | `batch_track_indirect` の `use_mmap` kwarg 追加 | 5 |
| `grep_helper/pipeline.py` | `run_full_pipeline` の 3 フェーズ化 | 6 |
| `grep_helper/dispatcher.py` | `apply_indirect_tracking` シグネチャ + `main` 3 フェーズ化 + CLI 引数 | 7, 8 |
| `scripts/smoke_solaris.md` | Solaris 10 ビルド/実行手順 | 9 |
| `tests/test_encoding.py` | encoding キャッシュ unit | 2 |
| `tests/test_source_files.py` | `_read_based_find` + `grep_filter_files` unit | 3, 4 |
| `tests/test_pipeline_run.py` | 集約処理 / エラー分離 | 6 |
| `tests/test_all_analyzer.py` | dispatcher 集約処理 / CLI フラグ | 7, 8 |

`grep_helper/file_cache.py` の `_file_lines_cache` パターンに倣う。`grep_helper/source_files.py` の `_resolve_file_cache` パターンに倣う。

---

## Task 1: ruff py37 ガード設置

**Files:**
- Create: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`

- [ ] **Step 1: `pyproject.toml` を新規作成**

`/workspaces/grep_helper_superpowers/pyproject.toml`:

```toml
[tool.ruff]
target-version = "py37"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "UP", "FA"]
# UP: pyupgrade — py37 ターゲットで walrus / pos-only / match/case 等を検出
# FA: flake8-future-annotations — `from __future__ import annotations` を強制
```

- [ ] **Step 2: `requirements.txt` の先頭にコメントを追加**

`/workspaces/grep_helper_superpowers/requirements.txt`:

```
# Python >=3.7 で動作する版の組み合わせ:
javalang>=0.13.0,<1.0.0
chardet>=5.0.0,<6.0.0
pyahocorasick>=2.0.0,<3.0.0   # Solaris では _aho_corasick.py の pure Python フォールバックに任せる
```

- [ ] **Step 3: `requirements-dev.txt` の先頭にコメントを追加**

`/workspaces/grep_helper_superpowers/requirements-dev.txt`:

ファイル先頭に以下 1 行を追加:

```
# Python >= 3.9（pytest 9.x） — Solaris 10 ランタイム互換の対象外。dev container でのみ使用。
```

既存の依存行はそのまま残す。

- [ ] **Step 4: ruff ベースラインが通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m ruff check grep_helper/ analyze_*.py
```

Expected: `All checks passed!` または相当のメッセージ（エラーゼロ）。

ruff が未インストールならインストール:
```bash
python -m pip install ruff
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt requirements-dev.txt
git commit -m "$(cat <<'EOF'
chore(C-1): add ruff py37 + FA guard via pyproject.toml

target-version = "py37" with UP/FA rules to lock current 3.7-compatible
syntax in grep_helper/ and analyze_*.py. Annotate requirements.txt and
requirements-dev.txt with Python version applicability.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: encoding キャッシュ (E-1)

**Files:**
- Modify: `grep_helper/encoding.py`
- Create: `tests/test_encoding.py`

- [ ] **Step 1: 失敗するテストを書く**

`/workspaces/grep_helper_superpowers/tests/test_encoding.py`（新規）:

```python
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
            # cp932 で書ける典型的な文字列
            p.write_bytes("こんにちは世界".encode("cp932"))
            first = detect_encoding(p)

            # ファイル中身を utf-8 由来バイト列に上書き
            p.write_bytes("Hello world Hello world".encode("utf-8"))
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

            # 中身を utf-8 由来のバイト列に上書き → キャッシュ存在中は first を返す
            p.write_bytes(("Hello world " * 50).encode("utf-8"))
            cached = detect_encoding(p)
            self.assertEqual(cached, first, "クリア前はキャッシュ通り")

            # クリアして再呼び出し → 新しい中身（ASCII 寄りの utf-8）に対して chardet 再走
            # ASCII 寄りの中身を chardet が cp932 と判定する確率はほぼゼロなので、
            # cp932 由来の first とは別の値が返ることを期待できる
            _encoding_cache_clear()
            re_detected = detect_encoding(p)
            self.assertNotEqual(re_detected, first,
                                "クリア後は新ファイル内容に対して chardet が再走するはず")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_encoding.py -v
```

Expected: `ImportError: cannot import name '_encoding_cache_clear' from 'grep_helper.encoding'` または `test_同じパスを2回呼ぶ...` で 2 回目の値が異なって fail する。

- [ ] **Step 3: encoding キャッシュを実装**

`/workspaces/grep_helper_superpowers/grep_helper/encoding.py` を以下に置き換える:

```python
"""文字コード検出。"""
from __future__ import annotations

from pathlib import Path

try:
    import chardet as _chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False


# プロセス内グローバルキャッシュ。override が None のケースのみキャッシュする。
# キーは str(path)。Path.resolve() は使わない（NFS で realpath コストが効くため、
# source_files._resolve_file_cache と同じ流儀）。
_encoding_cache: dict[str, str] = {}


def _encoding_cache_clear() -> None:
    """テスト/チューニング用: キャッシュをクリア。"""
    _encoding_cache.clear()


def detect_encoding(path: Path, override: str | None = None) -> str:
    """ファイルの文字コードを検出する。overrideがあればそのまま返す。

    巨大ファイル対策として先頭 4096 バイトのみを読む。
    結果はパス単位でキャッシュし、同一プロセス内の重複呼び出しでは
    chardet・I/O を起動しない。
    """
    if override is not None:
        return override
    key = str(path)
    cached = _encoding_cache.get(key)
    if cached is not None:
        return cached

    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
    except OSError:
        _encoding_cache[key] = "cp932"
        return "cp932"
    if not _CHARDET_AVAILABLE:
        _encoding_cache[key] = "cp932"
        return "cp932"
    result = _chardet.detect(raw)
    if result and result.get("confidence", 0) >= 0.6 and result.get("encoding"):
        encoding = result["encoding"]
    else:
        encoding = "cp932"
    _encoding_cache[key] = encoding
    return encoding
```

- [ ] **Step 4: テストが通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_encoding.py -v
```

Expected: 4 tests passed.

- [ ] **Step 5: 既存テストが壊れていないことを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/ -x -q --timeout=60
```

Expected: 全 pass（既存テストへの破壊的変更なし）。

- [ ] **Step 6: ruff チェック**

Run:
```bash
python -m ruff check grep_helper/encoding.py tests/test_encoding.py
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add grep_helper/encoding.py tests/test_encoding.py
git commit -m "$(cat <<'EOF'
feat(E-1): cache detect_encoding results per path

Avoid repeated chardet runs for the same file across batch_track_indirect
loops. Override path bypasses cache. _encoding_cache_clear() exposed for
tests, mirroring _file_lines_cache_clear / _source_files_cache_clear.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_read_based_find` 単体 (E-3 part 1)

**Files:**
- Modify: `grep_helper/source_files.py`
- Create: `tests/test_source_files.py`

- [ ] **Step 1: 失敗するテストを書く**

`/workspaces/grep_helper_superpowers/tests/test_source_files.py`（新規）:

```python
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
            # chunk_size=8 で「BIGNAME」(7 バイト) を境界 6-13 に置く
            # 1 チャンク目: 0..7 = b"X" * 6 + b"BI"
            # 2 チャンク目: 8..15 = b"GNAME" + b"X" * 3
            # prepend overlap = max(len(p)) - 1 = 6 バイトを 1 チャンク末尾から保持
            # 2 チャンク目処理時には overlap + new = "X" * 4 + "BIGNAME" + "X" * 3 になる想定
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_source_files.py -v
```

Expected: `ImportError: cannot import name '_read_based_find'`.

- [ ] **Step 3: `_read_based_find` を実装**

`/workspaces/grep_helper_superpowers/grep_helper/source_files.py` の先頭付近（既存の `iter_source_files` の上）に追加:

```python
_DEFAULT_READ_CHUNK = 1024 * 1024  # 1 MB


def _read_based_find(
    path: Path,
    patterns: list[bytes],
    *,
    chunk_size: int = _DEFAULT_READ_CHUNK,
) -> bool:
    """1MB チャンク + prepend オーバーラップでバイト列を検索する。

    mmap が使えない / 失敗するファイルに対する代替実装。
    seek は使わず、前チャンク末尾の (max(len(p)) - 1) バイトを保持して
    次チャンクの先頭に貼り付けてから find する。

    API 契約: ``patterns`` は非空であること（呼び出し元 ``grep_filter_files``
    で空 patterns は早期 return 済み）。
    """
    overlap = max(len(p) for p in patterns) - 1
    if overlap < 0:
        overlap = 0
    tail = b""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                return False
            buf = tail + chunk
            for pat in patterns:
                if buf.find(pat) != -1:
                    return True
            tail = buf[-overlap:] if overlap > 0 else b""
```

- [ ] **Step 4: テストが通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_source_files.py -v
```

Expected: 7 tests passed.

- [ ] **Step 5: ruff チェック**

Run:
```bash
python -m ruff check grep_helper/source_files.py tests/test_source_files.py
```

Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add grep_helper/source_files.py tests/test_source_files.py
git commit -m "$(cat <<'EOF'
feat(E-3): add _read_based_find with prepend-overlap chunking

mmap fallback helper for grep_filter_files. Uses 1MB chunks plus
(max(len(p)) - 1) byte prepend to cover boundary-spanning patterns.
No seek() so NFS stat-cache races are sidestepped. patterns must be
non-empty (caller enforces).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `grep_filter_files` の `use_mmap` 引数 (E-3 part 2)

**Files:**
- Modify: `grep_helper/source_files.py`
- Modify: `tests/test_source_files.py`

- [ ] **Step 1: 失敗する積分テストを追加**

`/workspaces/grep_helper_superpowers/tests/test_source_files.py` の末尾に追加（`if __name__ == "__main__"` の前）:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_source_files.py::TestGrepFilterFilesUseMmap -v
```

Expected: `TypeError: grep_filter_files() got an unexpected keyword argument 'use_mmap'`.

- [ ] **Step 3: `grep_filter_files` に `use_mmap` 引数を追加**

`/workspaces/grep_helper_superpowers/grep_helper/source_files.py` の `grep_filter_files` を以下に置き換える:

```python
def grep_filter_files(
    names: list[str],
    src_dir: Path,
    extensions: list[str],
    label: str = "",
    *,
    use_mmap: bool = True,
) -> list[Path]:
    """mmap によるバイト列検索でスキャン対象ファイルを絞り込む。

    iter_source_files で取得した (キャッシュ済み) ファイルリストに対し
    mmap.find（または ``use_mmap=False`` 時 / mmap 失敗時は ``_read_based_find``）
    で names の含有を判定する。
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
            if use_mmap:
                try:
                    with open(f, "rb") as fh, \
                         mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        hit = any(mm.find(p) != -1 for p in patterns)
                except (OSError, ValueError, mmap.error):
                    hit = _read_based_find(f, patterns)
            else:
                hit = _read_based_find(f, patterns)
            if hit:
                result.append(f)
        except OSError:
            result.append(f)

    if label:
        print(
            f"  [{label}] 事前フィルタ完了: {len(candidates)} → {len(result)} ファイルに絞り込み",
            file=sys.stderr, flush=True,
        )

    return result
```

- [ ] **Step 4: テストが通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_source_files.py -v
```

Expected: 全 10 tests passed (7 既存 + 3 新規).

- [ ] **Step 5: 既存テストが壊れていないことを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/ -x -q --timeout=120
```

Expected: 全 pass.

- [ ] **Step 6: ruff チェック**

Run:
```bash
python -m ruff check grep_helper/source_files.py tests/test_source_files.py
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add grep_helper/source_files.py tests/test_source_files.py
git commit -m "$(cat <<'EOF'
feat(E-3): grep_filter_files use_mmap kw + auto fallback

use_mmap=True (default) keeps the existing mmap path; on OSError /
ValueError / mmap.error each file falls back to _read_based_find. With
use_mmap=False every file uses the read-based path (intended for Solaris
+ NFS where mmap can hang).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 12 ハンドラの `batch_track_indirect` に `use_mmap` kwarg を伝播

**Files:**
- Modify: `grep_helper/languages/java.py`
- Modify: `grep_helper/languages/java_track.py`
- Modify: `grep_helper/languages/kotlin.py`
- Modify: `grep_helper/languages/c.py`
- Modify: `grep_helper/languages/proc.py`
- Modify: `grep_helper/languages/sql.py`
- Modify: `grep_helper/languages/sh.py`
- Modify: `grep_helper/languages/ts.py`
- Modify: `grep_helper/languages/python.py`
- Modify: `grep_helper/languages/perl.py`
- Modify: `grep_helper/languages/dotnet.py`
- Modify: `grep_helper/languages/groovy.py`
- Modify: `grep_helper/languages/plsql.py`

このタスクは機械的な API 拡張。各ハンドラの `batch_track_indirect` シグネチャに `use_mmap: bool = True` キーワード引数を追加し、内部で `grep_filter_files` を呼ぶ箇所では `use_mmap=use_mmap` を渡す。`grep_filter_files` を呼ばないハンドラ（`sh.py`, `sql.py`）はシグネチャだけ拡張して引数を受け取り、未使用としておく。

- [ ] **Step 1: 既存テストで現状の grep_filter_files 呼び出しが何件あるかを把握**

Run:
```bash
cd /workspaces/grep_helper_superpowers && grep -rn "grep_filter_files(" grep_helper/languages/ | wc -l
```

Expected: 11 件（先の調査と一致）。

- [ ] **Step 2: 12 ハンドラの `batch_track_indirect` に kwarg を追加**

各ファイルで以下の置換を行う:

```
# Before
def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:

# After
def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
    use_mmap: bool = True,
) -> list[GrepRecord]:
```

対象ファイル: `java.py`, `kotlin.py`, `c.py`, `proc.py`, `sql.py`, `sh.py`, `ts.py`, `python.py`, `perl.py`, `dotnet.py`, `groovy.py`, `plsql.py`。

- [ ] **Step 3: `grep_filter_files(...)` 呼び出し 11 箇所に `use_mmap=use_mmap` を渡す**

各ハンドラで:

```python
# Before
src_files = grep_filter_files(names, src_dir, [".java"], label="...")

# After
src_files = grep_filter_files(names, src_dir, [".java"], label="...", use_mmap=use_mmap)
```

`java.py` の `batch_track_indirect` 内（`grep_filter_files(all_names, src_dir, [".java"], label="Java追跡")` 呼び出し）も同様に `use_mmap=use_mmap` を追加。

`java_track.py` 内の 4 箇所（`_batch_track_constants`, `_batch_track_getters`, `_batch_track_setters`, `_batch_track_combined`）の `grep_filter_files(...)` には`use_mmap` を引数に追加して propagate する必要がある。各関数のシグネチャにも `use_mmap=True` を追加し、`java.py` の `batch_track_indirect` から呼ぶ箇所で `use_mmap=use_mmap` を渡す。

具体的には `java_track.py` で:

```python
# _batch_track_combined のシグネチャを拡張
def _batch_track_combined(
    const_tasks, getter_tasks, setter_tasks,
    source_dir, stats, file_list=None,
    *, encoding_override=None, workers=1, use_mmap=True,
) -> list[GrepRecord]:
    ...
    java_files = file_list if file_list is not None else grep_filter_files(
        all_names, source_dir, [".java"], label="Java追跡(統合)", use_mmap=use_mmap,
    )
    ...
```

`_batch_track_constants`, `_batch_track_getters`, `_batch_track_setters` も同様にシグネチャ拡張 + `grep_filter_files` 呼び出しに `use_mmap=use_mmap` を渡す。

`java.py` 側で `_batch_track_combined(...)` を呼ぶ箇所に `use_mmap=use_mmap` を追加し、`grep_filter_files(all_names, ...)` の呼び出しにも `use_mmap=use_mmap` を追加する。

- [ ] **Step 4: 既存テストが全て通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/ -x -q --timeout=120
```

Expected: 全 pass。`use_mmap` のデフォルト True で旧呼び出し互換が保たれていれば既存テストはノータッチで通るはず。

- [ ] **Step 5: 受け取るが使わないハンドラ (sh, sql) で `use_mmap` を受けるだけにする**

`sh.py` / `sql.py` の `batch_track_indirect` は `grep_filter_files` を呼ばないため、`use_mmap` を受けて捨てる。引数として宣言しておくだけで OK（未使用警告を避けるため `# noqa: ARG001` または `_ = use_mmap` で抑制）。最小限の対応として:

```python
def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
    use_mmap: bool = True,  # noqa: ARG001 - インターフェース統一のため受けるだけ
) -> list[GrepRecord]:
    ...
```

- [ ] **Step 6: ruff チェック**

Run:
```bash
python -m ruff check grep_helper/languages/
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add grep_helper/languages/
git commit -m "$(cat <<'EOF'
feat(E-3): propagate use_mmap kwarg through 12 batch_track_indirect

Default True for backward compat. Handlers calling grep_filter_files
forward the flag; sh/sql receive but ignore (no grep_filter_files use).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `pipeline.run_full_pipeline` 3 フェーズ化 (E-2 part 1)

**Files:**
- Modify: `grep_helper/pipeline.py`
- Modify: `tests/test_pipeline_run.py`

- [ ] **Step 1: 集約処理 と エラー分離 のテストを追加**

`/workspaces/grep_helper_superpowers/tests/test_pipeline_run.py` の末尾に追加（既存 `TestRunFullPipeline` クラスのあとに新クラス）:

```python
class TestRunFullPipelineAggregation(unittest.TestCase):
    """集約処理 (E-2): 複数 grep を 1 回の間接追跡で処理しても、
    grep ごとに 1 本ずつ処理した場合と完全一致の TSV が出る。
    """

    def test_複数grepでも単独処理と同じTSVが出力される(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            src_dir.mkdir()
            (src_dir / "sample.sql").write_text(
                "SELECT * FROM t WHERE x = 'A';\n"
                "SELECT * FROM t WHERE x = 'B';\n",
                encoding="utf-8",
            )

            # 集約: 同じ input_dir に 2 grep
            input_combined = tmp_path / "input_combined"
            input_combined.mkdir()
            (input_combined / "A.grep").write_text(
                "src/sample.sql:1:SELECT * FROM t WHERE x = 'A';\n",
                encoding="utf-8",
            )
            (input_combined / "B.grep").write_text(
                "src/sample.sql:2:SELECT * FROM t WHERE x = 'B';\n",
                encoding="utf-8",
            )
            output_combined = tmp_path / "output_combined"
            run_full_pipeline(
                source_dir=src_dir, input_dir=input_combined,
                output_dir=output_combined, handler=sql_handler, workers=1,
            )

            # 単独: 1 grep ずつ別 input_dir で実行
            output_solo = tmp_path / "output_solo"
            output_solo.mkdir()
            for stem, body in [("A", "1:SELECT * FROM t WHERE x = 'A';"),
                               ("B", "2:SELECT * FROM t WHERE x = 'B';")]:
                input_solo = tmp_path / f"input_{stem}"
                input_solo.mkdir()
                (input_solo / f"{stem}.grep").write_text(
                    f"src/sample.sql:{body}\n", encoding="utf-8",
                )
                run_full_pipeline(
                    source_dir=src_dir, input_dir=input_solo,
                    output_dir=output_solo, handler=sql_handler, workers=1,
                )

            # 比較: A.tsv / B.tsv の中身が一致
            for keyword in ("A", "B"):
                combined = (output_combined / f"{keyword}.tsv").read_bytes()
                solo = (output_solo / f"{keyword}.tsv").read_bytes()
                self.assertEqual(combined, solo,
                                 f"{keyword}.tsv が集約/単独で一致しない")

    def test_1つのgrepが読めなくても他のgrepは処理される(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            src_dir.mkdir()
            (src_dir / "sample.sql").write_text(
                "SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8",
            )
            input_dir = tmp_path / "input"
            input_dir.mkdir()
            # A.grep は正常
            (input_dir / "A.grep").write_text(
                "src/sample.sql:1:SELECT * FROM t WHERE x = 'A';\n",
                encoding="utf-8",
            )
            # B.grep は読み取り時に IsADirectoryError を起こすディレクトリ
            (input_dir / "B.grep").mkdir()

            output_dir = tmp_path / "output"
            run_full_pipeline(
                source_dir=src_dir, input_dir=input_dir,
                output_dir=output_dir, handler=sql_handler, workers=1,
            )
            # A.tsv は正常に生成されているはず
            self.assertTrue((output_dir / "A.tsv").exists())
            # B.tsv は失敗して未生成 or 空でもよい（仕様: 個別 grep 失敗は他に巻き込まない）
```

- [ ] **Step 2: テストが失敗することを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_pipeline_run.py::TestRunFullPipelineAggregation -v
```

Expected: `test_複数grepでも単独処理と同じTSVが出力される` は現実装でも通るはず（per-grep 処理だが結果は同じ）。`test_1つのgrepが読めなくても他のgrepは処理される` は **FAIL**（現実装は B.grep のディレクトリ open で IsADirectoryError が伝播し全体中断）。

- [ ] **Step 3: `pipeline.run_full_pipeline` を 3 フェーズ化**

`/workspaces/grep_helper_superpowers/grep_helper/pipeline.py` の `run_full_pipeline` を以下に置き換える:

```python
def run_full_pipeline(
    source_dir: Path,
    input_dir: Path,
    output_dir: Path,
    handler: ModuleType,
    *,
    encoding: str | None = None,
    workers: int = 1,
    use_mmap: bool = True,
    stats: ProcessStats | None = None,
) -> list[str]:
    """input_dir/*.grep を処理し、output_dir/<stem>.tsv を書き出す（in-process 完全版）。

    3 フェーズ:
      1. 全 grep ファイルの直接分類を先に終わらせる
      2. ハンドラの間接追跡を 1 回だけ呼ぶ
      3. 戻り値を keyword で振り分けて TSV 出力

    Returns: 処理した grep ファイル名のリスト（出力 TSV を実際に書いたもののみ）。
    """
    import sys as _sys  # noqa: PLC0415
    from grep_helper.tsv_output import write_tsv  # noqa: PLC0415

    if stats is None:
        stats = ProcessStats()

    output_dir.mkdir(parents=True, exist_ok=True)

    grep_files = sorted(input_dir.glob("*.grep"))
    direct_by_keyword: dict[str, list[GrepRecord]] = {}
    processed_files: list[str] = []

    # フェーズ 1: 直接分類（個別 grep の例外は他に巻き込まない）
    for grep_path in grep_files:
        keyword = grep_path.stem
        try:
            direct = process_grep_file(
                grep_path, source_dir, handler,
                keyword=keyword, encoding=encoding, stats=stats,
            )
        except Exception as exc:
            print(
                f"  警告: {grep_path.name} の直接分類で例外 ({exc!r}) - スキップして継続",
                file=_sys.stderr, flush=True,
            )
            continue
        direct_by_keyword[keyword] = direct
        processed_files.append(grep_path.name)

    if not direct_by_keyword:
        return processed_files

    # フェーズ 2: 間接追跡を 1 回だけ
    indirect_fn = getattr(handler, "batch_track_indirect", None)
    indirect_by_keyword: dict[str, list[GrepRecord]] = {}
    if indirect_fn is not None:
        all_direct: list[GrepRecord] = []
        for records in direct_by_keyword.values():
            all_direct.extend(records)
        indirect_all = indirect_fn(
            all_direct, source_dir, encoding,
            workers=workers, use_mmap=use_mmap,
        )
        for rec in indirect_all:
            indirect_by_keyword.setdefault(rec.keyword, []).append(rec)

    # フェーズ 3: keyword で振り分けて TSV 出力
    for keyword, direct_records in direct_by_keyword.items():
        indirect_records = indirect_by_keyword.get(keyword, [])
        all_records = list(direct_records) + list(indirect_records)
        output_path = output_dir / f"{keyword}.tsv"
        write_tsv(all_records, output_path)

    return processed_files
```

- [ ] **Step 4: テストが通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_pipeline_run.py -v
```

Expected: 全 pass（既存 + 新規 2）。

- [ ] **Step 5: 既存テストが全て通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/ -x -q --timeout=120
```

Expected: 全 pass。`scripts/measure_kpi.py` 経由のテスト（`tests/test_measure_kpi.py`）も含めて壊れていないこと。

- [ ] **Step 6: ruff チェック**

Run:
```bash
python -m ruff check grep_helper/pipeline.py tests/test_pipeline_run.py
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add grep_helper/pipeline.py tests/test_pipeline_run.py
git commit -m "$(cat <<'EOF'
feat(E-2): restructure run_full_pipeline into 3 phases

Phase 1 classifies all grep files first. Phase 2 calls handler
batch_track_indirect once with the union of direct records. Phase 3
splits indirect output back per keyword and writes TSVs. Per-grep
exceptions in phase 1 are now logged and skipped instead of aborting
the whole run; phase 2 failure still aborts (single call).

use_mmap kwarg added (default True) and forwarded to the handler.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `dispatcher` 3 フェーズ化 (E-2 part 2)

**Files:**
- Modify: `grep_helper/dispatcher.py`
- Modify: `tests/test_all_analyzer.py`

- [ ] **Step 1: 集約処理のテストを追加（dispatcher 経由）**

`/workspaces/grep_helper_superpowers/tests/test_all_analyzer.py` を一度開いて構造を確認:

```bash
head -50 /workspaces/grep_helper_superpowers/tests/test_all_analyzer.py
```

ファイル末尾に新クラスを追加:

```python
class TestDispatcherAggregation(unittest.TestCase):
    """dispatcher.main の集約処理 (E-2): 複数 grep を 1 回の間接追跡で
    処理しても、grep ごとに 1 本ずつ処理した場合と完全一致の TSV が出る。
    """

    def test_複数grep集約でもTSVが完全一致する(self):
        from grep_helper.dispatcher import process_grep_lines_all, apply_indirect_tracking
        from grep_helper.grep_input import iter_grep_lines
        from grep_helper.encoding import detect_encoding
        from grep_helper.tsv_output import write_tsv

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            src_dir.mkdir()
            (src_dir / "a.sql").write_text(
                "SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8",
            )
            (src_dir / "b.sql").write_text(
                "SELECT * FROM t WHERE y = 'B';\n", encoding="utf-8",
            )

            # 集約: 同じ input dir に 2 grep
            output_combined = tmp_path / "output_combined"
            output_combined.mkdir()
            stats = ProcessStats()
            all_direct = []
            for stem, line in [("A", "src/a.sql:1:SELECT * FROM t WHERE x = 'A';"),
                               ("B", "src/b.sql:1:SELECT * FROM t WHERE y = 'B';")]:
                grep_path = tmp_path / f"{stem}.grep"
                grep_path.write_text(line + "\n", encoding="utf-8")
                enc = detect_encoding(grep_path, None)
                direct = process_grep_lines_all(
                    iter_grep_lines(grep_path, enc), stem, src_dir, stats,
                )
                all_direct.extend(direct)
            indirect = apply_indirect_tracking(all_direct, src_dir, None, workers=1)
            from collections import defaultdict
            indirect_by_kw = defaultdict(list)
            for rec in indirect:
                indirect_by_kw[rec.keyword].append(rec)
            # write per-keyword
            kw_to_direct = defaultdict(list)
            for rec in all_direct:
                kw_to_direct[rec.keyword].append(rec)
            for kw, direct in kw_to_direct.items():
                write_tsv(direct + indirect_by_kw[kw], output_combined / f"{kw}.tsv")

            # 単独: 1 grep ずつ
            output_solo = tmp_path / "output_solo"
            output_solo.mkdir()
            for stem, line in [("A", "src/a.sql:1:SELECT * FROM t WHERE x = 'A';"),
                               ("B", "src/b.sql:1:SELECT * FROM t WHERE y = 'B';")]:
                grep_path = tmp_path / f"{stem}.grep"
                stats_solo = ProcessStats()
                enc = detect_encoding(grep_path, None)
                direct = process_grep_lines_all(
                    iter_grep_lines(grep_path, enc), stem, src_dir, stats_solo,
                )
                indirect = apply_indirect_tracking(direct, src_dir, None, workers=1)
                write_tsv(direct + indirect, output_solo / f"{stem}.tsv")

            for keyword in ("A", "B"):
                combined = (output_combined / f"{keyword}.tsv").read_bytes()
                solo = (output_solo / f"{keyword}.tsv").read_bytes()
                self.assertEqual(
                    combined, solo,
                    f"{keyword}.tsv が dispatcher の集約/単独で一致しない",
                )
```

`tests/test_all_analyzer.py` の冒頭で `from grep_helper.model import ProcessStats` が import されていなければ追加。

- [ ] **Step 2: テストが失敗 or 通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_all_analyzer.py::TestDispatcherAggregation -v
```

Expected: 通る可能性あり（apply_indirect_tracking 自体は既に集約に対応）。失敗する場合は use_mmap kwarg 不足など。

- [ ] **Step 3: `dispatcher.apply_indirect_tracking` のシグネチャを拡張**

`/workspaces/grep_helper_superpowers/grep_helper/dispatcher.py` の `apply_indirect_tracking` を以下に置き換える:

```python
def apply_indirect_tracking(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
    use_mmap: bool = True,
) -> list[GrepRecord]:
    """登録済み全ハンドラの batch_track_indirect を順次呼び出し、結果を結合する。"""
    results: list[GrepRecord] = []
    for handler in _all_handlers():
        fn = getattr(handler, "batch_track_indirect", None)
        if fn is None:
            continue
        results.extend(fn(direct_records, src_dir, encoding,
                          workers=workers, use_mmap=use_mmap))
    return results
```

- [ ] **Step 4: `dispatcher.main` を 3 フェーズ化**

`/workspaces/grep_helper_superpowers/grep_helper/dispatcher.py` の `main` 関数を以下に置き換える（CLI フラグの追加は Task 8）:

```python
def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"エラー: --source-dir が存在しません: {source_dir}", file=sys.stderr)
        return 1
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"エラー: --input-dir が存在しません: {input_dir}", file=sys.stderr)
        return 1

    grep_files = sorted(input_dir.glob("*.grep"))
    if not grep_files:
        print("エラー: grep結果ファイルがありません", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    stats = ProcessStats()
    direct_by_keyword: dict[str, list[GrepRecord]] = {}
    processed_files: list[str] = []

    # フェーズ 1: 直接分類（個別 grep 失敗は他に巻き込まない）
    for grep_path in grep_files:
        keyword = grep_path.stem
        try:
            enc = detect_encoding(grep_path, args.encoding)
            direct = process_grep_lines_all(
                iter_grep_lines(grep_path, enc), keyword, source_dir, stats,
                encoding=args.encoding,
            )
        except Exception as exc:
            print(
                f"  警告: {grep_path.name} の直接分類で例外 ({exc!r}) - スキップして継続",
                file=sys.stderr, flush=True,
            )
            continue
        direct_by_keyword[keyword] = direct
        processed_files.append(grep_path.name)

    # フェーズ 2: 間接追跡を 1 回だけ
    indirect_by_keyword: dict[str, list[GrepRecord]] = {}
    if direct_by_keyword:
        all_direct: list[GrepRecord] = []
        for records in direct_by_keyword.values():
            all_direct.extend(records)
        try:
            indirect_all = apply_indirect_tracking(
                all_direct, source_dir, args.encoding, workers=args.workers,
            )
        except Exception as exc:
            print(f"予期しないエラー（間接追跡フェーズ）: {exc}", file=sys.stderr)
            return 2
        for rec in indirect_all:
            indirect_by_keyword.setdefault(rec.keyword, []).append(rec)

    # フェーズ 3: keyword で振り分けて TSV 出力
    for keyword, direct_records in direct_by_keyword.items():
        indirect_records = indirect_by_keyword.get(keyword, [])
        all_records = list(direct_records) + list(indirect_records)
        output_path = output_dir / f"{keyword}.tsv"
        write_tsv(all_records, output_path)
        print(f"  {keyword}.grep → {output_path} "
              f"(直接: {len(direct_records)} 件, 間接: {len(indirect_records)} 件)")

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")
    return 0
```

- [ ] **Step 5: テストが通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_all_analyzer.py -v --timeout=60
```

Expected: 全 pass.

- [ ] **Step 6: 既存テスト全体を確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/ -x -q --timeout=120
```

Expected: 全 pass.

- [ ] **Step 7: ruff チェック**

Run:
```bash
python -m ruff check grep_helper/dispatcher.py tests/test_all_analyzer.py
```

Expected: All checks passed.

- [ ] **Step 8: Commit**

```bash
git add grep_helper/dispatcher.py tests/test_all_analyzer.py
git commit -m "$(cat <<'EOF'
feat(E-2): restructure dispatcher.main into 3 phases

Mirror pipeline.run_full_pipeline change for the multi-language CLI
entry point. Phase 1 collects direct records per keyword (per-grep
exceptions skip rather than abort). Phase 2 runs apply_indirect_tracking
once on the union. Phase 3 splits by keyword and writes TSVs. Phase 2
exceptions still abort with rc=2.

apply_indirect_tracking gains use_mmap kw (default True) propagated to
each handler's batch_track_indirect.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `--no-mmap` CLI フラグ + 環境変数 (E-3 part 3)

**Files:**
- Modify: `grep_helper/dispatcher.py`
- Modify: `tests/test_all_analyzer.py`

- [ ] **Step 1: フラグ解決ヘルパーのテストを書く**

`/workspaces/grep_helper_superpowers/tests/test_all_analyzer.py` の末尾に追加:

```python
class TestNoMmapFlag(unittest.TestCase):
    """--no-mmap フラグ + GREP_HELPER_NO_MMAP 環境変数の解決ロジック。"""

    def test_未指定環境変数なしならuse_mmap_True(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertTrue(_resolve_use_mmap(no_mmap_arg=False, env={}))

    def test_フラグ明示でuse_mmap_False(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertFalse(_resolve_use_mmap(no_mmap_arg=True, env={}))

    def test_環境変数で1ならuse_mmap_False(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertFalse(_resolve_use_mmap(
            no_mmap_arg=False, env={"GREP_HELPER_NO_MMAP": "1"},
        ))

    def test_環境変数で0ならuse_mmap_True(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertTrue(_resolve_use_mmap(
            no_mmap_arg=False, env={"GREP_HELPER_NO_MMAP": "0"},
        ))

    def test_フラグ優先(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        # CLI 明示は env を上書き（CLI False 時のみ env を読むので、
        # CLI True なら env="0" でも use_mmap=False のまま）
        self.assertFalse(_resolve_use_mmap(
            no_mmap_arg=True, env={"GREP_HELPER_NO_MMAP": "0"},
        ))

    def test_argparseで_no_mmapフラグが解釈される(self):
        from grep_helper.dispatcher import build_parser
        parser = build_parser()
        args = parser.parse_args(["--source-dir", "/tmp", "--no-mmap"])
        self.assertTrue(getattr(args, "no_mmap", False))

        args2 = parser.parse_args(["--source-dir", "/tmp"])
        self.assertFalse(getattr(args2, "no_mmap", False))
```

- [ ] **Step 2: テストが失敗することを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_all_analyzer.py::TestNoMmapFlag -v
```

Expected: `ImportError: cannot import name '_resolve_use_mmap'` および `argparse: unrecognized arguments: --no-mmap`.

- [ ] **Step 3: `dispatcher.build_parser` に `--no-mmap` を追加 + `_resolve_use_mmap` 実装**

`/workspaces/grep_helper_superpowers/grep_helper/dispatcher.py` を編集:

`build_parser()` 内に以下の引数を追加（既存 `--workers` の下）:

```python
    parser.add_argument(
        "--no-mmap", action="store_true",
        help="mmap 経由のファイル絞り込みを使わず read 経由にする（Solaris+NFS で推奨）",
    )
```

ファイル末尾の `if __name__ == "__main__":` 直前に `_resolve_use_mmap` ヘルパーを追加:

```python
def _resolve_use_mmap(no_mmap_arg: bool, env: dict | None = None) -> bool:
    """CLI フラグと環境変数から use_mmap の値を決定する。

    優先順:
      - CLI で --no-mmap 明示 (no_mmap_arg=True) なら use_mmap=False
      - 未指定なら GREP_HELPER_NO_MMAP=1 のとき use_mmap=False
      - それ以外は use_mmap=True
    """
    if no_mmap_arg:
        return False
    if env is None:
        env = os.environ
    if env.get("GREP_HELPER_NO_MMAP") == "1":
        return False
    return True
```

`main()` 内の `apply_indirect_tracking(...)` 呼び出しに `use_mmap` を渡す:

```python
        try:
            indirect_all = apply_indirect_tracking(
                all_direct, source_dir, args.encoding,
                workers=args.workers,
                use_mmap=_resolve_use_mmap(args.no_mmap),
            )
```

- [ ] **Step 4: テストが通ることを確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/test_all_analyzer.py::TestNoMmapFlag -v
```

Expected: 6 tests passed.

- [ ] **Step 5: 既存テスト全体を確認**

Run:
```bash
cd /workspaces/grep_helper_superpowers && python -m pytest tests/ -x -q --timeout=120
```

Expected: 全 pass.

- [ ] **Step 6: ruff チェック**

Run:
```bash
python -m ruff check grep_helper/dispatcher.py
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add grep_helper/dispatcher.py tests/test_all_analyzer.py
git commit -m "$(cat <<'EOF'
feat(E-3): add --no-mmap CLI flag and GREP_HELPER_NO_MMAP env

CLI flag presence forces use_mmap=False; otherwise env var
GREP_HELPER_NO_MMAP=1 also forces False; default True. _resolve_use_mmap
helper isolates the precedence logic for unit testing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Solaris スモーク手順ドキュメント (C-2)

**Files:**
- Create: `scripts/smoke_solaris.md`

- [ ] **Step 1: スモーク手順を新規作成**

`/workspaces/grep_helper_superpowers/scripts/smoke_solaris.md`:

````markdown
# Solaris 10 + Python 3.7 スモーク手順

`grep_helper` を Solaris 10 + Python 3.7.17 (cc 自前ビルド + venv 構成) で動かす際の確認手順。
spec: `docs/superpowers/specs/2026-05-06-perf-and-solaris-compat-design.md`

## 0. 前提パッケージ（OpenCSW から導入）

Solaris 10 同梱の Studio cc は Python 3.7 setup.py の前提から外れるため OpenCSW の gcc を使う。

```sh
$ /opt/csw/bin/pkgutil -y -i gcc4core gcc4g++ libssl_dev zlib_dev libffi_dev \
                              gnumake coreutils
```

## 1. Python 3.7.17 ビルド

`--with-openssl` を渡さないと `ssl` モジュールが無効化され `pip install` の TLS 接続が失敗する。

```sh
$ tar xzf Python-3.7.17.tgz && cd Python-3.7.17
$ CC=/opt/csw/bin/gcc \
  CFLAGS="-I/opt/csw/include" \
  LDFLAGS="-L/opt/csw/lib -R/opt/csw/lib" \
  ./configure --prefix=$HOME/py37 --enable-shared \
              --with-openssl=/opt/csw \
              --with-system-ffi
$ gmake -j4 && gmake install
```

## 2. venv 作成

```sh
$ $HOME/py37/bin/python3 -m venv $HOME/grep_helper_venv
$ source $HOME/grep_helper_venv/bin/activate
$ pip install --upgrade pip   # SSL が通れば成功
```

## 3. 依存インストール

cp312 wheel は Solaris で使えないため source build。

```sh
$ pip install --no-binary=:all: chardet javalang
# pyahocorasick の C 拡張は Solaris 10 の libc で通らない場合がある。
# 失敗しても run-time には grep_helper/_aho_corasick.py の pure Python
# フォールバックがあるので、|| true で無視して構わない。
$ pip install --no-binary=:all: pyahocorasick || true
```

## 4. ulimit 引き上げ

`--workers >= 2` を使う場合、`ProcessPoolExecutor` × `mmap` 同時オープン数で
Solaris 10 デフォルトの `nofiles(soft)=256` に当たる現実性がある。

```sh
$ ulimit -n 1024     # ユーザ shell の soft limit
# それ以上必要なら hard limit (デフォルト 65536) まで上げられる:
$ ulimit -n 4096
# zone 内で hard limit が 256 のままに見える場合は projmod / /etc/system の
#   set rlim_fd_cur = 4096
# で root 側調整が必要。
```

## 5. スモーク実行

```sh
$ python analyze_all.py --source-dir <path> \
    --input-dir input --output-dir output --no-mmap
```

## 6. 既知の制約・確認ポイント

- **NFS + mmap**: Solaris + NFS では `--no-mmap` または `GREP_HELPER_NO_MMAP=1` を推奨。
  NFS の stat キャッシュ古値で `mmap` 後に EOF を超えるエラーが出る事例あり。
- **zone CPU**: 実機の zone 内では `os.cpu_count()` が物理 CPU 数を返し `psrinfo` の
  制限を無視するので、`--workers` は明示指定する。
- **シンボリックリンクループ**: `/proc` 参照や NFS 自己参照を踏むと Python 3.7 の
  `pathlib.rglob` は `RecursionError` を出す。`--source-dir` に怪しいリンクが
  無いことを事前に確認すること。
- **shebang**: `analyze_*.py` は直接 `python analyze_all.py` で起動するため
  shebang は気にしなくてよい。直接実行したい場合は venv の `python3` が PATH
  に通っていることを確認。
````

- [ ] **Step 2: ファイルが存在することを確認**

Run:
```bash
test -f /workspaces/grep_helper_superpowers/scripts/smoke_solaris.md && echo "OK"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_solaris.md
git commit -m "$(cat <<'EOF'
docs(C-2): add scripts/smoke_solaris.md for Python 3.7 + Solaris 10

Coverage: OpenCSW gcc / OpenSSL / libffi prerequisites, configure flags
that prevent the typical SSL-less pip-install failure, ulimit / projmod
guidance for ProcessPoolExecutor + mmap, and known constraints (NFS
mmap caveat, zone cpu_count, rglob symlink loops).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: V-1 KPI before/after 計測

**Files:**
- Modify: `docs/superpowers/specs/2026-05-06-perf-and-solaris-compat-design.md`（末尾にクロージングノート追記）

このタスクは実装計画の **クロージング** にあたる。dev container 上で改造前後（main vs feature ブランチ）を比較し、網羅率と速度を spec の末尾に書き残す。

- [ ] **Step 1: feature ブランチのベースラインを記録**

現在の feature ブランチで:

```bash
cd /workspaces/grep_helper_superpowers
python scripts/measure_kpi.py --lang all > /tmp/kpi_after.txt 2>&1
```

`tests/golden/` 配下の各言語に対して analyze_all を回して時間を測る:

```bash
mkdir -p /tmp/after
for lang in java c proc sql sh kotlin plsql ts python perl dotnet groovy; do
  if [ -d "tests/golden/$lang/inputs" ] && [ -d "tests/golden/$lang/src" ]; then
    rm -rf /tmp/after/$lang
    mkdir -p /tmp/after/$lang
    { time python analyze_all.py \
        --source-dir tests/golden/$lang/src \
        --input-dir tests/golden/$lang/inputs \
        --output-dir /tmp/after/$lang ; } 2> /tmp/after/$lang.time
  fi
done
```

- [ ] **Step 2: main ブランチに切り替えてベースラインを取る**

別ディレクトリで main を clone するか、現ブランチをスタッシュして main に戻る:

```bash
git stash push -u -m "perf-feature-wip"
git checkout main
python scripts/measure_kpi.py --lang all > /tmp/kpi_before.txt 2>&1

mkdir -p /tmp/before
for lang in java c proc sql sh kotlin plsql ts python perl dotnet groovy; do
  if [ -d "tests/golden/$lang/inputs" ] && [ -d "tests/golden/$lang/src" ]; then
    rm -rf /tmp/before/$lang
    mkdir -p /tmp/before/$lang
    { time python analyze_all.py \
        --source-dir tests/golden/$lang/src \
        --input-dir tests/golden/$lang/inputs \
        --output-dir /tmp/before/$lang ; } 2> /tmp/before/$lang.time
  fi
done

git checkout -   # feature ブランチに戻る
git stash pop
```

- [ ] **Step 3: 出力 TSV の完全一致を確認**

Run:
```bash
diff -r /tmp/before /tmp/after
```

Expected: 出力ナシ（完全一致）。`.time` ファイルの差分は出るが TSV 自体は一致。

差分が出た場合は実装に欠陥がある。`*.tsv` ファイルだけを比較するならば:

```bash
for f in $(find /tmp/before -name "*.tsv"); do
    rel=${f#/tmp/before/}
    diff -q "$f" "/tmp/after/$rel" || echo "DIFF: $rel"
done
```

- [ ] **Step 4: KPI ゴールデンセット結果の同等性を確認**

Run:
```bash
diff /tmp/kpi_before.txt /tmp/kpi_after.txt
```

Expected: 出力ナシ（完全一致）。差分が出た場合、改造で網羅率/分類精度が変化している → 実装欠陥。

- [ ] **Step 5: 速度比較サマリを抽出**

```bash
echo "=== before ==="
for f in /tmp/before/*.time; do
    lang=$(basename ${f%.time})
    real=$(grep -E "^real" $f || echo "real -")
    echo "$lang $real"
done

echo "=== after ==="
for f in /tmp/after/*.time; do
    lang=$(basename ${f%.time})
    real=$(grep -E "^real" $f || echo "real -")
    echo "$lang $real"
done
```

speedup を一言で: `(before total) / (after total)`. `time_after` が `time_before` と同等以上であることを確認。

- [ ] **Step 6: spec 末尾にクロージングノートを追記**

`/workspaces/grep_helper_superpowers/docs/superpowers/specs/2026-05-06-perf-and-solaris-compat-design.md` の末尾に追加:

```markdown

---

## クロージングノート（2026-05-XX 計測）

### TSV / KPI 同等性

- `diff -r /tmp/before /tmp/after` の `.tsv` 比較: 完全一致
- `diff /tmp/kpi_before.txt /tmp/kpi_after.txt`: 完全一致

### 速度比較（dev container, Python 3.12, tests/golden/）

| 言語 | before (real) | after (real) | speedup |
|---|---|---|---|
| java | <測定値> | <測定値> | <比> |
| c | ... | ... | ... |
| ... | ... | ... | ... |

合計 wall clock: before <秒> / after <秒>、speedup ≈ <倍>。

### 残課題

- 60GB 級ソースでの本番計測は別 spec で扱う（KPI ゴールデンセット規模では encoding キャッシュの効果が小さいケースあり）。
- Solaris 10 実機でのスモークは出荷前に `scripts/smoke_solaris.md` の手順で実施。
```

具体的な数字は計測結果で埋める。

- [ ] **Step 7: クロージングノートを commit**

```bash
git add docs/superpowers/specs/2026-05-06-perf-and-solaris-compat-design.md
git commit -m "$(cat <<'EOF'
docs(specs/2026-05-06): add closing note with KPI before/after results

V-1 verification: TSV and KPI golden set bit-for-bit identical, speedup
recorded.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review ノート

実装中に注意する観点:

- **Task 5 の機械的編集**: 12 ハンドラに同じパターンの修正を入れる。1 ハンドラずつ個別 commit はせず、1 commit にまとめる（atomicity）。
- **Task 6 / Task 7 のテスト**: TSV のバイト一致比較を `read_bytes()` で行う。`splitlines()` 等で正規化しない（spec §順序保証で論証した「バイト一致」を直接検証する目的のため）。
- **Task 7 の `apply_indirect_tracking` 拡張**: 既存テスト `test_all_analyzer.py:317-399` 周辺のラッパが `apply_indirect_tracking(direct_records, source_dir, encoding, workers=workers)` のキーワード引数 `workers` を渡しているはず。`use_mmap` のデフォルト True で旧呼び出しを壊さない。
- **Task 8 の env テスト**: 実環境の `os.environ` を変更せず、`_resolve_use_mmap` に dict を渡してテストする（テスト副作用回避）。
- **Task 10 の計測**: dev container 上では encoding キャッシュ・mmap フォールバックの効果がほぼ可視化されない可能性あり（small dataset）。speedup が 1.0x 周辺でも TSV/KPI 一致なら「網羅率を維持しつつ重複作業を削った」要件は満たす。
