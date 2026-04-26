# grep-helper 全体リファクタ設計書

- 作成日: 2026-04-26
- 対象: `/workspaces/grep_helper_superpowers/`（grep-helper ツール本体）
- 種別: 設計（spec）
- 後続: `writing-plans` で実装プラン化 → 実装

---

## 1. 目的とスコープ

### 1.1 背景と動機

grep-helper は 14 個の `analyze_*.py` がリポジトリ root にフラットに並ぶ構成で、`analyze*.py` 合計 5,319 行（`aho_corasick.py` 65 行を加えると 5,384 行）。以下の構造的問題が累積している。

1. **巨大ファイル**: `analyze.py`（Java, 1,636 行）と `analyze_all.py`（1,100 行）。
2. **重複コード**: 各言語アナライザの `process_grep_file` / `build_parser` / `main` が同型で 14 ファイルに反復。`analyze_all.py` 内に言語ごとの batch tracker 5 セット（`_scan_files_for_*` / `_batch_track_*`）が並ぶ。
3. **責務の混雑**: `analyze_common.py` が dataclass / TSV / キャッシュ / scanner / encoding 検出の雑多な 8 機能を抱える。
4. **内部 API 漏れ**: `analyze_all.py` が各言語モジュールの private 関数を `# type: ignore[attr-defined]` で吸い出している（`_batch_track_combined` / `_get_method_scope` / `_build_define_map_c` 等）。

### 1.2 スコープ

- **In Scope**: コード本体の再編成 + テストの import パス更新 + docs の新構造への書き直し。リファクタ過程で見える「明らかな重複の畳み込み」（特に `analyze_all.py` の言語ごと重複バッチトラッカー）も含む。
- **Out of Scope**: 性能改善、機能追加、`pyproject.toml` 化、entry_points 登録、PyPI 公開、mypy strict 化、Python 最低バージョン変更、CI 追加。

### 1.3 不変の契約（リファクタ全体を通して守る）

1. CLI 名・引数: `python analyze.py --source-dir … --input-dir … --output-dir … --encoding … --workers …` および `analyze_<lang>.py` 全 11 個 + `analyze_all.py`。
2. TSV 出力: 列順・列名（"文言/参照種別/使用タイプ/ファイルパス/行番号/コード行/参照元変数名/参照元ファイル/参照元行番号"）・UTF-8 BOM 付き・タブ区切り・ソート順（keyword → filepath → lineno）。
3. 性能特性: grep ファイルストリーミング、LRU 256MB 既定、`--workers` 並列、Aho-Corasick / regex 自動切替閾値（100）。
4. 依存: `requirements.txt`（`javalang / chardet / pyahocorasick`）と `requirements-dev.txt`（`pytest`）の中身、`wheelhouse/` 構成。
5. `pyahocorasick` 不在時の Pure Python AC フォールバック挙動。

---

## 2. 設計方針

### 2.1 進め方: 段階的リファクタ + CLI 互換維持（内部は再構成、表面は不変）

- 内部実装は大胆に作り直す。ただしルートの `analyze*.py` 14 個は **shim** として残す（中身 5〜10 行で `grep_helper` 配下を呼ぶだけ）。
- 各フェーズの終了条件: `pytest tests/ -v` 全緑 + 既存 CLI が動く。フェーズごとに最低 1 コミット。

### 2.2 言語ハンドラ契約: モジュール = ハンドラ（緩やかな duck typing）

各言語モジュールは **トップレベル関数で契約を満たす**。Protocol クラスは型注釈用に置くが、強制継承はしない。

**ClassifyContext（共通コンテキスト）** — Java の特殊シグネチャを統一するためのデータクラス:

```python
# grep_helper/model.py
@dataclass(frozen=True)
class ClassifyContext:
    filepath: str
    lineno: int
    source_dir: Path
    stats: ProcessStats
    encoding_override: str | None
```

**必須シンボル:**
- `EXTENSIONS: tuple[str, ...]` — 拡張子（例: `(".java",)`、`(".kt", ".kts")`）
- `classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str` — 全言語で同一シグネチャ。Java など AST を見る言語は `ctx` を読む。シンプル言語（`python` `perl` `ts` 等）は `ctx` 引数を**受け取って無視する**（`# noqa: ARG001` などで明示）。dispatcher は常に `ctx` を渡す。

**任意シンボル:**
- `batch_track_indirect(direct_records: list[GrepRecord], src_dir: Path, encoding: str | None, *, workers: int = 1) -> list[GrepRecord]` — 間接追跡。**引数は dispatcher が集めた全言語分の直接参照レコード**で、ハンドラ内で自言語ぶんに絞り込む（`detect_handler(rec.filepath, src_dir) is self_module` でフィルタ）。返り値は当該言語が発見した間接参照レコード。dispatcher は `getattr(handler, "batch_track_indirect", None)` で有無判定。
- `SHEBANGS: tuple[str, ...]` — シバン判定が要る言語（sh / perl）が宣言。例: `sh.py` は `("sh", "bash", "csh", "tcsh", "ksh", "ksh93")`。`grep_helper/languages/__init__.py` がこれらを走査して **shebang → handler** マップを組み立てる（凝集度を高めるため、シバン知識を各言語に分散）。

