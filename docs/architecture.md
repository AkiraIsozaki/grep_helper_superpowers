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
| javalang | >=0.13.0,<1.0.0 | Java AST解析（`analyze.py` のみ） | Java 7以上のソースをPythonからAST解析できる唯一の実績あるライブラリ。C/SQL/Shell/Kotlin/PL/SQL は正規表現のみで不要 |
| chardet | 任意（pip install chardet） | 文字コード自動検出（`analyze_common.detect_encoding`） | Kotlin/PL/SQL等の新言語アナライザーで利用。未インストール時は cp932 フォールバック |
| pyahocorasick | 任意（pip install pyahocorasick） | Aho-Corasick 多パターンスキャン（`analyze_common.build_batch_scanner`） | パターン数 ≥ 100 の場合に自動使用。未インストール時は re.search にフォールバック |
| re | 標準ライブラリ | grep行パース・全言語の正規表現分類 | 外部依存不要。C/SQL/Shell/Kotlin/PL/SQL はこれのみで分類完結 |
| csv | 標準ライブラリ | UTF-8 BOM付きTSV出力（`analyze_common.py`） | `encoding='utf-8-sig'` でBOM付き出力をネイティブサポート |
| heapq | 標準ライブラリ | 大規模TSVの外部マージソート（`analyze_common.py`） | 100万件超のレコードをメモリ効率よくソートするためにチャンク分割+ヒープマージを使用 |
| tempfile | 標準ライブラリ | 外部ソート用一時ファイル管理（`analyze_common.py`） | チャンクファイルを一時ディレクトリに書き出し、マージ後に削除 |
| argparse | 標準ライブラリ | CLIオプション解析 | --source-dir等のオプション解析に十分 |
| pathlib | 標準ライブラリ | ファイルパス操作 | クロスプラットフォーム対応のパス操作 |
| mmap | 標準ライブラリ | バッチスキャン前のファイル事前フィルタ（`analyze_common.grep_filter_files`） | OS のカーネルレベルでファイルをメモリマップし、バイト列検索で不要ファイルを除外。Solaris 10 含む全 OS で動作 |

### 開発ツール

| 技術 | バージョン | 用途 | 選定理由 |
|------|-----------|------|----------|
| unittest | Python標準 | テスト記述 | 外部依存不要。テストクラス・アサーションを標準ライブラリで記述 |
| pytest | >=9.0.0,<10.0.0（`requirements-dev.txt`） | テスト実行 | `python -m pytest tests/ -v` で自動検出。unittest形式のテストもそのまま実行可能 |
| coverage | 最新安定版（任意） | カバレッジ測定 | `pip install coverage` で導入可能 |
| flake8 | 最新安定版（任意） | コード品質チェック | PEP 8準拠チェック・未使用インポート検出 |

## アーキテクチャパターン

### パイプラインアーキテクチャ

本ツールはバッチ処理CLIツールであり、データが段階的に変換される**パイプラインアーキテクチャ**を採用します。

```
┌─────────────────────────┐
│   入力レイヤー           │ ← argparse + parse_grep_line（analyze_common）
│   (CLIパース・ファイル読込)│   grep結果ファイルを読み込み
├─────────────────────────┤
│   分析レイヤー           │ ← 言語ごとに異なる（analyze.py / analyze_c.py / ...）
│   (言語別分類・追跡)    │   Java/Groovy: 4段階（直接→間接→getter経由→setter経由）
│                         │   C/Pro*C/Kotlin/C#・VB.NET: 2段階（直接 + 定数・変数経由の間接）
│                         │   Shell/SQL: 2段階（直接 + 同一ファイル内変数代入の間接）
│                         │   PL/SQL/TypeScript・JS/Python/Perl: 1段階（直接のみ）
├─────────────────────────┤
│   出力レイヤー           │ ← write_tsv（analyze_common）
│   (TSV出力・レポート)   │   結果をTSVに書き出しレポート表示
│                         │   100万件超: チャンク分割+ヒープマージの外部ソート
└─────────────────────────┘
```

#### 入力レイヤー（全言語共通: `analyze_common.py`）
- **責務**: CLIオプションのパース、`input/` 内の `.grep` ファイル検出、grep行のパース
- **許可される操作**: ファイル読み込み、行のパース
- **禁止される操作**: AST解析、TSV出力

