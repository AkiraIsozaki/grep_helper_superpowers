# B-1: 直接参照のみ言語への間接追跡追加 設計書

**日付**: 2026-05-04
**対象ファイル**:

- `grep_helper/languages/python.py`（既存改修）
- `grep_helper/languages/ts.py`（既存改修）
- `grep_helper/languages/perl.py`（既存改修）
- `grep_helper/languages/plsql.py`（既存改修）
- `scripts/measure_kpi.py`（`LANG_SPECS` の更新）
- `tests/golden/{python,ts,perl,plsql}/`（間接サンプル追加）
- `tests/test_python_handler.py`（新規）
- `tests/test_ts_handler.py`（新規）
- `tests/test_perl_handler.py`（新規）
- `tests/test_plsql_handler.py`（新規）

---

## 背景・動機

F（KPI 計測基盤）の整備により、各言語の網羅率・分類精度が定量的に測れるようになった。現状、`grep_helper/languages/` 配下のうち以下4言語は **直接参照のみ** の実装に留まっている:

- `python.py`（25 行）
- `ts.py`（26 行）
- `perl.py`（26 行）
- `plsql.py`（26 行）

これらは `classify_usage` のみを実装し、`batch_track_indirect` を持たないため、`run_full_pipeline` 中の間接追跡フェーズでスキップされる。実プロジェクトでは「定数を別ファイルからインポートして使用する」が主流であるため、直接参照のみでは網羅率が大きく落ちる。

本タスク（B-1）は KPI ゴールデンセット F-spec のロードマップ §後続タスク順序 で **「並行 / 後続: B 直接参照のみ言語への間接追跡追加 ← KPI で精度監視」** と位置付けられた作業の最初の塊（B-1）である。実装パターンは既存の `kotlin.py` / `dotnet.py` / `groovy.py` のクロスファイル追跡をテンプレートとして倣う。

---

## ロードマップ上の位置付け

本 spec は B（既存言語の深堀り）4 サブタスクのうち **B-1（直接参照のみ4言語への間接追跡追加）** に閉じる。後続のサブタスクは別 spec で扱う:

```
[今回] B-1: Python / TypeScript / Perl / PL/SQL に間接追跡追加（クロスファイル）
   ↓
[次] B-4: Java 慣用句追加対応（Lombok @Getter / record / Builder）
   ↓
[後続] B-2: Java 以外の AST 化（Kotlin / C# / Groovy）
   ↓
[後続] B-3: データフロー一歩手前の追跡（定数→定数連鎖、メソッド戻り値経由）
```

各サブタスクは独立した spec / 実装計画で扱う。本 spec は B-1 に閉じる。

### B-1 を最初に選んだ理由

- 既存の `kotlin.py` / `dotnet.py` / `groovy.py` の実装パターンの **横展開** であり、新規の設計判断が比較的少ない
- F の効果検証として理想的（4言語の KPI が「直接のみ」から「直接+間接」に拡張される）
- 4言語ぶんの実装で改造範囲が分散するため、各言語ごとに「実装→KPI 確認」のサイクルを回せる（増分安全性）

---

## 要件

1. **4言語に間接追跡を追加**: 各 handler に既存の `kotlin.py` 同様の関数構造（`extract_*_name`, `track_*`, `_scan_files_for_*`, `_batch_track_*`, `batch_track_indirect`）を実装。Python / TS / PL/SQL は 5 関数、Perl は `extract_*` が 2 系統あるため 6 関数
2. **クロスファイル追跡**: 同一ファイル内のみではなく、`src_dir` 配下の対象拡張子ファイル全体をスキャンする
3. **並列対応**: `ProcessPoolExecutor` で `workers >= 2` 時に並列化（既存パターン踏襲）
4. **既存パターンの再利用**: `grep_filter_files`(mmap), `build_batch_scanner`, `cached_file_lines`, `detect_encoding`, `resolve_file_cached` を全活用
5. **KPI ゴールデンセット拡張**: 4言語に間接サンプルを各 3-5 件追加。`LANG_SPECS` の `reference_kinds_required` に `"間接"` を追加
6. **`classify_usage` は不変**: F の既存テスト・サンプル・KPI 結果を壊さない。起点フィルタは `batch_track_indirect` 内で実装
7. **既存 8 言語の KPI を維持**: F で達成した Java / C / proc / SQL / Shell / Kotlin / dotnet / groovy の網羅率 100% / 分類精度 90% 以上を本タスクで落とさない

