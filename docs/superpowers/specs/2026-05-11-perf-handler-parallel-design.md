# パフォーマンス改善: ハンドラ並列化 + インクリメンタル TSV 出力 + バイトスキャン重複削減 設計書

**日付**: 2026-05-11
**対象ファイル**（テスト追加分も含む完全リスト）:

本体:

- `grep_helper/dispatcher.py`（変更: handler 並列化 + インクリメンタル書き出し + on_handler_complete コールバック + CLI `--handler-workers` 追加）
- `grep_helper/source_files.py`（変更: `grep_filter_files` にファイル単位 byte hit cache を追加 + `_filter_byte_cache_clear()` 公開）
- `grep_helper/tsv_output.py`（変更: `_sort_key` / `_row_sort_key` に `ref_type` と `usage_type` を加えて tie を消す）

`grep_helper/pipeline.py` は単一 handler 用途（個別 analyze\_\*.py CLI）専用のため、本タスクでは変更しない。`run_full_pipeline` 経由のインクリメンタル化・handler 並列化は意義が薄い（handler が 1 つしかない）。

`analyze_all.py` はトップレベル shim（5 行のみ）のため本タスクでは変更しない。CLI フラグ追加は `grep_helper/dispatcher.build_parser` 側で行う。

ドキュメント:

- 本 spec
- 後続: `docs/architecture.md` の Phase 2/3 の図と説明を更新（実装完了後）

テスト（§テスト戦略 で詳述）:

- `tests/test_dispatcher_parallel.py`（新規）
- `tests/test_source_files.py`（追記: byte hit cache）
- `tests/test_tsv_output.py`（追記または新規: 決定的ソートの tie 解消）
- `tests/test_pipeline_run.py`（追記: インクリメンタル書き出しの観察可能事実）

---

## 背景・動機

`docs/superpowers/specs/2026-05-06-perf-and-solaris-compat-design.md` で「集約バッチ間接追跡」（E-2）と Solaris 互換ガードが入った。その時点で残った後続課題のうち、本タスクは以下を扱う:

- **B1**: Phase 2（間接追跡）のハンドラ直列ループを並列化する（最大 12 ハンドラのうち実質 Java/Kotlin/C/Pro\*C 等の重量級が直列で消化されている）
- **B2'**: 同一プロセス内での `grep_filter_files` のバイト前フィルタ重複（特に C / Pro\*C が `.c/.h/.pc` を独立に 2 回スキャン）の削減
- **B3**: keyword 単位の TSV を「全 handler 完了時点」で逐次書き出し、TTFB（最初の TSV までの時間）を短縮
- **③**: 並列化に伴い tie 部分の挿入順依存が露見するため、`tsv_output._sort_key` を `(keyword, filepath, lineno, ref_type, usage_type)` で完全決定化

ロードマップ上の位置付け: 本タスクは「重複作業を削る」改善（E-2 が方向性を作った）の延長で、handler 並列化と I/O 重複削減を両輪で進める。AST cache のディスク永続化 (B4) / Phase 1 並列化 (B5) は別 spec で扱う。

---

## 想定実行環境

| 項目 | 値 |
|------|------|
| 主環境 | Solaris 10 + NFS、Python 3.7.17 |
| CPU | 4〜8 コア |
| RAM | 8〜16 GB |
| grep ファイル数 | 10〜30 本 |
| ソースファイル数 | 数千〜数万 |

設計判断の重み: **I/O 削減 > CPU 並列爆増**。NFS の往復が壁時計時間の大半を占める前提で、並列度はメモリ予算が許す範囲（handler 並列 2、内側 workers 2）に抑える。

---

## 要件

1. **性能改善**:
   - Phase 2 のハンドラループが `handler_workers` プロセスで並列実行されること
   - `grep_filter_files` の同一プロセス内 2 回目以降の呼び出しが、cache ヒット時に I/O を発生させないこと
   - 1 keyword の TSV が「その keyword に関わる全 handler の indirect 完了」直後に出力されること（**dispatcher 経路のみ Phase 3 廃止**。単一 handler 経路の `pipeline.run_full_pipeline` は handler 並列化の対象外で Phase 3 ループは維持される）

