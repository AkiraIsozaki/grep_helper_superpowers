# 開発ガイドライン (Development Guidelines)

## コーディング規約

### 命名規則

#### 変数・関数

```python
# 良い例
ast_cache: dict[str, object] = {}
source_dir: Path = Path(args.source_dir)
def parse_grep_line(line: str) -> dict | None: ...
def classify_usage_regex(code: str) -> str: ...

# 悪い例
d: dict = {}
sd = Path(args.source_dir)
def parse(line): ...
def classify(c): ...
```

**原則**:
- 変数: `snake_case`、名詞または名詞句
- 関数: `snake_case`、動詞で始める（`parse_`, `classify_`, `track_`, `write_`）
- 定数: `UPPER_SNAKE_CASE`（例: `USAGE_PATTERNS`, `DEFAULT_ENCODING`）
- Boolean: `is_`, `has_`, `should_` で始める（例: `is_valid`, `has_getter`）

#### クラス・列挙型

```python
# クラス: PascalCase、名詞
from dataclasses import dataclass
from enum import Enum

class GrepRecord(NamedTuple): ...

class UsageType(Enum):
    CONSTANT  = "定数定義"
    VARIABLE  = "変数代入"
    CONDITION = "条件判定"
    RETURN    = "return文"
    ARGUMENT  = "メソッド引数"
    ANNOTATION = "アノテーション"
    OTHER     = "その他"
```

#### ファイル名

```
# 共通インフラ
analyze_common.py
aho_corasick.py    # Aho-Corasick 多パターンスキャナ

# 統合エントリ
analyze_all.py     # 拡張子から言語を判定して各アナライザーに委譲

# 言語別アナライザー: analyze_[言語].py
analyze.py       # Java（言語名を省略）
analyze_c.py     # C
analyze_dotnet.py  # C#/VB.NET
analyze_groovy.py  # Groovy
analyze_kotlin.py  # Kotlin
analyze_perl.py    # Perl
analyze_plsql.py   # PL/SQL
analyze_proc.py  # Pro*C
analyze_python.py  # Python
analyze_sh.py    # Shell
analyze_sql.py   # SQL
analyze_ts.py    # TypeScript/JavaScript

# テスト
tests/test_analyze.py       # Java
tests/test_analyze_proc.py  # Pro*C
tests/test_common.py        # 共通インフラ
tests/test_aho_corasick.py  # Aho-Corasick スキャナ
tests/test_all_analyzer.py  # analyze_all.py（言語判定）
tests/test_c_analyzer.py
tests/test_dotnet_analyzer.py
tests/test_groovy_analyzer.py
tests/test_kotlin_analyzer.py
tests/test_perl_analyzer.py
tests/test_plsql_analyzer.py
tests/test_python_analyzer.py
tests/test_sh_analyzer.py
tests/test_sql_analyzer.py
tests/test_ts_analyzer.py

```

### コードフォーマット

**インデント**: 4スペース

**行の長さ**: 最大120文字

**型ヒント**: 必須（関数の引数・戻り値、クラスフィールド）

```python
# 良い例: 型ヒントで意図を明確に
def parse_grep_line(line: str) -> dict | None:
    ...

def write_tsv(records: list[GrepRecord], output_path: Path) -> None:
    ...

# 悪い例: 型ヒントなし
def parse_grep_line(line):
    ...
```

### コメント規約

**関数・クラスのdocstring**:
```python
def classify_usage(code: str, filepath: str, lineno: int,
                   source_dir: Path,
                   stats: ProcessStats) -> str:
    """コード行を解析し、使用タイプ文字列を返す。

    javalangによるAST解析を試み、パースエラーの場合は
    正規表現フォールバックで継続する。

    Args:
        code: 分類対象のコード行（前後の空白はtrim済み）
        filepath: Javaファイルのパス（AST解析用）
        lineno: 対象行の行番号（AST解析用）
        source_dir: Javaソースのルートディレクトリ
        stats: 処理統計（フォールバック件数の記録用）

    Returns:
        UsageType の value 文字列（7種のいずれか）
    """
```

**インラインコメント**:
```python
# 良い例: なぜそうするかを説明
# Windowsパス（C:\path\file.java:10:code）に対応するためmaxsplit=1を使用
parts = re.split(r':(\d+):', line.rstrip(), maxsplit=1)

# 良い例: 複雑なロジックを説明
# false positiveは許容（「もれなく」が最優先のため全件出力）
# 他クラスの同名getterが混入する可能性があるが仕様上許容
records.extend(track_getter_calls(getter_name, source_dir, origin, stats))

# 悪い例: コードを繰り返すだけ
# listをsortする
records.sort(key=lambda r: (r.keyword, r.filepath, r.lineno))
```