---

## アーキテクチャ

### 全体データフロー

```
[既存: pipeline.run_full_pipeline]
        ↓ direct_records 生成後
[新規: handler.batch_track_indirect(direct_records, src_dir, encoding, workers)]
        ↓ ① 起点フィルタ（言語別ロジックで「定義」レコードを抽出）
        ↓ ② tasks: dict[name, list[GrepRecord]] に集約
[新規: handler._batch_track_<lang>_<kind>(tasks, src_dir, ...)]
        ↓ ③ grep_filter_files で対象ファイル絞り込み（mmap）
        ↓ ④ workers>=2 → ProcessPoolExecutor / else 直列
[新規: handler._scan_files_for_<lang>_<kind>(files, src_dir, encoding, names, tasks_ext)]
        ↓ ⑤ build_batch_scanner で多名前検索 → 行ごとに RefType.INDIRECT レコード生成
indirect_records → write_tsv に渡る（パイプライン下流は不変）
```

`grep_helper/pipeline.py` の `run_full_pipeline` は既に `getattr(handler, "batch_track_indirect", None)` で間接追跡関数を動的に呼ぶ仕組みになっている（L96-101）。よって **パイプライン本体の変更は不要**、4言語の handler に `batch_track_indirect` を追加するだけで自動的にパイプライン経由で動く。

### 共通実装パターン（kotlin.py 雛形）

各言語の handler は以下の関数構造で揃える（Perl のみ `extract_*` が 2 系統あり 6 関数になる）:

| 関数 | 役割 | kotlin.py 該当 |
|---|---|---|
| `extract_<kind>_name(code: str) -> str \| None` | 定義行から名前抽出（言語別正規表現） | `extract_const_name` (L38-41) |
| `track_<kind>(name, src_dir, record, stats, encoding) -> list[GrepRecord]` | 単体追跡（直列実装、テスト用） | `track_const` (L44-81) |
| `_scan_files_for_<lang>_<kind>(files, src_dir, encoding, names, tasks_ext) -> list[GrepRecord]` | ProcessPool worker | `_scan_files_for_kotlin_const` (L84-118) |
| `_batch_track_<lang>_<kind>(tasks, src_dir, stats, encoding, *, workers) -> list[GrepRecord]` | バッチオーケストレータ（並列/直列分岐） | `_batch_track_kotlin_const` (L121-196) |
| `batch_track_indirect(direct_records, src_dir, encoding, *, workers) -> list[GrepRecord]` | エントリポイント。起点フィルタ＋集約 | (L199-226) |

`<kind>` は言語ごとに変える: Python = `module_const`, TS = `const`, Perl = `constant`, PL/SQL = `constant`。

---

## 言語別の詳細仕様

各言語で **(a) 起点フィルタ条件**、**(b) 定義行→名前抽出の正規表現**、**(c) 使用箇所スキャンの検索パターン** を定める。

### Python

#### (a) 起点フィルタ
- `record.usage_type == "変数代入"` **かつ**
- (`ALL_CAPS` 命名 **OR** インデントゼロ)

#### (b) 定義行から名前抽出（型注釈対応）

```python
_PYTHON_CONST_PAT = re.compile(r'^(\s*)(\w+)\s*(?::\s*[^=]+?)?\s*=(?!=)')

def extract_module_const_name(code: str) -> str | None:
    """モジュール定数名を抽出する。型注釈付き(MAX: int = 5)も対応。"""
    m = _PYTHON_CONST_PAT.match(code)
    if not m:
        return None
    indent, name = m.group(1), m.group(2)
    if name.isupper() or indent == "":
        return name
    return None
```