2. **出力一致**:
   - 改造前後で `python scripts/measure_kpi.py --lang all` の網羅率・分類精度が同一であること
   - 各 `<keyword>.tsv` の中身（決定的ソート後）が改造前と**行セットとして同一**であること
   - tie 部分の行順は `(keyword, filepath, lineno, ref_type, usage_type)` キーで決定的になる（既存スナップショットテストは 1 回更新する）

3. **後方互換**:
   - 各ハンドラの `batch_track_indirect(direct_records, src_dir, encoding, *, workers, use_mmap)` シグネチャは無変更
   - `dispatcher.apply_indirect_tracking` は新キーワード引数 `handler_workers`（**関数デフォルト 1 = 直列**）/ `on_handler_complete`（既定 None）を追加。**並列化は CLI からの明示指定でのみ有効化**。CLI 既定値（`--handler-workers 2`）でユーザー体感は並列、テストや既存呼び出し（引数省略）は従来通り直列で安定。これにより既存 `tests/test_*.py` の Phase 2 順序依存テストを壊さない
   - `pipeline.run_full_pipeline`（単一 handler 経路、個別 analyze\_\*.py CLI 用）は無変更

4. **CLI**:
   - `analyze_all.py` に `--handler-workers N`（既定 2）を追加
   - 既存の `--workers` `--no-mmap` は無変更

5. **やらないこと**:
   - AST cache のディスク永続化
   - Phase 1（直接分類）の並列化
   - 子プロセス間での `_file_lines_cache` / `_ast_cache` 共有
   - handler 公開 API の破壊的変更
   - 中断・再開機能（途中まで出した TSV を次回実行で活用するロジック）
   - `multi_filter_files` 形式の handler API 拡張（B 案の代わりに API 不変の B-cache を採用）
   - **子プロセスで積まれた `ProcessStats` 副作用（fallback_files / encoding_errors）を親プロセスに集約すること**（旧直列実装でも捨てられていた値で、新並列実装でも同様。将来集約する場合は `_run_one_handler` の戻り値拡張が必要）
   - byte hit cache の LRU 化（実測 200 MB/worker 超で後続検討）

---

## アーキテクチャ

### 全体フロー（新）

```
┌─ Phase 1 (直列、現状維持) ───────────────────────┐
│  for grep in input_dir/*.grep:                  │
│    direct_by_keyword[stem] = process_grep_file()│
└──────────────────────────────────────────────────┘
                       ↓
┌─ Phase 2 (handler_workers=2 並列, ProcessPool) ─────────────┐
│  all_direct = flatten(direct_by_keyword.values())            │
│  pending_handlers = { kw: {h1, h2, ...} for kw in direct }  │
│  indirect_by_keyword = { kw: [] for kw in direct }          │
│                                                              │
│  with ProcessPoolExecutor(max_workers=handler_workers) as ex:│
│    futures = { ex.submit(_run_one_handler, hname, ...): hname│
│               for hname in handler_names }                   │
│    for fut in as_completed(futures):                         │
│      hname = futures[fut]                                    │
│      partial = fut.result()                                  │
│      for rec in partial:                                     │
│        indirect_by_keyword[rec.keyword].append(rec)          │
│      for kw in direct_by_keyword:                            │
│        pending_handlers[kw].discard(hname)                   │
│        if not pending_handlers[kw]:                          │
│          write_tsv(direct_by_keyword[kw]                     │
│                    + indirect_by_keyword[kw],                │
│                    output_dir / f"{kw}.tsv")                 │
│          # ← この時点で TSV ファイルがディスクに出る         │
└──────────────────────────────────────────────────────────────┘
```

Phase 3（旧）は廃止。書き出しは Phase 2 のループ内で `as_completed` 通知に駆動される。

### B1: handler 並列化

`grep_helper/dispatcher.py`:

```python
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable

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
    例外など）はそのまま親プロセスへ propagate する。親側の `apply_indirect_tracking`
    が `fut.result()` を try/except で囲んで 1 handler スキップを実現する。
    """
    import importlib
    mod = importlib.import_module(handler_module_name)
    fn = getattr(mod, "batch_track_indirect", None)
    if fn is None:
        return []
    return fn(direct_records, src_dir, encoding, workers=workers, use_mmap=use_mmap)


def apply_indirect_tracking(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
    use_mmap: bool = True,
    handler_workers: int = 1,        # 関数デフォルトは直列。CLI で 2 を明示
    on_handler_complete: Callable[[str, list[GrepRecord]], None] | None = None,
) -> list[GrepRecord]:
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
                    # 子プロセスでの ImportError / AttributeError / handler 内例外をすべて吸収。
                    # `with ProcessPoolExecutor` を抜けずに残りの future を消化する。
                    print(
                        f"  警告: handler {hname} の間接追跡で例外 ({exc!r}) - "
                        f"この handler の indirect は欠落、他 handler は継続",
                        file=sys.stderr, flush=True,
                    )
                    continue
                _safe_complete(hname, partial)
        return results
    except OSError as exc:
        # Solaris fork 失敗 / ulimit -u 不足 等で ProcessPool 構築自体が失敗した場合
        print(
            f"  警告: ProcessPool 起動に失敗 ({exc!r}) - handler_workers=1 で直列実行に切替",
            file=sys.stderr, flush=True,
        )
        return _run_serial()
```

設計判断:

- **`handler_workers <= 1` で直列フォールバック** を残す。テストでは並列順序非決定性を避けるためこちらで結果一致を検証する
- **1 handler 例外の局所化**: 並列パスでは `fut.result()` を try/except で個別に囲み、直列パスでも `_run_one_handler` 呼び出しを try/except で囲む。これにより 1 handler の例外（子プロセス内 `ImportError`、`AttributeError`、`batch_track_indirect` 内のロジック例外を含む）が他 handler に伝播しない。§エラー処理表「1 handler 失敗 → その handler だけスキップ、他は出力、`return 0`」の挙動を保証する
- **ProcessPool 構築失敗時の自動フォールバック**: `with ProcessPoolExecutor(...)` を try で囲み、`OSError`（Solaris fork 失敗 / `ulimit -u` 不足等）が出たら直列パスに自動切替する。`stderr` に警告を出すが処理は継続
- **start method は fork (前提)**: Python 3.7 の `multiprocessing.get_start_method()` は Unix（Solaris 含む）で fork が既定。spec では明示設定しない（既定依存）。fork なら親プロセスの import 済みモジュール（`grep_helper.languages.*`、`javalang` 等）が COW で子に共有され、起動コストは ~10ms オーダーに収まる
- **モジュール名渡し（fork 固定だが将来 spawn 化に備える保険）**: ProcessPoolExecutor のタスク引数は pickle される。fork 前提でもモジュールオブジェクト直渡しは将来の start method 変更で破綻するリスクがあるため、`handler_module_name: str` を渡して子プロセス側で `importlib.import_module` する設計にしておく。spawn になる macOS（開発機テスト）でも同じコードで動くことが副次効果（spawn 化時は worker 初回起動に ~数百ms 上乗せされる旨を実装計画にメモする）
- **`_run_one_handler` の戻り値は `list[GrepRecord]` 単独**: handler 名は呼び出し側 `future_to_name[fut]` から取得できるため、戻り値に含めない
- **direct_records は pickle で 1 回コピー**: `ProcessPoolExecutor.submit` の引数は fork モードでも spawn モードでも pickle 経由でワーカープロセスに渡される（既起動ワーカーへパイプ経由ディスパッチのため COW は効かない）。grep 数が多くても direct records は数万件オーダーで、pickle 数百 KB 〜数 MB の範囲。Solaris の遅い RPC でも 1 ハンドラあたり数百 ms 程度のオーバーヘッドで、Java handler の実時間（秒〜分）からみれば許容範囲
- **子プロセス間の cache 未共有は許容**: `_file_lines_cache` / `_ast_cache` が子ワーカーごとに別空間になるのは現状の `--workers N` と同じ性質。今回これを解消するスコープには入れない（後続 spec で B4 として扱う）
- **メモリ予算**: 256MB（`_file_lines_cache` 上限）× 2 handler × 2 内側 workers = 最大 1GB。Solaris 8GB RAM で OS/NFS バッファに十分余裕
- **`ProcessStats` の副作用は子プロセスで完結し、親に伝わらない**: `java.batch_track_indirect` 等は内部で `stats = ProcessStats()` をローカル生成して fallback_files / encoding_errors を積む。これは旧（直列）でも捨てられていた値で、新（並列）でも同様に捨てられる。**動作変更ではないが、将来 stats を集約する場合は `_run_one_handler` の戻り値を `tuple[list[GrepRecord], dict]` 形式に拡張する必要がある旨を実装計画にメモする**（本タスクのスコープ外、§やらないこと参照）

