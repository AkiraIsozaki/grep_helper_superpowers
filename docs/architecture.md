# 技術仕様書 (Architecture Design Document)

## テクノロジースタック

### 言語・ランタイム

| 技術 | バージョン |
|------|-----------|
| Python | 3.12+ |
| venv | Python標準（3.12+） |

### フレームワーク・ライブラリ

| 技術 | バージョン | 用途 | 選定理由 |
|------|-----------|------|----------|
| javalang | >=0.13.0,<1.0.0 | Java AST解析（`grep_helper.languages.java` のみ） | Java 7以上のソースをPythonからAST解析できる唯一の実績あるライブラリ |
| chardet | >=5.0.0,<6.0.0 | 文字コード自動検出（`grep_helper.encoding.detect_encoding`） | 全ハンドラ共通で利用。`requirements.txt` の必須依存（コード側は try/except でフォールバックあり：未インストール時は cp932） |
| pyahocorasick | >=2.0.0,<3.0.0 | Aho-Corasick 多パターンスキャン（`grep_helper.scanner.build_batch_scanner`） | パターン数 ≥ 100 の場合に自動使用。`requirements.txt` の必須依存（コード側はフォールバックあり：未インストール時は同梱の `_aho_corasick.py` 純Python実装に切替） |
| re | 標準ライブラリ | grep行パース・全言語の正規表現分類 | 外部依存不要 |
| csv | 標準ライブラリ | UTF-8 BOM付きTSV出力（`grep_helper.tsv_output`） | `encoding='utf-8-sig'` でBOM付き出力をネイティブサポート |
| heapq | 標準ライブラリ | 大規模TSVの外部マージソート（`grep_helper.tsv_output`） | 100万件超のレコードをメモリ効率よくソートするためにチャンク分割+ヒープマージを使用 |
| argparse | 標準ライブラリ | CLIオプション解析（`grep_helper.cli`） | --source-dir等のオプション解析に十分 |
| mmap | 標準ライブラリ | バッチスキャン前のファイル事前フィルタ（`grep_helper.source_files.grep_filter_files`） | OS のカーネルレベルでファイルをメモリマップし、バイト列検索で不要ファイルを除外。Solaris 10 含む全 OS で動作 |

---

## ハンドラコントラクト（duck typing）

各言語の実装は「ハンドラ（handler）」と呼ぶ Python モジュールとして `grep_helper/languages/` に配置する。ハンドラには基底クラスは不要で、duck typing によって以下のシンボルの有無で機能を判定する。

### 必須シンボル

| シンボル | 型 | 説明 |
|---------|-----|------|
| `EXTENSIONS` | `tuple[str, ...]` | このハンドラが担当するファイル拡張子（例: `('.java',)`, `('.c', '.h')`） |
| `classify_usage` | `(code: str, *, ctx: ClassifyContext \| None = None) -> str` | コード行を受け取り使用タイプ文字列を返す。`ctx` は filepath 等の文脈情報（Pro*C の拡張子ディスパッチ等で利用） |

### 省略可能シンボル

| シンボル | 型 | 説明 |
|---------|-----|------|
| `batch_track_indirect` | `(direct_records, src_dir, encoding, *, workers=1) -> list[GrepRecord]` | 直接参照レコードを受け取り、間接参照レコードを返す。Java / C / Pro*C / Kotlin / C#・VB.NET / Groovy / Shell / SQL が実装する。PL/SQL / TypeScript / Python / Perl は省略 |
| `SHEBANGS` | `tuple[str, ...]` | 拡張子なしファイルのシバン行によるハンドラ判定に使用。`sh` と `perl` のみ実装する |

---

## レイヤー図

