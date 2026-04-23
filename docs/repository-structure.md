# リポジトリ構造定義書 (Repository Structure Document)

## プロジェクト構造

```
/（リポジトリルート）
├── analyze.py           # Javaアナライザー（3段階分析：直接/間接/getter経由）
├── analyze_common.py    # 全言語共通インフラ（GrepRecord, ProcessStats, parse_grep_line, write_tsv, detect_encoding）
├── analyze_c.py         # 純Cアナライザー（正規表現分類）
├── analyze_dotnet.py    # C#/VB.NETアナライザー（const/static readonly定数の間接追跡あり）
├── analyze_all.py       # 全言語対応ディスパッチャー（拡張子/シバン判定 → 各分類器に振り分け）
├── analyze_groovy.py    # Groovyアナライザー（static final間接追跡・setter追跡あり）
├── analyze_kotlin.py    # Kotlinアナライザー（const val定数の間接追跡あり）
├── analyze_perl.py      # Perlアナライザー（直接参照のみ）
├── analyze_plsql.py     # PL/SQLアナライザー（直接参照のみ）
├── analyze_proc.py      # Pro*Cアナライザー（.pc/.c拡張子ベースのディスパッチ）
├── analyze_python.py    # Pythonアナライザー（直接参照のみ）
├── analyze_sh.py        # Shellスクリプトアナライザー（BASH/CSH/TCSH）
├── analyze_sql.py       # Oracle SQLアナライザー
├── analyze_ts.py        # TypeScript/JavaScriptアナライザー（直接参照のみ）
├── tests/test_analyze.py          # Javaアナライザーのユニットテスト・統合テスト
├── tests/test_analyze_proc.py     # Pro*Cアナライザーのユニットテスト・統合テスト
├── tests/test_dotnet_analyzer.py  # C#/VB.NETアナライザーのユニットテスト・統合テスト
├── tests/test_groovy_analyzer.py  # Groovyアナライザーのユニットテスト・統合テスト
├── tests/test_kotlin_analyzer.py  # Kotlinアナライザーのユニットテスト・統合テスト
├── tests/test_perl_analyzer.py    # Perlアナライザーのユニットテスト・統合テスト
├── tests/test_plsql_analyzer.py   # PL/SQLアナライザーのユニットテスト・統合テスト
├── tests/test_python_analyzer.py  # Pythonアナライザーのユニットテスト・統合テスト
├── tests/test_ts_analyzer.py      # TypeScript/JSアナライザーのユニットテスト・統合テスト
├── requirements.txt     # 本番依存ライブラリ（javalang のみ）
├── requirements-dev.txt # 開発用依存ライブラリ（pytest）
├── README.md            # 利用者向け手順書（日本語）
├── CLAUDE.md            # Claude Code設定（AIアシスタントへの指示・技術スタック）
├── .flake8              # flake8設定（max-line-length=120等）
├── .gitignore           # Git除外設定
├── input/               # grep結果ファイルの配置ディレクトリ
│   └── .gitkeep
├── output/              # TSV出力先ディレクトリ（自動作成）
│   └── .gitkeep
├── tests/               # テスト用フィクスチャ（言語別）
│   ├── fixtures/        # Javaテストフィクスチャ（tests/test_analyze.py用）
│   │   ├── input/
│   │   ├── java/
│   │   ├── intense/     # 大規模Javaフィクスチャ（多パッケージ構成）
│   │   └── expected/
│   ├── c/               # Cテストフィクスチャ（test_c_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── proc/            # Pro*Cテストフィクスチャ（tests/test_analyze_proc.py用）
│   │   ├── input/
│   │   ├── src/         # .pc / .c 混在ファイル
│   │   └── expected/
│   ├── sh/              # Shellテストフィクスチャ（test_sh_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── sql/             # SQLテストフィクスチャ（test_sql_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── kotlin/          # Kotlinテストフィクスチャ（test_kotlin_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── plsql/           # PL/SQLテストフィクスチャ（test_plsql_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── ts/              # TypeScript/JSテストフィクスチャ（test_ts_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── python/          # Pythonテストフィクスチャ（test_python_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── perl/            # Perlテストフィクスチャ（test_perl_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── dotnet/          # C#/VB.NETテストフィクスチャ（test_dotnet_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── groovy/          # Groovyテストフィクスチャ（test_groovy_analyzer.py用）
│   │   ├── input/
│   │   ├── src/
│   │   └── expected/
│   ├── test_all_analyzer.py
│   ├── test_c_analyzer.py
│   ├── test_common.py
│   ├── test_dotnet_analyzer.py
│   ├── test_groovy_analyzer.py
│   ├── test_kotlin_analyzer.py
│   ├── test_perl_analyzer.py
│   ├── test_plsql_analyzer.py
│   ├── test_python_analyzer.py
│   ├── test_sh_analyzer.py
│   ├── test_sql_analyzer.py
│   └── test_ts_analyzer.py
├── docs/                # プロジェクトドキュメント
│   ├── product-requirements.md
│   ├── functional-design.md
│   ├── architecture.md
│   ├── repository-structure.md  （本ドキュメント）
│   ├── development-guidelines.md
│   ├── tool-overview.md
│   └── glossary.md
├── .claude/             # Claude Code設定・スキル定義
├── .devcontainer/       # VS Code Dev Containers設定
└── .steering/           # 作業単位のステアリングファイル（作業時に生成）
    └── [YYYYMMDD]-[task-name]/
```