#### 分析レイヤー（言語別）
- **Java（`analyze.py`）**: Javaソースファイルの読み込み・AST解析、ASTキャッシュの利用、3段階分析
- **C（`analyze_c.py`）**: 正規表現による分類、#define定数の間接追跡
- **Pro*C（`analyze_proc.py`）**: 拡張子ベースのディスパッチ、#define定数 + ホスト変数の間接追跡
- **SQL（`analyze_sql.py`）**: 正規表現による分類、`定数・変数定義` 行から変数名を抽出して同一ファイル内を間接追跡
- **Shell（`analyze_sh.py`）**: 正規表現による分類、`変数代入` / `環境変数エクスポート` 行から変数名を抽出して同一ファイル内を間接追跡（`$VAR` / `${VAR}` パターン）
- **Kotlin（`analyze_kotlin.py`）**: 正規表現による分類、const val定数のプロジェクト全体追跡
- **PL/SQL（`analyze_plsql.py`）**: 正規表現による直接参照のみ分類
- **TypeScript/JavaScript（`analyze_ts.py`）**: 正規表現による直接参照のみ分類（`.ts`/`.tsx`/`.js`/`.jsx`）
- **Python（`analyze_python.py`）**: 正規表現による直接参照のみ分類（`.py`）
- **Perl（`analyze_perl.py`）**: 正規表現による直接参照のみ分類（`.pl`/`.pm`）
- **C#/VB.NET（`analyze_dotnet.py`）**: 正規表現による分類、const/static readonly定数のプロジェクト全体追跡（`.cs`/`.vb`）
- **Groovy（`analyze_groovy.py`）**: 正規表現による分類、static final定数・フィールドのプロジェクト全体追跡、setter追跡（`.groovy`/`.gvy`）

#### 出力レイヤー（全言語共通: `analyze_common.py`）
- **責務**: 全レコードのソート、UTF-8 BOM付きTSV出力、処理サマリの標準出力表示
- **外部ソート**: レコード数 < 100万件 → インメモリソート。100万件以上 → 50万件ごとにチャンクファイルを作成し `heapq.merge` でマージ

### Java/Groovy 4段階分析フロー

```
第1段階（直接参照）
  └── grepヒット行をAST/正規表現で分類
  └── 参照種別 = 直接

第2段階（間接参照）
  └── 第1段階で「定数定義」→ プロジェクト全体で変数名を追跡
  └── 第1段階で「変数代入（フィールド）」→ 同一クラス内を追跡
  └── 第1段階で「変数代入（ローカル変数）」→ 同一メソッド内を追跡
  └── 参照種別 = 間接

第3段階（getter経由）
  └── 第2段階のフィールド追跡後に実施
  └── クラス内でgetter候補を特定（命名規則 + return文解析）
  └── プロジェクト全体でgetter呼び出しを追跡
  └── 参照種別 = 間接（getter経由）

第4段階（setter経由）
  └── 第2段階のフィールド追跡後に実施
  └── クラス内でsetter候補を特定（命名規則 + this.field=引数の解析）
  └── プロジェクト全体でsetter呼び出しを追跡
  └── 参照種別 = 間接（setter経由）
```

**注意**: GetterTracker/SetterTracker（第3・第4段階）は IndirectTracker（第2段階）のフィールド追跡完了後にのみ起動する。第2段階と並列実行は不可。Groovy は正規表現で同等の4段階分析を実施する。

## 共通キャッシュ・パフォーマンスインフラ（`analyze_common.py`）

Phase A〜F のパフォーマンス改善により、ファイル I/O・スキャン・パス解決にかかわるすべてのキャッシュとスキャンロジックが `analyze_common.py` に集約されている。各言語アナライザーは独自のファイルキャッシュを持たず、以下の共通 API を利用する。

### 共通 API 一覧