```
┌──────────────────────────────────────────────────────────────────┐
│  CLI エントリポイント（ルート shim: analyze*.py）                  │
│  5〜6 行のみ。grep_helper.cli.run / grep_helper.dispatcher.main   │
│  へ委譲する                                                       │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  オーケストレーション層                                           │
│  cli.py ─────── run(handler) ──────────── 単言語 CLI ループ       │
│  dispatcher.py ─ main()     ──────────── 多言語 CLI ループ        │
│  pipeline.py ─── process_grep_file() ─── 第1段階（grep 行分類）   │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  言語ハンドラ層（grep_helper/languages/）                         │
│  java.py / java_ast.py / java_classify.py / java_track.py        │
│  proc.py / proc_define_map.py / proc_track.py                    │
│  c.py / kotlin.py / dotnet.py / groovy.py / sh.py / sql.py /     │
│  plsql.py / ts.py / python.py / perl.py / _none.py               │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  I/O 共通インフラ層（grep_helper/ 直下）                          │
│  encoding.py ─── detect_encoding                                  │
│  grep_input.py ── iter_grep_lines / parse_grep_line               │
│  tsv_output.py ── write_tsv（外部ソート対応）                     │
│  source_files.py ─ iter_source_files / grep_filter_files /        │
│                    resolve_file_cached                             │
│  file_cache.py ── cached_file_lines（LRU 256MB）                  │
│  scanner.py ───── build_batch_scanner（AC / regex 自動選択）       │
│  _aho_corasick.py  Pure Python AC フォールバック                  │
│  model.py ──────── GrepRecord / ProcessStats / RefType /          │
│                    ClassifyContext                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## `detect_handler(filepath, src_dir)` の動作

`grep_helper.languages.__init__` に定義されている。ファイルパスからハンドラ（モジュール）を解決する。戻り値は `ModuleType`（言語不明時は `_none` モジュール）。

1. `filepath` の拡張子（`Path(filepath).suffix.lower()`）を `EXT_TO_HANDLER` 辞書で検索する
2. 拡張子が存在すれば対応するハンドラモジュールを返す
3. 拡張子がない場合（または辞書に存在しない場合）、`src_dir / filepath` の先頭行を読み込む
4. シバン行（`#!`で始まる行）のインタープリタ名を `SHEBANG_TO_HANDLER` 辞書で検索する
5. シバンが見つかれば対応するハンドラモジュールを返す
6. いずれにも該当しなければ `_none` モジュールを返す（`classify_usage` が常に `"その他"` を返す no-op ハンドラ）

---

## `cli.run(handler)` の処理フロー

```
cli.run(handler, description)
    ↓  build_parser() でオプション解析（--source-dir / --input-dir / --output-dir / --encoding / --workers）
    ↓  input_dir の .grep ファイルを glob
    loop 各 .grep ファイル:
        pipeline.process_grep_file(path, keyword, handler, src_dir, stats, encoding)
            ↓  iter_grep_lines → parse_grep_line → handler.classify_usage → GrepRecord
            → 直接参照レコード一覧を返す
        (optional) handler.batch_track_indirect(direct_records, src_dir, encoding, workers=N)
            → 間接参照レコード一覧を返す
        tsv_output.write_tsv(all_records, output_path)
    ↓  処理サマリを stdout に表示
```

---

## `dispatcher.main()` の処理フロー（多言語）

```
dispatcher.main()
    ↓  build_parser() でオプション解析
    ↓  input_dir の .grep ファイルを glob
    loop 各 .grep ファイル:
        process_grep_lines_all(lines, keyword, src_dir, stats, encoding)
            ↓  parse_grep_line → detect_handler(filepath, src_dir)
                → handler.classify_usage(code, ctx=ClassifyContext(filepath=...))
            → 直接参照レコード一覧（ハンドラ混在）を返す
        apply_indirect_tracking(direct_records, src_dir, encoding, workers)
            ↓  ハンドラ別にレコードを分類
            ↓  各ハンドラの batch_track_indirect を順次呼び出す
            → 間接参照レコード一覧を返す
        tsv_output.write_tsv(all_records, output_path)
    ↓  処理サマリを stdout に表示
```

---

## Java の分解 DAG（依存グラフ）

```
java_ast.py
  ├── _ast_cache: dict[str, object | None]
  ├── _ast_line_index: dict[str, dict[int, tuple]]
  └── _method_starts_cache: dict[str, list[int]]
        ↓ (import)
java_classify.py
  ├── UsageType（Enum）
  └── classify_usage_regex(code) → str
        ↓ (import)
java_track.py
  ├── track_field / track_local
  ├── find_getter_names / find_setter_names
  └── batch_track_combined(const_tasks, getter_tasks, setter_tasks, ...) → list[GrepRecord]
        ↓ (import)
java.py（公開 API）
  ├── EXTENSIONS = ('.java',)
  ├── classify_usage(code, *, ctx=None) → str
  └── batch_track_indirect(direct_records, src_dir, encoding, *, workers=1) → list[GrepRecord]
```