## ディレクトリ詳細

### analyze_common.py（共通インフラ）

**役割**: 全言語アナライザーが共有するデータモデル・ユーティリティを提供する

**配置クラス・関数**:
- `GrepRecord`（NamedTuple）: 分析結果の1件を表すデータモデル
- `ProcessStats`（dataclass）: 処理統計（スキップ・フォールバック件数）
- `RefType`（Enum）: 参照種別（直接/間接/間接（getter経由）/間接（setter経由））
- `parse_grep_line()`: grep結果1行のパース（全言語共通）
- `write_tsv()`: UTF-8 BOM付きTSV出力（100万件超は外部ソート）
- `detect_encoding()`: ファイルの文字コード自動検出（chardetオプション使用）

**依存関係**:
- 依存可能: `re`, `csv`, `argparse`, `pathlib`, `sys`, `dataclasses`, `enum`, `heapq`, `tempfile`
- オプション依存: `chardet`（文字コード自動検出。未インストール時は cp932 フォールバック）
- 依存禁止: `javalang`（Javaアナライザー専用のため）

---

### analyze.py（Javaアナライザー）

**役割**: Java grep結果の3段階分析エントリーポイント

**配置クラス・関数**:
- `classify_usage()`: AST（javalang）+ 正規表現フォールバックによる分類
- `classify_usage_regex()`: 正規表現フォールバック（7種）
- `process_grep_file()`: grepファイル全行の処理（第1段階）
- `track_constant()`: 定数のプロジェクト全体追跡（第2段階）
- `track_field()`: フィールドの同一クラス追跡（第2段階）
- `track_local()`: ローカル変数の同一メソッド追跡（第2段階）
- `find_getter_names()`: getter候補の特定（第3段階）
- `track_getter_calls()`: getter呼び出し箇所の追跡（第3段階）
- `print_report()`: 処理サマリの標準出力表示
- `main()`: エントリーポイント（argparse + 全処理の統括）

**依存関係**:
- `analyze_common`（GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv）
- `javalang`（唯一の外部依存）
- `re`, `argparse`, `pathlib`, `sys`

---

### analyze_c.py（Cアナライザー）

**役割**: 純C（`.c`/`.h`）grep結果の正規表現分類エントリーポイント

