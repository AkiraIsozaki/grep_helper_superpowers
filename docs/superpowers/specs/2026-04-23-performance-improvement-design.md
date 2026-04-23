# パフォーマンス改善・進捗表示 設計書

**日付**: 2026-04-23  
**対象ファイル**: `analyze_all.py`, `analyze.py`, `analyze_common.py`

---

## 背景・課題

- `--source-dir` として指定されるソースディレクトリが約 60GB
- `analyze_all.py` の Java 間接追跡フェーズ（`_apply_indirect_tracking`）で `_batch_track_constants` / `_batch_track_getters` / `_batch_track_setters` が呼ばれると、source_dir 配下の `.java` ファイル全件を Python でスキャンする
- grep 結果が数行でも「定数定義」が1件あれば数万ファイルの読み込みが始まり処理が終わらない
- 処理中の進捗が一切表示されず、生きているのか判断できない

## 要件

1. **処理速度改善**: Java 間接追跡の所要時間を大幅に削減する
2. **もれなく**: 既存の網羅性（false negative ゼロ）を維持する
3. **進捗表示**: 時間のかかる処理中は stderr に進捗を定期出力する
4. **クロスプラットフォーム**: Linux / Mac / Windows / **Solaris 10** で動作すること

---

## アーキテクチャ

### 基本方針

OS の `grep` コマンドには依存しない（Solaris 10 の `/usr/bin/grep` は `-r` / `--include` 未対応のため）。Python 標準ライブラリの `mmap` モジュールによるバイト列検索で代替する。

### 2フェーズスキャン

```
[フェーズ1: 高速バイト検索 (mmap)] ← 新規追加
  全 .java ファイルに対して
    mmap.find(b"IDENTIFIER") でいずれかのパターンが1件でもヒットすれば候補に追加
  → ヒットしたファイルのみリストアップ

[フェーズ2: 精密スキャン (既存の Python 正規表現)] ← 変更なし
  フェーズ1 で絞り込んだファイルのみスキャン
  既存の \b word boundary 正規表現で正確に分類
```

Java 識別子は ASCII 文字のみで構成されるため、Shift-JIS / UTF-8 どちらのエンコードでもバイト列は同一。エンコーディング非依存で確実に動作する。

### もれなく保証

フェーズ1は**スーパーセット**を返す（false negative ゼロ）。理由:
- `mmap.find()` はバイト列の完全一致検索で、`\b` なしのより緩い検索
- フェーズ2の正規表現（`\b` あり）でさらに精密に絞り込む
- エラー時は安全側（ファイルをスキップせずスキャン対象に含める）

---

## 実装詳細

### 1. `grep_filter_files()` を `analyze_common.py` に追加

```python
import mmap

def grep_filter_files(
    names: list[str],
    src_dir: Path,
    extensions: list[str],
    encoding: str | None = None,
) -> list[Path]:
    """mmap によるバイト列検索でスキャン対象ファイルを絞り込む。

    names に含まれる識別子を1つでも含むファイルのみ返す。
    エラー時は安全側（対象に含める）のフォールバックを行う。
    Solaris 10 / Windows を含む全 OS で動作する。
    """
    patterns = [n.encode("ascii") for n in names if n.isascii()]
    if not patterns:
        return sorted(f for ext in extensions for f in src_dir.rglob(f"*{ext}"))

    result: list[Path] = []
    for f in sorted(src_dir.rglob("*")):
        if f.suffix.lower() not in extensions:
            continue
        try:
            with open(f, "rb") as fh:
                size = f.stat().st_size
                if size == 0:
                    continue
                with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    if any(mm.find(p) != -1 for p in patterns):
                        result.append(f)
        except (OSError, ValueError, mmap.error):
            result.append(f)  # エラー時は安全側（スキップしない）
    return result
```

**配置**: `analyze_common.py`（`analyze.py` と `analyze_all.py` の両方からインポート可能にするため）