**ハンドラ解決順**（`detect_handler` の挙動・§4.2 で詳述）:
1. ファイル拡張子を `EXT_TO_HANDLER: dict[str, ModuleType]` で引く
2. 拡張子なしの場合のみ、ファイル先頭行を読む（**I/O が発生する**）→ シバンを `SHEBANG_TO_HANDLER` で引く
3. いずれもヒットしなければ `_none` ハンドラ（`classify_usage(code) -> "その他"`、`batch_track_indirect` なし）

### 2.3 状態管理

モジュールレベルキャッシュ（`_ast_cache` / `_file_lines_cache` / `_resolve_file_cache` 等）は**現状のまま維持**。クラス化はしない。理由:
- ProcessPoolExecutor で pickle するためのコストとリターンが見合わない。
- 既存テストの `_*_clear()` クリア API がそのまま使える。

**キャッシュのオブジェクト同一性保持（重要）**:
既存テストは dict オブジェクトそのものに対して assertion を行っている（例: `tests/test_common.py` の `assertIn(str(p), _file_lines_cache)`、`tests/test_analyze_proc.py:151` の `_define_map_cache.clear()`、`tests/test_analyze.py:21,428` の `_ast_cache` 参照）。したがって以下のキャッシュは **新パッケージで定義した dict オブジェクトを、shim が `from grep_helper.X import _Y as _Y` の形で参照のまま再 export** する必要がある（`from … import *` だけでは保証されない）。再代入は禁止。

| キャッシュ | 定義場所（新） | shim 経由で同一性を保つ参照元（旧） |
|---|---|---|
| `_file_lines_cache` (OrderedDict) | `grep_helper.file_cache` | `analyze_common._file_lines_cache` |
| `_source_files_cache` (dict) | `grep_helper.source_files` | `analyze_common._source_files_cache` |
| `_resolve_file_cache` (dict) | `grep_helper.source_files` | `analyze_common._resolve_file_cache` |
| `_define_map_cache` (dict) | `grep_helper.languages.proc_define_map` および `grep_helper.languages.c` | `analyze_proc._define_map_cache` / `analyze_c._define_map_cache` |
| `_ast_cache` (dict) | `grep_helper.languages.java_ast` | `analyze._ast_cache` |
| `_ast_line_index` (dict) | `grep_helper.languages.java_ast` | `analyze._ast_line_index` |
| `_method_starts_cache` (dict) | `grep_helper.languages.java_ast` | `analyze._method_starts_cache` |

Phase 1 / Phase 5 / Phase 6 のコミットでは、**当該テストが `assertIn` 等で dict 同一性に依存している箇所を grep で抽出 → 同一性が保たれていることを `assert old_module._X is new_module._X` で確認するスクリプトをローカルで実行**する手順を含める。

**ProcessPoolExecutor ワーカー内のキャッシュ**:
ワーカープロセスは fork/spawn 後それぞれ空のモジュールキャッシュを持つ。現状の `analyze_all.py` は `_build_define_map` を**メインプロセスで事前構築し、結果 dict を `scan_tasks` 引数としてワーカーに渡している**（`analyze_all.py:705` 付近）。新設計の `batch_track_indirect` でも**この事前構築 → 引数渡しのパターンを維持**する。ワーカー内で `_build_define_map` を再ビルドする実装に変えると `--workers=N` で N 回ビルドされ性能が退化するため禁止。

---

## 3. ターゲット構造

