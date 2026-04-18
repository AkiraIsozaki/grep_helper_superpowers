# 拡張機能設計書

## 概要

grep_analyzer の以下5機能を追加する。

| # | 機能 | 変更ファイル |
|---|------|------------|
| F-07 | 文字コード自動検出 + `--encoding` CLIオプション | `analyze_common.py` + 全アナライザー |
| New-1 | Kotlin対応 `analyze_kotlin.py` | 新規 `analyze_kotlin.py` |
| New-2 | PL/SQL対応 `analyze_plsql.py` | 新規 `analyze_plsql.py` |
| Java-4 | Java第4段階: setter経由の逆伝播追跡 | `analyze.py`, `analyze_common.py` |
| Indirect-1 | C/Pro*C: `#define` マクロ展開の多段追跡 | `analyze_c.py`, `analyze_proc.py` |

全機能は既存の「共通インフラ（`analyze_common.py`）+ 言語別アナライザー」アーキテクチャに沿って実装する。

---

## F-07: 文字コード自動検出

### 設計

`analyze_common.py` に以下の関数を追加する。

```python
def detect_encoding(path: Path, override: str | None = None) -> str
```

**動作:**
- `override` が指定されていればそのまま返す
- なければファイル先頭 4KB を読んで `chardet.detect()` で判定
- 信頼度 < 0.6 または検出失敗時は `cp932` にフォールバック
- フォールバック時は `ProcessStats.encoding_errors` に記録（エンコード不確実ファイルとして通知）

**各アナライザーへの変更（`analyze.py`, `analyze_c.py`, `analyze_proc.py`, `analyze_sql.py`, `analyze_sh.py`, `analyze_kotlin.py`, `analyze_plsql.py`）:**
- `argparse` に `--encoding` オプションを追加（デフォルト `None`、任意）
- `_get_cached_lines()` 等のファイル読み込み箇所で `encoding="cp932"` を `detect_encoding(path, args.encoding)` に置換

**新規依存:** `chardet>=5.0.0`（`requirements.txt` に追記）

### CLIオプション

```bash
python analyze_c.py --source-dir /path/to/src --encoding utf-8
python analyze.py --source-dir /path/to/src  # encodingなし→自動検出
```

---

## New-1: Kotlin対応

### 設計

新規ファイル `analyze_kotlin.py`（`analyze_sh.py` と同じ構造）。

**対象拡張子:** `.kt`, `.kts`

### 分類パターン（7種）

| 使用タイプ | 判定パターン |
|---|---|
| const定数定義 | `const\s+val\s+\w+\s*=` |
| 変数代入 | `(?:val\|var)\s+\w+\s*=` |
| 条件判定 | `\bif\s*\(` / `\bwhen\s*\(` |
| return文 | `\breturn\b` |
| アノテーション | `@\w+` |
| 関数引数 | `\w+\s*\(` |
| その他 | 上記以外 |

### 間接追跡

`const定数定義` に分類された行の定数名でプロジェクト全体（`.kt`/`.kts`）を追跡。C/Pro*Cの `track_define` と同等のアプローチ。参照種別 = `間接`。

### CLIエントリーポイント

```bash
python analyze_kotlin.py --source-dir /path/to/kotlin/src
```

---

## New-2: PL/SQL対応

### 設計

新規ファイル `analyze_plsql.py`。

**対象拡張子:** `.pls`, `.pck`, `.prc`, `.pkb`, `.pks`, `.fnc`, `.trg`

### 分類パターン（7種）

| 使用タイプ | 判定パターン |
|---|---|
| 定数/変数宣言 | `\bCONSTANT\b` / `:=` |
| EXCEPTION処理 | `\bWHEN\b.*\bTHEN\b` / `\bRAISE\b` |
| 条件判定 | `\bIF\b.*\bTHEN\b` / `\bCASE\s+WHEN\b` |
| カーソル定義 | `\bCURSOR\b.*\bIS\b` |
| INSERT/UPDATE値 | `\bINSERT\b` / `\bUPDATE\b.*\bSET\b` |
| WHERE条件 | `\bWHERE\b` |
| その他 | 上記以外 |

### 間接追跡

なし（直接参照のみ）。PL/SQLは変数スコープがブロック内に限定されるため、間接追跡の実用的価値が低い。

### 文字コード

F-07の `detect_encoding()` を使用。

### CLIエントリーポイント

```bash
python analyze_plsql.py --source-dir /path/to/plsql/src
```

---

## Java-4: setter経由の逆伝播追跡

### 設計

`analyze.py` に第4段階を追加。既存の第3段階（getter）完了後に実行。

### フロー

1. 第2段階の「変数代入（フィールド）」結果からフィールド名を抽出
2. setter候補を特定:
   - 命名規則: `fieldName` → `setFieldName()`
   - 非標準: `this.fieldName = 引数` しているメソッドも対象
3. プロジェクト全体（`.java`）でsetter呼び出し箇所を検索
4. 各呼び出し箇所をAST解析して7種の使用タイプに分類
5. `参照種別 = "間接（setter経由）"` として出力

### RefType 追加

`analyze_common.py` の `RefType` enumに追加:
```python
SETTER = "間接（setter経由）"
```

### 注意事項

- 他クラスの同名setterによるfalse positiveは許容（getter追跡と同方針。もれなく優先）
- 第2段階のフィールド追跡結果を入力として受け取るため、第3段階と同様に第2段階完了後に実行

---

## Indirect-1: C/Pro*C マクロ多段追跡

### 設計

`analyze_c.py` および `analyze_proc.py` の `track_define()` を拡張。

### 現状と拡張後の比較

| | 現状 | 拡張後 |
|---|---|---|
| 追跡深度 | 1段（`#define A "TARGET"` のみ） | n段（`#define C B` → `#define B A` → `#define A "TARGET"` の連鎖） |

### 実装方針

1. ソースファイル全体から `#define` マップを事前構築:
   ```
   { "A": "TARGET", "B": "A", "C": "B" }
   ```
2. 値が別の定数名を指している場合、その定数を再帰解決
3. 最大深度10でループ（循環参照）を防止
4. 中間定数（B, C等）も全て `参照種別 = "間接"` として出力

### 変更範囲

`analyze_c.py` と `analyze_proc.py` の `track_define` 関数のみ。既存の分類ロジックには手を加えない。

---

## テスト方針

各機能に対してユニットテスト・E2Eテストを追加する。

| 機能 | テストファイル | 検証内容 |
|---|---|---|
| F-07 | `tests/test_common.py` | `detect_encoding()` の自動検出・フォールバック・override動作 |
| New-1 | `tests/test_kotlin_analyzer.py` | 7種分類・`const val` 間接追跡 |
| New-2 | `tests/test_plsql_analyzer.py` | 7種分類 |
| Java-4 | `test_analyze.py` | setter候補特定・プロジェクト全体追跡・RefType.SETTER出力 |
| Indirect-1 | `tests/test_c_analyzer.py` | 多段マクロ展開・循環参照ガード |

E2Eテスト用フィクスチャ:
- `tests/kotlin/` — Kotlinサンプルソース + サンプルgrep結果
- `tests/plsql/` — PL/SQLサンプルソース + サンプルgrep結果