---

## Pro*C の分解（依存グラフ）

```
proc_define_map.py
  └── _define_map_cache + _build_define_map(path, encoding)
        ↑ (import)
proc_track.py
  ├── extract_define_name / extract_host_var
  ├── track_define / track_variable
  └── batch_track_define_all(names, src_dir, encoding, ...) → list[GrepRecord]
        ↑ (import)
proc.py（公開 API）
  ├── EXTENSIONS = ('.pc', '.c', '.h')
  ├── classify_usage(code, *, ctx=None) → str
  │     ↓ ctx.filepath の拡張子が .c/.h なら c.classify_usage、.pc なら proc 用分類
  └── batch_track_indirect(direct_records, src_dir, encoding, *, workers=1) → list[GrepRecord]
```

---

## キャッシュ同一性の不変条件

以下のキャッシュ辞書は各モジュールで **一度だけ定義** され、プロセス内で再バインドされない。テストはモジュールキャッシュのクリア規律（`setUp` で `_*_clear()` を呼ぶ）に依存している。

| キャッシュ変数 | 定義場所 |
|--------------|---------|
| `_file_lines_cache` | `grep_helper.file_cache` |
| `_source_files_cache` | `grep_helper.source_files` |
| `_resolve_file_cache` | `grep_helper.source_files` |
| `_define_map_cache`（C 用） | `grep_helper.languages.c` |
| `_define_map_cache`（Pro*C 用） | `grep_helper.languages.proc_define_map` |
| `_ast_cache` | `grep_helper.languages.java_ast` |
| `_ast_line_index` | `grep_helper.languages.java_ast` |
| `_method_starts_cache` | `grep_helper.languages.java_ast` |

**テスト並列化の注意**: `pytest-xdist` 等によるプロセス並列テスト実行は、このキャッシュクリア規律と相容れないため導入しないこと（詳細は `docs/development-guidelines.md` 参照）。

---

## アーキテクチャパターン

### パイプラインアーキテクチャ

本ツールはバッチ処理CLIツールであり、データが段階的に変換される**パイプラインアーキテクチャ**を採用する。

```
┌─────────────────────────┐
│   入力レイヤー           │ ← argparse（cli.py）+ parse_grep_line（grep_input.py）
│   (CLIパース・ファイル読込)│   grep結果ファイルを読み込み
├─────────────────────────┤
│   分析レイヤー           │ ← 言語ハンドラ（languages/*.py）
│   (言語別分類・追跡)    │   Java/Groovy: 4段階（直接→間接→getter経由→setter経由）
│                         │   C/Pro*C/Kotlin/C#・VB.NET: 2段階（直接 + 定数・変数経由）
│                         │   Shell/SQL: 2段階（直接 + 同一ファイル内変数代入）
│                         │   PL/SQL/TypeScript・JS/Python/Perl: 1段階（直接のみ）
├─────────────────────────┤
│   出力レイヤー           │ ← write_tsv（tsv_output.py）
│   (TSV出力・レポート)   │   結果をTSVに書き出しレポート表示
│                         │   100万件超: チャンク分割+ヒープマージの外部ソート
└─────────────────────────┘
```

---

## 共通キャッシュ・パフォーマンスインフラ

Phase A〜F のパフォーマンス改善により、ファイル I/O・スキャン・パス解決にかかわるすべてのキャッシュとスキャンロジックが `grep_helper/` パッケージ直下に集約されている。各言語ハンドラは独自のファイルキャッシュを持たず、以下の共通 API を利用する。

| 関数 | シグネチャ（簡略） | 説明 |
|------|-------------------|------|
| `iter_grep_lines` | `(path, encoding)` → generator | grep ファイルを 1 行ずつ yield するストリーミングジェネレータ |
| `iter_source_files` | `(src_dir, extensions)` → `list[Path]` | `rglob` 結果をモジュールグローバルにキャッシュして返す |
| `cached_file_lines` | `(path, encoding, stats)` → `list[str]` | サイズベース LRU 行キャッシュ（既定 256MB） |
| `resolve_file_cached` | `(filepath, src_dir)` → `Path \| None` | ファイルパス解決結果をキャッシュ |
| `build_batch_scanner` | `(patterns)` → `_BatchScanner` | パターン数 ≥ 100 で `pyahocorasick`（Aho-Corasick 法）を自動選択 |