| 関数 | シグネチャ（簡略） | 説明 |
|------|-------------------|------|
| `iter_grep_lines` | `(path, encoding)` → generator | grep ファイルを 1 行ずつ yield するストリーミングジェネレータ。全行をメモリに展開しないため GB 級ファイルでも OOM しない |
| `iter_source_files` | `(src_dir, extensions)` → `list[Path]` | `rglob` 結果をモジュールグローバルにキャッシュして返す。同一ディレクトリへの複数回呼び出しで rglob を再実行しない |
| `cached_file_lines` | `(path, encoding, stats)` → `list[str]` | サイズベース LRU 行キャッシュ（既定 256MB）。同一ファイルの重複読み込みをゼロにする |
| `resolve_file_cached` | `(filepath, src_dir)` → `Path \| None` | ファイルパス解決結果をキャッシュ。多パターン追跡で同一パスが繰り返し解決されるコストを排除 |
| `build_batch_scanner` | `(patterns)` → `_BatchScanner` | パターン数 ≥ 100 で `pyahocorasick`（Aho-Corasick 法）を自動選択、< 100 では `re.search` を使用。スキャナはパターン数によらず均一の API を提供 |

### メモリ使用量の見積もり

| コンポーネント | 上限 | 制御方法 |
|--------------|------|---------|
| ファイル行キャッシュ（`cached_file_lines`） | 256MB（既定） | `set_file_lines_cache_limit(n_bytes)` で変更可 |
| AST キャッシュ（Java のみ、`analyze.py`） | 最大 2000 件 × 推定 1〜3MB = 最大 6GB | `_MAX_AST_CACHE_SIZE`（`analyze.py`）を縮小 |
| iter_grep_lines ストリーミング | O(1) — 行単位 | 設定不要 |

### 並列処理（`--workers`）

`analyze_all.py` および `analyze.py` などの個別アナライザーは `--workers N`（既定: 1）を受け付け、間接追跡フェーズの**バッチスキャン処理**を `ProcessPoolExecutor` で並列化する。grep ファイル自体は順次処理されるが、各 grep ファイルにつき発生する Java 定数追跡 / Kotlin const val 追跡 / .NET const 追跡 / Groovy static final 追跡 / C・Pro\*C `#define` 追跡などのプロジェクト全体スキャンを、対象ファイルリストをワーカー数で分割（`src_files[i::workers]`）して並列実行する。各ワーカーは独立プロセスで動作するため GIL の制約を受けない。

`--workers` を持つ個別アナライザー: `analyze.py`（Java）, `analyze_sql.py`, `analyze_sh.py`, `analyze_ts.py`, `analyze_python.py`, `analyze_perl.py`, `analyze_plsql.py`。`analyze_c.py` / `analyze_kotlin.py` / `analyze_dotnet.py` / `analyze_groovy.py` / `analyze_proc.py` は `--workers` を持たず、並列実行は `analyze_all.py --workers` 経由となる。

```bash
# CPU コア数を --workers に指定するとバッチ追跡フェーズが N 並列で動く
python analyze_all.py --source-dir ./src --workers 4
```

**注意**: ワーカー数を増やすとメモリ使用量もワーカー数倍になる。ファイル行キャッシュ 256MB × N ワーカー分のメモリが必要。

## データ永続化戦略

### ストレージ方式

| データ種別 | ストレージ | フォーマット | 理由 |
|-----------|----------|-------------|------|
| grep結果入力 | ローカルファイルシステム | テキスト（`filepath:lineno:code`） | ユーザーがgrepを手動実行して配置 |
| 分析結果出力 | ローカルファイルシステム | TSV（UTF-8 BOM付き） | Excelで開いてフィルタ・ソート可能 |
| ASTキャッシュ | オンメモリ dict | javalangのASTオブジェクト | 同一ファイルの再解析を省略 |

### バックアップ戦略

- **対象**: なし（入力はユーザー管理のgrep結果ファイル、出力は再実行で再生成可能）
- **上書き**: 同名TSVファイルが存在する場合は上書き

## パフォーマンス要件

### レスポンスタイム

| 操作 | 目標時間 | 測定環境（参考値） |
|------|---------|---------|
| 4万行・500ファイル規模の処理 | 30分以内（目安） | Intel Core i5 8th Gen 相当（シングルスレッド性能基準）、メモリ8GB |
| 小規模（1000行・50ファイル） | 1分以内 | 同上 |

**注意**: 処理時間より**網羅性を優先**するため、時間制限は設けない。上記の目標時間はローカルノートPCでの参考値であり、精密な計測保証ではない。

### リソース使用量

