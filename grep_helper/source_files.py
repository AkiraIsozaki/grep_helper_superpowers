"""ソースファイル探索・解決キャッシュ。"""
from __future__ import annotations

import mmap
import sys
from pathlib import Path

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
