# リポジトリ構造定義書 (Repository Structure Document)

## プロジェクト構造

```
/（リポジトリルート）
├── analyze.py               # CLI shim（5行）→ grep_helper.languages.java
├── analyze_all.py           # CLI shim（5行）→ grep_helper.dispatcher.main
├── analyze_c.py             # CLI shim（6行）→ grep_helper.languages.c
├── analyze_dotnet.py        # CLI shim（6行）→ grep_helper.languages.dotnet
├── analyze_groovy.py        # CLI shim（6行）→ grep_helper.languages.groovy
├── analyze_kotlin.py        # CLI shim（6行）→ grep_helper.languages.kotlin
├── analyze_perl.py          # CLI shim（6行）→ grep_helper.languages.perl
├── analyze_plsql.py         # CLI shim（6行）→ grep_helper.languages.plsql
├── analyze_proc.py          # CLI shim（6行）→ grep_helper.languages.proc
├── analyze_python.py        # CLI shim（6行）→ grep_helper.languages.python
├── analyze_sh.py            # CLI shim（6行）→ grep_helper.languages.sh
├── analyze_sql.py           # CLI shim（6行）→ grep_helper.languages.sql
├── analyze_ts.py            # CLI shim（6行）→ grep_helper.languages.ts
│
├── grep_helper/                    # 主パッケージ
│   ├── __init__.py
│   ├── model.py                    # GrepRecord, ProcessStats, RefType, ClassifyContext
│   ├── cli.py                      # build_parser + run(handler)
│   ├── pipeline.py                 # process_grep_file（handler.classify_usage を呼ぶ）
│   ├── dispatcher.py               # 多言語一括フロー（旧 analyze_all.py 相当）
│   ├── encoding.py                 # detect_encoding
│   ├── grep_input.py               # iter_grep_lines, parse_grep_line
│   ├── tsv_output.py               # write_tsv（外部ソート対応）
│   ├── source_files.py             # iter_source_files, grep_filter_files, resolve_file_cached
│   ├── file_cache.py               # cached_file_lines（サイズベース LRU 256MB）
│   ├── scanner.py                  # build_batch_scanner（AC vs regex 自動選択）
│   ├── _aho_corasick.py            # Pure Python Aho-Corasick フォールバック
│   │
│   └── languages/
│       ├── __init__.py             # EXT_TO_HANDLER / SHEBANG_TO_HANDLER / detect_handler
│       ├── _none.py                # 言語不明用 no-op ハンドラ
│       │
│       ├── java.py                 # Java 公開 API + classify_usage（ctx対応）+ batch_track_indirect
│       ├── java_ast.py             # AST キャッシュ（_ast_cache / _ast_line_index / _method_starts_cache）
│       ├── java_classify.py        # 純粋分類（UsageType, classify_usage_regex 等）
│       ├── java_track.py           # 追跡処理（track_field, track_local, batch_track_combined 等）
│       │
│       ├── proc.py                 # Pro*C 公開 API + classify_usage（filepath対応: c↔proc）
│       ├── proc_define_map.py      # _define_map_cache + _build_define_map
│       ├── proc_track.py           # extract_*, track_* 各種関数
│       │
│       ├── c.py                    # C 言語（1ファイル完結）
│       ├── kotlin.py               # Kotlin（1ファイル完結）
│       ├── dotnet.py               # C#/VB.NET（1ファイル完結）
│       ├── groovy.py               # Groovy（1ファイル完結）
│       ├── sh.py                   # Shell（1ファイル完結、SHEBANGS あり）
│       ├── sql.py                  # Oracle SQL（1ファイル完結）
│       ├── plsql.py                # PL/SQL（1ファイル完結）
│       ├── ts.py                   # TypeScript/JavaScript（1ファイル完結）
│       ├── python.py               # Python（1ファイル完結）
│       └── perl.py                 # Perl（1ファイル完結、SHEBANGS あり）
│
├── tests/                          # pytest テスト（import は grep_helper.* パスに統一）
│   ├── test_analyze.py             # Java アナライザーのユニットテスト・統合テスト
│   ├── test_analyze_proc.py        # Pro*C アナライザーのユニットテスト・統合テスト
│   ├── test_aho_corasick.py        # Pure Python Aho-Corasick のユニットテスト
│   ├── test_common.py              # 共通インフラ（model / grep_input / tsv_output 等）のテスト
│   ├── test_all_analyzer.py        # dispatcher の E2E 統合テスト（多言語混在フィクスチャ使用）
│   ├── test_c_analyzer.py          # C アナライザーの E2E 統合テスト
│   ├── test_sh_analyzer.py         # Shell アナライザーの E2E 統合テスト
│   ├── test_sql_analyzer.py        # SQL アナライザーの E2E 統合テスト
│   ├── test_kotlin_analyzer.py     # Kotlin アナライザーのユニットテスト・E2E 統合テスト
│   ├── test_plsql_analyzer.py      # PL/SQL アナライザーのユニットテスト・E2E 統合テスト
│   ├── test_ts_analyzer.py         # TypeScript/JS アナライザーのユニットテスト・E2E 統合テスト
│   ├── test_python_analyzer.py     # Python アナライザーのユニットテスト・E2E 統合テスト
│   ├── test_perl_analyzer.py       # Perl アナライザーのユニットテスト・E2E 統合テスト
│   ├── test_dotnet_analyzer.py     # C#/VB.NET アナライザーのユニットテスト・E2E 統合テスト
│   ├── test_groovy_analyzer.py     # Groovy アナライザーのユニットテスト・E2E 統合テスト
│   └── fixtures/                   # 言語別テストフィクスチャ（詳細は後述）
│
├── scripts/
│   ├── check_cache_identity_phase1.py   # _file_lines_cache / _source_files_cache 同一性チェック
│   ├── check_cache_identity_phase4.py   # _define_map_cache (c) 同一性チェック
│   ├── check_cache_identity_phase5.py   # _define_map_cache (proc) 同一性チェック
│   └── check_cache_identity_phase6.py   # _ast_cache / _ast_line_index / _method_starts_cache 同一性チェック
│
├── docs/                           # プロジェクトドキュメント
│   ├── product-requirements.md
│   ├── functional-design.md
│   ├── architecture.md
│   ├── repository-structure.md     （本ドキュメント）
│   ├── development-guidelines.md
│   ├── tool-overview.md
│   ├── glossary.md
│   └── superpowers/                # superpowers スキルが利用するプラン・スペック等
│       ├── plans/
│       └── specs/
├── input/                          # grep 結果ファイルの配置ディレクトリ（.gitkeep のみ）
├── output/                         # TSV 出力先ディレクトリ（.gitkeep のみ）
├── wheelhouse/                     # オフライン install 用 wheel（javalang / chardet / pyahocorasick / pytest 他）
├── requirements.txt                # 本番依存（javalang / chardet / pyahocorasick）
├── requirements-dev.txt            # 開発用依存（pytest）
├── README.md                       # 利用者向け手順書（日本語）
├── CLAUDE.md                       # Claude Code 設定（AIアシスタントへの指示）
├── .flake8                         # flake8 設定（max-line-length=120 等）
├── .claude/                        # Claude Code 設定・スキル定義
├── .devcontainer/                  # VS Code Dev Containers 設定
└── .steering/                      # 作業単位のステアリングファイル（作業時に生成）
```