#### (c) 使用箇所スキャンパターン
```python
re.compile(r'\b' + re.escape(name) + r'\b')
```
※ Python 識別子の単語境界は `\b` で十分。`from foo import NAME` の `NAME` も拾うが、これは「使用箇所」として妥当。

#### エッジケース・スコープ外
- `__all__ = [...]` 等の dunder 名: 起点扱いになるが許容
- `from foo import NAME as ALIAS` の別名追跡: スコープ外
- 関数内 `MY_CONST = ...`: ALL_CAPS なら起点扱い（関数スコープ非考慮）

---

### TypeScript / JS

#### (a) 起点フィルタ
- `record.usage_type == "const定数定義"` のみ

#### (b) 定義行から名前抽出
```python
_TS_CONST_PAT = re.compile(r'\b(?:export\s+)?const\s+(\w+)\s*(?::\s*[^=]+?)?\s*=(?!=)')

def extract_const_name(code: str) -> str | None:
    m = _TS_CONST_PAT.search(code)
    return m.group(1) if m else None
```
※ `const X: number = 5` のような型注釈付きにも対応。

#### (c) 使用箇所スキャンパターン
```python
re.compile(r'\b' + re.escape(name) + r'\b')
```

#### エッジケース・スコープ外
- `import { foo as bar }` のリネーム: スコープ外
- 分割代入 `const { a, b } = obj`: 起点に含めない（最初の名前が `{` 直後の `a` でも、`{` 検出時に除外）
- `const X = ..., Y = ...` の同時宣言: 最初の名前のみ拾う
- TSX/JSX の JSX 識別子: 通常の参照として拾う（妥当）

---

### Perl

Perl は他3言語より複雑なので **2層構造** で扱う。

#### Tier 1（必須）: `use constant NAME` と `our $NAME`

##### (a) 起点フィルタ
- `record.usage_type == "use constant定義"` で **単一形式** `use constant NAME => "value"`
- `record.usage_type == "変数代入"` かつ **`our` で始まる** `our $NAME = ...`

##### (b) 定義行から名前抽出
```python
_PERL_USE_CONSTANT_PAT = re.compile(r'\buse\s+constant\s+(\w+)\s*=>')
_PERL_OUR_SCALAR_PAT = re.compile(r'\bour\s+\$(\w+)\s*=')

def extract_perl_constant_name(code: str) -> str | None:
    m = _PERL_USE_CONSTANT_PAT.search(code)
    return m.group(1) if m else None

def extract_perl_our_name(code: str) -> str | None:
    m = _PERL_OUR_SCALAR_PAT.search(code)
    return m.group(1) if m else None
```

##### (c) 使用箇所スキャンパターン
- 定数: `\bNAME\b`（Perl の constant は関数として呼ばれる）
- `our $NAME`: `\$NAME\b`（シジル付き検索）

#### Tier 2（任意）: `use constant { ... }` ハッシュ形式

```python
_PERL_USE_CONSTANT_HASH_PAT = re.compile(r'\buse\s+constant\s*\{([^}]*)\}', re.DOTALL)
_PERL_HASH_KEY_PAT = re.compile(r'(\w+)\s*=>')
```

ハッシュ内の全キーを起点として登録する。複数行ハッシュは grep 行が1行のみ拾うためスコープ外。

#### スコープ外（明示）
- `our @ARRAY` / `our %HASH` のシジル系
- `my` レキシカル変数（追跡意味薄）
- `use Module qw(FOO)` のエクスポート宣言から取得（呼び出し側の `FOO` は通常 grep が拾う）
- パッケージ修飾参照 `$Module::NAME` の `Module::` 部分は無視（`\$NAME\b` で末尾だけ拾う）

#### handler 内での Perl 2 系統の扱い

`extract_*` が2系統あるため、`batch_track_indirect` 内で2種類のタスク辞書を作って `_batch_track_perl_constant` をサブモードで2回呼ぶ、または1つの dict に統合（名前にプレフィックス `$NAME` のように区別）して1回で処理する。実装段階で確定（writing-plans フェーズ）。