| リソース | 上限 | 理由 |
|---------|------|------|
| メモリ | 256MB（行キャッシュ）× ワーカー数 + Java AST キャッシュ | ファイル行キャッシュは `cached_file_lines` のサイズベース LRU で 256MB に制限。AST キャッシュ（最大 2000 件 × 推定 1〜3MB）はメモリ不足時に `_MAX_AST_CACHE_SIZE`（`analyze.py`）を縮小すること。60GB 規模のソースでも grep ファイルはストリーミング読み込みのため OOM しない |
| CPU | `--workers N` コア（既定: 1） | `analyze_all.py` および `--workers` を受け付ける個別アナライザー（`analyze.py` 等）は `ProcessPoolExecutor` で間接追跡フェーズのバッチスキャンを並列実行 |
| ディスク | 入力の10倍まで | TSV出力のサイズ見積もり（列追加のため） |

## セキュリティアーキテクチャ

### データ保護

- **暗号化**: 不要（ローカルファイルのみ）
- **アクセス制御**: OSのファイルパーミッションに委譲
- **機密情報管理**: ハードコードされた機密情報なし

### 入力検証

- **`--source-dir`**: `Path.exists()` + `Path.is_dir()` で検証。失敗時は exit code 1
- **`--input-dir`**: 同上
- **grep行**: `re.split(r':(\d+):', line, maxsplit=1)` で厳密パース。不正行はスキップ
- **ファイル読み込み**: `errors='replace'` でエンコーディングエラーを無害化
- **grep結果ファイルサイズ**: `analyze.py`（Java）は 500MB 超の grep ファイルに対して警告を stderr に出力して処理を継続する（50MB 超で進捗報告も有効化）

### エラー表示

- エラーメッセージは日本語で **標準エラー出力（stderr）** へ出力
- スタックトレースは開発モード以外は非表示

## スケーラビリティ設計

### データ増加への対応

- **想定データ量**: grep結果4万行、Javaソースファイル500件
- **ASTキャッシュ**: `dict[str, object | None]` で O(1) アクセス。再解析コストをゼロに（上限 2000 件）
- **mmap 事前フィルタ（`grep_filter_files`）**: バッチスキャン前に `mmap.find()` でパターンを含まないファイルを除外。数万ファイルを数百ファイルに絞り込み、間接追跡フェーズを大幅に高速化
- **ストリーミング読み込み（`iter_grep_lines`）**: grep ファイルを 1 行ずつ yield。全行をメモリに展開しないため GB 級ファイルでも OOM しない
- **共通ファイル行キャッシュ（`cached_file_lines`）**: サイズベース LRU（256MB）。各アナライザーが同一ファイルを再読み込みするコストをゼロに
- **ファイル列挙キャッシュ（`iter_source_files`）**: rglob 結果をモジュールグローバルにキャッシュ。数万ファイルの walk を 1 回に抑制
- **Aho-Corasick スキャナ（`build_batch_scanner`）**: パターン数 ≥ 100 で自動的に `pyahocorasick` を選択。O(n) スキャンで O(n×m) の正規表現多重ループを置換
- **プロセス並列（`--workers`）**: `analyze_all.py` および対応する個別アナライザーが `ProcessPoolExecutor` で間接追跡フェーズのバッチスキャン（対象ファイルリストを `src_files[i::workers]` で分割）を N 並列処理。GIL を回避し CPU コア数に比例した高速化
- **アーカイブ戦略**: 不要（入力ファイルはユーザー管理）

### 機能拡張性

- **現在の構成**: 共通インフラ（`analyze_common.py`）+ 言語別アナライザー（`analyze_*.py`）の分離アーキテクチャ。新言語を追加する場合は `analyze_[言語].py` を新規作成して `analyze_common` をインポートするだけでよい
- **文字コード対応（F-07, Post-MVP）**: `open()` の `encoding=` パラメータ変更のみ
- **HTMLレポート（F-08, Post-MVP）**: `write_tsv` と並列で `write_html` を `analyze_common.py` に追加
- **設定のカスタマイズ**: `--input-dir` / `--output-dir` オプションで対応済み（全言語共通）

## テスト戦略

### ユニットテスト
- **フレームワーク**: unittest（Python標準ライブラリ、記述用）/ pytest（実行用、`requirements-dev.txt`）
- **対象ファイル**: `tests/test_*.py`（全言語。Java: `tests/test_analyze.py`、Pro*C: `tests/test_analyze_proc.py`）
- **カバレッジ目標**: 80%以上（推奨。マージのブロック条件ではない。詳細は `development-guidelines.md` 参照）

