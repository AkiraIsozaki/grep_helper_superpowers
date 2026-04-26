# grep-helper 全体リファクタ実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ルート 14 ファイル + `aho_corasick.py` のフラット構造（合計 5,384 行）を `grep_helper/` パッケージ + `grep_helper/languages/` サブパッケージに再編成し、CLI/TSV/性能/依存の不変契約を保ったまま重複バッチトラッカー 5 セットを各言語に畳み込む。

**Architecture:** 内部実装は再構成、ルートの `analyze*.py` 14 個は 5〜10 行の shim として残して CLI 互換を維持。各言語モジュールは `EXTENSIONS` / `classify_usage(code, *, ctx)` / 任意の `batch_track_indirect` の 3 つの「モジュール = ハンドラ」契約を満たす（duck typing、Protocol 強制継承なし）。dispatcher は拡張子→ハンドラ表で振り分け、間接追跡は登録済み全ハンドラの `batch_track_indirect` を順次呼び出すだけの薄いループに縮める。

**Tech Stack:** Python 3.10+ / `javalang` / `chardet` / `pyahocorasick`（Pure Python AC フォールバックあり）/ `pytest` / ProcessPoolExecutor 並列。

**Spec:** `docs/superpowers/specs/2026-04-26-refactor-design.md`

---

## 全体ルール

1. **CLI 不変**: `python analyze.py` および `python analyze_<lang>.py` 全 13 個のコマンド名・引数を変えない。
2. **TSV 不変**: 列順・列名・UTF-8 BOM・タブ区切り・ソート順（keyword → filepath → lineno）を維持。
3. **性能不変**: grep ストリーミング / LRU 256MB / `--workers` 並列 / AC↔regex 閾値 100。
4. **各 Phase 完了時の検証**:
   - `python -m pytest tests/ -v` 全緑
   - `flake8` 通過（`.flake8` の `max-line-length=120`）
   - 該当 Phase（1/5/6）では §2.3 のキャッシュ同一性 `is` チェックを実行
5. **コミット規律**: 各 Phase で最低 1 コミット。各言語の移植も基本 1 言語 1 コミット。
6. **新規テストは追加しない**（spec §6.4）。`dispatcher.py` のロジックは既存 `test_all_analyzer.py` でカバー済み。
7. **shim 層では旧シンボル alias re-export のために `# type: ignore` が残ってよい**。`grep_helper/` 配下では 0 件を目標にする。

---

## Phase 0: パッケージ骨格の作成

**Files:**
- Create: `grep_helper/__init__.py`
- Create: `grep_helper/languages/__init__.py`
- Create: `grep_helper/cli.py`
- Create: `grep_helper/pipeline.py`

### Task 0.1: `grep_helper/__init__.py` を作成

- [ ] **Step 1: ファイルを新規作成**

`grep_helper/__init__.py` を以下の内容で作成:

```python
"""grep-helper パッケージ。

各言語アナライザの共通インフラとディスパッチャーを提供する。

ハンドラ契約（module = handler、duck typing）:
- 必須: ``EXTENSIONS: tuple[str, ...]``
- 必須: ``classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str``
- 任意: ``batch_track_indirect(direct_records, src_dir, encoding, *, workers=1) -> list[GrepRecord]``
- 任意: ``SHEBANGS: tuple[str, ...]``  (拡張子のないシバン判定用)
"""
```

- [ ] **Step 2: コミット**

```bash
git add grep_helper/__init__.py
git commit -m "refactor(phase0): add grep_helper package skeleton"
```

### Task 0.2: `grep_helper/languages/__init__.py` を空で作成

- [ ] **Step 1: ファイルを新規作成**

`grep_helper/languages/__init__.py` を以下の内容で作成:

```python
"""言語ハンドラレジストリ。

各言語モジュールの ``EXTENSIONS`` / ``SHEBANGS`` を集約し、
``EXT_TO_HANDLER`` / ``SHEBANG_TO_HANDLER`` マップと
``detect_handler(filepath, src_dir) -> ModuleType`` を提供する（Phase 7 で実装）。
"""
```

- [ ] **Step 2: コミット**

```bash
git add grep_helper/languages/__init__.py
git commit -m "refactor(phase0): add grep_helper.languages skeleton"
```

### Task 0.3: `grep_helper/cli.py` の stub を作成

- [ ] **Step 1: ファイルを新規作成**

`grep_helper/cli.py` を以下の内容で作成:

```python
"""共通 CLI 雛形（Phase 2 で本実装）。"""
from __future__ import annotations

import argparse
from types import ModuleType


def build_parser(description: str) -> argparse.ArgumentParser:  # pragma: no cover - phase2 で実装
    raise NotImplementedError


def run(handler: ModuleType, *, description: str | None = None) -> int:  # pragma: no cover - phase2 で実装
    raise NotImplementedError
```

- [ ] **Step 2: コミット（pipeline.py と一緒に）**

(次のタスクで一緒にコミット)

### Task 0.4: `grep_helper/pipeline.py` の stub を作成

- [ ] **Step 1: ファイルを新規作成**

`grep_helper/pipeline.py` を以下の内容で作成:

```python
"""共通パイプライン（Phase 2 で本実装）。"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType


def process_grep_file(  # pragma: no cover - phase2 で実装
    grep_path: Path,
    src_dir: Path,
    handler: ModuleType,
    *,
    encoding: str | None = None,
    workers: int = 1,
):
    raise NotImplementedError
```

- [ ] **Step 2: パッケージが import 可能か確認**

```bash
python -c "import grep_helper, grep_helper.languages, grep_helper.cli, grep_helper.pipeline; print('OK')"
```

期待出力: `OK`

- [ ] **Step 3: 既存テストが緑のままか確認**

```bash
python -m pytest tests/ -v
```

期待: 全テスト pass。

- [ ] **Step 4: コミット**

```bash
git add grep_helper/cli.py grep_helper/pipeline.py
git commit -m "refactor(phase0): add cli/pipeline stubs"
```

---

## Phase 1: インフラ層を 8 ファイルに分解移植

`analyze_common.py`（352 行）と `aho_corasick.py`（65 行）を、`grep_helper/` 直下の 8 ファイルに分解する。**キャッシュ dict のオブジェクト同一性** が既存テストで assertion されているため、dict は新パッケージで定義し、`analyze_common.py` から `from grep_helper.X import _Y as _Y` の形で参照のみ再 export する。

### キャッシュ同一性保持表（Phase 1 で扱うもの）

| キャッシュ | 新定義場所 | 旧 shim 参照元 |
|---|---|---|
| `_file_lines_cache` (OrderedDict) | `grep_helper/file_cache.py` | `analyze_common._file_lines_cache` |
| `_source_files_cache` (dict) | `grep_helper/source_files.py` | `analyze_common._source_files_cache` |
| `_resolve_file_cache` (dict) | `grep_helper/source_files.py` | `analyze_common._resolve_file_cache` |

### Task 1.1: `grep_helper/model.py` を作成

**Files:**
- Create: `grep_helper/model.py`

- [ ] **Step 1: 新規ファイル作成**

`grep_helper/model.py` の内容:

```python
"""共通データモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import NamedTuple


class RefType(Enum):
    DIRECT   = "直接"
    INDIRECT = "間接"
    GETTER   = "間接（getter経由）"
    SETTER   = "間接（setter経由）"


class GrepRecord(NamedTuple):
    keyword:    str
    ref_type:   str
    usage_type: str
    filepath:   str
    lineno:     str
    code:       str
    src_var:    str = ""
    src_file:   str = ""
    src_lineno: str = ""


@dataclass
class ProcessStats:
    total_lines:     int = 0
    valid_lines:     int = 0
    skipped_lines:   int = 0
    fallback_files:  set[str] = field(default_factory=set)
    encoding_errors: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ClassifyContext:
    """言語ハンドラの classify_usage が AST 解析等で使う共通コンテキスト。

    シンプル言語（python/perl/ts 等）はこの引数を受け取って無視する
    （`# noqa: ARG001` で明示）。Java など AST を見る言語は ``filepath`` ``lineno``
    ``source_dir`` を使う。dispatcher は常に渡す。
    """
    filepath: str
    lineno: int
    source_dir: Path
    stats: ProcessStats
    encoding_override: str | None = None
```

### Task 1.2: `grep_helper/encoding.py` を作成

**Files:**
- Create: `grep_helper/encoding.py`

- [ ] **Step 1: 新規ファイル作成**

`grep_helper/encoding.py` の内容（`analyze_common.py:65-82` の `detect_encoding` を移植）:

```python
"""文字コード検出。"""
from __future__ import annotations

from pathlib import Path

try:
    import chardet as _chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False


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

### Task 1.3: `grep_helper/grep_input.py` を作成

**Files:**
- Create: `grep_helper/grep_input.py`

- [ ] **Step 1: 新規ファイル作成**

`grep_helper/grep_input.py` の内容（`analyze_common.py:54-108` の `iter_grep_lines` `parse_grep_line` `_BINARY_PATTERN` を移植）:

```python
"""grep 結果ファイルの読み込みとパース。"""
from __future__ import annotations

import re
from pathlib import Path

_BINARY_PATTERN    = re.compile(r'^Binary file .+ matches$')
_GREP_LINE_PATTERN = re.compile(r':(\d+):')


def iter_grep_lines(path: Path, encoding: str):
    """grep 結果ファイルを 1 行ずつジェネレータで返す。

    巨大ファイル対策。改行は除去済み。
    """
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        for line in f:
            yield line.rstrip("\n").rstrip("\r")


def parse_grep_line(line: str) -> dict | None:
    """grep結果の1行をパースする。不正行はNoneを返す。"""
    stripped = line.rstrip('\n\r')
    if not stripped.strip():
        return None
    if _BINARY_PATTERN.match(stripped):
        return None
    parts = _GREP_LINE_PATTERN.split(stripped, maxsplit=1)
    if len(parts) != 3:
        return None
    filepath, lineno, code = parts
    if not filepath or not lineno:
        return None
    return {"filepath": filepath, "lineno": lineno, "code": code.strip()}
```

### Task 1.4: `grep_helper/tsv_output.py` を作成

**Files:**
- Create: `grep_helper/tsv_output.py`

- [ ] **Step 1: 新規ファイル作成**

`grep_helper/tsv_output.py` の内容（`analyze_common.py:111-169` の `write_tsv` + 外部ソート + `_TSV_HEADERS` `_EXTERNAL_SORT_THRESHOLD` を移植）:

```python
"""TSV 出力（小規模はメモリソート、大規模はチャンク外部ソート）。"""
from __future__ import annotations

import csv
import heapq
import tempfile
from pathlib import Path

from grep_helper.model import GrepRecord

_TSV_HEADERS = [
    "文言", "参照種別", "使用タイプ", "ファイルパス", "行番号", "コード行",
    "参照元変数名", "参照元ファイル", "参照元行番号",
]
_EXTERNAL_SORT_THRESHOLD = 1_000_000


def write_tsv(records: list[GrepRecord], output_path: Path) -> None:
    """GrepRecordのリストをUTF-8 BOM付きTSVに出力する（ソート済み）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _sort_key(r: GrepRecord) -> tuple:
        lineno_int = int(r.lineno) if r.lineno.isdigit() else 0
        return (r.keyword, r.filepath, lineno_int)

    def _row_sort_key(row: list[str]) -> tuple:
        lineno_int = int(row[4]) if row[4].isdigit() else 0
        return (row[0], row[3], lineno_int)

    if len(records) < _EXTERNAL_SORT_THRESHOLD:
        records.sort(key=_sort_key)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(_TSV_HEADERS)
            for r in records:
                writer.writerow([
                    r.keyword, r.ref_type, r.usage_type, r.filepath,
                    r.lineno, r.code, r.src_var, r.src_file, r.src_lineno,
                ])
        return

    _CHUNK_SIZE = 500_000
    tmp_paths: list[Path] = []
    tmp_dir = output_path.parent
    try:
        for i in range(0, len(records), _CHUNK_SIZE):
            chunk = records[i:i + _CHUNK_SIZE]
            chunk.sort(key=_sort_key)
            fd, tmp_str = tempfile.mkstemp(
                suffix=".tmp", prefix=f".{output_path.stem}_chunk_", dir=tmp_dir,
            )
            tmp_path = Path(tmp_str)
            tmp_paths.append(tmp_path)
            with open(fd, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, delimiter="\t")
                for r in chunk:
                    w.writerow([
                        r.keyword, r.ref_type, r.usage_type, r.filepath,
                        r.lineno, r.code, r.src_var, r.src_file, r.src_lineno,
                    ])
            del chunk
        del records
        handles = [open(p, "r", encoding="utf-8", newline="") for p in tmp_paths]
        readers = [csv.reader(h, delimiter="\t") for h in handles]
        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(_TSV_HEADERS)
                for row in heapq.merge(*readers, key=_row_sort_key):
                    writer.writerow(row)
        finally:
            for h in handles:
                h.close()
    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)