**主要関数**:
- `classify_usage_c()`: 正規表現で6種（#define定数定義・条件判定・return文・変数代入・関数引数・その他）に分類
- `process_grep_file()`: grepファイル処理（直接参照のみ）
- `track_define()`: `#define` 定数のプロジェクト全体追跡（間接参照）
- `main()`: CLIエントリーポイント

**依存関係**: `analyze_common`, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_proc.py（Pro*Cアナライザー）

**役割**: Pro*C（`.pc`/`.c`混在）grep結果の分析エントリーポイント

**主要関数**:
- `classify_usage_proc()`: `.pc` ファイル向け7種分類（EXEC SQL文含む）
- `_classify_for_filepath()`: 拡張子ベースのディスパッチ（`.c`/`.h` は `classify_usage_c` を使用）
- `track_define()`: `#define` 定数の `.pc`/`.c` 横断追跡（間接参照）
- `main()`: CLIエントリーポイント

**依存関係**: `analyze_common`, `analyze_c`（`classify_usage_c` のみimport）

---

### analyze_sh.py（Shellアナライザー）

**役割**: BASH/CSH/TCSH grep結果の正規表現分類エントリーポイント

**使用タイプ（6種）**: 環境変数エクスポート・変数代入・条件判定・echo/print出力・コマンド引数・その他

**依存関係**: `analyze_common`, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_sql.py（SQLアナライザー）

**役割**: Oracle SQL（11g）grep結果の正規表現分類エントリーポイント

**使用タイプ（7種）**: 例外・エラー処理・定数・変数定義・WHERE条件・比較・DECODE・INSERT/UPDATE値・SELECT/INTO・その他

**依存関係**: `analyze_common`, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_kotlin.py（Kotlinアナライザー）

**役割**: Kotlin（`.kt`/`.kts`）grep結果の正規表現分類・const val定数間接追跡エントリーポイント

**主要関数**:
- `classify_usage_kotlin()`: 正規表現で7種（const定数定義・変数代入・条件判定・return文・アノテーション・関数引数・その他）に分類
- `extract_const_name()`: `const val` 定義行から定数名を抽出
- `track_const()`: `const val` 定数を `.kt`/`.kts` ファイル対象にプロジェクト全体追跡（間接参照）
- `process_grep_file()`: grepファイル処理（直接参照）
- `main()`: CLIエントリーポイント（`--encoding` オプションあり）

**依存関係**: `analyze_common`（`detect_encoding` 含む）, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_plsql.py（PL/SQLアナライザー）

**役割**: PL/SQL（`.pls`/`.pck`/`.prc`/`.pkb`/`.pks`/`.fnc`/`.trg`）grep結果の正規表現分類エントリーポイント

**主要関数**:
- `classify_usage_plsql()`: 正規表現で7種（定数/変数宣言・EXCEPTION処理・条件判定・カーソル定義・INSERT/UPDATE値・WHERE条件・その他）に分類
- `process_grep_file()`: grepファイル処理（直接参照のみ、間接追跡なし）
- `main()`: CLIエントリーポイント（`--encoding` オプションあり）

**依存関係**: `analyze_common`（`detect_encoding` 含む）, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_ts.py（TypeScript/JavaScriptアナライザー）

**役割**: TypeScript/JavaScript（`.ts`/`.tsx`/`.js`/`.jsx`）grep結果の正規表現分類エントリーポイント

**使用タイプ（7種）**: const定数定義・変数代入(let/var)・条件判定・return文・デコレータ・関数引数・その他

**依存関係**: `analyze_common`（`detect_encoding` 含む）, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_python.py（Pythonアナライザー）

**役割**: Python（`.py`）grep結果の正規表現分類エントリーポイント

**使用タイプ（6種）**: 変数代入・条件判定・return文・デコレータ・関数引数・その他

**依存関係**: `analyze_common`（`detect_encoding` 含む）, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_perl.py（Perlアナライザー）

**役割**: Perl（`.pl`/`.pm`）grep結果の正規表現分類エントリーポイント