### エラーハンドリング

**原則**:
- 予期されるエラー（不正入力、パースエラー）: スキップして統計に記録し処理継続
- 入力検証エラー（`--source-dir` 未指定等）: stderrに日本語メッセージ表示 + exit code 1
- 予期しないエラー: stderrに表示 + exit code 2（上位に伝播させる）
- **例外を無視しない**（`except: pass` は禁止）

```python
# 良い例: スキップして統計に記録
try:
    tree = javalang.parse.parse(source)
    _ast_cache[filepath] = tree
except Exception:
    _ast_cache[filepath] = None
    stats.fallback_files.add(filepath)  # setなので重複は自動的に無視
    # フォールバックを使用して処理継続

# 良い例: 入力エラーはstderrへ日本語で出力
if not source_dir.exists():
    print(f"エラー: --source-dir で指定したディレクトリが存在しません: {source_dir}",
          file=sys.stderr)
    sys.exit(1)

# 悪い例: 例外を握りつぶす
try:
    tree = javalang.parse.parse(source)
except Exception:
    pass  # NG: エラー情報が失われる
```

### パフォーマンス

**キャッシュは `analyze_common.py` に集約する（最重要）**:

すべてのファイル I/O キャッシュ・ファイル列挙キャッシュ・パス解決キャッシュは `analyze_common.py` に実装済みである。新規アナライザーを追加する場合も、モジュールスコープで独自の `_file_cache` / `_source_files` 等のキャッシュ辞書を作ってはならない。代わりに以下の共通 API を使うこと。

| 共通 API | 用途 |
|---------|------|
| `iter_grep_lines(path, encoding)` | grep ファイルのストリーミング読み込み。全行をリストに展開しない |
| `iter_source_files(src_dir, extensions)` | ソースファイル列挙（rglob 結果をキャッシュ） |
| `cached_file_lines(path, encoding, stats)` | ソースファイル行のサイズベース LRU キャッシュ（256MB） |
| `resolve_file_cached(filepath, src_dir)` | ファイルパス解決のキャッシュ |
| `build_batch_scanner(patterns)` | 多パターンスキャナ（Aho-Corasick / regex 自動選択） |

```python
# 良い例: 共通 API を使う
from analyze_common import (
    iter_source_files, cached_file_lines, resolve_file_cached, build_batch_scanner
)

def _track_constants(names: list[str], src_dir: Path, stats) -> list:
    scanner = build_batch_scanner(names)          # ≥100 パターンで自動 AC 選択
    for path in iter_source_files(src_dir, [".kt"]):
        lines = cached_file_lines(path, "utf-8", stats)  # LRU キャッシュから取得
        for i, line in enumerate(lines, 1):
            if scanner.search(line):
                ...

# 悪い例: 独自キャッシュを定義する（絶対にやらない）
_my_file_cache: dict[str, list[str]] = {}  # NG: analyze_common のキャッシュと二重管理になる

def _read_lines(path: Path) -> list[str]:
    if str(path) not in _my_file_cache:
        _my_file_cache[str(path)] = path.read_text().splitlines()
    return _my_file_cache[str(path)]
```

**ASTキャッシュ（Java のみ）**:
```python
# 良い例: キャッシュを使って再解析を省略
_ast_cache: dict[str, object | None] = {}

def get_ast(filepath: str, source_dir: Path) -> object | None:
    if filepath not in _ast_cache:
        full_path = source_dir / filepath
        try:
            source = full_path.read_text(encoding="shift_jis", errors="replace")
            _ast_cache[filepath] = javalang.parse.parse(source)
        except Exception:
            _ast_cache[filepath] = None
    return _ast_cache[filepath]

# 悪い例: キャッシュなしで毎回解析（大規模ファイルで極端に遅くなる）
def get_ast(filepath: str, source_dir: Path) -> object | None:
    source = (source_dir / filepath).read_text(encoding="shift_jis", errors="replace")
    return javalang.parse.parse(source)
```

**正規表現のプリコンパイル**:
```python
# 良い例: モジュールレベルでコンパイル（起動時に1度だけ）
import re

USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'@\w+\s*\('),        "アノテーション"),
    (re.compile(r'\bstatic\s+final\b'), "定数定義"),
    # ...
]

# 悪い例: ループ内でコンパイル（毎回コンパイルコストが発生）
for record in records:
    if re.search(r'@\w+\s*\(', record.code):  # NG
        ...
```