```

### Task 1.5: `grep_helper/source_files.py` を作成（キャッシュ同一性保持）

**Files:**
- Create: `grep_helper/source_files.py`

- [ ] **Step 1: 新規ファイル作成**

`grep_helper/source_files.py` の内容（`analyze_common.py:172-231, 283-306` の `iter_source_files` `grep_filter_files` `resolve_file_cached` + 関連キャッシュ + `_*_clear` を移植）:

```python
"""ソースファイルの探索とパス解決（mmap 事前フィルタ含む）。"""
from __future__ import annotations

import mmap
import sys
from pathlib import Path

# キャッシュ dict は新パッケージで「定義」する。
# analyze_common 側からは `from grep_helper.source_files import _source_files_cache as _source_files_cache`
# の形で参照のみ再 export することで、object identity が保たれる。
_source_files_cache: dict[tuple[str, tuple[str, ...]], list[Path]] = {}
_resolve_file_cache: dict[tuple[str, str], Path | None] = {}


def _source_files_cache_clear() -> None:
    """テスト用: source_files キャッシュをクリア。"""
    _source_files_cache.clear()


def _resolve_file_cache_clear() -> None:
    """テスト用: resolve_file キャッシュをクリア。"""
    _resolve_file_cache.clear()


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


def grep_filter_files(
    names: list[str],
    src_dir: Path,
    extensions: list[str],
    label: str = "",
) -> list[Path]:
    """mmap によるバイト列検索でスキャン対象ファイルを絞り込む。"""
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

### Task 1.6: `grep_helper/file_cache.py` を作成（LRU キャッシュ、同一性保持）

**Files:**
- Create: `grep_helper/file_cache.py`

- [ ] **Step 1: 新規ファイル作成**

`grep_helper/file_cache.py` の内容（`analyze_common.py:234-280` の LRU キャッシュを移植）:

```python
"""ファイル行リスト LRU キャッシュ（既定 256MB）。"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from grep_helper.model import ProcessStats

_file_lines_cache: OrderedDict[str, list[str]] = OrderedDict()
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
    return sum(len(s) for s in lines) + 64 * len(lines)


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
        _, old_lines = _file_lines_cache.popitem(last=False)
        _file_lines_cache_bytes -= _estimate_lines_bytes(old_lines)
    return lines
```

### Task 1.7: `grep_helper/_aho_corasick.py` と `grep_helper/scanner.py` を作成

**Files:**
- Create: `grep_helper/_aho_corasick.py`（ルートの `aho_corasick.py` の中身をそのまま移動）
- Create: `grep_helper/scanner.py`

- [ ] **Step 1: ルート `aho_corasick.py` の内容を確認**

```bash
cat /workspaces/grep_helper_superpowers/aho_corasick.py
```

- [ ] **Step 2: `grep_helper/_aho_corasick.py` を新規作成**

ルート `aho_corasick.py` の中身（65 行）をそのままコピー。

- [ ] **Step 3: `grep_helper/scanner.py` を新規作成**

`analyze_common.py:309-352` の `_BatchScanner` `build_batch_scanner` を移植。`pyahocorasick` 不在時のフォールバック先を `from grep_helper._aho_corasick import AhoCorasick` に変更:

```python
"""バッチスキャナ（Aho-Corasick / regex 自動切替）。"""
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
    閾値未満は combined regex。
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
            from grep_helper._aho_corasick import AhoCorasick
            return _BatchScanner(patterns, "ahocorasick", AhoCorasick(patterns))
    combined = re.compile(r"\b(" + "|".join(re.escape(p) for p in patterns) + r")\b")
    return _BatchScanner(patterns, "regex", combined)
```

### Task 1.8: `analyze_common.py` を shim 化（キャッシュ同一性 re-export）

**Files:**
- Modify: `analyze_common.py`（全置換）
- Modify: `aho_corasick.py`（全置換）

- [ ] **Step 1: `analyze_common.py` を shim に書き換え**

ファイル全体を以下に置換:

```python
"""DEPRECATED: ``grep_helper`` への移行用 shim。Phase 7 で削除予定。"""
from __future__ import annotations

# モデル・列挙型・データクラス
from grep_helper.model import GrepRecord, ProcessStats, RefType, ClassifyContext  # noqa: F401

# エンコーディング検出
from grep_helper.encoding import detect_encoding  # noqa: F401

# grep 入力
from grep_helper.grep_input import (  # noqa: F401
    iter_grep_lines, parse_grep_line, _BINARY_PATTERN, _GREP_LINE_PATTERN,
)

# TSV 出力
from grep_helper.tsv_output import write_tsv, _TSV_HEADERS, _EXTERNAL_SORT_THRESHOLD  # noqa: F401

# ソースファイル探索（dict 同一性保持のため `as` で参照のまま再 export）
from grep_helper.source_files import (  # noqa: F401
    iter_source_files, grep_filter_files, resolve_file_cached,
    _source_files_cache_clear, _resolve_file_cache_clear,
    _source_files_cache as _source_files_cache,
    _resolve_file_cache as _resolve_file_cache,
)

# ファイル行 LRU キャッシュ（dict 同一性保持）
from grep_helper.file_cache import (  # noqa: F401
    cached_file_lines, set_file_lines_cache_limit, _file_lines_cache_clear,
    _file_lines_cache as _file_lines_cache,
)

# スキャナ
from grep_helper.scanner import build_batch_scanner, _BatchScanner  # noqa: F401
```

- [ ] **Step 2: ルート `aho_corasick.py` を shim 化**

ファイル全体を以下に置換:

```python
"""DEPRECATED: ``grep_helper._aho_corasick`` への shim。Phase 7 で削除予定。"""
from grep_helper._aho_corasick import *  # noqa: F401, F403
from grep_helper._aho_corasick import AhoCorasick  # noqa: F401
```

### Task 1.9: キャッシュ同一性 `is` チェックスクリプトを作成・実行

**Files:**
- Create: `scripts/check_cache_identity_phase1.py`（リポジトリ root の scripts/ に配置）

- [ ] **Step 1: scripts/ ディレクトリと検証スクリプトを作成**

```bash
mkdir -p /workspaces/grep_helper_superpowers/scripts
```

`scripts/check_cache_identity_phase1.py` の内容:

```python
"""Phase 1 完了時のキャッシュ同一性チェック。

shim と新パッケージの両方から取得した dict が同一オブジェクトであることを確認する。
失敗した場合は AssertionError で終了する。
"""
from __future__ import annotations

import analyze_common
import grep_helper.file_cache
import grep_helper.source_files


def main() -> None:
    assert analyze_common._file_lines_cache is grep_helper.file_cache._file_lines_cache, \
        "_file_lines_cache identity broken"
    assert analyze_common._source_files_cache is grep_helper.source_files._source_files_cache, \
        "_source_files_cache identity broken"
    assert analyze_common._resolve_file_cache is grep_helper.source_files._resolve_file_cache, \
        "_resolve_file_cache identity broken"
    print("Phase 1 cache identity: OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 実行**

```bash
python /workspaces/grep_helper_superpowers/scripts/check_cache_identity_phase1.py
```

期待出力: `Phase 1 cache identity: OK`

- [ ] **Step 3: 既存テスト緑確認**

```bash
python -m pytest tests/ -v
```

期待: 全テスト pass。`test_common.py` の `assertIn(str(p), _file_lines_cache)` が壊れていないことを特に確認。

- [ ] **Step 4: flake8 確認**

```bash
flake8 grep_helper/ analyze_common.py aho_corasick.py
```

期待: 警告なし。

- [ ] **Step 5: コミット**

```bash
git add grep_helper/model.py grep_helper/encoding.py grep_helper/grep_input.py \
        grep_helper/tsv_output.py grep_helper/source_files.py grep_helper/file_cache.py \
        grep_helper/scanner.py grep_helper/_aho_corasick.py \
        analyze_common.py aho_corasick.py scripts/check_cache_identity_phase1.py