### 統合テスト（E2Eテスト）
- **方法**: 言語別のサンプルソース + サンプルgrep結果を使ったE2Eフロー
- **フィクスチャ**: `tests/[言語]/` 以下に言語別に配置（Java: `tests/fixtures/`, C: `tests/c/`, Kotlin: `tests/kotlin/`, PL/SQL: `tests/plsql/`, TypeScript・JS: `tests/ts/`, Python: `tests/python/`, Perl: `tests/perl/`, C#・VB.NET: `tests/dotnet/`, Groovy: `tests/groovy/`, etc.）
- **対象**: 直接参照・間接参照（対応言語のみ）・各言語固有のパターンが期待TSVと一致すること
- **注意（Javaのみ）**: フォールバック率が高い環境ではjavalangのAST解析が多くのファイルでパースエラーを起こすため、統合テストでフォールバック発生件数も確認すること

### 網羅率テスト（KPIテスト）
- 既知のテストケース（各参照パターンを含む言語別サンプルファイル群）を用意
- 実行結果と期待TSVを比較し、**全行が出力に含まれること**を確認

## 技術的制約

### 環境要件
- **OS**: Windows / Mac / Linux（クロスプラットフォーム）
- **Python**: 3.12以上
- **最小メモリ**: 512MB（小規模処理）、2GB推奨（大規模処理）
- **必要ディスク容量**: 入力の10倍程度
- **外部依存**: `javalang` のみ（`pip install -r requirements.txt` でインストール）
- **入力文字コード（ソースファイル / grep結果ファイル）**: `analyze_common.detect_encoding` で自動検出（`chardet` がインストールされている場合のみ）。未インストール時または信頼度 < 0.6 の場合は `cp932` にフォールバック。`--encoding` で強制指定も可能。読み込みは常に `errors='replace'`
- **出力文字コード（TSV）**: UTF-8 BOM付き（`encoding='utf-8-sig'`）— Excelで文字化けなく開くため

### パフォーマンス制約
- 処理時間の上限は設けない（網羅性優先）
- `analyze_all.py` および `--workers` を持つ個別アナライザー（`analyze.py` / `analyze_sql.py` / `analyze_sh.py` / `analyze_ts.py` / `analyze_python.py` / `analyze_perl.py` / `analyze_plsql.py`）は `--workers N` で間接追跡のバッチスキャンを N 並列実行可能（既定: 1）
- ファイル行キャッシュ（`cached_file_lines`）は 256MB LRU で制限。AST キャッシュは `_MAX_AST_CACHE_SIZE = 2000`（メモリ不足時は縮小可）
- 間接追跡フェーズは `grep_filter_files()` による mmap 事前フィルタで高速化（Solaris 10 対応）
- grep ファイルはストリーミング読み込み（`iter_grep_lines`）のため、GB 級でも全行展開しない

### セキュリティ制約
- ローカル実行のみ（ネットワーク接続なし）
- ユーザー指定のディレクトリ外へのファイル書き込みは行わない

## 依存関係管理

| ライブラリ | 用途 | バージョン管理方針 |
|-----------|------|-------------------|
| javalang | Java AST解析（`analyze.py` のみ） | `>=0.13.0,<1.0.0`（バグ修正のみ自動適用） |
| chardet | 文字コード自動検出（任意） | 任意インストール（`pip install chardet`）。未インストール時は cp932 にフォールバック |

**`requirements.txt`**（本番依存）:
```
javalang>=0.13.0,<1.0.0
```

**`requirements-dev.txt`**（開発用依存）:
```
pytest>=9.0.0,<10.0.0
```

**方針**:
- 必須外部依存は `javalang` 1本のみを維持する（C/SQL/Shell/Kotlin/PL/SQL/TypeScript・JS/Python/Perl/C#・VB.NET/Groovy は標準ライブラリのみで完結）
- `chardet` はオプション依存。インストール時のみ文字コード自動検出が有効になる
- `python3 -m venv .venv` で venv を作成し `pip install -r requirements.txt` を実行
- `pip list --outdated` で定期的に確認