**使用タイプ（6種）**: use constant定義・変数代入・条件判定・print/say出力・関数引数・その他

**依存関係**: `analyze_common`（`detect_encoding` 含む）, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_dotnet.py（C#/VB.NETアナライザー）

**役割**: C#/VB.NET（`.cs`/`.vb`）grep結果の正規表現分類・const/static readonly定数間接追跡エントリーポイント

**主要関数**:
- `classify_usage_dotnet()`: 正規表現で7種（定数定義(Const/readonly)・変数代入・条件判定・return文・属性(Attribute)・メソッド引数・その他）に分類
- `track_const()`: `const` / `static readonly` 定数を `.cs`/`.vb` ファイル対象にプロジェクト全体追跡（間接参照）
- `main()`: CLIエントリーポイント（`--encoding` オプションあり）

**依存関係**: `analyze_common`（`detect_encoding` 含む）, `re`, `argparse`, `pathlib`, `sys`

---

### analyze_groovy.py（Groovyアナライザー）

**役割**: Groovy（`.groovy`/`.gvy`）grep結果の正規表現分類・static final定数間接追跡・setter追跡エントリーポイント

**主要関数**:
- `classify_usage_groovy()`: 正規表現で7種（static final定数定義・変数代入・条件判定・return文・アノテーション・メソッド引数・その他）に分類
- `track_static_final_groovy()`: `static final` 定数をプロジェクト全体追跡（間接参照）
- `track_field_groovy()`: クラスフィールドを同一クラス内で追跡（間接参照）
- `find_getter_names_groovy()`: 正規表現でgetter候補メソッド名を特定
- `find_setter_names_groovy()`: 正規表現でsetter候補メソッド名を特定
- `_batch_track_getter_setter_groovy()`: getter/setter呼び出し箇所をプロジェクト全体で一括追跡
- `main()`: CLIエントリーポイント（`--encoding` オプションあり）

**依存関係**: `analyze_common`（`detect_encoding` 含む）, `re`, `argparse`, `pathlib`, `sys`

---

### tests/（テストファイル・フィクスチャ）

**言語別テストファイル（`tests/` 直下）**:
- `test_analyze.py`: `analyze.py`（Java）のユニットテスト・統合テスト
- `test_analyze_proc.py`: `analyze_proc.py`（Pro*C）のユニットテスト・統合テスト（E2E含む）
- `test_common.py`: `analyze_common` のユニットテスト
- `test_all_analyzer.py`: `analyze_all` のE2E統合テスト（多言語混在フィクスチャ使用）
- `test_c_analyzer.py`: `analyze_c` のE2E統合テスト
- `test_sh_analyzer.py`: `analyze_sh` のE2E統合テスト
- `test_sql_analyzer.py`: `analyze_sql` のE2E統合テスト
- `test_kotlin_analyzer.py`: `analyze_kotlin` のユニットテスト・E2E統合テスト
- `test_plsql_analyzer.py`: `analyze_plsql` のユニットテスト・E2E統合テスト
- `test_ts_analyzer.py`: `analyze_ts` のユニットテスト・E2E統合テスト
- `test_python_analyzer.py`: `analyze_python` のユニットテスト・E2E統合テスト
- `test_perl_analyzer.py`: `analyze_perl` のユニットテスト・E2E統合テスト
- `test_dotnet_analyzer.py`: `analyze_dotnet` のユニットテスト・E2E統合テスト
- `test_groovy_analyzer.py`: `analyze_groovy` のユニットテスト・E2E統合テスト