```
grep_helper_superpowers/
├── analyze.py                    # shim（CLI互換のため改名不可）
├── analyze_all.py                # shim
├── analyze_c.py / analyze_proc.py / analyze_kotlin.py / analyze_dotnet.py /
│   analyze_groovy.py / analyze_sh.py / analyze_sql.py / analyze_plsql.py /
│   analyze_ts.py / analyze_python.py / analyze_perl.py            # shim
│
├── grep_helper/
│   ├── __init__.py
│   ├── model.py                  # GrepRecord / ProcessStats / RefType / UsageType
│   ├── cli.py                    # 共通 argparse 雛形 + main 雛形
│   ├── pipeline.py               # grep行 → classify → write_tsv の汎用フロー
│   ├── dispatcher.py             # 全言語ディスパッチ（旧 analyze_all.py 相当）
│   ├── encoding.py               # detect_encoding
│   ├── grep_input.py             # parse_grep_line / iter_grep_lines
│   ├── tsv_output.py             # write_tsv（外部ソート含む）
│   ├── source_files.py           # iter_source_files / grep_filter_files / resolve_file_cached
│   ├── file_cache.py             # cached_file_lines（LRU）
│   ├── scanner.py                # build_batch_scanner（AC / regex 自動選択）
│   ├── _aho_corasick.py          # Pure Python AC（フォールバック）
│   │
│   └── languages/
│       ├── __init__.py           # 拡張子→モジュール登録テーブル + シバン判定
│       │
│       ├── java.py               # Java の公開 API
│       ├── java_ast.py           # AST キャッシュ + AST ベース分類
│       ├── java_classify.py      # 正規表現分類 + scope 判定
│       ├── java_track.py         # field / local / getter / setter トラッキング
│       │
│       ├── proc.py               # Pro*C の公開 API
│       ├── proc_define_map.py    # #define reverse map ビルド・キャッシュ
│       ├── proc_track.py         # define / variable / host_var トラッキング
│       │
│       ├── c.py                  # C: 1ファイル
│       ├── groovy.py             # Groovy: 1ファイル
│       ├── kotlin.py             # Kotlin: 1ファイル
│       ├── dotnet.py             # C#/VB: 1ファイル
│       ├── sh.py                 # Shell: 1ファイル
│       ├── sql.py                # SQL: 1ファイル
│       ├── plsql.py              # PL/SQL: 1ファイル
│       ├── ts.py                 # TS/JS: 1ファイル
│       ├── python.py             # Python: 1ファイル
│       ├── perl.py               # Perl: 1ファイル
│       └── _none.py              # 言語不明用 no-op ハンドラ
│
├── tests/                        # importパスのみ更新
├── docs/                         # 新構造に書き直し
├── input/  output/  wheelhouse/  # 不変
└── requirements.txt / requirements-dev.txt / .flake8 / CLAUDE.md / README.md
```

**フォルダ階層原則**: `grep_helper/` 直下と `grep_helper/languages/` 直下のみ。`io/` のようなサブフォルダは作らない。言語ファイルは **言語名プレフィックス**（`java_*.py` `proc_*.py`）でファイル名から内容を識別する。

---

## 4. 各モジュールの責務

### 4.1 `grep_helper/` 直下

| ファイル | 責務 | 移植元 |
|---|---|---|
| `model.py` | `GrepRecord`（NamedTuple）/ `ProcessStats`（dataclass）/ `RefType`（Enum）/ `UsageType`（Enum） | `analyze_common.py` + `analyze.py` 冒頭 |
| `encoding.py` | `detect_encoding(path, override)` — chardet 判定（4096 バイト先読み・しきい値 0.6） | `analyze_common.py` |
| `grep_input.py` | `iter_grep_lines(path, encoding)` / `parse_grep_line(line)` / バイナリ行・空行スキップ判定 | `analyze_common.py` |
| `tsv_output.py` | `write_tsv(records, output_path)` — 100万行を超えたら外部ソート（チャンク → heapq.merge） | `analyze_common.py` |
| `source_files.py` | `iter_source_files` / `grep_filter_files`（mmap 事前フィルタ）/ `resolve_file_cached` + テスト用 `_*_clear` | `analyze_common.py` |
| `file_cache.py` | `cached_file_lines` LRU（既定 256MB）+ `set_file_lines_cache_limit` + テスト用 `_clear` | `analyze_common.py` |
| `scanner.py` | `build_batch_scanner(patterns, threshold=100)` — pyahocorasick → `_aho_corasick` の順にフォールバック | `analyze_common.py` |
| `_aho_corasick.py` | Pure Python AC 実装 | `aho_corasick.py` |
| `pipeline.py` | `process_grep_file(grep_path, src_dir, handler, *, encoding) -> ProcessStats` 汎用フロー | 各 `analyze_*.py` の `process_grep_file` の共通骨格 |
| `cli.py` | 共通 argparse + `run(handler) -> int` 関数 | 各 `analyze_*.py` の `build_parser` / `main` |
| `dispatcher.py` | 全言語モード: 拡張子で振り分け、間接追跡は登録ハンドラ全部に対し `batch_track_indirect` 順次実行 | `analyze_all.py` |

### 4.2 `grep_helper/languages/` 直下

`__init__.py` がレジストリの中心。各言語モジュールから `EXTENSIONS` と（あれば）`SHEBANGS` を import し、以下を組み立てる:

```python
# grep_helper/languages/__init__.py の概念コード
from . import java, kotlin, c, proc, sh, perl, ...  # 全言語
_HANDLERS = (java, kotlin, c, proc, sh, perl, ...)
EXT_TO_HANDLER: dict[str, ModuleType] = {
    ext: h for h in _HANDLERS for ext in h.EXTENSIONS
}
SHEBANG_TO_HANDLER: dict[str, ModuleType] = {
    sb: h for h in _HANDLERS if hasattr(h, "SHEBANGS") for sb in h.SHEBANGS
}

def detect_handler(filepath: str, src_dir: Path) -> ModuleType:
    ext = Path(filepath).suffix.lower()
    if ext:
        return EXT_TO_HANDLER.get(ext, _none)
    # 拡張子なし → シバン判定（ファイル先頭行を読む = I/O 発生）
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
```

