# grep-helper

grepの結果ファイルを入力として受け取り、各ヒット行の使用タイプ分類と間接参照の追跡を行い、ExcelやLibreOffice Calcで開けるTSV形式で出力するツール。

---

## 概要

`grep -rn "777" ./src > input/TARGET.grep` のようにして作成したgrep結果ファイルを読み込み、各行が「定数定義なのか」「条件判定なのか」を自動分類する。さらに対応言語では、その定数・変数を間接的に参照している箇所、getter / setter 経由の参照箇所も追跡して一覧に含める。

詳細な説明は [`docs/tool-overview.md`](docs/tool-overview.md) を参照。

---

## 対応言語

| 言語 | スクリプト | 間接追跡 | getter/setter追跡 |
|------|-----------|:--------:|:-----------------:|
| Java | `analyze.py` | ✅ 定数・フィールド・ローカル変数 | ✅ |
| C | `analyze_c.py` | ✅ #define・変数 | — |
| Pro\*C | `analyze_proc.py` | ✅ #define・変数 | — |
| Oracle SQL | `analyze_sql.py` | — | — |
| Shell | `analyze_sh.py` | — | — |
| Kotlin | `analyze_kotlin.py` | ✅ const val 定数 | — |
| PL/SQL | `analyze_plsql.py` | — | — |
| TypeScript / JavaScript | `analyze_ts.py` | — | — |
| Python | `analyze_python.py` | — | — |
| Perl | `analyze_perl.py` | — | — |
| C# / VB.NET | `analyze_dotnet.py` | ✅ const / static readonly | — |
| Groovy | `analyze_groovy.py` | ✅ static final・フィールド | ✅ |
| 全言語（振り分け） | `analyze_all.py` | ✅ 各言語に準ずる | ✅ 各言語に準ずる |

---

## インストール

Python 3.7 以上が必要（オフライン install で同梱 wheel をそのまま使う場合は Python 3.12 / Linux x86_64。それ以外の環境では `pyahocorasick` のフォールバック動作になる、もしくは対応 wheel を追加する）。

### オンライン環境

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # javalang / chardet / pyahocorasick
```

テストも実行する場合は追加でインストールする。

```bash
pip install -r requirements-dev.txt   # pytest
```

### オフライン環境（wheelhouse使用）

`wheelhouse/` ディレクトリに `requirements.txt` と `requirements-dev.txt` の全依存（推移依存含む）の wheel が同梱されている。

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --no-index --find-links=./wheelhouse -r requirements.txt -r requirements-dev.txt
```

> **Python バージョンについて**  
> `pyahocorasick` のみ C 拡張のためプラットフォーム特化 wheel（`cp312` / Linux x86_64）を同梱している。それ以外は `py3-none-any` で Python マイナーバージョン非依存。`pyahocorasick` がインストールできない場合でも、コード側の防御的フォールバックにより同梱の純Python実装（`grep_helper/_aho_corasick.py`）に切り替わって動作する（性能のみ低下）。別プラットフォーム / 別 Python バージョンで使う場合は対応 wheel を追加するか、フォールバックに任せて差し支えない。

---

## 使い方

### 1. grep結果ファイルを用意する

```bash
mkdir -p input
grep -rn "777" ./src > input/TARGET.grep
```

ファイル名（拡張子なし）が出力TSVの「文言」列に使われる。複数ファイルを `input/` に置くとまとめて処理する。

### 2. アナライザーを実行する

```bash
python analyze.py \
  --source-dir ./src \
  --input-dir  ./input \
  --output-dir ./output
```

各アナライザーの引数は共通。

| 引数 | 必須 | 説明 |
|------|:---:|------|
| `--source-dir` | ✅ | ソースコードのルートディレクトリ |
| `--input-dir` | — | grep結果ファイルのディレクトリ（デフォルト: `input`） |
| `--output-dir` | — | TSV出力先ディレクトリ（デフォルト: `output`） |
| `--encoding` | — | 文字コード強制指定（例: `utf-8`、`cp932`）。省略時は自動検出 |
| `--workers` | — | バッチ追跡フェーズの並列ワーカー数（デフォルト: 1）。CPU 数を指定すると 4〜8 倍速くなる |

