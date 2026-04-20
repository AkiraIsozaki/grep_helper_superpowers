# analyze_all.py 設計仕様

**日付:** 2026-04-20  
**対象:** `analyze_all.py` — 全言語対応ディスパッチャーアナライザー

---

## 背景・目的

既存のアナライザーは言語ごとに個別スクリプトとして実装されており、grep結果ファイルに複数言語のファイルが混在している場合、拡張子フィルタなしで全行を処理してしまう（他言語の行を誤分類）。また複数アナライザーを順番に実行すると出力TSVを上書きし合うため、最後に実行したもの以外の結果が失われる。

`analyze_all.py` は1回の実行で全言語・未知言語を網羅し、漏れなく1本のTSVに出力することを目的とする。

---

## 設計方針

- **既存モジュールは一切変更しない**（import して関数を再利用するだけ）
- CLI引数は既存アナライザーと完全共通（`--source-dir`, `--input-dir`, `--output-dir`, `--encoding`）
- 出力は `output/TARGET.tsv` 1本（既存と同じファイル名・形式・UTF-8 BOM付き）

---

## アーキテクチャ

```
analyze_all.py
│
├── parse_grep_line()        ← analyze_common から流用
├── 拡張子ルーティングテーブル（dict）
├── シバン判定（拡張子なしファイル用）
├── classify_usage_<lang>() のマッピング（各モジュールからimport）
├── track_*() 関数群（各モジュールからimport）
└── write_tsv()              ← analyze_common から流用
```

---

## 拡張子ルーティングテーブル

| 拡張子 | 言語キー | 間接追跡 |
|--------|---------|:--------:|
| `.java` | java | ✅ |
| `.kt`, `.kts` | kotlin | ✅ |
| `.c`, `.h` | c | ✅ |
| `.pc`, `.pcc` | proc | ✅ |
| `.sql` | sql | ✅ |
| `.sh`, `.bash` | sh | ✅ |
| `.ts`, `.js`, `.tsx`, `.jsx` | ts | — |
| `.py` | python | — |
| `.pl`, `.pm` | perl | — |
| `.cs`, `.vb` | dotnet | ✅ |
| `.groovy`, `.gvy` | groovy | ✅ |
| `.pls`, `.pck`, `.prc`, `.pkb`, `.pks`, `.fnc`, `.trg` | plsql | — |
| **それ以外すべて** | other | — |

---

## シバン判定（拡張子なしファイル）

拡張子がないファイルは `source_dir/filepath` の1行目を読んでシバンを確認する。

| シバンパターン | ルーティング先 |
|----------------|--------------|
| `perl`, `env perl` | perl |
| `sh`, `bash`, `env bash` | sh |
| `csh`, `tcsh`, `env csh`, `env tcsh` | sh |
| `ksh`, `ksh93`, `env ksh` | sh |
| それ以外 / 読み取り失敗 | other |

シバン読み取り失敗（ファイル不存在・文字化けなど）は `other` にフォールバックして処理続行。

---

## 処理フロー（1 grepファイルに対して）

```
1. grep行を全行パース
   └─ parse_grep_line() で filepath / lineno / code を取得

2. 各行の filepath から言語を決定
   ├─ 拡張子あり → ルーティングテーブルで言語決定
   └─ 拡張子なし → source_dir/filepath の1行目を読んでシバン判定

3. 言語ごとに classify_usage_<lang>(code) を呼び、直接参照レコードを生成
   └─ other → usage_type="その他", ref_type="直接"

4. 間接追跡（言語ごとの track_*() を条件分岐で呼ぶ）
   ├─ java    : usage_type が定数定義/フィールド → track系関数
   ├─ kotlin  : "const val定数定義" → track_const
   ├─ c       : "#define定数定義" → track_define, "変数代入" → track_variable
   ├─ proc    : 同上
   ├─ sh      : "変数代入" → track_sh_variable
   ├─ sql     : "変数代入" → track_sql_variable
   ├─ dotnet  : "const定義" or "static readonly定義" → track_const_dotnet
   ├─ groovy  : "static final定数定義" → track_static_final_groovy
   │            "変数代入"(クラスフィールド) → track_field_groovy (getter/setter含む)
   └─ ts/python/perl/plsql/other : 間接追跡なし

5. 全レコードをマージ → write_tsv() で output/TARGET.tsv に出力
```

---

## エラーハンドリング

| ケース | 対応 |
|--------|------|
| シバン読み取り失敗 | `other` にフォールバック、処理続行 |
| 間接追跡中のエラー | 既存 `track_*` 関数のエラー処理を継承（スキップして続行） |
| 統計出力 | 既存アナライザーと同様、終了時に `total/valid/skipped` をstderrに表示 |

---

## テスト方針

`tests/all/` ディレクトリを新規作成し、以下のケースをカバーする。

1. 拡張子ありの各言語行が正しく分類される
2. 拡張子なし＋シバンあり（perl / sh / csh / tcsh / ksh）が正しくルーティングされる
3. 未知拡張子（`.xml`, `.yaml` など）が `"その他"` で出力される
4. 複数言語混在のgrepファイルで全行が出力に含まれる（漏れゼロ確認）

---

## スコープ外

- 既存アナライザーへの変更
- csh/tcsh/ksh専用の分類ロジック（sh分類器を流用）
- 言語別に別TSVへ分割する機能