**注**: `.h` は C のみに割り当てる（C++ サポートはスコープ外）。これは現状 `analyze_all.py:24` の `_EXT_TO_LANG` も同じ判断であり、新設計でも維持する。

| ファイル | 公開シンボル（共通契約） | 公開シンボル（言語固有） |
|---|---|---|
| `__init__.py` | `EXT_TO_HANDLER` / `SHEBANG_TO_HANDLER` / `detect_handler(filepath, src_dir) -> ModuleType` | — |
| `java.py` | `EXTENSIONS=(".java",)` / `classify_usage` / `batch_track_indirect` | `extract_variable_name` 等を `java_track` から re-export |
| `java_ast.py` | — | `get_ast` / `_ast_cache` / `_method_starts_cache` / `_get_or_build_ast_index` |
| `java_classify.py` | — | `classify_usage_regex` / `determine_scope` / `_classify_by_ast` |
| `java_track.py` | — | `track_field` / `track_local` / `find_getter_names` / `find_setter_names` / `_batch_track_combined` |
| `proc.py` | `EXTENSIONS / classify_usage / batch_track_indirect` | — |
| `proc_define_map.py` | — | `_build_define_map` / `_get_reverse_define_map` |
| `proc_track.py` | — | `track_define` / `track_variable` / `extract_host_var_name` |
| `c.py` | `EXTENSIONS=(".c", ".h")` / `classify_usage` / `batch_track_indirect` | `_build_define_map` / `_get_reverse_define_map` / `track_variable` |
| `groovy.py` | `EXTENSIONS / classify_usage / batch_track_indirect` | `track_field_groovy` 等 |
| `kotlin.py` / `dotnet.py` | `EXTENSIONS / classify_usage / batch_track_indirect` | 既存ロジック |
| `sh.py` | `EXTENSIONS=(".sh", ".bash") / SHEBANGS=("sh","bash","csh","tcsh","ksh","ksh93") / classify_usage` | 既存ロジック |
| `perl.py` | `EXTENSIONS=(".pl", ".pm") / SHEBANGS=("perl",) / classify_usage` | 既存ロジック |
| `sql.py` / `ts.py` / `python.py` / `plsql.py` | `EXTENSIONS / classify_usage` のみ（間接追跡なし、`batch_track_indirect` 未定義） | 既存ロジック |
| `_none.py` | `EXTENSIONS=()` / `classify_usage(code, *, ctx=None) -> "その他"` | — |

### 4.3 `analyze_all.py` 内重複バッチトラッカーの畳み込み

現在 `analyze_all.py` 内に並んでいる以下 5 セットを、**各言語ファイルの `batch_track_indirect` に統合**:

- `_scan_files_for_kotlin_const` / `_batch_track_kotlin_const` → `kotlin.py`
- `_scan_files_for_dotnet_const` / `_batch_track_dotnet_const` → `dotnet.py`
- `_scan_files_for_groovy_static_final` / `_batch_track_groovy_static_final` → `groovy.py`
- `_scan_files_for_define_c_all` / `_batch_track_define_c_all` → `c.py`
- `_scan_files_for_define_proc_all` / `_batch_track_define_proc_all` → `proc.py`

### 4.4 `_apply_indirect_tracking`（188 行のレコード分配ロジック）の移動先

現在 `analyze_all.py:834-1022` にある `_apply_indirect_tracking` は、直接参照レコードを言語別に振り分けつつ、各言語固有のヘルパ（`extract_variable_name` / `_resolve_java_file` / `_get_method_scope` / `extract_define_name` / `is_class_level_field` 等）を呼び出している。これは「**レコード分配 + 自言語の前処理**」のロジックで、言語ごとに異なる。

新設計ではこのロジックを **dispatcher と各言語の `batch_track_indirect` に分離**する:

- **dispatcher.py**:
  ```python
  def apply_indirect_tracking(direct_records, src_dir, encoding, *, workers):
      results = []
      for handler in _HANDLERS:
          fn = getattr(handler, "batch_track_indirect", None)
          if fn is None:
              continue
          results.extend(fn(direct_records, src_dir, encoding, workers=workers))
      return results
  ```
  dispatcher は **全レコードをそのまま渡す** だけ。フィルタ・前処理は知らない。

- **各言語の `batch_track_indirect`**:
  受け取った `direct_records` のうち「自分が処理すべきレコード」を内部で抽出（`detect_handler(rec.filepath, src_dir) is current_module` で判定）し、そのレコード集合に対して既存の前処理（変数名抽出・スコープ判定・define マップ参照など）+ 並列バッチスキャンを実行する。

これにより:
- dispatcher 側のロジックは ~10 行に縮む。
- 言語固有の前処理が言語モジュール内に閉じる（cross-module の private 関数参照が消える）。
- 新言語追加時、dispatcher を編集する必要がない。

---