git commit -m "refactor(phase1): split analyze_common.py into grep_helper/* (cache identity preserved via shim)"
```

---

## Phase 2: pipeline と CLI 雛形を実装

シンプル 6 言語のために、共通 `process_grep_file` と `build_parser` / `run(handler)` を pipeline / cli に集約する。

### Task 2.1: `grep_helper/cli.py` 本実装

**Files:**
- Modify: `grep_helper/cli.py`

- [ ] **Step 1: ファイル全体を以下に置換**

```python
"""共通 CLI 雛形。

各言語の analyze_<lang>.py shim から
``raise SystemExit(run(handler))`` の形で呼ばれる。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import ModuleType

from grep_helper.model import ProcessStats
from grep_helper.pipeline import process_grep_file


def build_parser(description: str) -> argparse.ArgumentParser:
    """共通 argparse 雛形（--source-dir / --input-dir / --output-dir / --encoding / --workers）。"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source-dir", required=True, help="ソースのルートディレクトリ")
    parser.add_argument("--input-dir",  default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--encoding",   default=None, help="文字コード強制指定（省略時は自動検出）")
    parser.add_argument(
        "--workers", type=int, default=1,
        help=f"並列ワーカー数（デフォルト: 1, 推奨: {os.cpu_count() or 4}）",
    )
    return parser


def run(handler: ModuleType, *, description: str | None = None) -> int:
    """ハンドラを使って input/*.grep を処理し、output/*.tsv を書き出す。

    終了コード: 0=成功, 1=引数エラー, 2=実行時エラー。
    """
    desc = description or f"{getattr(handler, '__name__', 'analyzer')} grep結果 自動分類ツール"
    parser = build_parser(desc)
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    input_dir  = Path(args.input_dir)
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

    from grep_helper.tsv_output import write_tsv

    stats = ProcessStats()
    processed_files: list[str] = []
    try:
        for grep_path in grep_files:
            keyword = grep_path.stem
            direct_records = process_grep_file(
                grep_path, source_dir, handler,
                keyword=keyword, encoding=args.encoding, stats=stats,
            )
            output_path = output_dir / f"{keyword}.tsv"
            write_tsv(list(direct_records), output_path)
            processed_files.append(grep_path.name)
            print(f"  {grep_path.name} → {output_path} (直接: {len(direct_records)} 件)")
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        return 2

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")
    return 0
```

### Task 2.2: `grep_helper/pipeline.py` 本実装

**Files:**
- Modify: `grep_helper/pipeline.py`

- [ ] **Step 1: ファイル全体を以下に置換**

```python
"""共通パイプライン: grep行 → handler.classify_usage → GrepRecord 変換。"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

from grep_helper.encoding import detect_encoding
from grep_helper.grep_input import iter_grep_lines, parse_grep_line
from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType


def process_grep_file(
    grep_path: Path,
    src_dir: Path,
    handler: ModuleType,
    *,
    keyword: str | None = None,
    encoding: str | None = None,
    stats: ProcessStats | None = None,
) -> list[GrepRecord]:
    """grep ファイルを 1 本処理し、handler.classify_usage で分類した直接参照レコードを返す。

    handler は ``classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str``
    を持つモジュール（duck typing）。
    """
    if keyword is None:
        keyword = grep_path.stem
    if stats is None:
        stats = ProcessStats()
    enc = detect_encoding(grep_path, encoding)

    records: list[GrepRecord] = []
    for line in iter_grep_lines(grep_path, enc):
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        try:
            lineno_int = int(parsed["lineno"])
        except ValueError:
            lineno_int = 0
        ctx = ClassifyContext(
            filepath=parsed["filepath"],
            lineno=lineno_int,
            source_dir=src_dir,
            stats=stats,
            encoding_override=encoding,
        )
        usage = handler.classify_usage(parsed["code"], ctx=ctx)
        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=usage,
            filepath=parsed["filepath"],
            lineno=parsed["lineno"],
            code=parsed["code"],
        ))
        stats.valid_lines += 1
    return records
```

### Task 2.3: 既存テスト緑確認とコミット

- [ ] **Step 1: pytest 実行**

```bash
python -m pytest tests/ -v
```

期待: 全テスト pass（pipeline/cli はまだ呼び出されていないため緑のまま）。

- [ ] **Step 2: flake8 確認**

```bash
flake8 grep_helper/
```

- [ ] **Step 3: コミット**

```bash
git add grep_helper/cli.py grep_helper/pipeline.py
git commit -m "refactor(phase2): implement grep_helper.cli and grep_helper.pipeline"
```

---

## Phase 3: シンプル 6 言語を移植（python / perl / ts / plsql / sh / sql）

各言語ごとに以下のテンプレートを実行する。**各言語 1 コミット**。

### 共通テンプレート（言語名を `<LANG>` とする）

**手順サマリ:**
1. `grep_helper/languages/<LANG>.py` を新規作成（`EXTENSIONS` + `classify_usage` を移植）
2. ルート `analyze_<LANG>.py` を 5〜10 行の shim に置換（旧シンボル alias re-export を含む）
3. `pytest tests/test_<LANG>_analyzer.py -v` で緑確認
4. コミット

### Task 3.1: `python` を移植

**Files:**
- Create: `grep_helper/languages/python.py`
- Modify: `analyze_python.py`（shim 化）

- [ ] **Step 1: `grep_helper/languages/python.py` を新規作成**

```python
"""Python 言語ハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".py",)

_PYTHON_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^\s*\w+\s*='),                          "変数代入"),
    (re.compile(r'\bif\b|\belif\b|==|!=|\bin\b'),         "条件判定"),
    (re.compile(r'\breturn\b'),                            "return文"),
    (re.compile(r'@\w+'),                                  "デコレータ"),
    (re.compile(r'\w+\s*\('),                              "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Python コード行の使用タイプを分類する（6 種）。``ctx`` は受け取って無視する。"""
    stripped = code.strip()
    for pattern, usage_type in _PYTHON_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
```

- [ ] **Step 2: `analyze_python.py` を shim に置換**

ファイル全体を以下に置換:

```python
"""DEPRECATED shim: ``grep_helper.languages.python`` への移行用。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import python as _handler
from grep_helper.languages.python import classify_usage as _classify_usage_new

# 旧 API 互換 (Phase 7 で削除予定)
classify_usage_python = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Python grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 3: テスト緑確認**

```bash
python -m pytest tests/test_python_analyzer.py -v
```

期待: 全テスト pass。

- [ ] **Step 4: CLI 動作確認**

```bash
python /workspaces/grep_helper_superpowers/analyze_python.py --help
```

期待: argparse の --help 出力が表示される。

- [ ] **Step 5: コミット**

```bash
git add grep_helper/languages/python.py analyze_python.py
git commit -m "refactor(phase3): port python analyzer to grep_helper.languages.python"
```

### Task 3.2: `perl` を移植

**Files:**
- Create: `grep_helper/languages/perl.py`
- Modify: `analyze_perl.py`

- [ ] **Step 1: 元ファイルから `classify_usage_perl` のパターンを確認**

```bash
grep -n "_PERL_USAGE_PATTERNS\|classify_usage_perl" /workspaces/grep_helper_superpowers/analyze_perl.py
```

- [ ] **Step 2: `grep_helper/languages/perl.py` を新規作成**

```python
"""Perl 言語ハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".pl", ".pm")
SHEBANGS: tuple[str, ...] = ("perl",)

# analyze_perl.py の _PERL_USAGE_PATTERNS をそのまま移植
# (行番号は元ファイルを参照)
_PERL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ↓ 元の analyze_perl.py:15-22 をそのまま貼る
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    stripped = code.strip()
    for pattern, usage_type in _PERL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
```

実装時は `analyze_perl.py` 内の `_PERL_USAGE_PATTERNS` 定義をそのまま貼り付ける。

- [ ] **Step 3: `analyze_perl.py` を shim に置換**

```python
"""DEPRECATED shim: ``grep_helper.languages.perl`` への移行用。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import perl as _handler
from grep_helper.languages.perl import classify_usage as _classify_usage_new

classify_usage_perl = _classify_usage_new  # noqa: E305 (Phase 7 で削除)


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Perl grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 4: テスト緑確認**

```bash
python -m pytest tests/test_perl_analyzer.py -v
```

- [ ] **Step 5: コミット**

```bash
git add grep_helper/languages/perl.py analyze_perl.py
git commit -m "refactor(phase3): port perl analyzer to grep_helper.languages.perl"
```

### Task 3.3: `ts` を移植

**Files:**
- Create: `grep_helper/languages/ts.py`
- Modify: `analyze_ts.py`

- [ ] **Step 1: `grep_helper/languages/ts.py` を新規作成**

```python
"""TypeScript / JavaScript 言語ハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx")

# analyze_ts.py の _TS_USAGE_PATTERNS をそのまま移植
_TS_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ↓ 元の analyze_ts.py 該当箇所をそのまま貼る
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    stripped = code.strip()
    for pattern, usage_type in _TS_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
```

- [ ] **Step 2: `analyze_ts.py` を shim 化**

```python
"""DEPRECATED shim: ``grep_helper.languages.ts``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import ts as _handler
from grep_helper.languages.ts import classify_usage as _classify_usage_new

classify_usage_ts = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="TypeScript/JavaScript grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 3: テスト緑確認**

```bash
python -m pytest tests/test_ts_analyzer.py -v
```

- [ ] **Step 4: コミット**

```bash
git add grep_helper/languages/ts.py analyze_ts.py
git commit -m "refactor(phase3): port ts analyzer to grep_helper.languages.ts"
```

### Task 3.4: `plsql` を移植

**Files:**
- Create: `grep_helper/languages/plsql.py`
- Modify: `analyze_plsql.py`

- [ ] **Step 1: `grep_helper/languages/plsql.py` を新規作成**

`analyze_plsql.py:15` の `_PLSQL_EXTENSIONS = (".pls", ".pck", ".prc", ".pkb", ".pks", ".fnc", ".trg")` を `EXTENSIONS` にリネームし、`classify_usage_plsql` を `classify_usage` に。`ctx` 引数は `# noqa: ARG001` で受け流す。

```python
"""PL/SQL 言語ハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".pls", ".pck", ".prc", ".pkb", ".pks", ".fnc", ".trg")

_PLSQL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ↓ 元の analyze_plsql.py の該当パターンをそのまま貼る
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    stripped = code.strip()
    for pattern, usage_type in _PLSQL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"
```

- [ ] **Step 2: `analyze_plsql.py` を shim 化**

```python
"""DEPRECATED shim: ``grep_helper.languages.plsql``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import plsql as _handler
from grep_helper.languages.plsql import classify_usage as _classify_usage_new

classify_usage_plsql = _classify_usage_new  # noqa: E305
_PLSQL_EXTENSIONS = _handler.EXTENSIONS  # 旧名互換


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="PL/SQL grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 3: テスト緑確認 + コミット**

```bash
python -m pytest tests/test_plsql_analyzer.py -v
git add grep_helper/languages/plsql.py analyze_plsql.py
git commit -m "refactor(phase3): port plsql analyzer to grep_helper.languages.plsql"
```

### Task 3.5: `sh` を移植

**Files:**
- Create: `grep_helper/languages/sh.py`
- Modify: `analyze_sh.py`

- [ ] **Step 1: `grep_helper/languages/sh.py` を新規作成**

`analyze_sh.py` から `classify_usage_sh` `extract_sh_variable_name` `track_sh_variable` などをそのまま移植。`EXTENSIONS = (".sh", ".bash")`、`SHEBANGS = ("sh", "bash", "csh", "tcsh", "ksh", "ksh93")`。

```python
"""Shell スクリプト言語ハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".sh", ".bash")
SHEBANGS: tuple[str, ...] = ("sh", "bash", "csh", "tcsh", "ksh", "ksh93")

# 元の analyze_sh.py から _SH_USAGE_PATTERNS / classify_usage_sh / extract_sh_variable_name /
# track_sh_variable をそのまま移植


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    # 元の classify_usage_sh の中身をそのまま
    ...


# 補助関数はそのまま公開（テスト互換のため）
def extract_sh_variable_name(code: str) -> str | None:
    ...


def track_sh_variable(...):  # 元と同じシグネチャ
    ...
```

- [ ] **Step 2: `analyze_sh.py` を shim 化**

```python
"""DEPRECATED shim: ``grep_helper.languages.sh``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import sh as _handler
from grep_helper.languages.sh import (
    classify_usage as _classify_usage_new,
    extract_sh_variable_name,
    track_sh_variable,
)

classify_usage_sh = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="シェルスクリプト grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 3: テスト緑確認 + コミット**

```bash
python -m pytest tests/test_sh_analyzer.py -v
git add grep_helper/languages/sh.py analyze_sh.py
git commit -m "refactor(phase3): port sh analyzer to grep_helper.languages.sh"
```

### Task 3.6: `sql` を移植

**Files:**
- Create: `grep_helper/languages/sql.py`
- Modify: `analyze_sql.py`

- [ ] **Step 1: `grep_helper/languages/sql.py` を新規作成**

`analyze_sql.py` から `classify_usage_sql` `extract_sql_variable_name` `track_sql_variable` を移植。`EXTENSIONS = (".sql",)`。

```python
"""SQL 言語ハンドラ。"""
from __future__ import annotations

import re

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = (".sql",)

# 元の analyze_sql.py から該当ロジックを全て移植


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    ...


def extract_sql_variable_name(code: str) -> str | None:
    ...


def track_sql_variable(...):
    ...
```

- [ ] **Step 2: `analyze_sql.py` を shim 化**

```python
"""DEPRECATED shim: ``grep_helper.languages.sql``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import sql as _handler
from grep_helper.languages.sql import (
    classify_usage as _classify_usage_new,
    extract_sql_variable_name,
    track_sql_variable,
)

classify_usage_sql = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="SQL grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 3: テスト緑確認 + flake8 + コミット**