### B2': ファイル単位 byte hit cache

`grep_helper/source_files.py`:

```python
# モジュールグローバル: ファイル単位の byte hit 結果
# キー = (str(path), bytes_pattern)、値 = bool（hit / miss）
_filter_byte_cache: dict[tuple[str, bytes], bool] = {}


def _filter_byte_cache_clear() -> None:
    """テスト用: byte hit cache をクリア。"""
    _filter_byte_cache.clear()


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
        # 全部 cache 済みで全部 miss
        return False
    # I/O 発生: 未 cache の pattern を 1 パスで判定
    hits = _find_any_with_per_pattern_result(path, unknown, use_mmap=use_mmap)
    for pat, hit in hits.items():
        _filter_byte_cache[(key_path, pat)] = hit
    return any(hits.values())


def _find_any_with_per_pattern_result(
    path: Path,
    patterns: list[bytes],
    *,
    use_mmap: bool,
) -> dict[bytes, bool]:
    """1 回の I/O で各 pattern の hit/miss を判定して返す（mmap 優先）。"""
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

`grep_filter_files` は内部で `_scan_file_for_patterns` を呼び替える:

```python
def grep_filter_files(names, src_dir, extensions, label="", *, use_mmap=True):
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

設計判断:

- **cache キーは `(str(path), bytes pattern)`**: ファイル数 × pattern 数 の積でエントリが増える。実測の dict オーバーヘッド込みで 1 エントリ 200〜300 B が現実的（PyObject + dict slot + ロードファクタ 2/3）。典型運用で 5,000 ヒット候補 × handler 内 names 累積 100 = 50 万エントリ → 100〜150 MB/worker。`handler_workers=2 × 内側 workers=2` で 400〜600 MB を覚悟する必要がある。Solaris 8 GB RAM では許容範囲だが、**§V-1 (KPI before/after) で実メモリを観測し、worker あたり 200 MB を恒常的に超える場合は後続 spec で LRU 化（FIFO drop 等）を検討する**旨を実装計画に明文化する
- **読み込み回数最小化**: pattern 集合 A でファイルを開き、B 集合で同じファイルを後から問い合わせるとき、A ∪ B のうち未 cache の差分だけ追加スキャンする。C handler が `{X, Y, Z}` でスキャン → Pro\*C handler が `{Y, W}` で問い合わせ → cache に未登録の `W` だけ新規スキャン → `Y` は cache 済み hit/miss 即答
- **mmap / read-based のフォールバック挙動は維持**: 既存テスト (`test_source_files.py`) で観察される `use_mmap=False` の挙動を変えない
- **空ファイルの扱いは旧挙動と同等**: 旧 `grep_filter_files` は `f.stat().st_size == 0` で `continue`（候補から除外）。新コードは `_scan_file_for_patterns` 経由で `_find_any_with_per_pattern_result` が `path.stat().st_size == 0` 時に `{p: False for p in patterns}` を返すため `_scan_file_for_patterns` は False を返し、`grep_filter_files` は候補に追加しない。**結果として空ファイルは旧と同様に除外される**。ロールアウト step 2 で `tests/golden/` 差分ゼロを要求する根拠の 1 つ
- **並列プロセス間で cache 共有はしない**: handler 並列化は ProcessPool ベースなので、cache は各子プロセスごと。ただし B2' の主目的である「C と Pro\*C が同じファイルを 2 回スキャンする」ケースは、handler 並列で別プロセスに分散すれば自然に解消する（C と Pro\*C が同一子プロセスに割り振られた場合のみ cache が効く）。最悪ケースでも従来挙動。**つまり cache の効果は同一プロセス内重複の保険であり、handler 並列化との合わせ技で底上げする位置付け**

### B3: インクリメンタル TSV 出力

`grep_helper/dispatcher.main`:

```python
def main() -> int:
    # ...（既存の argparse / バリデーション省略）...
    args = parser.parse_args()
    # ...

    # Phase 1: 直接分類（既存通り）
    direct_by_keyword: dict[str, list[GrepRecord]] = {}
    processed_files: list[str] = []
    for grep_path in grep_files:
        # ...（既存のループ）...
        direct_by_keyword[grep_path.stem] = direct
        processed_files.append(grep_path.name)

    # Phase 2 + インクリメンタル書き出し
    indirect_by_keyword: dict[str, list[GrepRecord]] = {kw: [] for kw in direct_by_keyword}
    handler_names = [
        h.__name__ for h in _all_handlers()
        if getattr(h, "batch_track_indirect", None) is not None
    ]
    pending: dict[str, set[str]] = {
        kw: set(handler_names) for kw in direct_by_keyword
    }
    written: set[str] = set()

    def on_complete(hname: str, partial: list[GrepRecord]) -> None:
        for rec in partial:
            if rec.keyword in indirect_by_keyword:
                indirect_by_keyword[rec.keyword].append(rec)
        for kw in list(pending.keys()):
            pending[kw].discard(hname)
            if not pending[kw] and kw not in written:
                output_path = output_dir / f"{kw}.tsv"
                all_records = list(direct_by_keyword[kw]) + indirect_by_keyword[kw]
                write_tsv(all_records, output_path)
                written.add(kw)
                direct_count = len(direct_by_keyword[kw])
                indirect_count = len(indirect_by_keyword[kw])
                print(
                    f"  {kw}.grep → {output_path} "
                    f"(直接: {direct_count} 件, 間接: {indirect_count} 件)",
                    flush=True,
                )

    if direct_by_keyword:
        # 縁ケース: handler_names が空（全 handler が batch_track_indirect を持たない）
        # の場合、pending[kw] は初期から空集合だが on_complete は一度も呼ばれない。
        # この場合は indirect なしで直接 TSV を書き出す。
        if not handler_names:
            for kw, recs in direct_by_keyword.items():
                output_path = output_dir / f"{kw}.tsv"
                write_tsv(list(recs), output_path)
                written.add(kw)
                print(
                    f"  {kw}.grep → {output_path} (直接: {len(recs)} 件)",
                    flush=True,
                )
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

            # 全 handler 完了後の念のためのドレイン:
            # pending[kw] が空になった keyword は必ず on_complete で書き出し済み。
            # ここでは「書き出されなかった keyword」が残っていないことを防御的に処理する。
            for kw, recs in direct_by_keyword.items():
                if kw not in written:
                    # 1 handler 失敗等で pending[kw] が空にならなかった場合のフォールバック
                    output_path = output_dir / f"{kw}.tsv"
                    write_tsv(
                        list(recs) + indirect_by_keyword.get(kw, []),
                        output_path,
                    )
                    written.add(kw)
                    print(
                        f"  {kw}.grep → {output_path} (フォールバック書き出し)",
                        flush=True,
                    )

    print("\n--- 処理完了 ---")
    print(f"処理ファイル: {', '.join(processed_files)}")
    print(f"総行数: {stats.total_lines}  有効: {stats.valid_lines}  スキップ: {stats.skipped_lines}")
    return 0
```

設計判断:

- **完了判定の単位は keyword × handler**: `pending[kw]` が空になった瞬間に書き出す。`as_completed` のループ内で `on_complete` が呼ばれるので、書き出しは親プロセスで直列実行（TSV 1 本ずつ）
- **書き出し I/O は順次**: NFS で複数 TSV を同時書きすると inode 競合の恐れがあるが、シリアルに書くので問題ない
- **`written` セット**: 同じ keyword を二重書きしないガード。`on_complete` は handler 数だけ呼ばれるが、書き出しは keyword あたり 1 回だけ
- **`on_handler_complete` の呼び出し契約**: **親プロセスのメインスレッドから、`as_completed` の同期ループ内でのみ呼ばれる**。`pending` / `indirect_by_keyword` / `written` の更新はロックなしで thread-safe な前提で書く。後続改修で別スレッドや別プロセスから呼ぶ場合はこの契約を破ることになるため、その時点で同期機構を再設計すること。本契約をテストで観測する必要はないが、`on_handler_complete` の docstring と本 spec に明記する
- **`run_full_pipeline` は対象外**: 単一 handler 経路（個別 analyze\_\*.py CLI）は handler 並列化が原理的に効かない。インクリメンタル書き出しも入れず、現行の Phase 3 ループを維持する（影響範囲を最小化）。なお、単一 handler 内での「内側 workers の並列化」は既存通り維持される

### ③ 決定的ソート完全化

`grep_helper/tsv_output.py`:

```python
def _sort_key(r: GrepRecord) -> tuple:
    lineno_int = int(r.lineno) if r.lineno.isdigit() else 0
    return (r.keyword, r.filepath, lineno_int, r.ref_type, r.usage_type)

def _row_sort_key(row: list[str]) -> tuple:
    lineno_int = int(row[4]) if row[4].isdigit() else 0
    # 列順: 0=keyword, 1=ref_type, 2=usage_type, 3=filepath, 4=lineno
    return (row[0], row[3], lineno_int, row[1], row[2])
```

設計判断:

- **`ref_type` + `usage_type` 追加で tie がほぼ消える理由**: 既存の (keyword, filepath, lineno) で tie になるのは、同一 (file, line) に複数の参照種別が出るケース（例: Java の「定数定義」直接 + 同行 setter 経由の間接）。これらは ref_type 文字列でアルファベット順に並ぶ。さらに同一 (keyword, file, line, ref_type) で usage_type だけ違う edge case（同一行が複数の分類カテゴリに該当）も usage_type で並ぶ
- **`code` をソートキーに含めない理由**: 同一 (keyword, file, line, ref_type, usage_type) で `code` だけ違うケースは、regex が同一行から複数 match を抽出して別 record にしている場合（例: 同行に複数変数）に発生しうる。これは現実装でも稀（1 行に複数の参照を出す handler はほぼ無く、grep 行 → record は 1:1）。仮に tie が残った場合は挿入順依存（並列順序依存）となる。本タスクでは「実用上 tie はほぼ発生しない」と見做して `code` をキーから除外する。これにより sort key 比較コストを抑える。完全な決定性を求める後続 spec では `code` を 6 タプル目に加える余地を残す
- **既存スナップショットテストの影響**: tie がある fixture でのみ行順が変わる。`tests/golden/*/expected/` 配下と `tests/test_*.py` のスナップショットを 1 回 regenerate する。実装計画段階で `pytest -q` を空回しして影響テストを列挙
- **`measure_kpi.py` は (filepath, lineno, ref_type) キーのセット比較**: 順序非依存なので無影響

---

## 順序保証の根拠（並列化後の決定性）

要件 §2 の「行セット同一 + 決定的順序」を担保する根拠:

1. **Phase 1 は直列維持**: direct_by_keyword の中身は改造前後で同一（grep ファイル順 → 行順）
2. **Phase 2 は handler 単位で独立**: 各 handler の `batch_track_indirect` は同じ direct_records を受け取り、同じ src_dir を見るため、戻り値の集合は handler 並列化前後で同一
3. **`indirect_by_keyword[kw]` の挿入順は handler の完了順に依存**: 並列化により完了順は実行ごとに変わりうる。よって書き出し直前の `_sort_key` で必ず最終順序を確定させる
4. **`_sort_key` のキー (keyword, filepath, lineno, ref_type, usage_type) は実用上 record 内容で一意**: ただし「**条件付き保証**」である点に注意。同一 5 タプルで `code` フィールドだけ違う tie が残る論理的可能性はある（§決定的ソート 設計判断参照）。本タスクでは「現実装では同行から複数 record を出すケースが稀」を根拠に 5 タプルで打ち切る。tie が残った record 群は挿入順依存（= 並列順序依存）となるため、将来この縁ケースが発覚した場合は `code` を 6 タプル目に加える後続改修を行う

---

## エラー処理

| 局面 | 旧挙動 | 新挙動 |
|---|---|---|
| 1 handler の `batch_track_indirect` で例外 | Phase 2 全体が中断（dispatcher は `return 2`） | **その handler だけスキップ**、他 handler の TSV は出力。`stderr` にエラー出力。`return 0` |
| ProcessPool の `submit` 自体が失敗（fork 不能等） | N/A | エラーログを出して `handler_workers=1` の直列フォールバックに自動切替 |
| `_scan_file_for_patterns` 内の OSError | フィルタ無効化（候補に残す = セーフ側） | 同左 |
| `write_tsv` での書き出し失敗 | 即中断 | 同左（ディスクフルなど致命的なため）|

**1 handler 失敗時の挙動変更について**: 旧実装は Phase 2 で 1 handler が落ちると全体中断していたが、handler 並列化により他 handler は独立して走る。よって 1 handler の失敗を全体失敗にせず、その handler の indirect だけ欠落させて続行する方が運用上の損失が小さい。stderr にエラーは必ず出す。

---

## テスト戦略