## 5. 移行手順（フェーズ分割）

各フェーズの終了条件: `pytest tests/ -v` 全緑 + 既存 CLI が動く。フェーズごとに 1 コミット以上。

### Phase 0: パッケージ骨格と契約の準備
- `grep_helper/__init__.py` と `grep_helper/languages/__init__.py` を空で作る。
- `grep_helper/cli.py` `pipeline.py` の空 stub（型シグネチャだけ）を置く。
- ハンドラ契約を `grep_helper/__init__.py` の docstring に明記。
- テスト変更なし。CLI 変更なし。

### Phase 1: インフラ層を分解移植
`analyze_common.py` を以下に分解:
- `model.py` ← `GrepRecord` `ProcessStats` `RefType`
- `encoding.py` ← `detect_encoding`
- `grep_input.py` ← `iter_grep_lines` `parse_grep_line` `_BINARY_PATTERN` 等
- `tsv_output.py` ← `write_tsv` + 外部ソート
- `source_files.py` ← `iter_source_files` `grep_filter_files` `resolve_file_cached` + キャッシュ
- `file_cache.py` ← `cached_file_lines` LRU
- `scanner.py` ← `build_batch_scanner`
- `_aho_corasick.py` ← ルートの `aho_corasick.py` を移動

互換性: `analyze_common.py` は当面残す。中身を空にして、**§2.3 のキャッシュ同一性表に挙げた dict は `from grep_helper.X import _Y as _Y` の参照 re-export**、その他の関数・クラスは `from grep_helper.model import *` 等で再 export。Phase 7 で削除。
ルート `aho_corasick.py` も同様に shim 化、Phase 7 で削除。

**Phase 1 終了時の検証スクリプト**（必須・コミット前に実行）:
```python
import analyze_common, grep_helper.file_cache, grep_helper.source_files
assert analyze_common._file_lines_cache is grep_helper.file_cache._file_lines_cache
assert analyze_common._source_files_cache is grep_helper.source_files._source_files_cache
assert analyze_common._resolve_file_cache is grep_helper.source_files._resolve_file_cache
```
（同種の `is` チェックを Phase 5・6 でも該当言語キャッシュに対して実施。）

### Phase 2: pipeline と CLI 雛形の組み立て
- `grep_helper/cli.py` に `build_parser()` `run(handler) -> int` を実装。共通 argparse（`--source-dir / --input-dir / --output-dir / --encoding / --workers`）。
- `grep_helper/pipeline.py` に `process_grep_file(grep_path, src_dir, handler, *, encoding, workers) -> ProcessStats` を実装。
- 既存のシンプル言語の `process_grep_file` の共通骨格を pipeline 側に吸い上げ。
- テスト変更なし。

### Phase 3: シンプル 6 言語を移植（間接追跡なし）
対象: `python / perl / ts / plsql / sh / sql`。順序は小さい順（依存薄い順）。各言語 1 コミット推奨。

各言語の手順:
1. `grep_helper/languages/<lang>.py` を新規作成し、`classify_usage_<lang>` を `classify_usage` にリネームして移植。`EXTENSIONS` 定数を追加。`batch_track_indirect` は定義しない（duck typing で no-op 扱い）。
2. ルート `analyze_<lang>.py` を shim に置き換え:
   ```python
   from grep_helper.cli import run
   from grep_helper.languages import <lang> as handler
   if __name__ == "__main__":
       raise SystemExit(run(handler))
   ```
3. shim 内で `from grep_helper.languages.<lang> import *` を実行し、テストの `from analyze_<lang> import classify_usage_<lang>` が壊れないよう旧名を一時 alias する（Phase 7 で撤去）。

### Phase 4: 中規模 4 言語を移植（間接追跡あり: Kotlin / .NET / Groovy / C）
対象: `kotlin / dotnet / groovy / c`。各言語 1 コミット推奨。

各言語の手順:
1. Phase 3 と同様に `classify_usage` を移植。
2. **`batch_track_indirect` を実装**: 既存の各言語側ロジック（`track_const` / `track_field_groovy` / `track_variable` 等）+ `analyze_all.py` 内の対応するバッチトラッカー（`_scan_files_for_kotlin_const / _batch_track_kotlin_const`、`_scan_files_for_dotnet_const / _batch_track_dotnet_const`、`_scan_files_for_groovy_static_final / _batch_track_groovy_static_final`、`_scan_files_for_define_c_all / _batch_track_define_c_all`）を**該当言語ファイルに吸い上げて統合**。
3. `analyze_all.py` 側の対応関数は当面残し、`from grep_helper.languages.<lang> import batch_track_indirect` の薄いラッパに変更。
4. ルート `analyze_<lang>.py` を shim 化。

### Phase 5: Pro*C を移植
- `analyze_proc.py` を `proc.py + proc_define_map.py + proc_track.py` に分解。
- `analyze_all.py` の `_scan_files_for_define_proc_all / _batch_track_define_proc_all` を吸い上げて統合。