---

### PL/SQL

#### (a) 起点フィルタ
- `record.usage_type == "定数/変数宣言"` **かつ** `code` に `\bCONSTANT\b`(case-insensitive) を含む

#### (b) 定義行から名前抽出
```python
_PLSQL_CONSTANT_PAT = re.compile(
    r'^\s*(\w+)\s+CONSTANT\b',
    re.IGNORECASE,
)

def extract_plsql_constant_name(code: str) -> str | None:
    m = _PLSQL_CONSTANT_PAT.match(code)
    return m.group(1) if m else None
```

#### (c) 使用箇所スキャンパターン
```python
re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
```
※ PL/SQL は case-insensitive。

#### エッジケース・スコープ外
- 普通の変数宣言 `v_count NUMBER := 0;`: 起点に含めない（CONSTANT キーワード必須）
- パッケージ修飾参照 `other_pkg.SAME_NAME` の名前空間衝突: 検出されるが許容（false positive 可）
- パッケージ仕様部 vs 本体での宣言重複: 両方を起点として登録

---

### 関数命名統一

| 言語 | `<kind>` | 関数名例 |
|---|---|---|
| Python | `module_const` | `extract_module_const_name`, `track_module_const`, `_scan_files_for_python_const`, `_batch_track_python_const` |
| TS/JS | `const` | `extract_const_name`, `track_const`, `_scan_files_for_ts_const`, `_batch_track_ts_const` |
| Perl | `constant` | `extract_perl_constant_name`, `extract_perl_our_name`, `track_perl_constant`, `_scan_files_for_perl_constant`, `_batch_track_perl_constant` |
| PL/SQL | `constant` | `extract_plsql_constant_name`, `track_plsql_constant`, `_scan_files_for_plsql_constant`, `_batch_track_plsql_constant` |

---

## KPI ゴールデンセット拡張

各言語の `tests/golden/<lang>/` に間接サンプルを **3-5件** 追加する。

### 各言語共通の追加要素

| 追加要素 | 役割 | 件数目安 |
|---|---|---|
| 定義側ファイル | キーワード（例: `777`）を含む定数定義 | 1件（既存ファイルへの追記でも可）|
| 使用側ファイル A | 別ファイルから定義を `import` / `use` / 修飾参照 | 1ファイル新規 |
| 使用側ファイル B | 異なるディレクトリにもう1つ使用側 | 1ファイル新規（クロスファイル網羅性確認）|
| `inputs/<keyword>.grep` | 既存の grep 行に定義側の行のみ追加（使用側は grep 出力しない = 間接で発見されるのが目的）| 1行追加 |
| `expected/<keyword>.tsv` | 既存の直接行 + 新たに間接行 3-5件を追加 | 3-5行追加 |

### 言語別の例（Python）

```
tests/golden/python/
  src/
    constants.py          # 777定数定義
    service.py            # from constants import ... (使用側 A)
    handler/
      worker.py           # from constants import ... (使用側 B)
  inputs/
    777.grep              # constants.py の定義行のみ追加
  expected/
    777.tsv               # 直接1件 + 間接2件
```

他3言語も同様の構造（各言語の定数構文に置き換え）。

### `LANG_SPECS` の更新

`scripts/measure_kpi.py` の 4 言語ぶんの spec で `reference_kinds_required` を更新:

```python
PYTHON_SPEC = {
    "usage_types": [...],
    "min_per_type": 1,
    "reference_kinds_required": ["直接", "間接"],   # 旧: ["直接"]
}
```

TS / Perl / PL/SQL も同様。`assert_coverage_distribution()` がこれらの分布をチェックして、間接サンプルが揃っているか自動検証する。

---

## テスト戦略

`feedback_test_style` 準拠（古典学派・ブラックボックス起点・WHAT を検証・テストメソッド名は日本語）、`feedback_tdd_stance` 準拠（TDD 推奨）。