`feedback_test_style.md` / `feedback_tdd_stance.md` 準拠。WHAT 検証、日本語メソッド名、古典学派、Red → Green → Refactor。

### B1: handler 並列化

新規 `tests/test_dispatcher_parallel.py`。

ブラックボックス:

- `def test_handler_workers_1_で直列実行されると全handlerが順番に呼ばれる`: `handler_workers=1` で `_run_one_handler` をモンキーパッチして呼び出し順を観察。順序は登録順
- `def test_handler_workers_2_で並列実行されても結果集合は直列と一致する`: 同じ direct_records で `handler_workers=1` と `handler_workers=2` を実行 → 戻り値を `(keyword, filepath, lineno, ref_type, usage_type)` のタプル集合に正規化して比較
- `def test_on_handler_complete_は全handler分呼ばれる`: コールバックの呼び出し回数 = handler 数
- `def test_1handlerの例外は他handlerに伝播しない`: 1 handler の `batch_track_indirect` を例外で差し替え → 他 handler の戻り値が返ってくる

並列化のテストは flaky 回避のため:
- 集合比較（順序非依存）
- `handler_workers=1` のテストで挙動を確定させ、`handler_workers=2` は集合等価性のみ確認

### B2': byte hit cache

`tests/test_source_files.py` に追記。WHAT 検証（HOW = open 呼び出し回数の観察は避ける）。

ブラックボックス:

- `def test_同じパターンを2回問い合わせると2回目はファイル変更後も古い結果が返る`: tmp_path にパターンを含むファイル → `_scan_file_for_patterns([pat])` で True → ファイル内容を削除（パターンを除去）→ `_filter_byte_cache_clear()` を呼ばずにもう一度問い合わせ → True が返る（cache 効果の観察可能事実）
- `def test_異なるパターン集合の2回目は差分判定だけで答えが返る`: 1 回目 `[A, B]` で結果取得 → ファイルから B のみ削除 → 2 回目 `[B, C]` で問い合わせ → B は cache hit のため True、C は未 cache のため新規スキャンされてその時点のファイル状態を反映（A と B の cache 値は変わらない）
- `def test_use_mmap_TrueとFalseでcache結果が同じ`: 既存テストの拡張
- `def test_filter_byte_cache_clear_でcacheが空になる`: clear 後の問い合わせでファイル内容が再度評価される

### B3: インクリメンタル書き出し

dispatcher 経由のため新規 `tests/test_dispatcher_incremental.py`。

ブラックボックス（fake コールバック観察、OS スケジューラ依存を排除）:

- `def test_keyword全handler完了時点でTSVが書き出される`: `apply_indirect_tracking` を fake で差し替え（`on_handler_complete` を順番に呼ぶだけのスタブ）→ 各コールバック後にディスク上の TSV ファイル存在を `Path.exists()` で観察。「最後のコールバック直前は未存在、直後は存在」を確定的に検証する（mtime 観察ではなく**存在のステップ関数**を見る）
- `def test_全handler完了後に全keywordのTSVが出揃う`: 既存テストと等価
- `def test_handler並列順序が違っても最終TSVはバイト一致`: 同じ入力で 3 回実行 → 全 TSV が完全一致（決定的ソートにより）。並列順序依存テストではなく、出力決定性のテスト
- `def test_handler_namesが空でも直接分類のみで全keywordのTSVが出揃う`: indirect handler を全て無効化（fake で `_all_handlers` を空にする）→ `on_handler_complete` は一度も呼ばれないが、初期化時のフォールバックで全 keyword の TSV が書き出される（後述の縁ケース対応）

「軽量 grep / 重量 grep を投入して mtime で順序観察」のような OS スケジューラ依存テストは flaky の温床になるため避ける。WHAT 検証としては `on_handler_complete` の fake 駆動で十分。

### ③ 決定的ソート

`tests/test_tsv_output.py` を新規 or 追記。

ホワイトボックス（_sort_key 単体テストは不要、ブラックボックスで足りる）:

- `def test_同一_file_line_に複数_ref_type_があるとref_type順で並ぶ`: tie のある fixture で `write_tsv` → ref_type のアルファベット順に並ぶこと

### 既存テスト・golden データの更新