```bash
python -m pytest tests/test_sql_analyzer.py tests/ -v
flake8 grep_helper/
git add grep_helper/languages/sql.py analyze_sql.py
git commit -m "refactor(phase3): port sql analyzer to grep_helper.languages.sql"
```

---

## Phase 4: 中規模 4 言語を移植（kotlin / dotnet / groovy / c）

各言語ごとに `classify_usage` の移植 + `batch_track_indirect` の実装を行う。`analyze_all.py` 内の `_scan_files_for_<lang>_*` / `_batch_track_<lang>_*` を **該当言語ファイルに吸い上げて統合**する。

### Task 4.1: `kotlin` を移植

**Files:**
- Create: `grep_helper/languages/kotlin.py`
- Modify: `analyze_kotlin.py`
- Modify: `analyze_all.py`（`_scan_files_for_kotlin_const` / `_batch_track_kotlin_const` を薄いラッパに）

- [ ] **Step 1: `grep_helper/languages/kotlin.py` を新規作成**

`analyze_kotlin.py` の `classify_usage_kotlin` `_CONST_VAL_PAT` `extract_const_name` `track_const` と、`analyze_all.py:225-336` の `_scan_files_for_kotlin_const` / `_batch_track_kotlin_const` を統合する。

```python
"""Kotlin 言語ハンドラ。"""
from __future__ import annotations

import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.source_files import grep_filter_files

EXTENSIONS: tuple[str, ...] = (".kt", ".kts")

# === 分類 ===
_KOTLIN_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ↓ 元の analyze_kotlin.py:14-23 をそのまま貼る
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    stripped = code.strip()
    for pattern, usage_type in _KOTLIN_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


# === 補助 ===
_CONST_VAL_PAT = re.compile(r'\bconst\s+val\s+(\w+)\s*=')


def extract_const_name(code: str) -> str | None:
    m = _CONST_VAL_PAT.search(code.strip())
    return m.group(1) if m else None


# === 直接参照 1 件用の追跡 (旧 analyze_kotlin.track_const) ===
def track_const(...):
    """元の analyze_kotlin.py:42-80 の track_const をそのまま移植。"""
    ...


# === バッチ間接追跡（dispatcher から呼ばれる） ===
def _scan_files_for_kotlin_const(...):
    """元の analyze_all.py:225-260 をそのまま移植。"""
    ...


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Kotlin の間接参照（const val 経由）をバッチ追跡する。

    direct_records は dispatcher が集めた全言語分。Kotlin ファイル
    （拡張子 .kt / .kts）に該当するものだけ内部でフィルタする。
    """
    from grep_helper.languages import detect_handler  # 循環回避のため遅延 import

    self_records = [
        r for r in direct_records
        if detect_handler(r.filepath, src_dir).__name__ == __name__
    ]
    if not self_records:
        return []
    # ↓ 元の analyze_all.py:262-336 の _batch_track_kotlin_const のロジックを移植。
    # ProcessPoolExecutor を使う場合、_scan_files_for_kotlin_const はモジュール
    # トップレベル関数のままにすること（pickle 可能性のため）。
    ...
```

実装上の注意:
- `detect_handler` は Phase 7 で本実装する。Phase 4 時点では `analyze_all.py` の `detect_language` を流用するか、簡易版（拡張子のみ判定）を `grep_helper/languages/__init__.py` に先に実装しておく。
- **簡易版を Phase 4 冒頭で先に追加する**（後述 Step 0 を参照）。

- [ ] **Step 0（事前作業 - Phase 4 全体で 1 度のみ）: `detect_handler` の簡易版実装**

`grep_helper/languages/__init__.py` に拡張子のみで判定する簡易 `detect_handler` を実装する（シバン判定は Phase 7 で完成版を入れる）。

`grep_helper/languages/__init__.py` 全体を以下に置換:

```python
"""言語ハンドラレジストリ。

Phase 4 時点では拡張子マップ + ``detect_handler`` の簡易版のみ提供する。
シバン判定は Phase 7 で完成させる。
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

# Phase 4 で利用可能になっているハンドラのみ import
# (その他の言語が追加されるたびに、この import 行を増やしていく)
from grep_helper.languages import _none  # 言語不明用

EXT_TO_HANDLER: dict[str, ModuleType] = {}
SHEBANG_TO_HANDLER: dict[str, ModuleType] = {}


def _register(handler: ModuleType) -> None:
    for ext in getattr(handler, "EXTENSIONS", ()):
        EXT_TO_HANDLER[ext] = handler
    for sb in getattr(handler, "SHEBANGS", ()):
        SHEBANG_TO_HANDLER[sb] = handler


def detect_handler(filepath: str, src_dir: Path) -> ModuleType:
    ext = Path(filepath).suffix.lower()
    if ext:
        return EXT_TO_HANDLER.get(ext, _none)
    # 拡張子なしのシバン判定は Phase 7 で実装
    return _none


# Phase 4 完了時の登録ハンドラ
# (各 Phase で言語を移植するたびに、ここに追加していく)
from grep_helper.languages import python as _python
from grep_helper.languages import perl as _perl
from grep_helper.languages import ts as _ts
from grep_helper.languages import plsql as _plsql
from grep_helper.languages import sh as _sh
from grep_helper.languages import sql as _sql

for _h in (_python, _perl, _ts, _plsql, _sh, _sql, _none):
    _register(_h)
```

- [ ] **Step 0b: `grep_helper/languages/_none.py` を新規作成**

```python
"""言語不明ファイル用の no-op ハンドラ。"""
from __future__ import annotations

from grep_helper.model import ClassifyContext

EXTENSIONS: tuple[str, ...] = ()


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    return "その他"
```

- [ ] **Step 1（Kotlin 本体）: `grep_helper/languages/kotlin.py` を実装**

（前述の Step 1 の通り）

- [ ] **Step 2: `grep_helper/languages/__init__.py` の登録ループに kotlin を追加**

```python
from grep_helper.languages import kotlin as _kotlin
# 登録ループに _kotlin を追加
for _h in (_python, _perl, _ts, _plsql, _sh, _sql, _kotlin, _none):
    _register(_h)
```

- [ ] **Step 3: `analyze_kotlin.py` を shim 化**

```python
"""DEPRECATED shim: ``grep_helper.languages.kotlin``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import kotlin as _handler
from grep_helper.languages.kotlin import (
    classify_usage as _classify_usage_new,
    extract_const_name,
    track_const,
)

classify_usage_kotlin = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Kotlin grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 4: `analyze_all.py` 内の `_scan_files_for_kotlin_const` / `_batch_track_kotlin_const` を薄いラッパ化**

`analyze_all.py:225-336` を以下に置換:

```python
# Phase 4: kotlin 移植により、ここはハンドラ呼び出しに委譲。
# Phase 7 のクリーンアップで dispatcher.apply_indirect_tracking に統合される。
from grep_helper.languages.kotlin import batch_track_indirect as _batch_track_kotlin_const_new


def _batch_track_kotlin_const(direct_records, src_dir, encoding, *, workers=1):
    """旧 API 互換ラッパ。Phase 7 で削除予定。"""
    return _batch_track_kotlin_const_new(direct_records, src_dir, encoding, workers=workers)
```

`_apply_indirect_tracking` 内の `_batch_track_kotlin_const(...)` 呼び出しは変更不要（同名で動く）。

- [ ] **Step 5: テスト緑確認**

```bash
python -m pytest tests/test_kotlin_analyzer.py tests/test_all_analyzer.py -v
```

期待: 全テスト pass。`test_all_analyzer.py` の Kotlin 関連ケースも緑のまま。

- [ ] **Step 6: コミット**

```bash
git add grep_helper/languages/__init__.py grep_helper/languages/_none.py \
        grep_helper/languages/kotlin.py analyze_kotlin.py analyze_all.py
git commit -m "refactor(phase4): port kotlin + detect_handler skeleton + _none handler"
```

### Task 4.2: `dotnet` を移植

**Files:**
- Create: `grep_helper/languages/dotnet.py`
- Modify: `analyze_dotnet.py`
- Modify: `analyze_all.py`

- [ ] **Step 1: `grep_helper/languages/dotnet.py` を新規作成**

`analyze_dotnet.py` の `_DOTNET_USAGE_PATTERNS` `classify_usage_dotnet` `_DOTNET_EXTENSIONS` `_CS_CONST_PATS` `_VB_CONST_PAT` `extract_const_name_dotnet` `track_const_dotnet` と、`analyze_all.py:340-454` の `_scan_files_for_dotnet_const` / `_batch_track_dotnet_const` を統合。

`EXTENSIONS = (".cs", ".vb")`、`classify_usage(code, *, ctx=None)`、`batch_track_indirect(direct_records, src_dir, encoding, *, workers=1)`。

スケルトン例:

```python
"""C# / VB.NET 言語ハンドラ。"""
from __future__ import annotations

import re
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.source_files import grep_filter_files

EXTENSIONS: tuple[str, ...] = (".cs", ".vb")

# 以下、analyze_dotnet.py + analyze_all.py の dotnet 関連を統合
# - _DOTNET_USAGE_PATTERNS
# - classify_usage(code, *, ctx=None)  ← classify_usage_dotnet をリネーム
# - extract_const_name_dotnet
# - track_const_dotnet
# - _scan_files_for_dotnet_const  (analyze_all.py:340-376 から)
# - batch_track_indirect  (analyze_all.py:377-454 の _batch_track_dotnet_const をリネーム + 自言語フィルタ)
```

- [ ] **Step 2: `grep_helper/languages/__init__.py` 登録ループに `dotnet` を追加**

- [ ] **Step 3: `analyze_dotnet.py` を shim 化**

```python
"""DEPRECATED shim: ``grep_helper.languages.dotnet``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import dotnet as _handler
from grep_helper.languages.dotnet import (
    classify_usage as _classify_usage_new,
    extract_const_name_dotnet,
    track_const_dotnet,
)

classify_usage_dotnet = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description=".NET (C#/VB) grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 4: `analyze_all.py` 内の `_scan_files_for_dotnet_const` / `_batch_track_dotnet_const` を薄いラッパ化**

```python
from grep_helper.languages.dotnet import batch_track_indirect as _batch_track_dotnet_const_new


def _batch_track_dotnet_const(direct_records, src_dir, encoding, *, workers=1):
    return _batch_track_dotnet_const_new(direct_records, src_dir, encoding, workers=workers)
```

- [ ] **Step 5: テスト緑確認 + コミット**

```bash
python -m pytest tests/test_dotnet_analyzer.py tests/test_all_analyzer.py -v
git add grep_helper/languages/__init__.py grep_helper/languages/dotnet.py \
        analyze_dotnet.py analyze_all.py
git commit -m "refactor(phase4): port dotnet to grep_helper.languages.dotnet"
```

### Task 4.3: `groovy` を移植

**Files:**
- Create: `grep_helper/languages/groovy.py`
- Modify: `analyze_groovy.py`
- Modify: `analyze_all.py`

- [ ] **Step 1: `grep_helper/languages/groovy.py` を新規作成**

`analyze_groovy.py`（359 行）の以下を全て移植:
- `_GROOVY_USAGE_PATTERNS` / `classify_usage_groovy` → `classify_usage`
- `_GROOVY_EXTENSIONS = (".groovy", ".gvy")` → `EXTENSIONS`
- `_STATIC_FINAL_PAT` `_CLASS_FIELD_PAT` `_GETTER_RETURN_PAT` `_SETTER_ASSIGN_PAT` `_METHOD_DEF_PAT`
- `extract_static_final_name` / `is_class_level_field` / `find_getter_names_groovy` / `find_setter_names_groovy`
- `track_static_final_groovy` / `track_field_groovy` / `_batch_track_getter_setter_groovy` / `_resolve_groovy_file`

加えて `analyze_all.py:455-569` の以下を統合:
- `_scan_files_for_groovy_static_final` / `_batch_track_groovy_static_final`

`batch_track_indirect` は両方を統合（static_final + getter/setter）。

- [ ] **Step 2: `grep_helper/languages/__init__.py` に groovy を追加**

- [ ] **Step 3: `analyze_groovy.py` を shim 化**

旧名 alias の対象（テスト互換のため）:
- `classify_usage_groovy`
- `extract_static_final_name`
- `is_class_level_field`
- `find_getter_names_groovy` / `find_setter_names_groovy`
- `track_static_final_groovy` / `track_field_groovy`

```python
"""DEPRECATED shim: ``grep_helper.languages.groovy``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import groovy as _handler
from grep_helper.languages.groovy import (
    classify_usage as _classify_usage_new,
    extract_static_final_name, is_class_level_field,
    find_getter_names_groovy, find_setter_names_groovy,
    track_static_final_groovy, track_field_groovy,
)