### 2. `analyze_all.py` のバッチ関数を更新

対象関数（8関数）:
- `_batch_track_constants` / `_batch_track_getters` / `_batch_track_setters`（Java）
- `_batch_track_kotlin_const`
- `_batch_track_dotnet_const`
- `_batch_track_groovy_static_final`
- `_batch_track_define_c_all`
- `_batch_track_define_proc_all`

各関数で以下を変更:
1. `src_dir.rglob("*.java")` 等の直接呼び出しを `grep_filter_files(list(tasks.keys()), src_dir, [".java"])` に置き換え
2. ファイルループ内に進捗表示を追加

### 3. `analyze.py` のバッチ関数を更新

対象関数（3関数）:
- `_batch_track_constants` / `_batch_track_getters` / `_batch_track_setters`

同様に `grep_filter_files()` を使用するよう更新。

### 4. 進捗表示フォーマット

```
  [定数追跡] 100/4200 ファイル処理済み (2%)
  [定数追跡] 200/4200 ファイル処理済み (5%)
  ...
  [定数追跡] 完了: 4200 ファイルスキャン / 参照 128 件発見
```

- **出力先**: `sys.stderr`（TSV 出力と分離）
- **表示間隔**: 100 ファイルごと（ファイル数が 100 未満の場合は完了時のみ）
- **フェーズ1完了時**: `[定数追跡] 事前フィルタ完了: 4200 → 87 ファイルに絞り込み` を表示

---

## エラーハンドリング

| ケース | 対応 |
|--------|------|
| `mmap.error` / `OSError` | そのファイルをスキャン対象に含める（安全側フォールバック） |
| ファイルサイズ 0 | スキップ（mmap は空ファイル非対応） |
| `names` が空 | `grep_filter_files()` を呼ばず元のロジックで rglob |

---

## テスト方針

1. **既存テストが全てパスすること**（インターフェース変更なし）
2. `grep_filter_files()` の単体テスト:
   - パターンを含むファイルが結果に含まれること
   - パターンを含まないファイルが除外されること
   - エラー時（permission denied 等）はフォールバックして対象に含まれること
   - `extensions` フィルタが正しく機能すること

---

### 5. grep ファイル処理開始メッセージ

`analyze_all.py` および `analyze.py` の main() ループ内、各 `.grep` ファイルの処理開始直後に以下を出力する。

```python
print(f"  処理中: {grep_path.name} ...", file=sys.stderr, flush=True)
```

**背景**: 複数の `.grep` ファイルがある場合、最初の小さいファイルの TSV が素早く出力された後、2ファイル目以降の間接追跡フェーズで無音のまま詰まるように見える事象への対処。このメッセージにより処理が継続していることが即座にわかる。

期待される出力例：
```
  処理中: keyword_A.grep ...
  keyword_A.grep → output/keyword_A.tsv (直接: 3件, 間接: 5件)
  処理中: keyword_B.grep ...
  [定数追跡] 事前フィルタ完了: 82000 → 134 ファイルに絞り込み
  [定数追跡] 100/134 ファイル処理済み (75%)
  ...
```

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `analyze_common.py` | `grep_filter_files()` を追加、`mmap` import 追加 |
| `analyze_all.py` | 8 バッチ関数を `grep_filter_files()` + 進捗表示に更新、処理開始メッセージ追加 |
| `analyze.py` | 3 バッチ関数を `grep_filter_files()` + 進捗表示に更新、処理開始メッセージ追加 |

---

## 期待効果

- **処理時間**: 60GB / 数万 .java ファイルのケースで、間接追跡フェーズが数時間→数分〜数十分に改善（実データのヒット率次第）
- **進捗可視性**: 「終わらない」ではなく「何ファイル中何ファイル処理済み」が常に見える。複数 grep ファイルでも各ファイルの処理開始が即座にわかる
- **互換性**: Solaris 10 を含む全 OS で動作、既存の網羅性を維持