## Git運用ルール

### ブランチ戦略

**ブランチ種別**:
- `main`: 本番環境にデプロイ可能な状態（zip配布可能）
- `develop`: 開発の最新状態
- `feature/[機能名]`: 新機能開発（例: `feature/f03-indirect-tracking`）
- `fix/[修正内容]`: バグ修正（例: `fix/ast-cache-none-handling`）
- `refactor/[対象]`: リファクタリング

**マージフロー**:
```
feature/* / fix/* / refactor/*
    ↓ PR（機能完成時）
  develop
    ↓ PR（リリース時、zip配布タグを付与）
   main
```

**マージ条件**:
- レビュアー1名以上の承認
- 全テストパス（`python -m pytest tests/ -v`）
- コードスタイル準拠（`python -m flake8 analyze*.py tests/`）
- `feature/*` / `fix/*` → `develop` へマージ後、ブランチを削除する
- `develop` → `main` はリリース時のみ（`vX.Y.Z` タグを付与）

### コミットメッセージ規約

**フォーマット**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: コードフォーマット
- `refactor`: リファクタリング
- `test`: テスト追加・修正
- `chore`: ビルド、補助ツール等

**例**:
```
feat(tracker): getter経由の間接参照追跡機能を追加（F-04）

フィールドに代入された値がgetter経由で使われる箇所を追跡する。
- 命名規則（type → getType()）によるgetter候補特定
- return文解析による非標準命名のgetter検出
- プロジェクト全体でのgetter呼び出し箇所をAST解析
- false positiveは許容（もれなく優先）

Closes #12
```

### プルリクエストプロセス

**作成前のチェック（作成者）**:
- [ ] 全てのテストがパス（`python -m pytest tests/ -v`）
- [ ] 構文エラーがない（`python -m py_compile analyze*.py`）
- [ ] コードスタイル準拠（`python -m flake8 analyze*.py tests/`）
- [ ] 型ヒントが適切に付与されている
- [ ] `USAGE_PATTERNS` 等の定数がモジュールレベルで定義されている

**マージ条件（レビュアー）**:
- レビュアー1名以上の承認
- 上記チェックリストが全て完了していること
- マージ後はブランチを削除する

## テスト戦略

### テストの種類

#### ユニットテスト

**対象**: 個別の関数・クラス  
**カバレッジ目標**: 80%以上（PRレビュー前に `coverage report` で確認。80%を下回る場合はテスト追加を推奨するが、マージのブロック条件ではない）  
**フレームワーク**: `unittest`（標準ライブラリ、記述用）/ `pytest`（実行用）  
**テストファイル配置**: 全テストファイルは `tests/` 配下に配置する。Java は `tests/test_analyze.py`、Pro*C は `tests/test_analyze_proc.py`、その他は `tests/test_[言語]_analyzer.py`

```python
import unittest
from pathlib import Path

class TestGrepParser(unittest.TestCase):
    """F-01: parse_grep_line() のテスト。"""

    def test_正常なgrep行をパースして辞書を返す(self):
        """正常なgrep行をパースして辞書を返すこと。"""
        # Arrange
        line = "src/main/java/Constants.java:10:    public static final String CODE = \"TARGET\";"

        # Act
        result = parse_grep_line(line)

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result["filepath"], "src/main/java/Constants.java")
        self.assertEqual(result["lineno"], "10")
        self.assertIn("CODE", result["code"])

    def test_バイナリ通知行はNoneを返す(self):
        """バイナリ通知行はNoneを返すこと。"""
        line = "Binary file src/main/resources/logo.png matches"
        self.assertIsNone(parse_grep_line(line))

    def test_空行や空白のみの行はNoneを返す(self):
        """空行・空白のみの行はNoneを返すこと。"""
        self.assertIsNone(parse_grep_line(""))
        self.assertIsNone(parse_grep_line("   "))
```

#### 分類精度テスト

**KPI**: 7種の使用タイプへの自動分類が90%以上の精度であること