> **注意**: 旧実装の `analyze_common.py` と `aho_corasick.py` はリファクタ完了により削除済み。
> ルート直下の `analyze*.py` は互換性維持のための CLI shim（5〜6行）であり、実装は `grep_helper/` パッケージに移管されている。

---

## `grep_helper/` 直下ファイルの責務

| ファイル | 責務 |
|---------|------|
| `model.py` | `GrepRecord`（NamedTuple）/ `ProcessStats`（dataclass）/ `RefType`（Enum）/ `ClassifyContext`（dataclass）を定義する。全モジュールのデータモデル基盤 |
| `cli.py` | `build_parser()` と `run(handler, description)` を提供する。`run()` は `input/*.grep` を glob して `pipeline.process_grep_file` を呼び、`handler.batch_track_indirect`（任意）を呼び、`write_tsv` で出力する汎用 CLI ループ |
| `pipeline.py` | `process_grep_file(path, keyword, handler, src_dir, stats, *, encoding)` — grep ファイル全行を読み込み `handler.classify_usage` で分類して `GrepRecord` リストを返す第1段階処理 |
| `dispatcher.py` | `main()` / `process_grep_lines_all()` / `apply_indirect_tracking()` — 多言語一括フロー。`detect_handler` でレコードごとに適切なハンドラを解決し、全ハンドラの `batch_track_indirect` を順次実行する |
| `encoding.py` | `detect_encoding(path, encoding_override)` — ファイル先頭 4096 バイトを `chardet` で推定し、信頼度 < 0.6 の場合は `cp932` にフォールバックする |
| `grep_input.py` | `iter_grep_lines(path, encoding)` — grep ファイルを 1 行ずつ yield するストリーミングジェネレータ。`parse_grep_line(line)` — `filepath:lineno:code` 形式をパースして `dict` を返す |
| `tsv_output.py` | `write_tsv(records, output_path)` — `GrepRecord` リストを UTF-8 BOM 付き TSV に出力。100 万件超は `heapq.merge` ベースの外部ソートに切り替える |
| `source_files.py` | `iter_source_files(src_dir, extensions)` — rglob 結果をキャッシュして返す。`grep_filter_files(names, src_dir, extensions)` — mmap バイト列検索で事前フィルタ。`resolve_file_cached(filepath, src_dir)` — パス解決結果をキャッシュする |
| `file_cache.py` | `cached_file_lines(path, encoding, stats)` — サイズベース LRU（デフォルト 256MB）によるファイル行キャッシュ。`set_file_lines_cache_limit(n_bytes)` — 上限を変更する |
| `scanner.py` | `build_batch_scanner(patterns)` — パターン数 ≥ 100 で `pyahocorasick` を自動選択、< 100 では combined regex を使用する多パターンスキャナを返す |
| `_aho_corasick.py` | Pure Python 実装の Aho-Corasick オートマトン。`pyahocorasick` が未インストールの場合に `scanner.py` からフォールバック利用される |

