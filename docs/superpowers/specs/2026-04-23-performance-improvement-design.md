# パフォーマンス改善・進捗表示 設計書

**日付**: 2026-04-23  
**対象ファイル**: `analyze_all.py`, `analyze.py`, `analyze_common.py`

---

## 背景・課題

- `--source-dir` として指定されるソースディレクトリが約 60GB
- `analyze_all.py` の Java 間接追跡フェーズ（`_apply_indirect_tracking`）で `_batch_track_constants` / `_batch_track_getters` / `_batch_track_setters` が呼ばれると、source_dir 配下の `.java` ファイル全件を Python でスキャンする
- grep 結果が数行でも「定数定義」が1件あれば数万ファイルの読み込みが始まり処理が終わらない
- 処理中の進捗が一切表示されず、生きているのか判断できない
- 複数の `.grep` ファイルがある場合、最初の小さいファイルの TSV 出力後に無音のまま詰まるように見える

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
  対象拡張子のファイルに対して
    mmap.find(b"IDENTIFIER") でいずれかのパターンが1件でもヒットすれば候補に追加
  → ヒットしたファイルのみリストアップ（数秒〜十数秒）

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

**配置**: `analyze_common.py`（`analyze.py` と `analyze_all.py` の両方からインポート可能にするため）

```python
import mmap

def grep_filter_files(
    names: list[str],
    src_dir: Path,
    extensions: list[str],   # 例: [".java"] または [".kt", ".kts"]
    encoding: str | None = None,
) -> list[Path]:
    """mmap によるバイト列検索でスキャン対象ファイルを絞り込む。

    names に含まれる識別子を1つでも含むファイルのみ返す。
    エラー時は安全側（対象に含める）のフォールバックを行う。
    Solaris 10 / Windows を含む全 OS で動作する。
    """
    patterns = [n.encode("ascii") for n in names if n.isascii()]
    ext_set = set(extensions)

    # パターンなし → 全ファイルを返す
    if not patterns:
        result: list[Path] = []
        for ext in extensions:
            result.extend(src_dir.rglob(f"*{ext}"))
        return sorted(result)

    result = []
    for ext in extensions:                      # 拡張子ごとに rglob（"*" は使わない）
        for f in src_dir.rglob(f"*{ext}"):
            try:
                if f.stat().st_size == 0:
                    continue
                with open(f, "rb") as fh, \
                     mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    if any(mm.find(p) != -1 for p in patterns):
                        result.append(f)
            except (OSError, ValueError, mmap.error):
                result.append(f)               # エラー時は安全側（スキップしない）
    return sorted(result)
```

**バグ修正ポイント**: `rglob("*")` + 拡張子フィルタではなく `rglob("*.java")` 形式を使う。`rglob("*")` は全ファイルを列挙してから Python でフィルタするため、非対象ファイルも含む大量のパスを処理してしまう。

### 2. Java 3バッチスキャンの rglob を1回に集約（`analyze_all.py`）

`_apply_indirect_tracking()` 内で定数・getter・setter の追跡が連続して行われ、それぞれが独立して `grep_filter_files()` → rglob を実行していた。Java ファイルリストの事前フィルタを1回にまとめて共有する。

```python
# _apply_indirect_tracking() 内、Java バッチ処理の直前
if java_project_tasks or java_getter_tasks or java_setter_tasks:
    all_java_names = (
        list(java_project_tasks.keys())
        + list(java_getter_tasks.keys())
        + list(java_setter_tasks.keys())
    )
    java_candidates = grep_filter_files(all_java_names, source_dir, [".java"], encoding)
    # java_candidates を3つのバッチ関数に渡す（file_list 引数として受け取る形に変更）
```

`_batch_track_constants` / `_batch_track_getters` / `_batch_track_setters` の引数に `file_list: list[Path] | None = None` を追加し、渡された場合はその一覧を使う。

**効果**: Java の場合 rglob 3回 → 1回に削減。

### 3. `analyze_all.py` の非 Java バッチ関数を更新

対象関数（5関数）:
- `_batch_track_kotlin_const`
- `_batch_track_dotnet_const`
- `_batch_track_groovy_static_final`
- `_batch_track_define_c_all`
- `_batch_track_define_proc_all`