### 各言語の単体テスト（4ファイル新規）

`tests/test_python_handler.py` / `test_ts_handler.py` / `test_perl_handler.py` / `test_plsql_handler.py`

| テスト対象 | 方針 | テスト名例 |
|---|---|---|
| `extract_*_name(code)` | ブラックボックス: 各種定義行入力 → 抽出名 | `test_全大文字の定数定義から名前を抽出する` |
| `extract_*_name(code)` の境界 | 起点除外条件（小文字+インデント等）| `test_インデント有りの小文字代入は名前を返さない` |
| `track_*` 単体 | 一時 src_dir に2ファイル作って、片方に定義/もう片方に参照 | `test_別ファイルの参照が間接レコードとして記録される` |
| `batch_track_indirect` | direct_records → 間接 records の集約。usage_type フィルタリング | `test_変数代入以外のレコードは起点にならない` |
| `batch_track_indirect` の workers=2 | ProcessPool 経由で同じ結果 | `test_並列実行でも直列と同じレコード集合を返す` |
| 定義行の自己参照除外 | 定義行自体が間接レコードにならないこと（`kotlin.py` L65-68 と同様） | `test_定義行自身は間接レコードに含まれない` |

#### Perl のみ追加

- `test_use_constantのハッシュ形式から複数の名前を抽出する`（Tier 2 検証）

### E2E テスト

E2E は既存の `test_measure_kpi.py` の各言語テストで自動カバーされる（パイプラインに `batch_track_indirect` を追加するだけで `run_full_pipeline` 経由で呼ばれるため）。**E2E テストファイル新設は不要**。

期待TSV に間接行を追加し、`assert_coverage_distribution` が `"間接"` の存在を要求するようになるので、既存の E2E テストが間接追跡の存在検証を兼ねる。

---

## 実装の段階化（単一 plan 内のステップ構成）

writing-plans では1つの implementation plan 内で6ステップに段階化する。**各言語ごとに「実装→KPI 確認」のサイクル**を回すことで、増分安全性を確保する。

### Step 1: 共通準備

- `LANG_SPECS` を4言語ぶん更新（`reference_kinds_required` に `"間接"` 追加）
- `tests/golden/<lang>/` 各言語の `src/` `inputs/` `expected/` `README.md` を間接サンプル分だけ拡張
- この段階では handler 未実装なので KPI は WARN になる（=期待通りの「赤」状態を確認）

### Step 2: Python 実装 + 単体テスト + KPI 確認 ★検証ゲート

- `python.py` に 5 関数を追加（TDD で extract → track → batch_track_indirect の順）
- `tests/test_python_handler.py` 新設
- `python scripts/measure_kpi.py --lang python` で網羅率 100% 達成を手動確認

**この時点で1言語ぶんの完全動作を確認。** 設計に問題があればここで判明するので、他3言語に展開する前に修正できる。

### Step 3: TypeScript / JS 実装 + 単体テスト + KPI 確認

- `ts.py` に 5 関数を追加
- `tests/test_ts_handler.py` 新設
- `python scripts/measure_kpi.py --lang ts` で網羅率 100% を確認

### Step 4: Perl 実装 + 単体テスト + KPI 確認

- `perl.py` に 6 関数を追加（Tier 1 のみ → Tier 2 ハッシュ形式の順）
- `tests/test_perl_handler.py` 新設
- `python scripts/measure_kpi.py --lang perl` で網羅率 100% を確認

### Step 5: PL/SQL 実装 + 単体テスト + KPI 確認

- `plsql.py` に 5 関数を追加
- `tests/test_plsql_handler.py` 新設
- `python scripts/measure_kpi.py --lang plsql` で網羅率 100% を確認

### Step 6: 全体統合確認 + ドキュメント

- `python scripts/measure_kpi.py --lang all` で全12言語が引き続き動くこと確認
- `pytest` 全件 pass 確認
- `tests/golden/{python,ts,perl,plsql}/README.md` に間接サンプル説明を追記
- 本 spec の §成功条件 全項目を点検

---