---

## `grep_helper/languages/` ファイルの責務

| ファイル | 言語 | 責務 |
|---------|------|------|
| `__init__.py` | — | `EXT_TO_HANDLER`（拡張子→ハンドラ辞書）/ `SHEBANG_TO_HANDLER`（シバン→ハンドラ辞書）/ `detect_handler(filepath, src_dir)` を定義・公開する |
| `_none.py` | — | 言語不明用 no-op ハンドラ。`classify_usage` は常に `"その他"` を返す |
| `java.py` | Java | `EXTENSIONS = ('.java',)` / `classify_usage(code, *, ctx)` / `batch_track_indirect(direct_records, src_dir, encoding, *, workers)` を公開する。内部は `java_ast` / `java_classify` / `java_track` の 3 サブモジュールに委譲する |
| `java_ast.py` | Java | AST キャッシュ 3 辞書（`_ast_cache` / `_ast_line_index` / `_method_starts_cache`）を定義する。`get_ast` / `get_ast_line_info` / `get_method_starts` 等の キャッシュ付き AST アクセサを提供する |
| `java_classify.py` | Java | `UsageType` Enum / `classify_usage_regex(code)` / スコープ判定などの純粋分類ロジックを提供する |
| `java_track.py` | Java | `track_field` / `track_local` / `find_getter_names` / `find_setter_names` / `batch_track_combined` 等の追跡ロジックを提供する |
| `proc.py` | Pro*C | `EXTENSIONS = ('.pc', '.c', '.h')` / `classify_usage(code, *, ctx)` — `ctx.filepath` の拡張子に応じて `.c`/`.h` は `c.classify_usage`、`.pc` は Pro*C 用分類に切り替える。`batch_track_indirect` で `#define` 定数を横断追跡する |
| `proc_define_map.py` | Pro*C | `_define_map_cache`（`#define` 定義マップのキャッシュ）と `_build_define_map(path, encoding)` を定義する |
| `proc_track.py` | Pro*C | `extract_define_name` / `track_define` / `track_variable` 等の Pro*C 向け追跡関数を提供する |
| `c.py` | C | `EXTENSIONS = ('.c', '.h')` / `classify_usage(code, *, ctx)` — 正規表現で 6 種に分類。`batch_track_indirect` で `#define` 定数をプロジェクト全体追跡する |
| `kotlin.py` | Kotlin | `EXTENSIONS = ('.kt', '.kts')` / `classify_usage` — 正規表現で 7 種に分類。`batch_track_indirect` で `const val` 定数をプロジェクト全体追跡する |
| `dotnet.py` | C#/VB.NET | `EXTENSIONS = ('.cs', '.vb')` / `classify_usage` — 正規表現で 7 種に分類。`batch_track_indirect` で `const` / `static readonly` 定数をプロジェクト全体追跡する |
| `groovy.py` | Groovy | `EXTENSIONS = ('.groovy', '.gvy')` / `classify_usage` — 正規表現で 7 種に分類。`batch_track_indirect` で `static final` 定数・フィールド・getter/setter をプロジェクト全体追跡する |
| `sh.py` | Shell | `EXTENSIONS = ('.sh',)` / `SHEBANGS = ('bash', 'sh', 'csh', 'tcsh', 'ksh', 'ksh93')` / `classify_usage` — 正規表現で 6 種に分類。`batch_track_indirect` で変数代入・環境変数エクスポートを同一ファイル内追跡する |
| `sql.py` | Oracle SQL | `EXTENSIONS = ('.sql',)` / `classify_usage` — 正規表現で 7 種に分類。`batch_track_indirect` で定数・変数定義を同一ファイル内追跡する |
| `plsql.py` | PL/SQL | `EXTENSIONS = ('.pls', '.pck', '.prc', '.pkb', '.pks', '.fnc', '.trg')` / `classify_usage` — 正規表現で 7 種に分類。間接追跡なし |
| `ts.py` | TypeScript/JS | `EXTENSIONS = ('.ts', '.tsx', '.js', '.jsx')` / `classify_usage` — 正規表現で 7 種に分類。間接追跡なし |
| `python.py` | Python | `EXTENSIONS = ('.py',)` / `classify_usage` — 正規表現で 6 種に分類。間接追跡なし |
| `perl.py` | Perl | `EXTENSIONS = ('.pl', '.pm')` / `SHEBANGS = ('perl',)` / `classify_usage` — 正規表現で 6 種に分類。間接追跡なし |