各関数内の `src_dir.rglob("*.kt")` 等を `grep_filter_files(list(tasks.keys()), src_dir, [...])` に置き換える。

### 4. `analyze.py` のバッチ関数を更新

`_batch_track_constants` / `_batch_track_getters` / `_batch_track_setters` の3関数。  
`_get_java_files()` による全件スキャンを `grep_filter_files()` に置き換える。  
`analyze.py` の main() でも、定数・getter・setter の file_list を1回の `grep_filter_files()` で共有する（上記②と同様）。

### 5. Java AST キャッシュサイズの拡大（`analyze.py`）

```python
# 変更前
_MAX_AST_CACHE_SIZE = 300

# 変更後
_MAX_AST_CACHE_SIZE = 2000
```

**背景**: 60GB のソースでは数万の `.java` ファイルが存在し得る。キャッシュが 300 件では頻繁に evict が発生し、同一ファイルを何度も javalang でパースし直す。2000 に拡大することで直接参照フェーズの AST 再解析を大幅に削減する（AST オブジェクト 1 件あたり推定 1〜3MB、2000 件 ≈ 2〜6GB。メモリが許す環境では有効）。

> **注意**: メモリが制限される環境では 500〜1000 程度に調整すること。

### 6. 進捗表示フォーマット

```
  処理中: keyword_B.grep ...                          ← grep ファイル処理開始（新規）
  [定数追跡] 事前フィルタ完了: 82000 → 134 ファイルに絞り込み
  [定数追跡] 100/134 ファイル処理済み (75%)
  [定数追跡] 完了: 134 ファイルスキャン / 参照 128 件発見
```

- **出力先**: `sys.stderr`（TSV 出力と分離）
- **grep ファイル開始メッセージ**: `analyze_all.py` / `analyze.py` の main() ループ先頭で出力
- **バッチスキャン進捗**: 100 ファイルごと（ファイル数が 100 未満の場合は完了時のみ）
- **フェーズ1完了時**: 絞り込み結果（全件数 → 候補件数）を表示

---

## エラーハンドリング

| ケース | 対応 |
|--------|------|
| `mmap.error` / `OSError` | そのファイルをスキャン対象に含める（安全側フォールバック） |
| ファイルサイズ 0 | スキップ（mmap は空ファイル非対応） |
| `names` が空 | `grep_filter_files()` は全ファイルを返す（rglob のみ） |
| AST キャッシュ超過 | 最古エントリを evict（既存動作を維持） |

---

## テスト方針

1. **既存テストが全てパスすること**（外部インターフェース変更なし）
2. `grep_filter_files()` の単体テスト:
   - パターンを含むファイルが結果に含まれること
   - パターンを含まないファイルが除外されること
   - エラー時（permission denied 等）はフォールバックして対象に含まれること
   - `extensions` フィルタが正しく機能すること（`rglob("*.java")` 形式）
3. Java バッチ関数で `file_list` 共有が正しく動作すること（定数・getter・setter が同一候補リストを使う）

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `analyze_common.py` | `grep_filter_files()` を追加、`mmap` import 追加 |
| `analyze_all.py` | 8 バッチ関数を `grep_filter_files()` + 進捗表示に更新、Java 3バッチの rglob を1回に集約、処理開始メッセージ追加 |
| `analyze.py` | 3 バッチ関数を `grep_filter_files()` + 進捗表示に更新、Java 3バッチの rglob を1回に集約、`_MAX_AST_CACHE_SIZE` を 2000 に拡大、処理開始メッセージ追加 |

---

## 期待効果

| 改善内容 | 効果 |
|---------|------|
| mmap 事前フィルタ | 間接追跡のスキャン対象ファイルを数万→数百以下に削減（実データのヒット率次第） |
| `rglob("*.java")` 修正 | 非 Java ファイルの無駄な列挙を排除 |
| Java rglob 3回→1回 | rglob コスト（60GB ディレクトリ走査）を1/3に削減 |
| AST キャッシュ拡大 | 同一 Java ファイルの再パースを削減、直接参照フェーズが速くなる |
| 進捗表示 | 「終わらない」→「何ファイル中何ファイル処理済み」が常に見える |
| 処理開始メッセージ | 複数 grep ファイル時の「無音フリーズ」感を解消 |
