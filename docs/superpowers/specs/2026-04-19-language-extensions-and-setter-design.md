# 設計書: 多言語拡張 + setter追跡

**日付**: 2026-04-19  
**スコープ**: 5言語の新規アナライザー追加 + Java/Groovy setter追跡

---

## 1. 概要

### 追加する言語アナライザー

| ファイル | 対象言語 | 間接追跡 | setter追跡 |
|---|---|---|---|
| `analyze_groovy.py` | Groovy (.groovy / .gvy) | ✅ static final + フィールド | ✅ |
| `analyze_dotnet.py` | C# (.cs) + VB.NET (.vb) | ✅ Const / readonly static | — |
| `analyze_ts.py` | TypeScript / JavaScript (.ts / .tsx / .js / .jsx) | — | — |
| `analyze_python.py` | Python (.py) | — | — |
| `analyze_perl.py` | Perl (.pl / .pm) | — | — |

### 既存アナライザーへの追加

| ファイル | 変更内容 |
|---|---|
| `analyze.py` | setter追跡（Stage 2.5）を追加 |

---

## 2. 使用タイプ定義

### Groovy（7種）

| 使用タイプ | 検出パターン（正規表現） |
|---|---|
| static final定数定義 | `\bstatic\s+final\b` |
| 変数代入 | `\b(def\s+\w+\s*=\|[\w<>\[\]]+\s+\w+\s*=)` |
| 条件判定 | `\bif\s*\(\|\bswitch\s*\(\|==\|!=\|\.equals\s*\(` |
| return文 | `\breturn\b` |
| アノテーション | `@\w+` |
| メソッド引数 | `\w+\s*\(` |
| その他 | 上記すべてに非マッチ |

### VB.NET / C#（7種）

| 使用タイプ | 検出パターン |
|---|---|
| 定数定義(Const/readonly) | `\bconst\b`（C#）/ `\bConst\b`（VB）/ `\breadonly\b` |
| 変数代入 | `\b(var\|string\|int\|String)\s+\w+\s*=`（C#）/ `\bDim\b.*=`（VB） |
| 条件判定 | `\bif\s*\(\|\bIf\b\|==\|!=\|<>\|\.Equals\s*\(` |
| return文 | `\breturn\b`（C#）/ `\bReturn\b`（VB） |
| 属性(Attribute) | `\[[\w]+` （C#）/ `<[\w]+` （VB） |
| メソッド引数 | `\w+\s*\(` |
| その他 | 上記すべてに非マッチ |

### TypeScript / JavaScript（7種）

| 使用タイプ | 検出パターン |
|---|---|
| const定数定義 | `\bconst\s+\w+\s*=` |
| 変数代入(let/var) | `\b(let\|var)\s+\w+\s*=` |
| 条件判定 | `\bif\s*\(\|\bswitch\s*\(\|===\|!==\|==\|!=` |
| return文 | `\breturn\b` |
| デコレータ | `@\w+` |
| 関数引数 | `\w+\s*\(` |
| その他 | 上記すべてに非マッチ |

### Python（6種）

| 使用タイプ | 検出パターン |
|---|---|
| 変数代入 | `^\s*\w+\s*=` |
| 条件判定 | `\bif\b\|\belif\b\|==\|!=\|\bin\b` |
| return文 | `\breturn\b` |
| デコレータ | `@\w+` |
| 関数引数 | `\w+\s*\(` |
| その他 | 上記すべてに非マッチ |

### Perl（6種）

| 使用タイプ | 検出パターン |
|---|---|
| use constant定義 | `\buse\s+constant\b` |
| 変数代入 | `\$\w+\s*=\|\bmy\b.*=\|\bour\b.*=` |
| 条件判定 | `\bif\s*\(\|\bunless\s*\(\|==\|ne\b\|eq\b` |
| print/say出力 | `\bprint\b\|\bsay\b\|\bprintf\b` |
| 関数引数 | `\w+\s*\(` |
| その他 | 上記すべてに非マッチ |

---

## 3. 間接追跡の設計

### 3-1. Groovy

Kotlinの `track_const` と同構造。加えてJavaと同様のフィールド追跡も実施する。

**定数追跡（`track_static_final_groovy`）:**
- 起点: `static final定数定義` に分類された行
- 定数名の抽出: `\bstatic\s+final\s+\w[\w<>]*\s+(\w+)\s*=` でキャプチャ
- 追跡対象: `source_dir` 以下の全 `.groovy` / `.gvy` ファイル
- スコープ: プロジェクト全体
- 出力参照種別: `間接`

**フィールド追跡（`track_field_groovy`）:**
- 起点: `変数代入` に分類され、かつクラスレベルの宣言と判定された行
- 追跡スコープ: 同一クラス内（同一ファイル内）
- 出力参照種別: `間接`
- setter追跡も起動する（後述）

**クラスレベル判定:**
正規表現で `(private|protected|public|def)\s+\w[\w<>]*\s+\w+\s*[=;]` にマッチする行をフィールドとみなす。

### 3-2. VB.NET / C#（`analyze_dotnet.py`）

**定数追跡（`track_const_dotnet`）:**