---

## ルート shim の役割

ルート直下の `analyze*.py`（13 ファイル）は互換性維持のための CLI エントリポイント shim である。各ファイルはおよそ 5〜6 行のみで構成され、実質的なロジックはすべて `grep_helper/` パッケージに委譲する。

**shim の典型的な構造（例: `analyze_kotlin.py`）**:
```python
"""``grep_helper.languages.kotlin`` への CLI shim。"""
from grep_helper.cli import run
from grep_helper.languages import kotlin as _handler

if __name__ == "__main__":
    raise SystemExit(run(_handler, description="Kotlin grep結果 自動分類・使用箇所洗い出しツール"))
```

`analyze.py`（Java）は `grep_helper.languages.java` へ、`analyze_all.py` は `grep_helper.dispatcher.main` へ委譲している。

---

## `tests/` の構成

テストファイルは全て `tests/` 直下に配置し、インポートパスは `grep_helper.*` に統一されている（旧 `analyze_common` / `analyze` 等の直接インポートは廃止済み）。

**言語別テストファイル**:

| テストファイル | 対象モジュール |
|-------------|--------------|
| `test_analyze.py` | `grep_helper.languages.java` のユニットテスト・統合テスト |
| `test_analyze_proc.py` | `grep_helper.languages.proc` のユニットテスト・統合テスト（E2E 含む） |
| `test_aho_corasick.py` | `grep_helper._aho_corasick`（Pure Python Aho-Corasick）のユニットテスト |
| `test_common.py` | `grep_helper.model` / `grep_helper.grep_input` / `grep_helper.tsv_output` のユニットテスト |
| `test_all_analyzer.py` | `grep_helper.dispatcher` の E2E 統合テスト（多言語混在フィクスチャ使用） |
| `test_c_analyzer.py` | `grep_helper.languages.c` の E2E 統合テスト |
| `test_sh_analyzer.py` | `grep_helper.languages.sh` の E2E 統合テスト |
| `test_sql_analyzer.py` | `grep_helper.languages.sql` の E2E 統合テスト |
| `test_kotlin_analyzer.py` | `grep_helper.languages.kotlin` のユニットテスト・E2E 統合テスト |
| `test_plsql_analyzer.py` | `grep_helper.languages.plsql` のユニットテスト・E2E 統合テスト |
| `test_ts_analyzer.py` | `grep_helper.languages.ts` のユニットテスト・E2E 統合テスト |
| `test_python_analyzer.py` | `grep_helper.languages.python` のユニットテスト・E2E 統合テスト |
| `test_perl_analyzer.py` | `grep_helper.languages.perl` のユニットテスト・E2E 統合テスト |
| `test_dotnet_analyzer.py` | `grep_helper.languages.dotnet` のユニットテスト・E2E 統合テスト |
| `test_groovy_analyzer.py` | `grep_helper.languages.groovy` のユニットテスト・E2E 統合テスト |