classify_usage_groovy = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Groovy grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 4: `analyze_all.py` の `_*_groovy_static_final` を薄ラッパ化**

```python
from grep_helper.languages.groovy import batch_track_indirect as _batch_track_groovy_static_final_new


def _batch_track_groovy_static_final(direct_records, src_dir, encoding, *, workers=1):
    return _batch_track_groovy_static_final_new(direct_records, src_dir, encoding, workers=workers)
```

- [ ] **Step 5: テスト緑確認 + コミット**

```bash
python -m pytest tests/test_groovy_analyzer.py tests/test_all_analyzer.py -v
git add grep_helper/languages/__init__.py grep_helper/languages/groovy.py \
        analyze_groovy.py analyze_all.py
git commit -m "refactor(phase4): port groovy to grep_helper.languages.groovy"
```

### Task 4.4: `c` を移植（`_define_map_cache` 同一性保持あり）

**Files:**
- Create: `grep_helper/languages/c.py`
- Modify: `analyze_c.py`
- Modify: `analyze_all.py`

**キャッシュ同一性保持:** `_define_map_cache` は `analyze_c._define_map_cache` を `tests/test_c_analyzer.py:214-215` が直接 `clear()` する → 新パッケージで定義し、shim は参照のまま再 export する。

- [ ] **Step 1: `grep_helper/languages/c.py` を新規作成**

`analyze_c.py`（316 行）の以下を全て移植:
- `_C_USAGE_PATTERNS` / `classify_usage_c` → `classify_usage`
- `_define_map_cache: dict = {}` → そのまま
- `_C_TYPES_PAT` / `extract_variable_name_c`
- `_DEFINE_PAT` / `_DEFINE_ALIAS_PAT`
- `extract_define_name` / `_build_reverse_define_map`
- `_build_define_map` / `_get_reverse_define_map`
- `_collect_define_aliases`
- `track_define` / `track_variable`

加えて `analyze_all.py:570-699` の `_scan_files_for_define_c_all` / `_batch_track_define_c_all` を統合。

`EXTENSIONS = (".c", ".h")`。

`batch_track_indirect` の冒頭で `_build_define_map` を**メインプロセスで事前構築**し、ProcessPoolExecutor のワーカーには結果 dict を引数で渡すパターンを維持する（spec §2.3 末尾）。

- [ ] **Step 2: `analyze_c.py` を shim 化（`_define_map_cache` 同一性保持）**

```python
"""DEPRECATED shim: ``grep_helper.languages.c``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import c as _handler
from grep_helper.languages.c import (
    classify_usage as _classify_usage_new,
    _define_map_cache as _define_map_cache,  # dict 同一性保持
    _build_define_map, _get_reverse_define_map,
    _collect_define_aliases,
    extract_variable_name_c, extract_define_name,
    track_define, track_variable,
)

classify_usage_c = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="C grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 3: `analyze_all.py` の `_*_define_c_all` を薄ラッパ化**

```python
from grep_helper.languages.c import batch_track_indirect as _batch_track_define_c_all_new


def _batch_track_define_c_all(direct_records, src_dir, encoding, *, workers=1):
    return _batch_track_define_c_all_new(direct_records, src_dir, encoding, workers=workers)
```

- [ ] **Step 4: `grep_helper/languages/__init__.py` 登録ループに `c` を追加**

```python
from grep_helper.languages import c as _c
# 登録ループに _c を追加
for _h in (_python, _perl, _ts, _plsql, _sh, _sql, _kotlin, _dotnet, _groovy, _c, _none):
    _register(_h)
```

- [ ] **Step 5: `_define_map_cache` 同一性チェックスクリプトを作成・実行**

`scripts/check_cache_identity_phase4.py` を新規作成:

```python
"""Phase 4 完了時のキャッシュ同一性チェック（C の _define_map_cache）。"""
from __future__ import annotations

import analyze_c
import grep_helper.languages.c


def main() -> None:
    assert analyze_c._define_map_cache is grep_helper.languages.c._define_map_cache, \
        "_define_map_cache (c) identity broken"
    print("Phase 4 cache identity: OK")


if __name__ == "__main__":
    main()
```

```bash
python /workspaces/grep_helper_superpowers/scripts/check_cache_identity_phase4.py
```

期待: `Phase 4 cache identity: OK`

- [ ] **Step 6: テスト緑確認 + flake8 + コミット**

```bash
python -m pytest tests/test_c_analyzer.py tests/test_all_analyzer.py -v
flake8 grep_helper/
git add grep_helper/languages/__init__.py grep_helper/languages/c.py \
        analyze_c.py analyze_all.py scripts/check_cache_identity_phase4.py
git commit -m "refactor(phase4): port c to grep_helper.languages.c (preserve _define_map_cache identity)"
```

---

## Phase 5: Pro*C を移植（3 ファイル分解）

`analyze_proc.py`（337 行）を `proc.py + proc_define_map.py + proc_track.py` に分解する。`_define_map_cache` の同一性も保持。

### Task 5.1: `grep_helper/languages/proc_define_map.py` を作成

**Files:**
- Create: `grep_helper/languages/proc_define_map.py`

- [ ] **Step 1: 新規ファイル作成**

`analyze_proc.py:32, 72-104` の以下を移植:
- `_define_map_cache` (dict)
- `_DEFINE_PAT` `_DEFINE_ALIAS_PAT`
- `_build_define_map`
- `_get_reverse_define_map`

```python
"""Pro*C: #define リバースマップ構築・キャッシュ層。"""
from __future__ import annotations

import re
from pathlib import Path

# キャッシュ同一性保持（analyze_proc._define_map_cache から as 経由で参照される）
_define_map_cache: dict[tuple[str, str], tuple[dict[str, str], dict[str, list[str]]]] = {}

_DEFINE_PAT = re.compile(r'#\s*define\s+(\w+)\s+')
_DEFINE_ALIAS_PAT = re.compile(r'#\s*define\s+(\w+)\s+(\w+)\s*$')


def _build_define_map(...):
    """元の analyze_proc.py:76-99 をそのまま移植。"""
    ...


def _get_reverse_define_map(src_dir: Path, encoding_override: str | None) -> dict[str, list[str]]:
    """元の analyze_proc.py:100-104 をそのまま移植。"""
    ...
```

### Task 5.2: `grep_helper/languages/proc_track.py` を作成

**Files:**
- Create: `grep_helper/languages/proc_track.py`

- [ ] **Step 1: 新規ファイル作成**

`analyze_proc.py:60-218` の以下を移植:
- `_C_TYPES_PAT` / `extract_variable_name_proc`
- `extract_define_name`
- `extract_host_var_name`
- `track_define` / `track_variable`

`_get_reverse_define_map` の参照は `from grep_helper.languages.proc_define_map import _get_reverse_define_map` で行う。

### Task 5.3: `grep_helper/languages/proc.py` を作成（公開 API）

**Files:**
- Create: `grep_helper/languages/proc.py`

- [ ] **Step 1: 新規ファイル作成**

```python
"""Pro*C 言語ハンドラ（公開 API）。"""
from __future__ import annotations

import re
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord
from grep_helper.scanner import build_batch_scanner
from grep_helper.source_files import grep_filter_files

from grep_helper.languages.proc_define_map import (
    _define_map_cache, _build_define_map, _get_reverse_define_map,
    _DEFINE_PAT, _DEFINE_ALIAS_PAT,
)
from grep_helper.languages.proc_track import (
    extract_variable_name_proc, extract_define_name, extract_host_var_name,
    track_define, track_variable, _C_TYPES_PAT,
)

EXTENSIONS: tuple[str, ...] = (".pc", ".pcc")

_PROC_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ↓ analyze_proc.py:19-30 をそのまま貼る
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:
    """Pro*C コード行の使用タイプを分類する。

    EXEC SQL ブロック内とそれ以外で挙動が変わるため、ctx.filepath を見ることが
    あるが、現状の analyze_proc.classify_usage_proc はファイルパスを使わないので
    ctx は無視できる（_classify_for_filepath は filepath を使うが、これは内部関数）。
    """
    # 元の classify_usage_proc の中身をそのまま移植
    ...


def _scan_files_for_define_proc_all(...):
    """元の analyze_all.py:700-738 をそのまま移植。"""
    ...


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Pro*C の間接参照（#define 経由）をバッチ追跡する。

    direct_records から `.pc` / `.pcc` のものだけ内部でフィルタする。
    _build_define_map はメインプロセスで事前構築してワーカーに渡す。
    """
    from grep_helper.languages import detect_handler

    self_records = [
        r for r in direct_records
        if detect_handler(r.filepath, src_dir).__name__ == __name__
    ]
    if not self_records:
        return []
    # 元の analyze_all.py:739-833 _batch_track_define_proc_all を移植
    # _build_define_map をメインプロセスで先にビルドして dict を引数渡し
    ...
```

### Task 5.4: shim 化と `analyze_all.py` の薄ラッパ化

**Files:**
- Modify: `analyze_proc.py`（shim 化、`_define_map_cache` 同一性保持）
- Modify: `analyze_all.py`（`_*_define_proc_all` を薄ラッパ化）

- [ ] **Step 1: `analyze_proc.py` を shim 化**

```python
"""DEPRECATED shim: ``grep_helper.languages.proc``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import proc as _handler
from grep_helper.languages.proc import (
    classify_usage as _classify_usage_new,
    _scan_files_for_define_proc_all,
)
from grep_helper.languages.proc_define_map import (
    _define_map_cache as _define_map_cache,  # dict 同一性保持
    _build_define_map, _get_reverse_define_map,
)
from grep_helper.languages.proc_track import (
    extract_variable_name_proc, extract_define_name, extract_host_var_name,
    track_define, track_variable,
)

classify_usage_proc = _classify_usage_new  # noqa: E305


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Pro*C grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 2: `analyze_all.py` の `_*_define_proc_all` を薄ラッパ化**

```python
from grep_helper.languages.proc import batch_track_indirect as _batch_track_define_proc_all_new


def _batch_track_define_proc_all(direct_records, src_dir, encoding, *, workers=1):
    return _batch_track_define_proc_all_new(direct_records, src_dir, encoding, workers=workers)
```

- [ ] **Step 3: `grep_helper/languages/__init__.py` 登録ループに `proc` 追加**

### Task 5.5: キャッシュ同一性チェック + テスト緑確認

- [ ] **Step 1: 同一性チェックスクリプト**

`scripts/check_cache_identity_phase5.py` を新規作成:

```python
"""Phase 5 完了時のキャッシュ同一性チェック。"""
from __future__ import annotations

import analyze_proc
import grep_helper.languages.proc_define_map


def main() -> None:
    assert analyze_proc._define_map_cache is grep_helper.languages.proc_define_map._define_map_cache, \
        "_define_map_cache (proc) identity broken"
    print("Phase 5 cache identity: OK")


if __name__ == "__main__":
    main()
```

```bash
python /workspaces/grep_helper_superpowers/scripts/check_cache_identity_phase5.py
```

期待: `Phase 5 cache identity: OK`

- [ ] **Step 2: テスト緑確認 + flake8 + コミット**

```bash
python -m pytest tests/test_analyze_proc.py tests/test_all_analyzer.py -v
flake8 grep_helper/
git add grep_helper/languages/proc.py grep_helper/languages/proc_define_map.py \
        grep_helper/languages/proc_track.py grep_helper/languages/__init__.py \
        analyze_proc.py analyze_all.py scripts/check_cache_identity_phase5.py
git commit -m "refactor(phase5): split proc analyzer into proc/proc_define_map/proc_track (cache identity preserved)"
```

---

## Phase 6: Java を移植（最大の山場、4 ファイル分解）

`analyze.py`（1,636 行）を依存方向 `java_ast → {java_classify, java_track} → java` の DAG で 4 ファイルに分解する。

**重要キャッシュ:** `_ast_cache` / `_ast_line_index` / `_method_starts_cache` を `grep_helper/languages/java_ast.py` で定義し、`analyze.py` shim から参照のまま再 export する。

### Task 6.1: `grep_helper/languages/java_ast.py` を作成（最下層）

**Files:**
- Create: `grep_helper/languages/java_ast.py`

- [ ] **Step 1: 新規ファイル作成**

`analyze.py` から AST キャッシュ系のみを抽出して移植:
- `_JAVALANG_AVAILABLE` 判定（`try: import javalang` 部分）
- `_ast_cache: dict = {}` （現状定義位置を `analyze.py` 内で確認）
- `_ast_line_index: dict = {}`
- `_method_starts_cache: dict = {}`
- `_ast_cache_clear` などのテスト用クリア関数があれば移植
- `get_ast(filepath, source_dir, *, encoding_override)` (analyze.py:190 付近)
- `_get_or_build_ast_index(filepath, tree)` (analyze.py:240 付近)
- `_get_method_starts(filepath, tree)` (analyze.py:480 付近)

**注意**: `_resolve_java_file` は `java_track.py` に置く（AST のキーとなるパス解決と AST のキャッシュは別関心）。`java_ast.py` は `_resolve_java_file` を呼ばない構造に整理する。AST のキーは呼び出し側が解決済みパス文字列を渡す。

- [ ] **Step 2: 行範囲特定の補助コマンド**

```bash
grep -n "_ast_cache\|_ast_line_index\|_method_starts_cache\|_JAVALANG_AVAILABLE\|^def get_ast\|^def _get_or_build_ast_index\|^def _get_method_starts" /workspaces/grep_helper_superpowers/analyze.py
```

該当行を `java_ast.py` に移植する。

### Task 6.2: `grep_helper/languages/java_classify.py` を作成

**Files:**
- Create: `grep_helper/languages/java_classify.py`

- [ ] **Step 1: 新規ファイル作成**

`analyze.py` から純粋分類ロジックのみを抽出:
- `UsageType` Enum (analyze.py:52)
- `USAGE_PATTERNS` 等の正規表現テーブル
- `classify_usage_regex(code)` (analyze.py:292)
- `_classify_by_ast(tree, lineno, filepath)` (analyze.py:357)
- `determine_scope(...)` (analyze.py:385)
- `extract_variable_name(code, usage_type)` (analyze.py:433)

依存は `grep_helper.languages.java_ast` のみ。

`UsageType.OTHER.value` などの定数は使い続ける（既存テストが Enum 値を読む可能性があるため）。

### Task 6.3: `grep_helper/languages/java_track.py` を作成

**Files:**
- Create: `grep_helper/languages/java_track.py`

- [ ] **Step 1: 新規ファイル作成**

`analyze.py` からトラッキング系を抽出:
- `_FIELD_DECL_PATTERN`
- `_resolve_java_file(filepath, source_dir)` (analyze.py:461)
- `_get_method_scope(...)` (analyze.py:511)
- `_search_in_lines(...)` (analyze.py:570)
- `_get_java_files(source_dir)` (analyze.py:634)
- `track_constant` (analyze.py:643)
- `track_field` (analyze.py:690)
- `track_local` (analyze.py:734)
- `find_getter_names` (analyze.py:785)
- `find_setter_names` (analyze.py:842)
- `track_setter_calls` (analyze.py:887)
- `track_getter_calls` (analyze.py:931)
- `_scan_files_for_combined` (analyze.py:1000)
- `_batch_track_combined` (analyze.py:1080)
- `_batch_track_constants` (analyze.py:1193)
- `_batch_track_getters` (analyze.py:1265)
- `_batch_track_setters` (analyze.py:1338)

依存は `grep_helper.languages.java_ast` と `grep_helper.model` `grep_helper.scanner` `grep_helper.source_files` `grep_helper.file_cache` のみ。**`java_classify` を import しない**。

`print_report` は `analyze.py` の `main` 専用ヘルパなので、`java.py` 側に置くか、shim に残す（テスト依存がなければ shim 側で十分）。

### Task 6.4: `grep_helper/languages/java.py` を作成（オーケストレーション層）

**Files:**
- Create: `grep_helper/languages/java.py`

- [ ] **Step 1: 新規ファイル作成**

```python
"""Java 言語ハンドラ（公開 API + オーケストレーション）。"""
from __future__ import annotations

import re
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType

from grep_helper.languages import java_ast as _ast
from grep_helper.languages import java_classify as _cls
from grep_helper.languages import java_track as _trk

EXTENSIONS: tuple[str, ...] = (".java",)


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:
    """Java コード行を分類する。

    AST 解析を試み、失敗時は正規表現フォールバック。
    ctx が None の場合（直接呼び出し時）は AST 経路をスキップして regex で返す。
    """
    if ctx is None:
        return _cls.classify_usage_regex(code)
    tree = _ast.get_ast(ctx.filepath, ctx.source_dir, encoding_override=ctx.encoding_override)
    if tree is None:
        if _ast._JAVALANG_AVAILABLE:
            ctx.stats.fallback_files.add(ctx.filepath)
        return _cls.classify_usage_regex(code)
    try:
        usage = _cls._classify_by_ast(tree, ctx.lineno, ctx.filepath)
        if usage is not None:
            return usage
    except Exception:
        ctx.stats.fallback_files.add(ctx.filepath)
    return _cls.classify_usage_regex(code)


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Java の間接参照（field/local/getter/setter/constant）をバッチ追跡する。

    direct_records から `.java` のものだけ内部でフィルタし、
    determine_scope による振り分け → 各 _batch_track_* 呼び出し → 結果結合
    の順で実行する。元の analyze_all._apply_indirect_tracking の Java ブロック
    （analyze_all.py:834-920 付近）と analyze.py:1547-1597 のオーケストレーションを
    ここに統合する。
    """
    from grep_helper.languages import detect_handler

    self_records = [
        r for r in direct_records
        if detect_handler(r.filepath, src_dir).__name__ == __name__
    ]
    if not self_records:
        return []
    # 旧 _apply_indirect_tracking の Java 分配ロジック + analyze.py のオーケストレーションを移植
    # determine_scope で各レコードを class/method/project に分類
    # → _batch_track_combined / _batch_track_constants / _batch_track_getters / _batch_track_setters を呼ぶ
    ...
```

### Task 6.5: `analyze.py` を shim 化（旧シンボル alias を網羅）

**Files:**
- Modify: `analyze.py`（全置換、~30 行 shim）

- [ ] **Step 1: テスト互換のため必要な旧シンボル一覧を `grep` で抽出**

```bash
grep -h "from analyze import" /workspaces/grep_helper_superpowers/tests/*.py | sed 's/.*import //' | tr ',' '\n' | sort -u
```

このリストを基に shim の re-export を組む。

- [ ] **Step 2: `analyze.py` を shim に置換**

```python
"""DEPRECATED shim: ``grep_helper.languages.java``。Phase 7 で削除。"""
from __future__ import annotations

from grep_helper.cli import run
from grep_helper.languages import java as _handler
from grep_helper.languages.java import (
    classify_usage as _classify_usage_new,
    batch_track_indirect,
)
from grep_helper.languages.java_ast import (
    _JAVALANG_AVAILABLE,
    _ast_cache as _ast_cache,                  # dict identity
    _ast_line_index as _ast_line_index,        # dict identity
    _method_starts_cache as _method_starts_cache,  # dict identity
    get_ast,
    _get_or_build_ast_index,
)
from grep_helper.languages.java_classify import (
    UsageType,
    classify_usage_regex,
    _classify_by_ast,
    determine_scope,
    extract_variable_name,
)
from grep_helper.languages.java_track import (
    _FIELD_DECL_PATTERN, _resolve_java_file, _get_method_scope,
    _search_in_lines, _get_java_files,
    track_constant, track_field, track_local,
    find_getter_names, find_setter_names,
    track_setter_calls, track_getter_calls,
    _scan_files_for_combined, _batch_track_combined,
    _batch_track_constants, _batch_track_getters, _batch_track_setters,
)


def classify_usage(code, filepath, lineno, source_dir, stats, *, encoding_override=None):
    """旧シグネチャ互換ラッパ。Phase 7 で削除予定。"""
    from grep_helper.model import ClassifyContext
    ctx = ClassifyContext(
        filepath=filepath, lineno=lineno, source_dir=source_dir,
        stats=stats, encoding_override=encoding_override,
    )
    return _classify_usage_new(code, ctx=ctx)


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Java grep結果 自動分類・使用箇所洗い出しツール"))
```

### Task 6.6: `analyze_all.py` から Java 関連 import を整理

**Files:**
- Modify: `analyze_all.py`

- [ ] **Step 1: Java 関連のテンポラリ参照を 1 本化**

`analyze_all.py` の `import analyze as _java_mod` および private 関数の `# type: ignore[attr-defined]` 参照を、`from grep_helper.languages.java import classify_usage as _java_classify_usage_new, batch_track_indirect as _java_batch_track_indirect` に集約する。

`_apply_indirect_tracking` の Java 分配ロジックは Phase 7 でまとめて削る予定だが、Phase 6 完了時点では「動く状態」を維持するため、ここでは旧 `_batch_track_combined` などへの参照を `from grep_helper.languages.java_track import _batch_track_combined` に書き換えるだけ（ロジックは触らない）。

- [ ] **Step 2: `# type: ignore[attr-defined]` 0 件確認（grep_helper 配下のみ）**

```bash
grep -rn "type: ignore\[attr-defined\]" /workspaces/grep_helper_superpowers/grep_helper/ || echo "OK: 0 hits in grep_helper/"
```

期待: `OK: 0 hits in grep_helper/`

`analyze_all.py` 内の `# type: ignore[attr-defined]` は Phase 7 のクリーンアップで除去する。

### Task 6.7: キャッシュ同一性チェック + テスト緑確認

- [ ] **Step 1: 同一性チェックスクリプト**

`scripts/check_cache_identity_phase6.py` を新規作成:

