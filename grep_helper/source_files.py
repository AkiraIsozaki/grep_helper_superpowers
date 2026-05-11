"""ソースファイル探索・解決キャッシュ。"""
from __future__ import annotations

import mmap
import sys
from pathlib import Path
from typing import Iterator

_source_files_cache: dict[tuple[str, tuple[str, ...]], list[Path]] = {}

# モジュールグローバル: ファイル単位の byte hit 結果
# キー = (str(path), bytes_pattern)、値 = bool（hit / miss）
_filter_byte_cache: dict[tuple[str, bytes], bool] = {}


def _filter_byte_cache_clear() -> None:
    """テスト用: byte hit cache をクリア。"""
    _filter_byte_cache.clear()


_DEFAULT_READ_CHUNK = 1024 * 1024  # 1 MB


def _iter_read_with_overlap(
    path: Path,
    overlap: int,
    *,
    chunk_size: int = _DEFAULT_READ_CHUNK,
) -> Iterator[bytes]:
    """1 チャンクずつ読み、前チャンク末尾を ``overlap`` バイトだけ prepend して
    境界をまたぐパターンも検出可能な連結バッファ列を yield するジェネレータ。

    seek を使わない（NFS / 一部の特殊 fs で seek が高コストな場合の保険）。
    ``overlap`` は呼び出し側が ``max(len(p)) - 1`` 等から計算する。
    EOF まで読み切ったら通常通り iteration を終了する。
    """
    if overlap < 0:
        overlap = 0
    tail = b""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                return
            buf = tail + chunk
            yield buf
            tail = buf[-overlap:] if overlap > 0 else b""


def _read_based_find(
    path: Path,
    patterns: list[bytes],
    *,
    chunk_size: int = _DEFAULT_READ_CHUNK,
) -> bool:
    """1MB チャンク + prepend オーバーラップでバイト列を検索する。

    mmap が使えない / 失敗するファイルに対する代替実装。
    ``_iter_read_with_overlap`` を共有ヘルパーとして使う。

    API 契約: ``patterns`` は非空であること（呼び出し元 ``grep_filter_files``
    で空 patterns は早期 return 済み）。
    """
    overlap = max(len(p) for p in patterns) - 1
    for buf in _iter_read_with_overlap(path, overlap, chunk_size=chunk_size):
        for pat in patterns:
            if buf.find(pat) != -1:
                return True
    return False


def _find_any_with_per_pattern_result(
    path: Path,
    patterns: list[bytes],
    *,
    use_mmap: bool,
) -> tuple[dict[bytes, bool], bool]:
    """1 回の I/O で各 pattern の hit/miss を判定して返す（mmap 優先）。

    Args:
        path:     対象ファイル
        patterns: バイトパターンのリスト（非空であること）
        use_mmap: mmap 経路を試すか

    Returns:
        ``(hits, cacheable)`` の 2-tuple。``hits`` は各 pattern → True/False。
        spec §B2' に従い、stat() で OSError が起きた場合はセーフ側として
        全 pattern を True としつつ ``cacheable=False`` を返す
        （NFS hiccup などの transient エラーで永続的に hit を誤判定するのを防ぐ）。
        正常終了時は ``cacheable=True``。
    """
    result = {p: False for p in patterns}
    try:
        if path.stat().st_size == 0:
            return result, True
    except OSError:
        # spec §B2': セーフ側で全 True を返すが、これは cache してはならない
        return {p: True for p in patterns}, False
    if use_mmap:
        try:
            with open(path, "rb") as fh, \
                 mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for p in patterns:
                    if mm.find(p) != -1:
                        result[p] = True
            return result, True
        except (OSError, ValueError):
            pass
    overlap = max(len(p) for p in patterns) - 1 if patterns else 0
    for buf in _iter_read_with_overlap(path, overlap):
        for p in patterns:
            if not result[p] and buf.find(p) != -1:
                result[p] = True
        if all(result.values()):
            return result, True
    return result, True


def _scan_file_for_patterns(
    path: Path,
    patterns: list[bytes],
    *,
    use_mmap: bool = True,
) -> bool:
    """ファイルが patterns のいずれかを含むかを返す。

    各 (path, pattern) の組について cache する。cache 済みなら I/O ゼロ。
    未 cache の pattern だけまとめて 1 回の mmap / read で判定する。
    ``_find_any_with_per_pattern_result`` が ``cacheable=False`` を返した場合
    （= stat OSError のセーフ側フォールバック）は cache に書き込まない。
    """
    key_path = str(path)
    unknown: list[bytes] = []
    for pat in patterns:
        cached = _filter_byte_cache.get((key_path, pat))
        if cached is True:
            return True
        if cached is None:
            unknown.append(pat)
    if not unknown:
        return False
    hits, cacheable = _find_any_with_per_pattern_result(
        path, unknown, use_mmap=use_mmap,
    )
    if cacheable:
        for pat, hit in hits.items():
            _filter_byte_cache[(key_path, pat)] = hit
    return any(hits.values())


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
    try:
        if candidate.is_absolute():
            result = candidate if candidate.exists() else None
        elif candidate.exists():
            result = candidate
        else:
            resolved = src_dir / filepath
            result = resolved if resolved.exists() else None
    except OSError:
        # ENAMETOOLONG など、stat 段で OS が拒否する病的パスは未解決扱い
        result = None
    _resolve_file_cache[key] = result
    return result