**フィクスチャ構成**:
```
tests/
├── fixtures/          # Java（test_analyze.py 用）
│   ├── input/         # SAMPLE.grep
│   ├── java/          # Constants.java, Entity.java, Service.java
│   ├── intense/       # 多パッケージ大規模フィクスチャ
│   └── expected/      # SAMPLE.tsv（手動作成・コミット管理）
├── c/                 # C（test_c_analyzer.py 用）
│   ├── input/ src/ expected/
├── proc/              # Pro*C（test_analyze_proc.py 用）
│   ├── input/ src/ expected/
├── sh/                # Shell（test_sh_analyzer.py 用）
│   ├── input/ src/ expected/
├── sql/               # SQL（test_sql_analyzer.py 用）
│   ├── input/ src/ expected/
├── kotlin/            # Kotlin（test_kotlin_analyzer.py 用）
│   ├── input/ src/ expected/
├── plsql/             # PL/SQL（test_plsql_analyzer.py 用）
│   ├── input/ src/ expected/
├── ts/                # TypeScript/JS（test_ts_analyzer.py 用）
│   ├── input/ src/ expected/
├── python/            # Python（test_python_analyzer.py 用）
│   ├── input/ src/ expected/
├── perl/              # Perl（test_perl_analyzer.py 用）
│   ├── input/ src/ expected/
├── dotnet/            # C#/VB.NET（test_dotnet_analyzer.py 用）
│   ├── input/ src/ expected/
├── groovy/            # Groovy（test_groovy_analyzer.py 用）
│   ├── input/ src/ expected/
└── all/               # dispatcher（test_all_analyzer.py 用）
    ├── input/  src/
```

> 各テストメソッドは日本語で命名する（例: `test_直接参照のとき間接フラグは立たない`）。テストファイル名・モジュール構成は英語の `snake_case` を維持する。

> `expected/*.tsv` は手動作成してコミット管理する（自動生成しない）。

---

## `scripts/` の構成

リファクタで導入したキャッシュ dict の object identity チェッカ。各フェーズで新旧実装が「同じキャッシュ dict を共有しているか」を検証するために利用した。