C# の検出パターン:
```
\bconst\s+\w[\w<>]*\s+(\w+)\s*=
\bpublic\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*=
\bprivate\s+static\s+readonly\s+\w[\w<>]*\s+(\w+)\s*=
```

VB.NET の検出パターン:
```
\bConst\s+(\w+)\s+As\b
```

- 追跡対象: `source_dir` 以下の全 `.cs` / `.vb` ファイル
- スコープ: プロジェクト全体
- 出力参照種別: `間接`

**フィールド追跡（`track_field_dotnet`）:**
- 起点: `readonly` フィールド宣言（インスタンスレベル）
- 追跡スコープ: 同一クラス内
- 出力参照種別: `間接`
- setter追跡は実施しない

---

## 4. setter追跡の設計

### 4-1. 対象

- Java (`analyze.py`) — 既存コードに Stage 2.5 として追加
- Groovy (`analyze_groovy.py`) — 新規実装に組み込み

### 4-2. 起動条件

以下のいずれかのレコードを起点とする:

1. **直接参照**の行が setter呼び出しパターンに一致する場合
   - パターン: `\bset[A-Z]\w*\s*\(` （例: `obj.setType("777")`）
2. **Stage 2の間接参照**レコードの行が setter呼び出しパターンに一致する場合
   - 例: `obj.setType(CODE)` （CODEが間接参照として追跡された結果）

### 4-3. 処理手順

**ステップ1: setterメソッド名の抽出**

パターン: `\.?(set[A-Z]\w*)\s*\(` でキャプチャ  
例: `obj.setType(CODE)` → `setType`

**ステップ2: フィールド名の推定（2方式）**

方式1（命名規則）:
- `setType` → `type`（先頭の `set` を除去し先頭小文字化）

方式2（ASTによるメソッド本体解析）:
- Javaの場合: javalang ASTで `setType` メソッドを探し、`this.field = param` の代入文からフィールド名を取得
- Groovyの場合: 正規表現で `this\.(\w+)\s*=\s*\w+` または `(\w+)\s*=\s*\w+` をメソッド本体内で検索

**ステップ3: getter呼び出しの追跡**

- Java: 既存の `find_getter_names` / `track_getter_calls`（`analyze.py` 内）を呼び出す
- Groovy: `analyze_groovy.py` 内に `find_getter_names_groovy` / `track_getter_calls_groovy` を実装する（正規表現ベース。javalangは使用しない）

**ステップ4: 出力**

- 参照種別: `間接（setter経由）`（`RefType.SETTER`）
- `src_var`: setterメソッド名（例: `setType`）
- `src_file` / `src_lineno`: setter呼び出し行のファイル・行番号

---

## 5. ファイル・フィクスチャ構成

### 新規ソースファイル

```
analyze_groovy.py
analyze_dotnet.py
analyze_ts.py
analyze_python.py
analyze_perl.py
```

### テストファイル・フィクスチャ

```
tests/
├── groovy/
│   ├── input/    # TARGET.grep
│   ├── src/      # sample.groovy（static final定数・フィールド・setter呼び出し含む）
│   └── expected/ # TARGET.tsv
├── dotnet/
│   ├── input/    # TARGET.grep
│   ├── src/      # sample.cs, sample.vb
│   └── expected/ # TARGET.tsv
├── ts/
│   ├── input/    # TARGET.grep
│   ├── src/      # sample.ts, sample.js
│   └── expected/ # TARGET.tsv
├── python/
│   ├── input/    # TARGET.grep
│   ├── src/      # sample.py
│   └── expected/ # TARGET.tsv
└── perl/
    ├── input/    # TARGET.grep
    ├── src/      # sample.pl
    └── expected/ # TARGET.tsv

tests/
├── test_groovy_analyzer.py
├── test_dotnet_analyzer.py
├── test_ts_analyzer.py
├── test_python_analyzer.py
└── test_perl_analyzer.py
```

### analyze.py への変更

`main()` 内の Stage 2 処理の後に setter追跡ループを追加する:

```python
# Stage 2.5: setter経由追跡
for record in list(stage2_records) + list(direct_records):
    if _is_setter_call(record.code):
        setter_name = _extract_setter_name(record.code)
        if setter_name:
            all_records.extend(
                track_setter_calls(setter_name, source_dir, record, stats)
            )
```

新規追加関数:
- `_is_setter_call(code: str) -> bool`
- `_extract_setter_name(code: str) -> str | None`
- `track_setter_calls(setter_name, source_dir, origin, stats) -> list[GrepRecord]`

---

## 6. 共通実装パターン

全新規アナライザーは既存の `analyze_kotlin.py` / `analyze_plsql.py` と同一の構造に従う:

- `detect_encoding()` を使用（chardetオプション対応）
- `--encoding` オプションを全アナライザーに追加
- `_file_cache` / `_MAX_FILE_CACHE = 800` をモジュールレベルで定義
- `build_parser()` / `main()` の構造を統一

---

## 7. スコープ外

- Groovy / VB.NET / C# のAST解析（全て正規表現のみで実装）
- TypeScript の型情報を使った追跡
- Python の間接追跡（命名規則ベースのため精度が低い）
- Perl の間接追跡
- VB.NET / C# の setter追跡