### Phase 6: Java を移植（最大の山場）
`analyze.py`（1,636 行）を 4 ファイルに分解:
- `java.py` ← **オーケストレーション層**: 公開 API（`EXTENSIONS` / `classify_usage` / `batch_track_indirect`）を実装。`java_classify` と `java_track` を**共に呼び出す**。`analyze.py:1547-1597` のオーケストレーションブロック相当。
- `java_ast.py` ← AST キャッシュ系（`_ast_cache` / `_ast_line_index` / `_method_starts_cache` / `get_ast` / `_get_or_build_ast_index`）。最下層。
- `java_classify.py` ← 純粋な分類ロジック（`classify_usage_regex` / `_classify_by_ast` / `determine_scope`）。`java_ast` のみに依存。
- `java_track.py` ← トラッキング（`track_field` / `track_local` / `find_getter_names` / `find_setter_names` / `_batch_track_combined` / `_get_method_scope`）。`java_ast` のみに依存。

依存方向は **`java_ast → {java_classify, java_track} → java`** の DAG（`java_classify` と `java_track` は互いを参照しない兄弟関係）。`java.py` だけが両者を呼び出してオーケストレーションする。これにより `analyze.py:1555` 付近の「`determine_scope` を呼んでから `track_field` `find_getter_names` `find_setter_names` `track_local` を呼ぶ」フローは `java.py` 側に移し、`java_classify.py` から `java_track.py` への参照を発生させない。循環 import を避ける。

`analyze_all.py` の Java 関連 import（`_batch_track_combined` 等）は `from grep_helper.languages.java import batch_track_indirect` 1 本に統合。**`grep_helper/` 配下のコードでは `# type: ignore[attr-defined]` を 0 件にする**（shim 層では旧シンボル alias re-export のために `# type: ignore` が残る場合があり、これは Phase 7 のクリーンアップ完了時に消滅する）。

ルート `analyze.py` を shim 化 + 旧シンボル alias で既存テスト互換維持。

### Phase 7: dispatcher 移植 + クリーンアップ
- `analyze_all.py` の本体を `grep_helper/dispatcher.py` に移植。
- `analyze_all.py` を shim 化。
- 既存テストの import を新パスに一括置換（`from analyze_<lang> import …` → `from grep_helper.languages.<lang> import …` 等）。テストファイル構成は変えない、import パスのみ。
- shim 内の旧名 alias を削除。
- ルート `analyze_common.py` `aho_corasick.py` を物理削除。
- 最終的に shim 14 個はそれぞれ 5〜10 行に。

### Phase 8: docs 更新
- `docs/architecture.md` `docs/repository-structure.md` `docs/functional-design.md` `docs/tool-overview.md` `docs/development-guidelines.md` を新構造で書き直し。
- README の「リポジトリ構成」を追記。実行例の CLI コマンド名は不変。

---

## 6. テスト戦略

**基本方針**: 既存テストは「機能の網羅性を維持したまま、import パスのみ更新」。テストの構造・観点・ファイル分割は変えない。

### 6.1 既存テストの取り扱い

| テストファイル | サイズ | 方針 |
|---|---:|---|
| `test_analyze.py` | 80KB | import を `from analyze import …` → `from grep_helper.languages.java import …` 等に置換 |
| `test_all_analyzer.py` | 22KB | import を `from analyze_all import …` → `from grep_helper.dispatcher import …` に置換 |
| `test_analyze_proc.py` | 20KB | `from analyze_proc import …` → `from grep_helper.languages.proc import …` |
| `test_common.py` | 15KB | `from analyze_common import …` → `grep_helper` 配下の各モジュール（`grep_helper.grep_input` `tsv_output` 等）に分散 |
| `test_c_analyzer.py` | 12KB | `from analyze_c import …` → `from grep_helper.languages.c import …` |
| `test_dotnet_analyzer.py` | 9KB | 同様 |
| `test_groovy_analyzer.py` | 9KB | 同様 |
| `test_kotlin_analyzer.py` | 7KB | 同様 |
| `test_aho_corasick.py` | 2KB | `from aho_corasick import …` → `from grep_helper._aho_corasick import …` |
| その他小テスト | 各 3〜5KB | 同様（一括置換可能） |

### 6.2 Private シンボルへの参照

現状テストは `from analyze import _batch_track_combined` のような private シンボルを直接 import している箇所が多い。

- **Phase 6 完了時点では旧パスでは動かなくなる** → shim 内で `from grep_helper.languages.java.java_track import _batch_track_combined` のように旧シンボルを alias re-export することで、テスト変更を Phase 7 のクリーンアップにまとめて遅延できる。
- **Phase 7 で alias を削除する際**、テストの import を新パスへ一括置換。

### 6.3 各 Phase での pytest 緑保持の保証