```python
class TestUsageClassifier(unittest.TestCase):
    """F-02: classify_usage_regex() の7種分類テスト。"""

    def test_static_final定数定義を正しく分類する(self):
        """static final定数定義を正しく分類すること。"""
        code = 'public static final String CODE = "TARGET";'
        self.assertEqual(classify_usage_regex(code), "定数定義")

    def test_equalsを含む行を条件判定として分類する(self):
        """.equals() を含む行を条件判定と分類すること。"""
        code = 'if (someVar.equals(CODE)) {'
        self.assertEqual(classify_usage_regex(code), "条件判定")

    def test_アノテーション行を正しく分類する(self):
        """アノテーション行を正しく分類すること。"""
        code = '@RequestMapping("TARGET")'
        self.assertEqual(classify_usage_regex(code), "アノテーション")

    def test_return文を正しく分類する(self):
        """return文を正しく分類すること。"""
        code = 'return CODE;'
        self.assertEqual(classify_usage_regex(code), "return文")

    def test_メソッド引数を正しく分類する(self):
        """メソッド引数を正しく分類すること。"""
        code = 'someService.process(CODE);'
        self.assertEqual(classify_usage_regex(code), "メソッド引数")

    def test_変数代入を正しく分類する(self):
        """変数代入を正しく分類すること。"""
        code = 'String msg = CODE;'
        self.assertEqual(classify_usage_regex(code), "変数代入")

    def test_コメント行をその他に分類する(self):
        """コメント行をその他に分類すること。"""
        code = '// TARGET はここで使われる'
        self.assertEqual(classify_usage_regex(code), "その他")
```

#### 統合テスト（網羅率KPIテスト）

**フィクスチャ管理方針（言語別）**:
```
tests/
├── fixtures/         # Java（tests/test_analyze.py用）
│   ├── input/        # SAMPLE.grep
│   ├── java/         # Constants.java, Entity.java, Service.java
│   ├── intense/      # 多パッケージ大規模フィクスチャ
│   └── expected/     # SAMPLE.tsv（手動作成・コミット管理）
├── c/                # C（tests/test_c_analyzer.py用）
│   ├── input/  src/  expected/
├── proc/             # Pro*C（tests/test_analyze_proc.py用）
│   ├── input/  src/  expected/
├── sh/               # Shell（tests/test_sh_analyzer.py用）
│   ├── input/  src/  expected/
├── sql/              # SQL（tests/test_sql_analyzer.py用）
│   ├── input/  src/  expected/
├── ts/               # TypeScript/JS（tests/test_ts_analyzer.py用）
│   ├── input/  src/  expected/
├── python/           # Python（tests/test_python_analyzer.py用）
│   ├── input/  src/  expected/
├── perl/             # Perl（tests/test_perl_analyzer.py用）
│   ├── input/  src/  expected/
├── dotnet/           # C#/VB.NET（tests/test_dotnet_analyzer.py用）
│   ├── input/  src/  expected/
├── groovy/           # Groovy（tests/test_groovy_analyzer.py用）
│   ├── input/  src/  expected/
├── kotlin/           # Kotlin（tests/test_kotlin_analyzer.py用）
│   ├── input/  src/  expected/
├── plsql/            # PL/SQL（tests/test_plsql_analyzer.py用）
│   ├── input/  src/  expected/
└── all/              # analyze_all.py（tests/test_all_analyzer.py用）
    ├── input/  src/
```