**フィクスチャ構成**:
```
tests/
├── fixtures/          # Java（tests/test_analyze.py用）
│   ├── input/         # SAMPLE.grep
│   ├── java/          # Constants.java, Entity.java, Service.java
│   ├── intense/       # 多パッケージ大規模フィクスチャ
│   │   ├── grep/      # ORDER_TYPE_NORMAL.grep, orderStatus.grep
│   │   └── java/      # com/example/ 以下の多ファイル構成
│   └── expected/      # SAMPLE.tsv（手動作成・コミット管理）
├── c/                 # C（test_c_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.c
│   └── expected/      # TARGET.tsv
├── proc/              # Pro*C（tests/test_analyze_proc.py用）
│   ├── input/         # TARGET.grep, MIXVAL.grep
│   ├── src/           # sample.pc, sample_c.c, mixed.pc
│   └── expected/      # TARGET.tsv, MIXVAL.tsv
├── sh/                # Shell（test_sh_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.sh
│   └── expected/      # TARGET.tsv
├── sql/               # SQL（test_sql_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.sql
│   └── expected/      # TARGET.tsv
├── kotlin/            # Kotlin（test_kotlin_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.kt
│   └── expected/      # TARGET.tsv
├── plsql/             # PL/SQL（test_plsql_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.pls
│   └── expected/      # TARGET.tsv
├── ts/                # TypeScript/JS（test_ts_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.ts
│   └── expected/      # TARGET.tsv
├── python/            # Python（test_python_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.py
│   └── expected/      # TARGET.tsv
├── perl/              # Perl（test_perl_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.pl
│   └── expected/      # TARGET.tsv
├── dotnet/            # C#/VB.NET（test_dotnet_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.cs
│   └── expected/      # TARGET.tsv
├── groovy/            # Groovy（test_groovy_analyzer.py用）
│   ├── input/         # TARGET.grep
│   ├── src/           # sample.groovy
│   └── expected/      # TARGET.tsv
└── all/               # 全言語ディスパッチャー（test_all_analyzer.py用）
    ├── input/         # TARGET.grep（複数言語混在）
    └── src/           # Main.java, Service.groovy, deploy.sh, config.xml, cleanup（シバン付き）
```

**運用ルール**:
- `expected/*.tsv` は手動作成してコミット管理する（自動生成しない）
- フィクスチャは最小限のコード行数で各言語の全パターンをカバーする

---

### README.md（利用者向け手順書）

**役割**: リポジトリのトップレベルに置く日本語の手順書。Claude Codeなどの開発ツールに依存しない利用者向けドキュメント。

**記載すべき最低限の内容**:
1. 前提条件（Python 3.12以上、対応OS）
2. セットアップ手順（`python -m venv .venv` + `pip install -r requirements.txt`）
3. 基本的な使い方（`grep -rn "文言" /path/to/src > input/文言.grep` → `python analyze.py --source-dir ...`）
4. CLIオプション一覧（`--source-dir`・`--input-dir`・`--output-dir`）
5. 出力TSVの列定義
6. よくあるエラーと対処方法

---

### input/ および output/

**役割**:
- `input/`: ユーザーが `grep -rn "文言" /java > input/文言.grep` で配置する
- `output/`: ツールが `analyze.py` 実行時に自動作成・TSVを書き出す

**ファイル命名規則**:
- 入力: `[文言].grep`（拡張子は `.grep`）
- 出力: `[文言].tsv`（入力ファイル名と対応）

**例**:
```
input/
├── .gitkeep
├── ERROR_CODE.grep    # "ERROR_CODE" を grep した結果
└── STATUS_OK.grep     # "STATUS_OK" を grep した結果

output/
├── .gitkeep
├── ERROR_CODE.tsv     # ERROR_CODE の分析結果
└── STATUS_OK.tsv      # STATUS_OK の分析結果
```

---

### tests/（統合テスト用フィクスチャ）

**役割**: `TestIntegration` クラスが使用するサンプルファイル群

**構造**:
```
tests/fixtures/
├── input/
│   └── SAMPLE.grep          # サンプルgrep結果ファイル
├── java/
│   ├── Constants.java        # 直接参照・定数定義のサンプルJavaソース
│   ├── Entity.java           # フィールド・getterのサンプルJavaソース
│   └── Service.java          # 間接参照・getter呼び出しのサンプルJavaソース
└── expected/
    └── SAMPLE.tsv            # 期待出力TSV（手動作成・コミット管理）
```