```python
"""Phase 6 完了時のキャッシュ同一性チェック（Java AST キャッシュ）。"""
from __future__ import annotations

import analyze
import grep_helper.languages.java_ast as java_ast


def main() -> None:
    assert analyze._ast_cache is java_ast._ast_cache, "_ast_cache identity broken"
    assert analyze._ast_line_index is java_ast._ast_line_index, "_ast_line_index identity broken"
    assert analyze._method_starts_cache is java_ast._method_starts_cache, \
        "_method_starts_cache identity broken"
    print("Phase 6 cache identity: OK")


if __name__ == "__main__":
    main()
```

```bash
python /workspaces/grep_helper_superpowers/scripts/check_cache_identity_phase6.py
```

期待: `Phase 6 cache identity: OK`

- [ ] **Step 2: 全テスト緑確認**

```bash
python -m pytest tests/ -v
```

特に `tests/test_analyze.py`（80KB の Java テストスイート、import が多数）と `tests/test_all_analyzer.py` を重点確認。

- [ ] **Step 3: flake8 確認**

```bash
flake8 grep_helper/
```

- [ ] **Step 4: コミット**

```bash
git add grep_helper/languages/java.py grep_helper/languages/java_ast.py \
        grep_helper/languages/java_classify.py grep_helper/languages/java_track.py \
        grep_helper/languages/__init__.py analyze.py analyze_all.py \
        scripts/check_cache_identity_phase6.py
git commit -m "refactor(phase6): split analyze.py into java/java_ast/java_classify/java_track (DAG; cache identity preserved)"
```

---

## Phase 7: dispatcher 移植 + テスト import 一括置換 + クリーンアップ

### Task 7.1: `grep_helper/dispatcher.py` を新規作成

**Files:**
- Create: `grep_helper/dispatcher.py`

- [ ] **Step 1: 新規ファイル作成**

`analyze_all.py` から以下を移植:
- `process_grep_lines_all` (analyze_all.py:137-224)
- `_classify_for_lang` 相当のロジック → `detect_handler` + `handler.classify_usage(code, ctx=ctx)` の 1 行に置換
- `apply_indirect_tracking` 新版（10 行のループ）

```python
"""全言語ディスパッチャー（旧 analyze_all.py 相当）。"""
from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from grep_helper.encoding import detect_encoding
from grep_helper.grep_input import iter_grep_lines, parse_grep_line
from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.tsv_output import write_tsv
from grep_helper.languages import detect_handler

# レジストリ全ハンドラ（__init__.py で _register された順）
from grep_helper.languages import (
    EXT_TO_HANDLER,
    SHEBANG_TO_HANDLER,
)


def _all_handlers():
    """登録済みのユニークなハンドラ集合を返す。"""
    seen = set()
    for h in EXT_TO_HANDLER.values():
        if h.__name__ not in seen:
            seen.add(h.__name__)
            yield h


def process_grep_lines_all(
    lines: Iterable[str],
    keyword: str,
    source_dir: Path,
    stats: ProcessStats,
    *,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """grep 行を読んで、ファイル拡張子から handler を引いて分類する。"""
    records: list[GrepRecord] = []
    for line in lines:
        stats.total_lines += 1
        parsed = parse_grep_line(line)
        if parsed is None:
            stats.skipped_lines += 1
            continue
        try:
            lineno_int = int(parsed["lineno"])
        except ValueError:
            lineno_int = 0
        handler = detect_handler(parsed["filepath"], source_dir)
        ctx = ClassifyContext(
            filepath=parsed["filepath"], lineno=lineno_int,
            source_dir=source_dir, stats=stats, encoding_override=encoding_override,
        )
        usage = handler.classify_usage(parsed["code"], ctx=ctx)
        records.append(GrepRecord(
            keyword=keyword,
            ref_type=RefType.DIRECT.value,
            usage_type=usage,
            filepath=parsed["filepath"],
            lineno=parsed["lineno"],
            code=parsed["code"],
        ))
        stats.valid_lines += 1
    return records


def apply_indirect_tracking(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """登録済み全ハンドラの batch_track_indirect を順次呼び出し、結果を結合する。"""
    results: list[GrepRecord] = []
    for handler in _all_handlers():
        fn = getattr(handler, "batch_track_indirect", None)
        if fn is None:
            continue
        results.extend(fn(direct_records, src_dir, encoding, workers=workers))
    return results


def main() -> int:
    """旧 analyze_all.main を移植。argparse + 全フローのオーケストレーション。"""
    # 元の analyze_all.py:1029-1099 の build_parser + main を移植
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

### Task 7.2: `grep_helper/languages/__init__.py` を完成版に更新（シバン判定込み）

**Files:**
- Modify: `grep_helper/languages/__init__.py`

- [ ] **Step 1: 完成版 `detect_handler` を実装**

```python
"""言語ハンドラレジストリ。"""
from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType

from grep_helper.languages import _none

EXT_TO_HANDLER: dict[str, ModuleType] = {}
SHEBANG_TO_HANDLER: dict[str, ModuleType] = {}

_SHEBANG_PAT = re.compile(r'^#!\s*(?:.*/)?(?:env\s+)?(\S+)')


def _register(handler: ModuleType) -> None:
    for ext in getattr(handler, "EXTENSIONS", ()):
        EXT_TO_HANDLER[ext] = handler
    for sb in getattr(handler, "SHEBANGS", ()):
        SHEBANG_TO_HANDLER[sb] = handler


def detect_handler(filepath: str, src_dir: Path) -> ModuleType:
    """拡張子 → シバン の順でハンドラを引く。不明は _none。"""
    ext = Path(filepath).suffix.lower()
    if ext:
        return EXT_TO_HANDLER.get(ext, _none)

    # 拡張子なし: src_dir 相対 / 絶対 / CWD 相対の順でファイル先頭行を読む
    from grep_helper.source_files import resolve_file_cached
    candidate = resolve_file_cached(filepath, src_dir)
    if candidate is None:
        return _none
    try:
        first_line = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        m = _SHEBANG_PAT.match(first_line)
        if m:
            return SHEBANG_TO_HANDLER.get(m.group(1).lower(), _none)
    except Exception:
        pass
    return _none


# 全言語登録
from grep_helper.languages import (  # noqa: E402
    java, kotlin, c, proc, sql, sh, ts, python, perl, dotnet, groovy, plsql,
)

for _h in (java, kotlin, c, proc, sql, sh, ts, python, perl, dotnet, groovy, plsql, _none):
    _register(_h)
```

### Task 7.3: `analyze_all.py` を shim 化

**Files:**
- Modify: `analyze_all.py`

- [ ] **Step 1: ファイル全体を以下に置換**

```python
"""DEPRECATED shim: ``grep_helper.dispatcher``。次のメジャーリリースで削除。"""
from __future__ import annotations

from grep_helper.dispatcher import (
    main,
    process_grep_lines_all,
    apply_indirect_tracking,
)


# 旧 _apply_indirect_tracking 名のエイリアス（テスト互換のため）
_apply_indirect_tracking = apply_indirect_tracking


# 旧 detect_language 名のエイリアス
def detect_language(filepath, source_dir):
    """旧 API 互換: ハンドラのモジュール名から言語キーを返す。"""
    from grep_helper.languages import detect_handler
    h = detect_handler(filepath, source_dir)
    name = h.__name__.rsplit(".", 1)[-1]
    if name == "_none":
        return "other"
    return name


if __name__ == "__main__":
    raise SystemExit(main())