## 実装の依存関係

| 種別 | パス | 内容 |
|---|---|---|
| 必須変更 | `grep_helper/languages/python.py` | 25 行 → 約 220 行（kotlin.py 同等規模）|
| 必須変更 | `grep_helper/languages/ts.py` | 26 行 → 約 220 行 |
| 必須変更 | `grep_helper/languages/perl.py` | 26 行 → 約 240 行（`use constant` のハッシュ形式があるため少し複雑）|
| 必須変更 | `grep_helper/languages/plsql.py` | 26 行 → 約 220 行 |
| 必須変更 | `scripts/measure_kpi.py` | `LANG_SPECS` の4言語の `reference_kinds_required` に `"間接"` 追加 |
| 新規追加 | `tests/golden/{python,ts,perl,plsql}/src/` 配下に追加サンプル | 各言語 2-3 ファイル追加 |
| 必須変更 | `tests/golden/{python,ts,perl,plsql}/inputs/*.grep` | 間接サンプル分の grep 行を追加 |
| 必須変更 | `tests/golden/{python,ts,perl,plsql}/expected/*.tsv` | 間接行 3-5 件分追加 |
| 新規追加 | `tests/test_python_handler.py` | Python handler の単体テスト |
| 新規追加 | `tests/test_ts_handler.py` | TS handler の単体テスト |
| 新規追加 | `tests/test_perl_handler.py` | Perl handler の単体テスト |
| 新規追加 | `tests/test_plsql_handler.py` | PL/SQL handler の単体テスト |
| 必須変更 | `tests/golden/{python,ts,perl,plsql}/README.md` | 間接サンプル説明を追記 |

`grep_helper/pipeline.py` は **無変更**（`run_full_pipeline` の `getattr(handler, "batch_track_indirect", None)` 経由で自動的に新ハンドラを呼ぶ）。

---

## スコープ外（明示）

- **B-2 (AST 化)**: Kotlin / C# / Groovy の AST 化は B-2 タスクで別 spec
- **B-3 (多段追跡)**: 定数→定数の連鎖、メソッド戻り値経由は B-3 タスクで別 spec
- **B-4 (Java 慣用句)**: Lombok / record / Builder は B-4 タスクで別 spec
- **getter/setter 経由の追跡**: 4言語ではアクセサが必須でないため追加しない
- **import 文のリネーム追跡**: TS の `import { foo as bar }`, Python の `from X import Y as Z`
- **Python の関数内ローカル定数**: 関数内 `MY_CONST` は ALL_CAPS なら拾うが、関数スコープを意識した追跡はしない
- **Perl の `my` レキシカル変数**: 追跡意味が薄いため対象外
- **PL/SQL のパッケージ修飾名前空間**: `pkg1.NAME` と `pkg2.NAME` の同名衝突は許容
- **Python `from foo import *` のワイルドカード追跡**: 対象外
- **Perl の複数行 `use constant { ... }`**: grep 行が1行のみ拾うため対象外
- **件数を Java と同水準まで厚くすること**: 各言語の間接サンプルは 3-5 件に留める（後続タスクで拡充）

---

## 成功条件

1. `grep_helper/languages/{python,ts,perl,plsql}.py` に `batch_track_indirect` が実装されている
2. `python scripts/measure_kpi.py --lang python` で網羅率 100%・分類精度 90% 以上を達成
3. 他3言語（ts / perl / plsql）でも同様に網羅率 100% を達成
4. `python scripts/measure_kpi.py --lang all` で全 12 言語が成功（exit code 0）
5. `tests/test_python_handler.py` 等 4 本が pytest で全件 pass する
6. `assert_coverage_distribution()` が4言語のゴールデンセットに対して `"間接"` 種別を含めて警告ゼロ
7. ProcessPool 並列化が動く（`workers=2` 以上で直列と同じレコード集合を返す）
8. F の既存 KPI（Java / C / proc / SQL / Shell / Kotlin / dotnet / groovy）が引き続き網羅率 100% / 分類精度 90% 以上を維持