| ファイル | 検証対象 |
|---------|---------|
| `check_cache_identity_phase1.py` | `file_cache._file_lines_cache` / `source_files._source_files_cache` |
| `check_cache_identity_phase4.py` | `languages.c._define_map_cache` |
| `check_cache_identity_phase5.py` | `languages.proc.proc_define_map._define_map_cache` |
| `check_cache_identity_phase6.py` | `languages.java_ast._ast_cache` / `_ast_line_index` / `_method_starts_cache` |

---

## ファイル配置規則

### パッケージ構成

| ファイル種別 | 配置先 | 命名規則 |
|------------|--------|---------|
| 共通インフラ | `grep_helper/` | モジュール名（例: `encoding.py`, `cli.py`） |
| 言語別ハンドラ（1 ファイル） | `grep_helper/languages/` | `<言語>.py`（例: `c.py`, `kotlin.py`） |
| 言語別ハンドラ（複数ファイル） | `grep_helper/languages/` | `<言語>_<役割>.py`（例: `java_ast.py`, `proc_track.py`） |
| CLI shim | プロジェクトルート | `analyze[_<言語>].py`（旧来の名前を維持） |
| テスト | `tests/` | `test_[対象].py` |
| テストフィクスチャ | `tests/<言語>/` | 言語別サブディレクトリ |

### 設定ファイル

| ファイル種別 | 配置先 |
|------------|--------|
| 本番依存ライブラリ | `requirements.txt` |
| 開発用依存ライブラリ | `requirements-dev.txt` |
| Python 仮想環境 | `.venv/`（gitignore 対象） |

---

## 命名規則

### ファイル名

- **Python モジュール**: `snake_case.py`
- **ドキュメント（Markdown）**: `kebab-case.md`

### Python コード内

- **関数・変数**: `snake_case`（例: `parse_grep_line`, `source_dir`）
- **クラス**: `PascalCase`（例: `GrepRecord`, `ProcessStats`, `UsageType`）
- **定数**: `UPPER_SNAKE_CASE`（例: `EXTENSIONS`, `EXT_TO_HANDLER`）
- **プライベート変数**: `_snake_case`（モジュールレベルキャッシュ等）（例: `_ast_cache`）

---

## 依存関係のルール

```
tests/test_*.py
    ↓ (import)
grep_helper.languages.* / grep_helper.dispatcher
    ↓ (import)
grep_helper.pipeline / grep_helper.cli
    ↓ (import)
grep_helper.{model, encoding, grep_input, tsv_output, source_files, file_cache, scanner, _aho_corasick}
    ↓ (import)
標準ライブラリ (re, csv, argparse, pathlib, sys, dataclasses, enum, heapq, tempfile, mmap)
chardet         # 必須依存（wheelhouse に同梱）
pyahocorasick   # 必須依存（wheelhouse に同梱。未インストール時は _aho_corasick.py フォールバック）

grep_helper.languages.java* のみ:
    ↓ (import)
javalang  # 必須外部依存（Java AST 解析専用）

grep_helper.languages.proc のみ:
    ↓ (import)
grep_helper.languages.c  # .c/.h ファイルのディスパッチ用
```

**禁止される依存**:
- `grep_helper/` 共通インフラに `javalang` を追加しない（Java ハンドラ専用）
- `grep_helper.languages.c` から `grep_helper.languages.proc` への循環参照を作らない
- テストファイルに `unittest` / `pytest` 以外の外部ライブラリを追加しない

---

## docs/（ドキュメントディレクトリ）

| ドキュメント | 内容 |
|------------|------|
| `product-requirements.md` | プロダクト要求定義書（PRD） |
| `functional-design.md` | 機能設計書 |
| `architecture.md` | アーキテクチャ設計書（ハンドラコントラクト・レイヤー図） |
| `repository-structure.md` | リポジトリ構造定義書（本ドキュメント） |
| `development-guidelines.md` | 開発ガイドライン（新言語追加手順・テスト方針など） |
| `tool-overview.md` | ツール概要説明書（管理者・業務担当者向け） |
| `glossary.md` | 用語集 |
| `superpowers/` | superpowers スキルが利用するプラン（`plans/`）・スペック（`specs/`）を保管するサブディレクトリ |