`tests/golden/*/expected/*.tsv` のうち tie がある fixture は 1 回 regenerate。具体的には `_sort_key` 拡張を適用してから `pytest -q` を空回し → 失敗した snapshot を手動更新（あるいは `analyze_all.py` で actual TSV を再生成して `tests/golden/*/expected/` にコピー）して揃える。実装計画の最初のステップ（§ロールアウト計画 #1）で対象 fixture を列挙する。

---

## 検証 (V-1: KPI before/after)

### 起動経路の確認

`scripts/measure_kpi.py` は **`pipeline.run_full_pipeline` を呼ぶ**（`scripts/measure_kpi.py:447` の `run_full_pipeline(...)`）。`pipeline.run_full_pipeline` は本タスクで無変更のため、KPI スクリプト経由では handler 並列化・インクリメンタル化の効果は出ない。**KPI スクリプトは網羅率・分類精度の回帰チェック専用**（行セット一致の検証）と位置付ける。

性能効果の計測は **`analyze_all.py` (dispatcher 経由)** で別途行う。これにより `--handler-workers 2` 既定値が効く。

実装計画のクロージング条件として以下を実施:

```bash
# 1. KPI 回帰チェック（pipeline 経由、性能変化は出ないが網羅率・分類精度の同値を確認）
$ python scripts/measure_kpi.py --lang all > /tmp/kpi_before.txt   # main ブランチで
$ python scripts/measure_kpi.py --lang all > /tmp/kpi_after.txt    # 本ブランチで
$ diff /tmp/kpi_before.txt /tmp/kpi_after.txt    # 網羅率・分類精度の同値

# 2. 性能計測（dispatcher 経由、handler 並列化・インクリメンタル化の効果を観測）
#    注意: main ブランチには --handler-workers フラグが存在しないため、before 側では渡せない。
#    before 側は実質 handler_workers=1（旧直列）相当、after 側は --handler-workers 2 で並列。
#    --workers の値は揃えて、handler 並列化単独の差分を見るため両側に同じ値を渡す。
$ time python analyze_all.py --source-dir <代表ソース> --workers 2 \
       > /tmp/run_before.txt 2>&1                                          # main で
$ time python analyze_all.py --source-dir <代表ソース> --workers 2 --handler-workers 2 \
       > /tmp/run_after.txt 2>&1                                           # 本ブランチで

# 3. TSV 行セット一致（決定的ソート後）
$ for f in output/*.tsv; do diff $f main_output/$f; done

# 4. メモリ使用量（B2' cache の試算検証）
$ /usr/bin/time -v python analyze_all.py --source-dir <代表ソース> --workers 2 --handler-workers 2 \
       2>&1 | grep "Maximum resident set size"   # worker あたり 200 MB 超なら LRU 化検討
```

KPI 値は同一、wall clock は短縮、TTFB（最初の TSV までの時間）は大幅短縮、を期待値とする。Solaris 実機計測は本タスクのスコープ外（`scripts/smoke_solaris.md` の手順で個別検証）。

---

## ロールアウト計画

1. `_sort_key` / `_row_sort_key` の決定的化 → **golden 再生成はこのステップでのみ実施**（後続ステップで差分が出たら blocker 扱い、再生成では誤魔化さない）
2. `grep_filter_files` の byte hit cache 追加（API 不変、`_filter_byte_cache_clear()` 公開）→ `pytest -q` 全パス。golden は再生成しない（前ステップで確定済み）
3. `apply_indirect_tracking` の `handler_workers` / `on_handler_complete` 引数追加（後方互換、関数デフォルトは `handler_workers=1`、`on_handler_complete=None`）→ `pytest -q` 全パス。golden は再生成しない
4. `dispatcher.main` のインクリメンタル書き出し化 + CLI `--handler-workers 2` 既定 → `pytest -q` 全パス。golden は再生成しない
5. §V-1 検証: KPI 回帰チェック + 性能計測 + メモリ使用量計測

**golden 再生成ポリシー**: ステップ 1 で決定的ソートの仕様変更に伴う影響を一度だけ吸収する。ステップ 2 以降で `tests/golden/` との差分が出るのは並列化のバグ（行内容の欠落・重複・挿入順依存 tie）を示すため、ここで再生成すると問題を隠蔽してしまう。**ステップ 2 以降は差分ゼロを必須条件**とし、出た場合は実装ステップを巻き戻して原因究明する。

各ステップで `pytest -q` を通し、最後に Solaris スモーク (`scripts/smoke_solaris.md`) を手動で実行する。