---

## 並列処理（`--workers`）

`analyze_all.py`（`dispatcher.main`）と各個別アナライザーは `--workers N`（既定: 1）を受け付け、`batch_track_indirect` フェーズのバッチスキャン処理を `ProcessPoolExecutor` で並列化する。各ワーカーは独立プロセスで動作するため GIL の制約を受けない。

```bash
# CPU コア数を --workers に指定するとバッチ追跡フェーズが N 並列で動く
python analyze_all.py --source-dir ./src --workers 4
```

**注意**: ワーカー数を増やすとメモリ使用量もワーカー数倍になる。ファイル行キャッシュ 256MB × N ワーカー分のメモリが必要。

---

## データ永続化戦略

| データ種別 | ストレージ | フォーマット |
|-----------|----------|-------------|
| grep結果入力 | ローカルファイルシステム | テキスト（`filepath:lineno:code`） |
| 分析結果出力 | ローカルファイルシステム | TSV（UTF-8 BOM付き） |
| ASTキャッシュ | オンメモリ dict | javalangのASTオブジェクト（`java_ast._ast_cache`） |

---

## パフォーマンス要件

| 操作 | 目標時間 |
|------|---------|
| 4万行・500ファイル規模の処理 | 30分以内（目安） |
| 小規模（1000行・50ファイル） | 1分以内 |

**注意**: 処理時間より**網羅性を優先**するため、時間制限は設けない。

| リソース | 上限 | 制御方法 |
|---------|------|---------|
| ファイル行キャッシュ | 256MB（既定） | `file_cache.set_file_lines_cache_limit(n_bytes)` で変更可 |
| AST キャッシュ（Java のみ） | `_MAX_AST_CACHE_SIZE = 2000` 件 | `java_ast` モジュール内の定数を縮小 |
| grep ファイルのメモリ使用量 | O(1) — 行単位 | `iter_grep_lines` によるストリーミング読み込み |

---

## セキュリティアーキテクチャ

- **暗号化**: 不要（ローカルファイルのみ）
- **アクセス制御**: OSのファイルパーミッションに委譲
- **入力検証**: `--source-dir` / `--input-dir` は `Path.exists()` + `Path.is_dir()` で検証
- **ファイル読み込み**: `errors='replace'` でエンコーディングエラーを無害化
- **エラーメッセージ**: 日本語で **標準エラー出力（stderr）** へ出力

---

## 依存関係管理

**`requirements.txt`**（本番依存）:
```
javalang>=0.13.0,<1.0.0
chardet>=5.0.0,<6.0.0
pyahocorasick>=2.0.0,<3.0.0
```

**`requirements-dev.txt`**（開発用依存）:
```
pytest>=9.0.0,<10.0.0
```

**方針**:
- 本番依存は `javalang` / `chardet` / `pyahocorasick` の3本。すべて `wheelhouse/` に wheel を同梱しているのでオフラインインストール可能
- C/SQL/Shell/Kotlin/PL/SQL/TypeScript・JS/Python/Perl/C#・VB.NET/Groovy のパース処理自体は標準ライブラリ（`re`）のみで完結

---

## テスト戦略

### ユニットテスト
- **フレームワーク**: unittest（Python標準ライブラリ、記述用）/ pytest（実行用、`requirements-dev.txt`）
- **対象ファイル**: `tests/test_*.py`（全言語）
- **カバレッジ目標**: 80%以上（推奨。マージのブロック条件ではない）

### 統合テスト（E2Eテスト）
- **方法**: 言語別のサンプルソース + サンプルgrep結果を使ったE2Eフロー
- **フィクスチャ**: `tests/<言語>/` 以下に言語別に配置
- **対象**: 直接参照・間接参照（対応言語のみ）・各言語固有のパターンが期待TSVと一致すること

詳細は `docs/repository-structure.md` を参照。
