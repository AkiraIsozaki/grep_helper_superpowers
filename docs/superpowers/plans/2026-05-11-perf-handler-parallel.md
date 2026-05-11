# パフォーマンス改善: ハンドラ並列化 + インクリメンタル TSV 出力 + バイトスキャン重複削減 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `analyze_all.py` (dispatcher 経由) の Phase 2 を ProcessPool でハンドラ並列化し、keyword 単位の TSV を「全 handler 完了時点」で逐次書き出すことで壁時計時間と TTFB を短縮する。同時に `grep_filter_files` にファイル単位 byte hit cache を入れて重複バイトスキャンを削減し、決定的ソートを 5 タプル化して並列化に伴う tie 部分の挿入順依存を消す。

**Architecture:** 4 段階のロールアウト。Task 1 で決定的ソート完全化（独立変更、golden 再生成）→ Task 2 で byte cache（API 不変）→ Task 3 で `apply_indirect_tracking` の並列化インフラ（関数デフォルトは直列、後方互換）→ Task 4 で `dispatcher.main` のインクリメンタル化 + CLI `--handler-workers` 既定 2 を入れる。Task 5 で V-1 検証。Task 2 以降は `tests/golden/` 差分ゼロを必須条件とし、差分が出たら原因究明（再生成では誤魔化さない）。

**Tech Stack:** Python 3.7+ / `concurrent.futures.ProcessPoolExecutor` (fork start method) / `unittest` + pytest / `mmap` + read-based fallback / 既存の `pyahocorasick` 等は無変更。

**仕様根拠:** `docs/superpowers/specs/2026-05-11-perf-handler-parallel-design.md`

---

## ファイル構造

**改造対象 (3 ファイル):**

| ファイル | 責務 |
|----------|------|
| `grep_helper/tsv_output.py` | TSV 書き出し + 決定的ソート (5 タプル sort key) |
| `grep_helper/source_files.py` | ソースファイル探索 + バイト前フィルタ + **新規: file-level byte hit cache** |
| `grep_helper/dispatcher.py` | dispatcher.main 統合 + **新規: handler 並列化 + インクリメンタル書き出し + CLI `--handler-workers`** |

**追加テスト (3 ファイル新規 + 1 ファイル追記):**

| ファイル | 責務 |
|----------|------|
| `tests/test_tsv_output.py` (新規) | 決定的ソート tie 解消の検証 |
| `tests/test_source_files.py` (追記) | byte hit cache の cache 効果検証 |
| `tests/test_dispatcher_parallel.py` (新規) | `apply_indirect_tracking` の並列実行 / 1 handler 例外スキップ |
| `tests/test_dispatcher_incremental.py` (新規) | keyword 完了タイミングでの TSV インクリメンタル書き出し |

**コーディング規約 (`/workspaces/grep_helper_superpowers/.claude/skills/coding-conventions.md`):**
- コメント・docstring は日本語
- 識別子は英語
- モジュール・クラス・public 関数には docstring 必須

**テスト方針 (memory `feedback_test_style.md` / `feedback_tdd_stance.md`):**
- WHAT 検証 (HOW = 内部関数呼び出し回数の観察は避ける)
- メソッド名は日本語 (`def test_xxxを渡すとyyyが返る`)
- 古典学派 (実物オブジェクト優先、必要に応じてのみ fake)
- TDD: Red → Green → Refactor

---

## Task 1: 決定的ソート完全化

`_sort_key` / `_row_sort_key` を `(keyword, filepath, lineno, ref_type, usage_type)` の 5 タプルに拡張し、tie 部分の挿入順依存を消す。

**Files:**
- Create: `tests/test_tsv_output.py`
- Modify: `grep_helper/tsv_output.py:23-29`

- [ ] **Step 1.1: 決定的ソートの tie 解消テストを書く**

新規 `tests/test_tsv_output.py`:

```python
"""tsv_output の決定的ソート 5 タプル化テスト。"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.model import GrepRecord, RefType
from grep_helper.tsv_output import write_tsv


class TestWriteTsvDeterministicOrder(unittest.TestCase):
    """同一 (keyword, filepath, lineno) で複数 ref_type / usage_type が出るとき、
    アルファベット順で決定的に並ぶ。
    """

    def _read_rows(self, path: Path) -> list[list[str]]:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader)  # ヘッダ
            return list(reader)

    def test_同一file_line_で複数ref_typeがあるとref_type順に並ぶ(self):
        records = [
            GrepRecord(keyword="K", ref_type=RefType.SETTER.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="x"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "K.tsv"
            write_tsv(records, out)
            rows = self._read_rows(out)
            # 「間接（setter経由）」 vs 「直接」: アルファベット順 (sjis でも unicode 順でも)
            # 「直接」 < 「間接（setter経由）」 ではなく Python 文字列順で判定される。
            # 観察可能事実として「同入力で 2 回呼んでも順序が一致する」を主眼にする。
            self.assertEqual(len(rows), 2)
            # 同じ入力を 2 回ソートしても順序が変わらない (決定性)
            with tempfile.TemporaryDirectory() as tmp2:
                out2 = Path(tmp2) / "K.tsv"
                write_tsv(list(reversed(records)), out2)
                rows2 = self._read_rows(out2)
                self.assertEqual(rows, rows2)

    def test_同一file_line_ref_typeで複数usage_typeがあるとusage_type順に並ぶ(self):
        records = [
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UB",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="y"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "K.tsv"
            write_tsv(records, out)
            rows = self._read_rows(out)
            self.assertEqual([r[2] for r in rows], ["UA", "UB"])

    def test_異なる挿入順で書き出しても結果TSVがバイト一致する(self):
        base = [
            GrepRecord(keyword="K", ref_type=RefType.DIRECT.value, usage_type="UA",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.SETTER.value, usage_type="UB",
                       filepath="a.java", lineno="10", code="x"),
            GrepRecord(keyword="K", ref_type=RefType.GETTER.value, usage_type="UA",
                       filepath="b.java", lineno="5", code="y"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            write_tsv(list(base), t / "a.tsv")
            write_tsv(list(reversed(base)), t / "b.tsv")
            self.assertEqual((t / "a.tsv").read_bytes(), (t / "b.tsv").read_bytes())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 1.2: テストを走らせて失敗を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_tsv_output.py -v`