```

### Task 7.4: テスト import を一括置換

**Files:**
- Modify: 全 `tests/test_*.py` の import 文

- [ ] **Step 1: import 置換マップ**

| 旧 | 新 |
|---|---|
| `from analyze_common import …` | 適切な `grep_helper.<module>` に分散 |
| `import analyze_common` | `import grep_helper.file_cache as analyze_common` 不可（dict 同一性は shim 側で保証されたままのため、置換時はそれぞれの分割先 module を import する） |
| `from aho_corasick import …` | `from grep_helper._aho_corasick import …` |
| `from analyze import …` | `from grep_helper.languages.java import …` (公開 API) または `from grep_helper.languages.java_<sub> import …` (細かい関数) |
| `from analyze_all import …` | `from grep_helper.dispatcher import …` |
| `from analyze_proc import …` | `from grep_helper.languages.proc import …` (or `proc_define_map` / `proc_track`) |
| `from analyze_c import …` | `from grep_helper.languages.c import …` |
| `from analyze_kotlin import …` | `from grep_helper.languages.kotlin import …` |
| `from analyze_dotnet import …` | `from grep_helper.languages.dotnet import …` |
| `from analyze_groovy import …` | `from grep_helper.languages.groovy import …` |
| `from analyze_sh import …` | `from grep_helper.languages.sh import …` |
| `from analyze_sql import …` | `from grep_helper.languages.sql import …` |
| `from analyze_plsql import …` | `from grep_helper.languages.plsql import …` |
| `from analyze_ts import …` | `from grep_helper.languages.ts import …` |
| `from analyze_python import …` | `from grep_helper.languages.python import …` |
| `from analyze_perl import …` | `from grep_helper.languages.perl import …` |

- [ ] **Step 2: dict 参照テストの置換（spec §6.5 の表）**

| 旧 | 新 |
|---|---|
| `from analyze_common import _file_lines_cache` | `from grep_helper.file_cache import _file_lines_cache` |
| `from analyze_common import _source_files_cache` | `from grep_helper.source_files import _source_files_cache` |
| `from analyze_common import _resolve_file_cache` | `from grep_helper.source_files import _resolve_file_cache` |
| `from analyze import _ast_cache` | `from grep_helper.languages.java_ast import _ast_cache` |
| `from analyze_proc import _define_map_cache` | `from grep_helper.languages.proc_define_map import _define_map_cache` |
| `from analyze_c import _define_map_cache` | `from grep_helper.languages.c import _define_map_cache` |

- [ ] **Step 3: `tests/test_aho_corasick.py` を更新**

```bash
sed -i 's/from aho_corasick import/from grep_helper._aho_corasick import/g' tests/test_aho_corasick.py
```

- [ ] **Step 4: `tests/test_common.py` を更新**

`from analyze_common import …` を分解して、それぞれの新モジュールから import する。`tests/test_common.py:4` を例に:

```python
from grep_helper.model import GrepRecord, ProcessStats, RefType
from grep_helper.grep_input import parse_grep_line
from grep_helper.tsv_output import write_tsv
from grep_helper.source_files import grep_filter_files
```

など、内容ごとに分割して置換する。手で確認しつつ。

- [ ] **Step 5: その他の `tests/test_*.py` を機械的に置換**

```bash
cd /workspaces/grep_helper_superpowers
# 単純な find-replace（検証必要）
sed -i 's/from analyze_common import GrepRecord, ProcessStats, RefType/from grep_helper.model import GrepRecord, ProcessStats, RefType/g' tests/*.py
sed -i 's/from analyze_common import ProcessStats, GrepRecord, RefType/from grep_helper.model import ProcessStats, GrepRecord, RefType/g' tests/*.py
sed -i 's/from analyze_common import ProcessStats, GrepRecord/from grep_helper.model import ProcessStats, GrepRecord/g' tests/*.py
sed -i 's/from analyze_common import ProcessStats/from grep_helper.model import ProcessStats/g' tests/*.py
sed -i 's/from analyze_common import detect_encoding/from grep_helper.encoding import detect_encoding/g' tests/*.py
sed -i 's/from analyze_common import iter_grep_lines/from grep_helper.grep_input import iter_grep_lines/g' tests/*.py
sed -i 's/from analyze_common import iter_source_files, _source_files_cache_clear/from grep_helper.source_files import iter_source_files, _source_files_cache_clear/g' tests/*.py
sed -i 's/from analyze_common import resolve_file_cached, _resolve_file_cache_clear/from grep_helper.source_files import resolve_file_cached, _resolve_file_cache_clear/g' tests/*.py
sed -i 's/from analyze_common import cached_file_lines, _file_lines_cache_clear, _file_lines_cache, set_file_lines_cache_limit/from grep_helper.file_cache import cached_file_lines, _file_lines_cache_clear, _file_lines_cache, set_file_lines_cache_limit/g' tests/*.py
sed -i 's/from analyze_common import cached_file_lines, _file_lines_cache_clear, _file_lines_cache/from grep_helper.file_cache import cached_file_lines, _file_lines_cache_clear, _file_lines_cache/g' tests/*.py
sed -i 's/from analyze_common import cached_file_lines, _file_lines_cache_clear/from grep_helper.file_cache import cached_file_lines, _file_lines_cache_clear/g' tests/*.py
sed -i 's/from analyze_common import build_batch_scanner/from grep_helper.scanner import build_batch_scanner/g' tests/*.py
sed -i 's/import analyze_common$/import grep_helper.file_cache as analyze_common/g' tests/*.py  # _file_lines_cache_clear 用
```

`import analyze_common` だけは多数のテストで `analyze_common._file_lines_cache_clear()` の形で使われているので、`grep_helper.file_cache` を `as analyze_common` で alias して動かすのは不正（他のメンバーが見えない）。代わりに、各テストの `import analyze_common` の行を **本来呼びたい関数の import に置き換える**:

```bash
# 例: setUp で _file_lines_cache_clear() のみ使っている場合
# 'import analyze_common' を 'from grep_helper.file_cache import _file_lines_cache_clear' に置換し、
# 'analyze_common._file_lines_cache_clear()' を '_file_lines_cache_clear()' に置換する。
```

この置換は機械的では危ない（alias の使われ方が複数）ので、**`tests/` 全体に対して `analyze_common\.` の使用箇所を grep で確認 → 一件ずつ置換**する。

```bash
grep -n "analyze_common\." /workspaces/grep_helper_superpowers/tests/*.py
```

- [ ] **Step 6: shim 内の旧名 alias を削除**

各 shim ファイル（`analyze_python.py` 等）から、Phase 3〜6 で追加した旧名 alias 行（`classify_usage_python = _classify_usage_new` など）を削除する。

shim は最終的に 5〜10 行に縮む:

```python
"""``grep_helper.languages.python`` への CLI shim。"""
from grep_helper.cli import run
from grep_helper.languages import python as _handler


if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Python grep結果 自動分類・使用箇所洗い出しツール"))
```

- [ ] **Step 7: ルート `analyze_common.py` と `aho_corasick.py` を物理削除**

```bash
rm /workspaces/grep_helper_superpowers/analyze_common.py
rm /workspaces/grep_helper_superpowers/aho_corasick.py
```

- [ ] **Step 8: 検証（DoD §9-4）**

```bash
# 旧 import がテスト・grep_helper 配下にゼロ件
grep -rn "from analyze_common" /workspaces/grep_helper_superpowers/ --include="*.py" || echo "OK: 0 hits"
grep -rn "from aho_corasick" /workspaces/grep_helper_superpowers/ --include="*.py" || echo "OK: 0 hits"
# grep_helper/ 配下に type: ignore[attr-defined] 0 件
grep -rn "type: ignore\[attr-defined\]" /workspaces/grep_helper_superpowers/grep_helper/ || echo "OK: 0 hits in grep_helper/"
```

期待: いずれも 0 件。

- [ ] **Step 9: 全テスト緑確認**

```bash
python -m pytest tests/ -v
```

期待: 全テスト pass。

- [ ] **Step 10: TSV 同一性検証（DoD §9-3）**

`tests/fixtures/` を入力に、`analyze_all` の出力 TSV をリファクタ前後で比較する。

```bash
mkdir -p /tmp/refactor-tsv-check/{before,after,input}
# fixtures から grep ファイルを 1 件作る（既存の手順がない場合は省略してテストカバレッジで担保）

# (フェーズ移行前の commit に切り替えて実行 → /tmp/refactor-tsv-check/before/ に出力)
# (現在のコミットで実行 → /tmp/refactor-tsv-check/after/ に出力)
diff -r /tmp/refactor-tsv-check/before /tmp/refactor-tsv-check/after
```

期待: 差分なし。

**注**: テストフィクスチャがすでに `tests/fixtures/` に十分揃っており、`pytest tests/test_all_analyzer.py` がリファクタ前後の動作を網羅しているなら、このステップは省略可（コミット前にテスト緑であれば代替できる）。

- [ ] **Step 11: flake8 確認**

```bash
flake8 grep_helper/ tests/ analyze*.py
```

- [ ] **Step 12: コミット**

```bash
git add tests/ analyze*.py grep_helper/dispatcher.py grep_helper/languages/__init__.py
git rm analyze_common.py aho_corasick.py
git commit -m "refactor(phase7): port dispatcher to grep_helper, sweep test imports, drop old shims"
```

---

## Phase 8: docs 更新

各ドキュメントを新構造に合わせて書き直す。コードに触れないので pytest は不変。

### Task 8.1: `docs/repository-structure.md` を新構造で書き直し

**Files:**
- Modify: `docs/repository-structure.md`

- [ ] **Step 1: 現状ファイル確認**

```bash
cat /workspaces/grep_helper_superpowers/docs/repository-structure.md | head -50
```

- [ ] **Step 2: 全面書き直し**

新ディレクトリツリー（spec §3 の図）と各ファイルの責務一覧（spec §4.1 / §4.2 の表）を反映する。`grep_helper/` 直下と `grep_helper/languages/` の 2 階層フラット構造であることを強調。

### Task 8.2: `docs/architecture.md` を新構造で書き直し

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: 全面書き直し**

新レイヤ図と責務分担（io 系 / scanner / pipeline / dispatcher / languages）を記述。spec §2.2 のハンドラ契約と §4 の責務一覧を反映。

### Task 8.3: `docs/development-guidelines.md` を全面書き直し

**Files:**
- Modify: `docs/development-guidelines.md`

- [ ] **Step 1: 「新言語の追加手順」セクションをハンドラ契約ベースに書き換え**

手順:
1. `grep_helper/languages/<lang>.py` を作成
2. `EXTENSIONS` と `classify_usage(code, *, ctx)` を実装
3. 必要なら `batch_track_indirect(direct_records, src_dir, encoding, *, workers)` を実装
4. `grep_helper/languages/__init__.py` の登録ループに追加
5. `tests/test_<lang>_analyzer.py` を追加
6. `docs/repository-structure.md` に追記

- [ ] **Step 2: pytest-xdist を導入しないことを明記**（spec §6.6）

「テストはモジュールキャッシュのクリア規律（setUp の `_*_clear()` 呼び出し）に依存しているため、`pytest-xdist` 等の並列実行は導入しないこと」を 1 行追加。

- [ ] **Step 3: TSV 同一性検証手順を追記**（spec §9-3）

「リファクタやロジック変更時に TSV 出力が変わっていないことを確認するには、`tests/fixtures/` を入力に `python analyze_all.py --source-dir tests/fixtures/<lang> --input-dir <grep-dir>` を before/after で実行し `diff -r` で比較する」旨を 1 段落追加。

### Task 8.4: `docs/functional-design.md` を更新

**Files:**
- Modify: `docs/functional-design.md`

- [ ] **Step 1: 関数名・モジュール名を新パスに更新**

`analyze.classify_usage` → `grep_helper.languages.java.classify_usage` 等の置換を全文に渡って行う。処理フロー図は基本維持。

### Task 8.5: `docs/tool-overview.md` を更新

**Files:**
- Modify: `docs/tool-overview.md`

- [ ] **Step 1: モジュール参照名のみを新パスに置換**

フロー説明（CLI の使い方）は不変。

### Task 8.6: `README.md` を更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 「リポジトリ構成」セクションを追記**

`grep_helper/` パッケージの存在に触れ、ルート `analyze*.py` が shim であることを 1 段落で説明。CLI 実行例（`python analyze.py --source-dir … --input-dir … --output-dir …`）は不変。

### Task 8.7: docs まとめコミット

- [ ] **Step 1: コミット**

```bash
git add docs/ README.md
git commit -m "docs(phase8): rewrite docs for new grep_helper package structure"
```

---

## 完了条件チェックリスト（spec §9）

Phase 7 + Phase 8 完了時に以下を機械的に確認する:

- [ ] `python -m pytest tests/ -v` 全緑
- [ ] `python analyze.py --help` および `python analyze_<lang>.py --help` 全 13 個が動作
- [ ] TSV 同一性: リファクタ前後で `analyze_all` 出力 TSV が `diff -r` で完全一致（手順は §Phase 7 Task 7.4 Step 10 / docs §development-guidelines.md）
- [ ] `grep -rn "from analyze_common" .` が 0 件（`docs/` `*.md` 内のサンプルコードを除く）
- [ ] `grep -rn "from aho_corasick" .` が 0 件
- [ ] `grep -rn "type: ignore\[attr-defined\]" grep_helper/` が 0 件
- [ ] `docs/architecture.md` `docs/repository-structure.md` `docs/development-guidelines.md` が新構造で書き直し済
- [ ] `flake8 grep_helper/ tests/ analyze*.py` 警告なし
- [ ] §2.3 のキャッシュ同一性 `is` チェックスクリプト 4 つ（Phase 1 / 4 / 5 / 6）が全てパス

---

## リスク管理（spec §8）

| リスク | 緩和策（このプランでの対応箇所） |
|---|---|
| Java 4 ファイル分解で循環 import | Task 6.1〜6.4 で `java_ast → {java_classify, java_track} → java` の DAG を厳守。`java_classify` と `java_track` は互いを参照しない（Task 6.3 末尾の注） |
| Shim 旧シンボル alias 削除漏れ | Task 7.4 Step 6 で全 shim を 5〜10 行のテンプレに置換。Step 8 の `grep -rn` で旧 import が残っていないことを確認 |
| `analyze_all.py` の重複バッチトラッカー畳み込みで挙動変化 | 各 Phase 4/5/6 のコミット前に `pytest tests/test_all_analyzer.py` を必ず緑化 |
| テスト import 一括置換のタイポ・漏れ | Task 7.4 Step 8 で `grep -rn "from analyze_common" .` `grep -rn "from aho_corasick" .` が 0 件であることを機械的に確認 |
| `--workers` 並列の pickle 互換 | バッチトラッカーは全てモジュール関数のまま。class instance 化しない（spec §10 ハンドラ契約 B 案の選択理由） |
| キャッシュ object identity が shim 越しに保てない | §2.3 表の dict 全てを Phase 1 / 5 / 6 で `as` 参照 re-export。`scripts/check_cache_identity_phase{1,5,6}.py` を実行 |
| ワーカープロセスがキャッシュ再ビルド | `_build_define_map` はメインプロセスで事前構築 → `scan_tasks` 引数でワーカー渡し（Task 4.4 / Task 5.3 の `batch_track_indirect` 内で明示） |
| pytest-xdist 並列でモジュールキャッシュ汚染 | Task 8.3 で docs に「pytest-xdist を導入しない」旨を明記 |

---

## コミット粒度（spec §10）

参考目安: 全 17 コミット程度。

| Phase | コミット数（目安） |
|---|---:|
| Phase 0 | 2 |
| Phase 1 | 1 |
| Phase 2 | 1 |
| Phase 3 | 6（言語ごと 1） |
| Phase 4 | 4（言語ごと 1） |
| Phase 5 | 1 |
| Phase 6 | 1 |
| Phase 7 | 1 |
| Phase 8 | 1 |
| 合計 | 18 |