- Phase 1〜6 中: `analyze_common.py` `aho_corasick.py` `analyze_<lang>.py` `analyze_all.py` はすべて shim として旧シンボルを re-export し続ける。既存テストの import は壊れない。フェーズ完了時に必ず `pytest tests/ -v` を全緑化してからコミット。
- Phase 7: テスト import 一括置換 → shim alias 削除 → `analyze_common.py` `aho_corasick.py` 物理削除 → 全緑確認 → コミット。
- Phase 8: docs のみ変更、コードに触らないので pytest は不変。

### 6.4 新規テストは追加しない

スコープ B（リファクタ中の重複畳み込みは許可、機能変更はしない）の方針に従い、新規テストは追加しない。`dispatcher.py` のハンドラ駆動ロジックは既存の `test_all_analyzer.py` でカバーされている。

### 6.5 キャッシュクリア用 `_*_clear()` 関数とオブジェクト同一性

新パッケージ側でも同名で公開（`grep_helper.source_files._source_files_cache_clear` 等）。テストは原則 import パスのみ変更。

**ただし**: 既存テストの一部は dict オブジェクトそのものに対して `assertIn(...)` 等の assertion を行っている（例: `tests/test_common.py:262-292` の `_file_lines_cache`、`tests/test_analyze_proc.py:151` の `_define_map_cache.clear()`、`tests/test_analyze.py:21,428` の `_ast_cache`）。これらのテストは「単純 find-replace で済まない」ケースに該当する。

対応:
- §2.3 の同一性保持表に従い、shim と新パッケージ両方から **同一 dict を参照で公開**する設計とする。
- Phase 7 のテスト import 一括置換時、**dict 参照テスト** は §2.3 の表に従って新パスへ向け直す。具体的には:
  - `from analyze_common import _file_lines_cache` → `from grep_helper.file_cache import _file_lines_cache`
  - `from analyze import _ast_cache` → `from grep_helper.languages.java_ast import _ast_cache`
  - `from analyze_proc import _define_map_cache` → `from grep_helper.languages.proc_define_map import _define_map_cache`
  - `from analyze_c import _define_map_cache` → `from grep_helper.languages.c import _define_map_cache`
- Phase 7 で `grep -rn "_ast_cache\|_file_lines_cache\|_define_map_cache\|_source_files_cache\|_resolve_file_cache\|_ast_line_index\|_method_starts_cache" tests/` を実行して、対象テストの全箇所を漏れなく置換できたことを確認する。

### 6.6 テストの並列実行に関する注意

現在テストは pytest の単一プロセスで動かしている前提で、`setUp` で `_*_clear()` を呼ぶ規律によって test 間の汚染を防いでいる。新設計でもこの前提を継承する（`pytest-xdist` 並列実行は導入しない）。docs（`docs/development-guidelines.md`）にも「テストはモジュールキャッシュのクリア規律に依存しているため `pytest-xdist` を導入しないこと」を一行で明記する。

### 6.7 CI / lint

- `.flake8` 設定（max-line-length=120）はそのまま。
- `pytest` 実行コマンドは不変（`python -m pytest tests/ -v`）。
- 各フェーズで lint が通ることも併せて確認。

---

## 7. docs 更新方針（Phase 8）

| ドキュメント | 更新方針 |
|---|---|
| `README.md` | 「対応言語」表のスクリプト名（CLI コマンド名）は不変。「リポジトリ構成」の説明だけ追記。実行例は不変。 |
| `docs/architecture.md` | 大幅書き直し。新構造のレイヤ図と責務分担。`io 系 / scanner / pipeline / dispatcher / languages` の関係図。 |
| `docs/repository-structure.md` | 全面書き直し。新ディレクトリツリーとファイル単位の責務一覧。 |
| `docs/functional-design.md` | 関数名・モジュール名を新パスに更新。処理フロー図は基本維持。 |
| `docs/tool-overview.md` | モジュール参照の名前を新パスに置換。フロー説明は不変。 |
| `docs/glossary.md` | 不変。 |
| `docs/product-requirements.md` | 不変。 |
| `docs/development-guidelines.md` | 「新言語の追加手順」をハンドラ契約ベースで全面書き直し。手順: ① `grep_helper/languages/<lang>.py` を作成、② `EXTENSIONS` と `classify_usage` を実装、③ 必要なら `batch_track_indirect` を追加、④ `__init__.py` の `EXT_TO_HANDLER` に登録、⑤ tests を追加、⑥ docs を更新。 |
| `docs/superpowers/specs/2026-04-26-refactor-design.md` | 本書。 |

---

## 8. リスクと緩和策