**expected/*.tsv の管理**:
- 手動作成してコミット管理する（自動生成しない）
- フィクスチャは最小限のコード行数で各言語の全パターンをカバーする

### テスト命名規則

**パターン**: `test_<日本語の自然な文>`（メソッド名・docstringともに日本語で記述する）

テストメソッド名は「何をテストするか」を日本語の自然な文で表現する。
あわせて docstring にも日本語で振る舞いを記述する（pytest 出力での可読性向上のため）。

```python
# 良い例: 日本語の自然な文 + 日本語docstring
def test_正常なgrep行をパースして辞書を返す(self):
    """正常なgrep行をパースして辞書を返すこと。"""
    ...

def test_バイナリ通知行はNoneを返す(self):
    """バイナリ通知行はNoneを返すこと。"""
    ...

def test_static_final定数定義を正しく分類する(self):
    """static final定数定義を正しく分類すること。"""
    ...

def test_UTF8_BOM付きで出力されExcelで文字化けしない(self):
    """write_tsv が UTF-8 BOM 付きで出力されること。"""
    ...

# 悪い例
def test1(self): ...
def test_parse(self): ...
def test_ok(self): ...
def test_parse_valid_line_returns_dict(self): ...  # 英語のみは不可
```

### テスト実行

```bash
# 全テスト実行
python -m pytest tests/ -v

# 特定のテストファイル
python -m pytest tests/test_analyze.py::TestGrepParser -v
python -m pytest tests/test_c_analyzer.py -v

# カバレッジ測定（coverage.py）
coverage run -m pytest tests/
coverage report
coverage html  # htmlcov/index.html で視覚的に確認
```

## コードレビュー基準

### レビューポイント

**機能性（最重要）**:
- [ ] 「もれなく」の原則に従っているか（スキップではなく「その他」で出力）
- [ ] エッジケースが考慮されているか（空行・バイナリ通知・Windowsパスなど）
- [ ] エラーハンドリングが適切か（例外を握りつぶしていないか）

**可読性**:
- [ ] 命名が明確か（`snake_case`、動詞始まり関数名）
- [ ] 型ヒントが適切か
- [ ] 複雑なロジックにコメントがあるか

**パフォーマンス**:
- [ ] ファイル I/O に `cached_file_lines` / `iter_source_files` / `resolve_file_cached` を使用しているか（独自 `_file_cache` を定義していないか）
- [ ] grep ファイルの読み込みに `iter_grep_lines` を使用しているか（全行をリストに展開していないか）
- [ ] 多パターンスキャンに `build_batch_scanner` を使用しているか
- [ ] ASTキャッシュ（Java）を使用しているか
- [ ] 正規表現がモジュールレベルでプリコンパイルされているか
- [ ] 不要な計算・ループがないか

**セキュリティ**:
- [ ] 入力検証が適切か（`--source-dir` 等の存在確認）
- [ ] エラーメッセージが日本語でstderrに出力されているか

### レビューコメントの優先度

- `[必須]`: 修正必須（バグ・セキュリティ問題・テスト漏れ）
- `[推奨]`: 修正推奨（パフォーマンス・可読性）
- `[提案]`: 検討してほしい
- `[質問]`: 理解のための質問

## 開発環境セットアップ

### 必要なツール

| ツール | バージョン | インストール方法 |
|--------|-----------|-----------------|
| Python | 3.12以上 | devcontainer に含まれる |
| venv | Python標準 | Python 3.12+ に同梱 |
| javalang | >=0.13.0,<1.0.0 | `pip install -r requirements.txt` |
| chardet | >=5.0.0,<6.0.0 | `pip install -r requirements.txt` |
| pyahocorasick | >=2.0.0,<3.0.0 | `pip install -r requirements.txt` |

**flake8設定** (`.flake8`):
```ini
[flake8]
max-line-length = 120
exclude =
    .venv,
    __pycache__,
    dist,
    .steering
```
プロジェクトルートの `.flake8` で設定済み。`python -m flake8 analyze*.py tests/` で実行する。

### セットアップ手順

#### devcontainerを使う場合（推奨）

VS Code Dev Containers または GitHub Codespaces を使うと、Python 3.12とvenvが自動でセットアップされます。

```bash
# VS Code Dev Containers
# 1. VS Code で「Reopen in Container」を実行
# 2. コンテナ起動後、依存関係をインストール
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. テストの実行
python -m pytest tests/ -v
```

#### ローカル環境を使う場合

```bash
# 1. リポジトリのクローン
git clone [URL]
cd grep_analyzer

# 2. venv作成と依存関係のインストール
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. テストの実行
python -m pytest tests/ -v

# 4. ツールの実行（テスト用）
python analyze.py --source-dir /path/to/sample/java
```

## チェックリスト

実装完了前に確認:

### コード品質
- [ ] 命名が明確で一貫している（`snake_case`）
- [ ] 型ヒントが適切に定義されている
- [ ] 関数が単一の責務を持っている（20〜50行を目安）
- [ ] `USAGE_PATTERNS` 等の定数がモジュールレベルで定義されている
- [ ] ASTキャッシュが適切に使われている（Java のみ）
- [ ] ファイル I/O キャッシュは `analyze_common.py` の共通 API を使っている（独自 `_file_cache` を定義していない）

### 網羅性（最重要）
- [ ] 分類できないものは「その他」で出力している（スキップしていない）
- [ ] バイナリ通知行・空行はスキップして統計に記録している
- [ ] javalangパースエラーは正規表現フォールバックで継続している
- [ ] エンコーディングエラーは `errors='replace'` で継続している

### テスト
- [ ] `python -m pytest tests/ -v` が全件パスする
- [ ] 7種の使用タイプそれぞれのテストケースがある
- [ ] 境界ケース（空行・バイナリ通知行・Windowsパス）のテストがある

### ドキュメント
- [ ] 複雑なロジック（getter候補特定・スコープ判定）にコメントがある
- [ ] 公開関数にdocstringがある

### ツール
- [ ] 変更したモジュールすべてで `python -m py_compile [ファイル名]` が通る（構文エラーなし）
- [ ] `python -m flake8 analyze*.py tests/` が通る（コードスタイル準拠）