> **大規模ソースディレクトリの場合**  
> `--source-dir` 配下のファイル数が多い場合（数万ファイル以上）、間接追跡フェーズの進捗が標準エラー出力（stderr）に表示される。
> ```
>   処理中: TARGET.grep ...
>   [Java追跡] 事前フィルタ完了: 82000 → 134 ファイルに絞り込み
>   [Java定数追跡] 100/134 ファイル処理済み (75%)
>   [Java定数追跡] 完了: 134 ファイルスキャン / 参照 128 件発見
> ```
> TSV が出力されていなくても処理は継続中。stdout のみ取得する場合は `2>/dev/null` で抑制できる。
>
> 60GB 規模のソースディレクトリや GB 級の grep ファイルでも OOM しない設計になっている。  
> grep ファイルはストリーミング読み込みで全行をメモリに展開せず、ソースファイルはサイズベース LRU キャッシュ（既定 256MB）で重複 I/O を排除する。  
> CPU が多い環境では `--workers` で並列スキャンすると大幅に高速化できる。
> ```bash
> # 4 並列でスキャン（CPU コア数に合わせて調整）
> python analyze_all.py --source-dir /path/to/src --workers 4
> ```

### 3. 出力を確認する

`output/TARGET.tsv` が生成される。Excelで開いてフィルタ・ソートして使用する。

---

## 出力フォーマット

UTF-8 BOM付きTSV（Excelで文字化けなく開ける）。

| 列名 | 説明 |
|------|------|
| 文言 | 調査した文字列 |
| 参照種別 | `直接` / `間接` / `間接（getter経由）` / `間接（setter経由）` |
| 使用タイプ | 定数定義・条件判定・変数代入 など（言語ごとに異なる） |
| ファイルパス | 該当行のソースファイルパス |
| 行番号 | ファイル内の行番号 |
| コード行 | 該当行のコード内容 |
| 参照元変数名 | 間接参照の場合：経由した変数名・メソッド名 |
| 参照元ファイル | 間接参照の場合：変数が定義されているファイル |
| 参照元行番号 | 間接参照の場合：変数が定義されている行番号 |

---

## 言語別の実行例

```bash
# 全言語まとめて処理（推奨）
python analyze_all.py --source-dir ./src --input-dir input --output-dir output

# Java
python analyze.py --source-dir ./src/main/java --input-dir input --output-dir output

# Kotlin
python analyze_kotlin.py --source-dir ./src --input-dir input --output-dir output

# C# / VB.NET
python analyze_dotnet.py --source-dir ./src --input-dir input --output-dir output

# Groovy
python analyze_groovy.py --source-dir ./src --input-dir input --output-dir output

# TypeScript / JavaScript
python analyze_ts.py --source-dir ./src --input-dir input --output-dir output

# Python
python analyze_python.py --source-dir ./src --input-dir input --output-dir output

# Perl
python analyze_perl.py --source-dir ./src --input-dir input --output-dir output

# PL/SQL
python analyze_plsql.py --source-dir ./src --input-dir input --output-dir output

# C / Pro*C
python analyze_c.py   --source-dir ./src --input-dir input --output-dir output
python analyze_proc.py --source-dir ./src --input-dir input --output-dir output

# Shell
python analyze_sh.py --source-dir ./src --input-dir input --output-dir output

# Oracle SQL
python analyze_sql.py --source-dir ./src --input-dir input --output-dir output
```

---

## テスト

```bash
python -m pytest tests/ -v
```

---

## リポジトリ構成

このツールは `grep_helper/` パッケージとして実装されています。ルート直下の `analyze*.py` は CLI エントリポイントとしての shim で、各言語のロジックは `grep_helper/languages/<lang>.py` にあります。

- `grep_helper/` — 共通インフラ (`encoding.py` / `grep_input.py` / `tsv_output.py` / `source_files.py` / `file_cache.py` / `scanner.py` / `_aho_corasick.py` / `cli.py` / `pipeline.py` / `dispatcher.py` / `model.py`)
- `grep_helper/languages/<lang>.py` — 各言語の `EXTENSIONS` / `classify_usage` / 任意の `batch_track_indirect`
- `analyze<_lang>.py` — CLI shim（5〜6 行）— 互換性維持のため残しています
- `tests/` — pytest 規約のモジュールキャッシュクリア前提のため、`pytest-xdist` 並列実行は使わないでください
- `scripts/check_cache_identity_phase*.py` — リファクタで導入したキャッシュ dict の object identity チェッカ

詳細は [`docs/repository-structure.md`](docs/repository-structure.md) を参照。

---

## ドキュメント

| ファイル | 内容 |
|---------|------|
| [`docs/tool-overview.md`](docs/tool-overview.md) | 管理者向け概要説明（処理フロー・呼び出し順序・出力形式） |
| [`docs/product-requirements.md`](docs/product-requirements.md) | 要件定義 |
| [`docs/architecture.md`](docs/architecture.md) | アーキテクチャ設計 |
| [`docs/functional-design.md`](docs/functional-design.md) | 機能設計書 |
| [`docs/glossary.md`](docs/glossary.md) | 用語集・使用タイプ定義 |
| [`docs/development-guidelines.md`](docs/development-guidelines.md) | 開発ガイドライン |
| [`docs/repository-structure.md`](docs/repository-structure.md) | リポジトリ構成 |