**運用ルール**:
- `expected/*.tsv` は手動作成してコミット管理する（自動生成しない）
- サンプルJavaソースは最小限のコード行数で全参照パターンをカバーする

---

### docs/（ドキュメントディレクトリ）

**配置ドキュメント**:
- `product-requirements.md`: プロダクト要求定義書（PRD）
- `functional-design.md`: 機能設計書
- `architecture.md`: アーキテクチャ設計書（本ドキュメントの姉妹ドキュメント）
- `repository-structure.md`: リポジトリ構造定義書（本ドキュメント）
- `development-guidelines.md`: 開発ガイドライン
- `tool-overview.md`: ツール概要説明書（管理者・業務担当者向け）
- `glossary.md`: 用語集

## ファイル配置規則

### ソースファイル

| ファイル種別 | 配置先 | 命名規則 | 例 |
|------------|--------|---------|-----|
| 共通インフラ | プロジェクトルート | `analyze_common.py` | - |
| 言語別アナライザー | プロジェクトルート | `analyze_[言語].py` | `analyze_c.py`, `analyze_kotlin.py`, `analyze_plsql.py`, `analyze_proc.py` |
| Javaアナライザー | プロジェクトルート | `analyze.py` | - |
| テスト | `tests/` | `test_[対象].py` | `tests/test_analyze.py`, `tests/test_analyze_proc.py` |

### テストファイル

| テスト種別 | 配置先 | 命名規則 | 例 |
|-----------|--------|---------|-----|
| Java・Pro*Cユニット/統合テスト | `tests/` | `test_[対象モジュール].py` | `tests/test_analyze.py`, `tests/test_analyze_proc.py` |
| C/SQL/Shell/Kotlin/PL/SQL/TS・JS/Python/Perl/C#・VB.NET/Groovyアナライザーテスト | `tests/` | `test_[言語]_analyzer.py` | `test_c_analyzer.py`, `test_kotlin_analyzer.py`, `test_plsql_analyzer.py`, `test_ts_analyzer.py`, `test_python_analyzer.py`, `test_perl_analyzer.py`, `test_dotnet_analyzer.py`, `test_groovy_analyzer.py` |
| 全言語ディスパッチャーテスト | `tests/` | `test_all_analyzer.py` | - |
| 共通インフラテスト | `tests/` | `test_common.py` | - |
| フィクスチャ（入力・期待値） | `tests/[言語]/` | 言語別サブディレクトリ | `tests/c/`, `tests/proc/` |

### 設定ファイル

| ファイル種別 | 配置先 | 命名規則 |
|------------|--------|---------|
| 本番依存ライブラリ | プロジェクトルート | `requirements.txt` |
| 開発用依存ライブラリ | プロジェクトルート | `requirements-dev.txt` |
| Python仮想環境 | プロジェクトルート | `.venv/`（gitignore対象） |

## 命名規則

### ファイル名

- **Pythonスクリプト**: `snake_case.py`
  - 例: `analyze.py`, `tests/test_analyze.py`
- **ドキュメント（Markdown）**: `kebab-case.md`
  - 例: `product-requirements.md`, `functional-design.md`
- **ステアリングディレクトリ**: `[YYYYMMDD]-[task-name]` 形式（`kebab-case`）
  - 例: `20250115-implement-f01-grep-parser`

### Pythonコード内

- **関数・変数**: `snake_case`
  - 例: `parse_grep_line`, `ast_cache`, `source_dir`
- **クラス**: `PascalCase`
  - 例: `GrepRecord`, `ProcessStats`, `UsageType`
- **定数**: `UPPER_SNAKE_CASE`
  - 例: `USAGE_PATTERNS`, `DEFAULT_ENCODING`
- **プライベート変数**: `_snake_case`（モジュールレベルキャッシュ等）
  - 例: `_ast_cache`

