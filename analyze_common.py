"""全言語アナライザー共通インフラ。

GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv を提供する。
analyze.py / analyze_proc.py / analyze_sql.py / analyze_sh.py から import される。
"""
from __future__ import annotations

import csv
import mmap
import sys
import heapq
import re
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import NamedTuple

try:
    import chardet as _chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False


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


_BINARY_PATTERN   = re.compile(r'^Binary file .+ matches$')
_GREP_LINE_PATTERN = re.compile(r':(\d+):')

_TSV_HEADERS = [
    "文言", "参照種別", "使用タイプ", "ファイルパス", "行番号", "コード行",
    "参照元変数名", "参照元ファイル", "参照元行番号",
]

_EXTERNAL_SORT_THRESHOLD = 1_000_000


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
        _, old_lines = _file_lines_cache.popitem(last=False)
        _file_lines_cache_bytes -= _estimate_lines_bytes(old_lines)
    return lines


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
            from aho_corasick import AhoCorasick  # type: ignore[import-not-found]
            return _BatchScanner(patterns, "ahocorasick", AhoCorasick(patterns))
    combined = re.compile(r"\b(" + "|".join(re.escape(p) for p in patterns) + r")\b")
    return _BatchScanner(patterns, "regex", combined)