| リスク | 緩和策 |
|---|---|
| Java 4 ファイル分解で循環 import を踏む | Phase 6 で `java_ast → {java_classify, java_track} → java` の DAG を保つ（§5 Phase 6 で詳述）。`java.py` がオーケストレーション層として `java_classify` と `java_track` を呼ぶ。`java_classify` と `java_track` は互いを参照しない兄弟関係。 |
| Shim の旧シンボル alias で名前衝突 | 各 shim の alias 一覧をフェーズ単位でドキュメント化し、Phase 7 のクリーンアップで全削除を機械的に確認できるようにする。 |
| `analyze_all.py` の重複バッチトラッカーを各言語に畳み込む際、振る舞いが微妙に変わる | 各言語移植 Phase（4・5・6）で `test_all_analyzer.py` の該当ケースが緑であることを 1 件ずつ確認。コミット前に必ず pytest 緑を機械的に守る。 |
| テスト import の一括置換でタイポ・漏れ | Phase 7 で `grep -r "from analyze_common" tests/` `grep -r "from aho_corasick" tests/` 等が 0 件になることをチェック。 |
| `--workers` 並列処理（ProcessPoolExecutor）が新パッケージ構造でも pickle 可能か | バッチトラッカーをモジュール関数として保てば pickle 可能。クラスメソッド化しないこと（B 案の選択理由）。 |
| **キャッシュの object identity を shim 越しに保てない** | §2.3 の表で同一性を保持するキャッシュを列挙。Phase 1/5/6 のコミット前に `is` チェックスクリプトを実行（§5 Phase 1 末尾参照）。 |
| **ワーカープロセスがキャッシュを再ビルドして性能退化** | `_build_define_map` は dispatcher 側で事前構築 → ワーカーへ引数渡しの現状パターンを維持（§2.3 末尾）。`batch_track_indirect` 内でワーカー実行前にメインプロセスでビルドする。 |
| **テスト並列実行（pytest-xdist）でモジュールキャッシュ汚染** | docs に「`pytest-xdist` を導入しない」ことを明記（§6.6）。setUp で `_*_clear()` を呼ぶ規律は維持。 |
| **`# type: ignore[attr-defined]` を完全 0 件にできない可能性** | `grep_helper/` 配下では 0 件を目標とする。shim 層では旧シンボル alias re-export のために残る場合がある（DoD §9-4 で明示的に scope を限定）。 |

---

## 9. 完了条件（Definition of Done）

1. `python -m pytest tests/ -v` が全緑（Phase 0〜7 の各 Phase 完了時点でも全緑）。
2. `python analyze.py --help` および `python analyze_<lang>.py --help` 全 13 個が動作し、引数仕様が変わっていない。
3. **TSV 同一性検証スクリプト** がパスする: リファクタ前のブランチで `tests/fixtures/` をソースに `analyze_all.py` を実行 → 出力 TSV を保存 → 新ブランチで同条件で実行 → `diff -r` で完全一致を確認。Phase 7 完了時に CI 的に手で 1 回実行する手順を README または `docs/development-guidelines.md` に記載。
4. `grep -rn "from analyze_common" .` `grep -rn "from aho_corasick" .` がすべて 0 件。`grep_helper/` 配下では `grep -rn "type: ignore\[attr-defined\]" grep_helper/` が 0 件（shim 層は対象外）。
5. `docs/architecture.md` `docs/repository-structure.md` `docs/development-guidelines.md` の 3 つが新構造で書き直されている。
6. `flake8` が通る。
7. §2.3 のキャッシュ同一性表に挙げた dict について、`is` 同一性チェックスクリプトが各 Phase（1/5/6）の完了時にパスしている。

---

## 10. 決定ログ（ブレストでの選択）

| 決定 | 採用 | 理由 |
|---|---|---|
| 進め方 | F（段階的 + CLI 互換維持・表面不変・内部再構成） | E（一気に大改造）は CLI 名を README で 10 箇所以上指している現状では破壊コストが大きい。F なら shim 維持コスト ≒ 0 で互換を保ちつつ内部は同等に再構成できる。 |
| スコープ | C（コード + テスト + docs） | 実装と docs の乖離が一番痛い。テストは import パスのみ更新で工数小。 |
| 構造の輪郭 | 案 3（ハイブリッド型: Java/Pro\*C のみ複数ファイル、他は単一ファイル） | 1 ファイルで足りる小言語をフォルダ化するのは形式主義。大きい言語だけ分解。 |
| ファイル命名 | 言語名プレフィックス（`java_ast.py` 等）+ フォルダ最小化 | ファイル名だけで言語と役割が分かる。`io/` 等のサブフォルダも作らずフラットに。 |
| ハンドラ契約 | B（モジュール = ハンドラ、duck typing） | A（Protocol 厳格）はモジュールレベル状態を class instance に押し込む作業量に見合うリターンが薄い。pickle 互換のためにもモジュール関数のままが安全。 |
| 性能・挙動の改修 | B（移植中の重複畳み込みは許可、性能・挙動は不変） | A（純粋移植のみ）は `analyze_all.py` の重複が `dispatcher.py` の重複として残るだけ。C（性能改善も）は別 PR の方が bisect しやすい。 |
| フェーズ粒度 | 8 フェーズ・15+ コミット（言語ごとに分割） | 各フェーズで pytest 緑を保証。bisect しやすさを優先。 |