Expected: 3 件中 1〜2 件が FAIL（既存の 3 タプルソートでは tie が挿入順依存）

- [ ] **Step 1.3: `_sort_key` と `_row_sort_key` を 5 タプル化**

`grep_helper/tsv_output.py:23-29` を編集:

```python
def _sort_key(r: GrepRecord) -> tuple:
    """GrepRecord を決定的に並べるためのキー。tie を避けるため 5 タプル。"""
    lineno_int = int(r.lineno) if r.lineno.isdigit() else 0
    return (r.keyword, r.filepath, lineno_int, r.ref_type, r.usage_type)


def _row_sort_key(row: list[str]) -> tuple:
    """外部マージソート用の行キー。_sort_key と同じ並び。"""
    lineno_int = int(row[4]) if row[4].isdigit() else 0
    # 列順: 0=keyword, 1=ref_type, 2=usage_type, 3=filepath, 4=lineno
    return (row[0], row[3], lineno_int, row[1], row[2])
```

- [ ] **Step 1.4: テストを走らせて通過を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_tsv_output.py -v`

Expected: 3 件全 PASS

- [ ] **Step 1.5: 既存テスト全体を走らせて影響 fixture を特定**

Run: `cd /workspaces/grep_helper_superpowers && pytest -q 2>&1 | tee /tmp/pytest_after_sort.log`

Expected: tie のある fixture を持つテストのみ FAIL（多くは PASS のまま）。失敗テストの一覧を `/tmp/pytest_after_sort.log` で確認。

- [ ] **Step 1.6: 影響 fixture の golden TSV を再生成**

失敗した各テストについて、`tests/golden/<lang>/expected/*.tsv` のうち tie がある行が含まれるファイルを特定する。再生成手順 (1 言語ずつ):

```bash
# 例: java の golden 再生成 (Step 1.5 で java の test が落ちた場合)
$ cd /workspaces/grep_helper_superpowers
$ python scripts/measure_kpi.py --lang java --quiet
# → tests/golden/java/expected/ と KPI 計算が再走される
# → 比較で差分が出るのは tie の並べ替えのみ (行数・内容は同じ)
# → 差分を確認: diff -u tests/golden/java/expected/<old>.tsv <regenerated>.tsv
# → 並べ替え以外の差分が無いことを確認したら、新出力で expected を上書き
```

判定基準: **`diff` の差分が「同一 (filepath, lineno) 内の行順変更のみ」**であれば OK。それ以外の差分（行の追加・削除・内容変更）が出た場合は実装バグなので **再生成せずに調査**する。

各言語ぶん回して `tests/golden/*/expected/*.tsv` を更新。

- [ ] **Step 1.7: 全テスト緑化を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest -q`

Expected: 全 PASS。failure があれば Step 1.6 の判定基準で「行順変更以外」が混ざっていないか再確認。

- [ ] **Step 1.8: コミット**

```bash
cd /workspaces/grep_helper_superpowers
git add grep_helper/tsv_output.py tests/test_tsv_output.py tests/golden/
git commit -m "feat(tsv_output): make sort key fully deterministic (5-tuple)

(keyword, filepath, lineno) で tie になる行を ref_type/usage_type で
完全決定化する。並列化フェーズに備えた基盤変更。

golden は本コミットで一度だけ再生成。以降のタスクでは差分ゼロを必須とする。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: file-level byte hit cache

`grep_helper/source_files.py` に `_filter_byte_cache` を追加し、同一ファイル × 同一パターンへの 2 回目以降のバイトスキャンを I/O 無しで返せるようにする。**公開 API は不変**。

**Files:**
- Modify: `grep_helper/source_files.py`
- Modify: `tests/test_source_files.py` (追記)

- [ ] **Step 2.1: cache 効果のテストを追記**

`tests/test_source_files.py` の末尾（`if __name__ == "__main__":` の直前）に追記:

```python
class TestFilterByteCache(unittest.TestCase):
    """grep_filter_files が file-level byte hit cache を持つ。
    同じ (path, pattern) の 2 回目以降の問い合わせは I/O を伴わず、
    cache 済みの結果を返す。
    """

    def setUp(self):
        from grep_helper.source_files import _source_files_cache_clear, _filter_byte_cache_clear
        _source_files_cache_clear()
        _filter_byte_cache_clear()

    def test_同じパターンを2回問い合わせるとファイル削除後も結果が変わらない(self):
        """cache 効果の観察可能事実: 1 回目で hit/miss を確定 → ファイル変更後の
        2 回目でも同じ結果が返る。clear するまで cache される。
        """
        from grep_helper.source_files import grep_filter_files
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            f = src / "a.java"
            f.write_text("class A { String FOO = \"hit\"; }\n")
            first = grep_filter_files(["FOO"], src, [".java"], use_mmap=True)
            self.assertEqual([p.name for p in first], ["a.java"])
            # ファイルからパターンを除去
            f.write_text("class A { /* empty */ }\n")
            # cache クリアせずに 2 回目 → cache 済み hit が返る
            second = grep_filter_files(["FOO"], src, [".java"], use_mmap=True)
            self.assertEqual([p.name for p in second], ["a.java"])

    def test_異なるパターン集合の2回目は差分パターンだけ新規スキャンされる(self):
        """1 回目で {A, B}、2 回目で {B, C} を問い合わせると、
        B は cache hit、C は新規スキャン。観察可能事実として:
        - 1 回目で A=hit, B=hit と判定されたファイルがある
        - 2 回目で B が cache hit、C を新規スキャンしてその時点の内容を反映
        """
        from grep_helper.source_files import grep_filter_files
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            f = src / "a.java"
            f.write_text("A B\n")
            # 1 回目: A と B が両方 hit → ファイルがリストに入る
            first = grep_filter_files(["A", "B"], src, [".java"], use_mmap=True)
            self.assertEqual([p.name for p in first], ["a.java"])
            # ファイルから A を除去 (B はそのまま、C を追加)
            f.write_text("B C\n")
            # 2 回目: B (cache hit, 古い True) + C (新規スキャン, hit)
            #         → どちらかが hit なのでファイルはリストに入る
            second = grep_filter_files(["B", "C"], src, [".java"], use_mmap=True)
            self.assertEqual([p.name for p in second], ["a.java"])

    def test_filter_byte_cache_clearでcacheが空になる(self):
        """cache クリア後はファイル内容を再評価する。"""
        from grep_helper.source_files import (
            grep_filter_files,
            _filter_byte_cache_clear,
            _source_files_cache_clear,
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            f = src / "a.java"
            f.write_text("FOO\n")
            first = grep_filter_files(["FOO"], src, [".java"], use_mmap=True)
            self.assertEqual([p.name for p in first], ["a.java"])
            # ファイルからパターン除去 + 両方の cache をクリア
            f.write_text("(empty)\n")
            _filter_byte_cache_clear()
            _source_files_cache_clear()
            second = grep_filter_files(["FOO"], src, [".java"], use_mmap=True)
            self.assertEqual([p.name for p in second], [])
```

- [ ] **Step 2.2: テストを走らせて失敗を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_source_files.py::TestFilterByteCache -v`

Expected: 3 件全 FAIL（`_filter_byte_cache_clear` が未定義のため `ImportError`、または cache 効果が無いため挙動不一致）

- [ ] **Step 2.3: `_filter_byte_cache` と `_filter_byte_cache_clear` を追加**

`grep_helper/source_files.py` の `_source_files_cache` 直後（10〜46 行目の周辺）に追加:

```python
# モジュールグローバル: ファイル単位の byte hit 結果
# キー = (str(path), bytes_pattern)、値 = bool（hit / miss）
_filter_byte_cache: dict[tuple[str, bytes], bool] = {}


def _filter_byte_cache_clear() -> None:
    """テスト用: byte hit cache をクリア。"""
    _filter_byte_cache.clear()
```

- [ ] **Step 2.4: `_find_any_with_per_pattern_result` を実装**

`grep_helper/source_files.py` の `_read_based_find` 関数の直後に追加:

```python
def _find_any_with_per_pattern_result(
    path: Path,
    patterns: list[bytes],
    *,
    use_mmap: bool,
) -> dict[bytes, bool]:
    """1 回の I/O で各 pattern の hit/miss を判定して返す（mmap 優先）。

    Args:
        path:     対象ファイル
        patterns: バイトパターンのリスト（非空であること）
        use_mmap: mmap 経路を試すか

    Returns:
        各 pattern → True/False の dict。OSError 時はセーフ側で全て True。
    """
    result = {p: False for p in patterns}
    try:
        if path.stat().st_size == 0:
            return result
    except OSError:
        return {p: True for p in patterns}   # セーフ側
    if use_mmap:
        try:
            with open(path, "rb") as fh, \
                 mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for p in patterns:
                    if mm.find(p) != -1:
                        result[p] = True
            return result
        except (OSError, ValueError):
            pass   # → read-based に落とす
    # read-based: 1 MB チャンク + (max(len(p))-1) オーバーラップ
    overlap = max(len(p) for p in patterns) - 1 if patterns else 0
    if overlap < 0:
        overlap = 0
    tail = b""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_DEFAULT_READ_CHUNK)
            if not chunk:
                return result
            buf = tail + chunk
            for p in patterns:
                if not result[p] and buf.find(p) != -1:
                    result[p] = True
            if all(result.values()):
                return result
            tail = buf[-overlap:] if overlap > 0 else b""
```

- [ ] **Step 2.5: `_scan_file_for_patterns` を実装**

`_find_any_with_per_pattern_result` の直後に追加:

```python
def _scan_file_for_patterns(
    path: Path,
    patterns: list[bytes],
    *,
    use_mmap: bool = True,
) -> bool:
    """ファイルが patterns のいずれかを含むかを返す。

    各 (path, pattern) の組について cache する。cache 済みなら I/O ゼロ。
    未 cache の pattern だけまとめて 1 回の mmap / read で判定する。
    """
    key_path = str(path)
    unknown: list[bytes] = []
    for pat in patterns:
        cached = _filter_byte_cache.get((key_path, pat))
        if cached is True:
            return True       # 既知 hit があれば即真
        if cached is None:
            unknown.append(pat)
    if not unknown:
        return False          # 全 cache 済み・全 miss
    hits = _find_any_with_per_pattern_result(path, unknown, use_mmap=use_mmap)
    for pat, hit in hits.items():
        _filter_byte_cache[(key_path, pat)] = hit
    return any(hits.values())
```

- [ ] **Step 2.6: `grep_filter_files` を新ロジックに書き換え**

`grep_helper/source_files.py:65-110` の `grep_filter_files` 全体を以下に置換:

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
    _scan_file_for_patterns でパターン含有を判定する。
    エラー時は安全側（スキャン対象に含める）でフォールバック。
    file-level byte hit cache が効くため、同一プロセス内で同じ (path, pattern)
    の 2 回目以降の問い合わせは I/O を伴わない。
    """
    candidates = iter_source_files(src_dir, extensions)
    patterns = [n.encode("ascii") for n in names if n.isascii()]
    if not patterns:
        return candidates

    result: list[Path] = []
    for f in candidates:
        try:
            if _scan_file_for_patterns(f, patterns, use_mmap=use_mmap):
                result.append(f)
        except OSError:
            result.append(f)   # セーフ側

    if label:
        print(
            f"  [{label}] 事前フィルタ完了: {len(candidates)} → {len(result)} ファイルに絞り込み",
            file=sys.stderr, flush=True,
        )

    return result
```

旧 `grep_filter_files` 内の `mmap.mmap` 直叩きロジックは `_find_any_with_per_pattern_result` に移ったため削除する。

- [ ] **Step 2.7: 新規テストを走らせて通過を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_source_files.py -v`

Expected: TestReadBasedFind / TestGrepFilterFilesUseMmap / **TestFilterByteCache** 全 PASS

- [ ] **Step 2.8: 既存全テスト緑化を確認 (golden 差分ゼロを必須)**

Run: `cd /workspaces/grep_helper_superpowers && pytest -q`

Expected: 全 PASS。**特に `tests/golden/*` 比較系テストが PASS のまま**であること。FAIL が出たら byte hit cache のロジックバグなので Step 2.3〜2.6 を再確認（cache 再生成では誤魔化さない）。

- [ ] **Step 2.9: コミット**

```bash
cd /workspaces/grep_helper_superpowers
git add grep_helper/source_files.py tests/test_source_files.py
git commit -m "feat(source_files): add file-level byte hit cache to grep_filter_files

同一 (path, pattern) への 2 回目以降のバイトスキャンを I/O 無しで返す。
C / Pro*C 等が同じファイルセットを別 names でスキャンする場面で重複を削減する。
公開 API は不変。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: handler 並列化インフラ

`apply_indirect_tracking` に `handler_workers` / `on_handler_complete` 引数を追加し、`_run_one_handler` を別関数に切り出して ProcessPool で並列実行できるようにする。**関数デフォルトは `handler_workers=1` で直列実行**、後方互換を保つ。CLI の有効化は Task 4 で行う。

**Files:**
- Modify: `grep_helper/dispatcher.py`
- Create: `tests/test_dispatcher_parallel.py`

- [ ] **Step 3.1: 並列化テストを書く**

新規 `tests/test_dispatcher_parallel.py`:

```python
"""apply_indirect_tracking の handler 並列化テスト。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.dispatcher import apply_indirect_tracking
from grep_helper.model import GrepRecord, RefType


def _make_minimal_src(tmp: Path) -> Path:
    """全 12 言語の最小限のソースを置いた src_dir を返す。"""
    src = tmp / "src"
    src.mkdir()
    (src / "a.sql").write_text("SELECT * FROM t WHERE x = 'A';\n")
    return src


def _direct_records() -> list[GrepRecord]:
    return [
        GrepRecord(keyword="A", ref_type=RefType.DIRECT.value, usage_type="WHERE条件",
                   filepath="a.sql", lineno="1", code="SELECT * FROM t WHERE x = 'A';"),
    ]


class TestApplyIndirectTrackingHandlerWorkers(unittest.TestCase):
    """handler_workers の値に関わらず結果集合は同じ（並列順序非依存）。"""

    def test_handler_workers_1_と_2_で結果集合が同一(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_minimal_src(Path(tmp))
            direct = _direct_records()
            serial = apply_indirect_tracking(
                direct, src, encoding=None, workers=1, handler_workers=1,
            )
            parallel = apply_indirect_tracking(
                direct, src, encoding=None, workers=1, handler_workers=2,
            )
            # 並列順序に依存しないように tuple 化して集合比較
            def _key(r: GrepRecord) -> tuple:
                return (r.keyword, r.ref_type, r.usage_type, r.filepath,
                        r.lineno, r.code, r.src_var, r.src_file, r.src_lineno)
            self.assertEqual(
                sorted(map(_key, serial)),
                sorted(map(_key, parallel)),
            )


class TestApplyIndirectTrackingOnComplete(unittest.TestCase):
    """on_handler_complete は handler ごとに 1 回呼ばれる。"""

    def test_handler_workers_1_でon_handler_completeが全handler分呼ばれる(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_minimal_src(Path(tmp))
            calls: list[str] = []
            apply_indirect_tracking(
                _direct_records(), src, encoding=None,
                handler_workers=1,
                on_handler_complete=lambda hname, recs: calls.append(hname),
            )
            # batch_track_indirect を持つ handler は 12 言語ぶん（_none は除外）
            # 各 handler が一度だけ呼ばれる
            self.assertEqual(len(calls), len(set(calls)))
            self.assertGreaterEqual(len(calls), 10)  # 12 言語前後

    def test_handler_workers_2_でon_handler_completeが全handler分呼ばれる(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_minimal_src(Path(tmp))
            calls: list[str] = []
            apply_indirect_tracking(
                _direct_records(), src, encoding=None,
                handler_workers=2,
                on_handler_complete=lambda hname, recs: calls.append(hname),
            )
            self.assertEqual(len(calls), len(set(calls)))
            self.assertGreaterEqual(len(calls), 10)


class TestApplyIndirectTrackingExceptionIsolation(unittest.TestCase):
    """1 handler の例外は他 handler に伝播しない。直列・並列ともに。"""

    def _patch_one_handler_to_raise(self, monkey_target: str):
        """テスト helper: 指定 handler module の batch_track_indirect を例外で差し替える。"""
        import importlib
        mod = importlib.import_module(monkey_target)
        original = mod.batch_track_indirect
        def _boom(*args, **kwargs):
            raise RuntimeError("intentional test failure")
        mod.batch_track_indirect = _boom
        return mod, original

    def test_1handlerが例外を投げても他handlerのon_completeは呼ばれる_直列(self):
        # SQL handler を例外化 → 他 11 言語の on_complete が呼ばれることを確認
        target = "grep_helper.languages.sql"
        mod, original = self._patch_one_handler_to_raise(target)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = _make_minimal_src(Path(tmp))
                calls: list[str] = []
                apply_indirect_tracking(
                    _direct_records(), src, encoding=None,
                    handler_workers=1,
                    on_handler_complete=lambda hname, recs: calls.append(hname),
                )
                # 例外を出した sql は呼ばれない、他は呼ばれる
                self.assertNotIn(target, calls)
                self.assertGreaterEqual(len(calls), 9)
        finally:
            mod.batch_track_indirect = original


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3.2: テストを走らせて失敗を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_dispatcher_parallel.py -v`

Expected: 全 FAIL（`apply_indirect_tracking` に `handler_workers` / `on_handler_complete` 引数が無いため `TypeError`）

- [ ] **Step 3.3: `_run_one_handler` を実装**

`grep_helper/dispatcher.py` の `apply_indirect_tracking` の直前に追加:

```python
def _run_one_handler(
    handler_module_name: str,
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    workers: int,
    use_mmap: bool,
) -> list[GrepRecord]:
    """子プロセスで動的 import → batch_track_indirect 呼び出し。

    handler_module_name はトップレベル import 可能な完全修飾名（例:
    "grep_helper.languages.java"）。pickle 安全のためモジュールオブジェクト
    そのものは渡さない。handler 識別は呼び出し側の future_to_name で行うため、
    戻り値は records のみ。

    子プロセス内の例外（ImportError, AttributeError, batch_track_indirect 内の
    例外など）はそのまま親プロセスへ propagate する。親側の apply_indirect_tracking
    が fut.result() を try/except で囲んで 1 handler スキップを実現する。
    """
    import importlib
    mod = importlib.import_module(handler_module_name)
    fn = getattr(mod, "batch_track_indirect", None)
    if fn is None:
        return []
    return fn(direct_records, src_dir, encoding, workers=workers, use_mmap=use_mmap)
```

- [ ] **Step 3.4: `apply_indirect_tracking` を並列化対応に書き換え**

`grep_helper/dispatcher.py:64-80` の `apply_indirect_tracking` 全体を以下に置換:

```python
def apply_indirect_tracking(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
    use_mmap: bool = True,
    handler_workers: int = 1,
    on_handler_complete: "Callable[[str, list[GrepRecord]], None] | None" = None,
) -> list[GrepRecord]:
    """登録済み全ハンドラの batch_track_indirect を呼び出し、結果を結合する。

    handler_workers > 1 のとき ProcessPoolExecutor で handler 単位の並列実行。
    1 handler の例外（子プロセス内 ImportError 等を含む）は stderr 警告のみで
    他 handler に伝播しない。on_handler_complete は親プロセスのメインスレッドから
    as_completed の同期ループ内で呼ばれる（thread-safe 前提）。
    """
    handler_modules = [
        h.__name__ for h in _all_handlers()
        if getattr(h, "batch_track_indirect", None) is not None
    ]
    results: list[GrepRecord] = []

    def _safe_complete(hname: str, partial: list[GrepRecord]) -> None:
        results.extend(partial)
        if on_handler_complete is not None:
            on_handler_complete(hname, partial)

    def _run_serial() -> list[GrepRecord]:
        for hname in handler_modules:
            try:
                partial = _run_one_handler(
                    hname, direct_records, src_dir, encoding, workers, use_mmap,
                )
            except Exception as exc:
                print(
                    f"  警告: handler {hname} の間接追跡で例外 ({exc!r}) - "
                    f"この handler の indirect は欠落、他 handler は継続",
                    file=sys.stderr, flush=True,
                )
                continue
            _safe_complete(hname, partial)
        return results

    if handler_workers <= 1:
        return _run_serial()

    try:
        with ProcessPoolExecutor(max_workers=handler_workers) as ex:
            future_to_name = {
                ex.submit(_run_one_handler, hname, direct_records, src_dir,
                          encoding, workers, use_mmap): hname
                for hname in handler_modules
            }
            for fut in as_completed(future_to_name):
                hname = future_to_name[fut]
                try:
                    partial = fut.result()
                except Exception as exc:
                    print(
                        f"  警告: handler {hname} の間接追跡で例外 ({exc!r}) - "
                        f"この handler の indirect は欠落、他 handler は継続",
                        file=sys.stderr, flush=True,
                    )
                    continue
                _safe_complete(hname, partial)
        return results
    except OSError as exc:
        print(
            f"  警告: ProcessPool 起動に失敗 ({exc!r}) - handler_workers=1 で直列実行に切替",
            file=sys.stderr, flush=True,
        )
        return _run_serial()
```

`grep_helper/dispatcher.py` のファイル冒頭の import に以下を追加（既存 `from concurrent.futures import …` が無ければ）:

```python
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable
```

- [ ] **Step 3.5: 新規テストを走らせて通過を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_dispatcher_parallel.py -v`

Expected: 全 PASS。`ProcessPoolExecutor` がローカルで動くこと前提。

- [ ] **Step 3.6: 既存全テスト緑化を確認 (後方互換チェック)**

Run: `cd /workspaces/grep_helper_superpowers && pytest -q`

Expected: 全 PASS。特に `tests/test_all_analyzer.py` の old API compat shim（`_apply_indirect_tracking(...)` でキーワード引数 `handler_workers` を渡さない呼び出し）が通ること。**`tests/golden/*` 差分ゼロも必須**。

- [ ] **Step 3.7: コミット**

```bash
cd /workspaces/grep_helper_superpowers
git add grep_helper/dispatcher.py tests/test_dispatcher_parallel.py
git commit -m "feat(dispatcher): add handler-level parallel execution infra

apply_indirect_tracking に handler_workers / on_handler_complete を追加。
関数デフォルトは handler_workers=1 で直列実行、後方互換維持。
1 handler の例外（ImportError 含む）は他 handler に伝播しない。
ProcessPool 構築失敗時は直列フォールバック。

CLI 経由の並列化有効化は次タスク。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: dispatcher.main インクリメンタル化 + CLI

`dispatcher.main` の Phase 3 を廃止し、`on_handler_complete` コールバックで keyword 単位の TSV を逐次書き出す。CLI に `--handler-workers N`（既定 2）を追加。

**Files:**
- Modify: `grep_helper/dispatcher.py`
- Create: `tests/test_dispatcher_incremental.py`

- [ ] **Step 4.1: インクリメンタル書き出しテストを書く**

新規 `tests/test_dispatcher_incremental.py`:

```python
"""dispatcher.main のインクリメンタル TSV 書き出しテスト。

WHAT 観察: 各 keyword の TSV がディスク上に出現するタイミングを
on_handler_complete を fake で駆動して確定的に検証する（OS スケジューラ依存を排除）。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.model import GrepRecord, ProcessStats, RefType


class TestDispatcherIncrementalWrite(unittest.TestCase):
    """全 handler 完了時点で各 keyword の TSV が書き出される。"""

    def _setup_dirs(self, tmp: Path) -> tuple[Path, Path, Path]:
        src = tmp / "src"; src.mkdir()
        inp = tmp / "input"; inp.mkdir()
        out = tmp / "output"; out.mkdir()
        (src / "a.sql").write_text("SELECT 'A' FROM t;\n")
        (inp / "A.grep").write_text("a.sql:1:SELECT 'A' FROM t;\n")
        (inp / "B.grep").write_text("a.sql:1:SELECT 'A' FROM t;\n")
        return src, inp, out

    def test_全handler完了後に全keywordのTSVが出揃う(self):
        from grep_helper import dispatcher
        with tempfile.TemporaryDirectory() as tmp:
            src, inp, out = self._setup_dirs(Path(tmp))
            argv = [
                "analyze_all.py",
                "--source-dir", str(src),
                "--input-dir", str(inp),
                "--output-dir", str(out),
            ]
            with patch.object(sys, "argv", argv):
                rc = dispatcher.main()
            self.assertEqual(rc, 0)
            self.assertTrue((out / "A.tsv").exists())
            self.assertTrue((out / "B.tsv").exists())

    def test_handler_namesが空でも直接分類のみで全keywordのTSVが出揃う(self):
        """全 handler が batch_track_indirect を持たない縁ケース。
        _all_handlers() を fake で空にして dispatcher.main を呼ぶ。
        """
        from grep_helper import dispatcher
        with tempfile.TemporaryDirectory() as tmp:
            src, inp, out = self._setup_dirs(Path(tmp))
            argv = [
                "analyze_all.py",
                "--source-dir", str(src),
                "--input-dir", str(inp),
                "--output-dir", str(out),
            ]
            # _all_handlers() を空 generator で fake
            with patch.object(dispatcher, "_all_handlers", lambda: iter([])), \
                 patch.object(sys, "argv", argv):
                rc = dispatcher.main()
            self.assertEqual(rc, 0)
            # indirect なし、direct のみで TSV が出る
            self.assertTrue((out / "A.tsv").exists())
            self.assertTrue((out / "B.tsv").exists())

    def test_同じ入力で3回実行しても全TSVがバイト一致する(self):
        """決定的ソートにより、handler 並列順序が違っても出力は同じ。"""
        from grep_helper import dispatcher
        with tempfile.TemporaryDirectory() as tmp:
            src, inp, out1 = self._setup_dirs(Path(tmp))
            out2 = Path(tmp) / "output2"; out2.mkdir()
            out3 = Path(tmp) / "output3"; out3.mkdir()
            for out in (out1, out2, out3):
                argv = [
                    "analyze_all.py",
                    "--source-dir", str(src),
                    "--input-dir", str(inp),
                    "--output-dir", str(out),
                    "--handler-workers", "2",
                ]
                with patch.object(sys, "argv", argv):
                    rc = dispatcher.main()
                self.assertEqual(rc, 0)
            self.assertEqual(
                (out1 / "A.tsv").read_bytes(),
                (out2 / "A.tsv").read_bytes(),
            )
            self.assertEqual(
                (out2 / "A.tsv").read_bytes(),
                (out3 / "A.tsv").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4.2: テストを走らせて失敗を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_dispatcher_incremental.py -v`

Expected: 3 件中 `test_同じ入力で3回実行しても全TSVがバイト一致する` は CLI フラグ `--handler-workers` が未定義のため argparse エラーで FAIL。残り 2 件は dispatcher.main が現状でも動くため PASS 又はインクリメンタル挙動非要件で PASS。

- [ ] **Step 4.3: `build_parser` に `--handler-workers` を追加**

`grep_helper/dispatcher.py:83-99` の `build_parser` 関数の `parser.add_argument("--no-mmap", ...)` の**直後**に追加:

```python
    parser.add_argument(
        "--handler-workers", type=int, default=2,
        help="ハンドラ間並列度（デフォルト: 2、I/O が許せば 3〜4 まで）",
    )
```

- [ ] **Step 4.4: `dispatcher.main` をインクリメンタル書き出しに改造**

`grep_helper/dispatcher.py:119-192` の `main` 関数全体を以下に置換:

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

    # フェーズ 2 + インクリメンタル書き出し
    handler_names = [
        h.__name__ for h in _all_handlers()
        if getattr(h, "batch_track_indirect", None) is not None
    ]
    indirect_by_keyword: dict[str, list[GrepRecord]] = {
        kw: [] for kw in direct_by_keyword
    }
    pending: dict[str, set[str]] = {
        kw: set(handler_names) for kw in direct_by_keyword
    }
    written: set[str] = set()

    def _write_kw_tsv(kw: str) -> None:
        from grep_helper.tsv_output import write_tsv  # noqa: PLC0415
        output_path = output_dir / f"{kw}.tsv"
        all_records = list(direct_by_keyword[kw]) + indirect_by_keyword.get(kw, [])
        write_tsv(all_records, output_path)
        written.add(kw)
        direct_count = len(direct_by_keyword[kw])
        indirect_count = len(indirect_by_keyword.get(kw, []))
        print(
            f"  {kw}.grep → {output_path} "
            f"(直接: {direct_count} 件, 間接: {indirect_count} 件)",
            flush=True,
        )

    def on_complete(hname: str, partial: list[GrepRecord]) -> None:
        for rec in partial:
            if rec.keyword in indirect_by_keyword:
                indirect_by_keyword[rec.keyword].append(rec)
        for kw in list(pending.keys()):
            pending[kw].discard(hname)
            if not pending[kw] and kw not in written:
                _write_kw_tsv(kw)

    if direct_by_keyword:
        if not handler_names:
            # 縁ケース: 全 handler が batch_track_indirect を持たない
            # → indirect なしで直接 TSV を書き出す
            for kw in direct_by_keyword:
                _write_kw_tsv(kw)
        else:
            all_direct: list[GrepRecord] = []
            for records in direct_by_keyword.values():
                all_direct.extend(records)
            try:
                apply_indirect_tracking(
                    all_direct, source_dir, args.encoding,
                    workers=args.workers,
                    use_mmap=_resolve_use_mmap(args.no_mmap),
                    handler_workers=args.handler_workers,
                    on_handler_complete=on_complete,
                )
            except Exception as exc:
                print(f"予期しないエラー（間接追跡フェーズ）: {exc}", file=sys.stderr)
                return 2

            # ドレイン: 1 handler 全失敗等で pending が残った keyword をフォールバック書き出し
            for kw in direct_by_keyword:
                if kw not in written:
                    _write_kw_tsv(kw)

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")
    return 0
```

- [ ] **Step 4.5: 新規テストを走らせて通過を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest tests/test_dispatcher_incremental.py -v`

Expected: 3 件全 PASS

- [ ] **Step 4.6: 既存全テスト緑化を確認**

Run: `cd /workspaces/grep_helper_superpowers && pytest -q`

Expected: 全 PASS。**`tests/golden/*` 差分ゼロが必須**。差分が出たらインクリメンタル化のロジックバグ。

- [ ] **Step 4.7: コミット**

```bash
cd /workspaces/grep_helper_superpowers
git add grep_helper/dispatcher.py tests/test_dispatcher_incremental.py
git commit -m "feat(dispatcher): incremental TSV write + --handler-workers CLI

dispatcher.main の Phase 3 を廃止し、on_handler_complete で keyword 単位の
TSV を逐次書き出す。CLI --handler-workers (default 2) を追加。
TTFB 大幅短縮 + handler 並列化による壁時計時間短縮。
handler_names 空の縁ケースもフォールバック分岐で対応。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: V-1 検証 (KPI before/after)

実装の最終クロージング。仕様 §V-1 の手順を実機で実行し、結果を spec の closing note に追記する。**コード変更なし**。

**Files:**
- Modify: `docs/superpowers/specs/2026-05-11-perf-handler-parallel-design.md`（closing note を追記）

- [ ] **Step 5.1: KPI 回帰チェック（pipeline 経由）**

```bash
cd /workspaces/grep_helper_superpowers
# main ブランチで before を取得
git stash  # 本ブランチの変更を退避
git checkout main
python scripts/measure_kpi.py --lang all --quiet > /tmp/kpi_before.txt 2>&1
git checkout -  # 本ブランチへ戻る
git stash pop  # 退避を戻す

# 本ブランチで after を取得
python scripts/measure_kpi.py --lang all --quiet > /tmp/kpi_after.txt 2>&1

# 比較
diff /tmp/kpi_before.txt /tmp/kpi_after.txt
```

Expected: 網羅率・分類精度の数値が完全一致。差分が出たら回帰なので Task 1〜4 を再点検。

- [ ] **Step 5.2: 性能計測（dispatcher 経由、代表ソースが利用可能な場合）**

代表ソース `<repr>` がない場合は `tests/golden/java/src` 等を流用して実行時間を比較。

```bash
cd /workspaces/grep_helper_superpowers
# main ブランチ
git stash; git checkout main
time python analyze_all.py --source-dir tests/golden/java/src --input-dir tests/golden/java/inputs \
    --output-dir /tmp/out_before --workers 2 2>&1 | tail -20 | tee /tmp/run_before.txt
git checkout -; git stash pop

# 本ブランチ
time python analyze_all.py --source-dir tests/golden/java/src --input-dir tests/golden/java/inputs \
    --output-dir /tmp/out_after --workers 2 --handler-workers 2 2>&1 | tail -20 | tee /tmp/run_after.txt
```

Expected: `time` の real 時間が短縮。最初の TSV が出るまでの時間（stdout の最初の `→` 行までの経過時間）が大幅短縮。

- [ ] **Step 5.3: TSV 行セット一致を確認**

```bash
cd /workspaces/grep_helper_superpowers
for f in /tmp/out_after/*.tsv; do
    fn=$(basename "$f")
    diff -q "/tmp/out_before/$fn" "$f" || true
done
```

Expected: 全 TSV がバイト一致（決定的ソートにより）。差分が出たら回帰。

- [ ] **Step 5.4: メモリ使用量を確認**

```bash
cd /workspaces/grep_helper_superpowers
/usr/bin/time -v python analyze_all.py \
    --source-dir tests/golden/java/src --input-dir tests/golden/java/inputs \
    --output-dir /tmp/out_mem --workers 2 --handler-workers 2 \
    2>&1 | grep "Maximum resident set size"
```

Expected: ピーク RSS が 1 GB 未満（spec のメモリ予算内）。worker あたり 200 MB を恒常的に超える場合は spec §やらないこと「byte hit cache の LRU 化」を後続検討項目として残す。

- [ ] **Step 5.5: spec に closing note を追記してコミット**

`docs/superpowers/specs/2026-05-11-perf-handler-parallel-design.md` の末尾に追記:

```markdown

---

## 実装完了ノート（YYYY-MM-DD）

- **KPI 回帰**: 網羅率・分類精度は before/after で完全一致を確認
- **性能改善**:
  - wall clock: `tests/golden/java/src` で N 秒 → M 秒（N/M = X% 短縮）
  - TTFB（最初の TSV まで）: N 秒 → M 秒（N/M = X% 短縮）
- **メモリ**: ピーク RSS N MB（予算 1 GB 以内）
- **TSV 行セット一致**: 全ファイル バイト一致

Solaris 実機での計測は `scripts/smoke_solaris.md` の手順で別途実施する。
```

実測値を埋めてからコミット:

```bash
cd /workspaces/grep_helper_superpowers
git add docs/superpowers/specs/2026-05-11-perf-handler-parallel-design.md
git commit -m "docs(specs/2026-05-11): add closing note with KPI before/after results

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review チェックリスト（実装者が完走後に確認）

- [ ] spec §要件1 (性能改善): Task 3 + Task 4 で handler 並列化 + インクリメンタル書き出しを実装したか
- [ ] spec §要件2 (出力一致): Task 1 で 5 タプル sort key 化したか、Task 2〜4 で `tests/golden/` 差分ゼロを保ったか
- [ ] spec §要件3 (後方互換): `apply_indirect_tracking` の関数デフォルト `handler_workers=1` で既存呼び出しが直列のままか、`batch_track_indirect` のシグネチャが無変更か、`pipeline.run_full_pipeline` が無変更か
- [ ] spec §要件4 (CLI): `--handler-workers N` (default 2) を追加し、`--workers` / `--no-mmap` が無変更か
- [ ] spec §やらないこと: AST cache 永続化 / Phase 1 並列化 / 子プロセス cache 共有 / handler 公開 API 破壊変更 / 中断再開機能 / multi_filter_files / ProcessStats 集約 / byte cache LRU 化 を**やっていない**か
- [ ] spec §エラー処理表: 1 handler 例外スキップ / ProcessPool 構築失敗時の直列フォールバック / `_scan_file_for_patterns` の OSError セーフ側 / `write_tsv` 失敗は致命的 が実装されているか
- [ ] spec §テスト戦略: WHAT 検証 / 日本語メソッド名 / 古典学派 / handler 並列テストの集合等価比較 / インクリメンタル書き出しの fake コールバック観察 が守られているか