## 依存関係のルール

```
tests/test_analyze.py / tests/test_analyze_proc.py / tests/test_*.py
    ↓ (import)
analyze.py / analyze_c.py / analyze_kotlin.py / analyze_plsql.py /
analyze_proc.py / analyze_sh.py / analyze_sql.py /
analyze_ts.py / analyze_python.py / analyze_perl.py /
analyze_dotnet.py / analyze_groovy.py
    ↓ (import)
analyze_common.py   ← 共通インフラ（全言語から依存可）
    ↓ (import)
re, csv, argparse, pathlib, sys, dataclasses, enum, heapq, tempfile  # 標準ライブラリ
chardet  # オプション（未インストール時は cp932 フォールバック）

analyze.py
    ↓ (import)
javalang  # 必須外部依存（Javaアナライザーのみ）

analyze_proc.py
    ↓ (import)
analyze_c  # classify_usage_c のみ（.c/.h ファイルのディスパッチ用）
```

**禁止される依存**:
- `analyze_common.py` に必須の外部ライブラリを追加しない（javalangも不可）。`chardet` はオプション扱いのみ許容
- `analyze.py` 以外のアナライザーに `javalang` を追加しない
- テストファイルに `unittest` / `pytest` 以外の外部ライブラリを追加しない
- `analyze_c.py` から `analyze_proc.py` への循環参照を作らない

## スケーリング戦略

### 機能の追加

新しい機能を追加する際の配置方針:

1. **新言語対応**: `analyze_[言語].py` を新規作成し `analyze_common` をインポートする
2. **共通ロジックの追加**: `analyze_common.py` に追加（全言語で共有されるもののみ）
3. **Java分析の機能拡張**: `analyze.py` に追加（javalangを使うものはここのみ）

### ファイルサイズの管理

**分割の目安**:
- 各アナライザーが500行を超えた場合: 言語固有サブモジュールへの分離を検討
- `analyze_common.py` が肥大化した場合: `analyze_common_io.py` (I/O) と `analyze_common_models.py` (データモデル) への分割を検討

## 特殊ディレクトリ

### .steering/（ステアリングファイル）

**役割**: 特定の開発作業における「今回何をするか」を定義

**構造**:
```
.steering/
└── [YYYYMMDD]-[task-name]/
    ├── requirements.md      # 今回の作業の要求内容
    ├── design.md            # 変更内容の設計
    └── tasklist.md          # タスクリスト
```

**命名規則**: `20250115-implement-f01-grep-parser` 形式

### .claude/（Claude Code設定）

**役割**: Claude Code設定とカスタマイズ

**主要なサブディレクトリ**（詳細はClaude Code公式ドキュメント参照）:
```
.claude/
├── commands/                # スラッシュコマンド定義
├── skills/                  # タスクモード別スキル定義
└── settings.json            # Claude Code設定ファイル
```

### CLAUDE.md（AIアシスタント設定）

**役割**: Claude Codeへの動作指示とプロジェクトメモリ。技術スタック・開発プロセス・ディレクトリ構造の概要を定義する。新規参加者がプロジェクト全体像を把握するための出発点でもある。

### .flake8（コードスタイル設定）

**役割**: flake8の設定ファイル。`max-line-length = 120` を定義し、`.venv/`・`dist/`・`.steering/` を解析対象から除外する。

## 除外設定

### .gitignore

プロジェクトで除外すべきファイル:
- `.venv/`（仮想環境）
- `__pycache__/`
- `*.pyc` / `*.pyo`
- `dist/`（パッケージング成果物）
- `*.egg-info/`
- `.env`
- `*.log`
- `.DS_Store`
- `output/*.tsv`（生成物。必要に応じてコミット対象に変更）

### コード品質ツール（flake8等）

ツールで除外すべきディレクトリ:
- `.venv/`
- `__pycache__/`
- `.steering/`
- `dist/`
