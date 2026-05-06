# パフォーマンス改善 + Solaris 10 互換 設計書

**日付**: 2026-05-06
**対象ファイル**:

- `grep_helper/encoding.py`（変更）
- `grep_helper/source_files.py`（変更）
- `grep_helper/dispatcher.py`（変更）
- `grep_helper/pipeline.py`（変更）
- `grep_helper/languages/*.py`（12 ハンドラ全体: `batch_track_indirect` のキーワード引数追加）
- `analyze_all.py`（CLI フラグ `--no-mmap` 追加）
- `pyproject.toml`（新規 / ruff 設定）
- `requirements.txt`（コメント追記）
- `requirements-dev.txt`（コメント追記）
- `scripts/smoke_solaris.md`（新規）
- `tests/test_encoding.py`（新規）
- `tests/test_source_files.py`（新規）
- `tests/test_pipeline_run.py`（追記）

---

## 背景・動機

`docs/superpowers/specs/2026-04-23-performance-improvement-design.md` で 2 フェーズスキャン（mmap 事前フィルタ + Python 精密スキャン）と進捗表示が導入され、`docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` の §E-性能・スケール では以下が後続課題として明記されている。

- 第 1 段階（grep 行分類）の並列化
- 増分処理
- AST キャッシュのディスク永続化
- 60GB 級ソースでのプロファイリング

本タスクはこれらの「重量級」E 項目に踏み込む前段として、現コードに残っている**重複作業**を削る軽量な性能改善と、出荷先である **Solaris 10** での実運用に向けたランタイム互換ガードを 1 本にまとめて実施する。具体的には以下:

- **E-1**: `detect_encoding` の重複呼び出しを削るキャッシュ追加
- **E-2**: 全 grep ファイルの直接分類を先に集約してから間接追跡を 1 回だけ走らせる構造変更
- **E-3**: Solaris 10 + NFS 上での `mmap` 不安定性に備えた自動フォールバック + `--no-mmap` フラグ
- **C-1**: Python 3.7 互換ガード（ruff `target-version = "py37"`）
- **C-2**: Solaris 10 + Python 3.7.17 build からの動作スモーク手順を `scripts/` に記録
- **V-1**: KPI ゴールデンセットを使った before/after の網羅率と所要時間の比較

---

## ロードマップ上の位置付け

`docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` の「F-first を起点に選んだ理由」で、E（性能改善）は KPI で網羅率維持を検証しながら進めると明記されている。本タスクは V-1 でその通りに進める。

E 課題のうち本タスクが扱うのは「重複作業を削る」軽量な改善のみ。第 1 段階並列化・増分処理・AST キャッシュ永続化・本番プロファイリングは独立した spec で扱う。

---

## 要件

1. **性能改善**:
   - 同一ファイルに対する `detect_encoding` 呼び出しでバイト読み込み + chardet が高々 1 回しか発生しないこと
   - 間接追跡（`batch_track_indirect`）の呼び出し回数が grep ファイル数 N ではなく言語ハンドラ数（最大 12）に比例すること
2. **網羅率維持**: 改造前後で `python scripts/measure_kpi.py --lang all` の結果が同一であること（行単位で完全一致）
3. **Solaris 10 互換**:
   - Python 3.7.17 (cc 自前 build, venv 構成) で `analyze_all.py` が import から実行まで通ること
   - NFS 上で `mmap` がハングする状況を `--no-mmap` または環境変数 `GREP_HELPER_NO_MMAP=1` で回避できること
4. **後方互換**: ハンドラ層の公開 API（`classify_usage`, `batch_track_indirect`）は破壊的変更を行わない。`batch_track_indirect` への新引数 `use_mmap` はキーワード専用、デフォルト True で旧呼び出し互換
5. **やらないこと**:
   - `scripts/measure_kpi.py` および `tests/` の Python 3.7 動作対応
   - pytest 9 → 7 ダウングレード
   - 第 1 段階（直接分類）の並列化
   - 60GB 級ソースでの本番プロファイリング
   - AST キャッシュのディスク永続化
   - Solaris 用 Python 3.7 build / `pyahocorasick` cp37 wheel の作成（`scripts/smoke_solaris.md` に手順は書くが、ビルド成果物は本リポジトリには持たない）
   - `grep_filter_files` の非 ASCII 識別子対応

---

## アーキテクチャ

### E-1: encoding キャッシュ

`grep_helper/encoding.py` にプロセス内グローバル `dict[str, str]` を追加し、`override` が指定されないケースで `str(path) → encoding` をメモ化する。

```
detect_encoding(path, override) の動作:
  override is not None → そのまま返す（キャッシュしない）
  cache hit            → 格納値を返す
  cache miss           → 既存の chardet ロジックを実行 → 結果（cp932 フォールバック含む）をキャッシュ
```

設計判断:

- キャッシュキーは `str(path)` のみ。`override` は早期 return 済みなのでキーから除外する。
- chardet が None / 低 confidence を返した既存の `cp932` フォールバック結果も**キャッシュする**（同じパスで毎回 chardet を起動しないため）。
- `OSError` で読めなかった場合の `cp932` もキャッシュする（同じパスで再度 stat しないため）。
- LRU 上限は導入しない。`iter_source_files` でスキャンされるファイル数（数千〜数万）のオーダー、1 エントリ ~80B、合計数 MB の見込みで、LRU の複雑度に見合わない。
- テスト用に `_encoding_cache_clear()` を公開する（既存の `_source_files_cache_clear` 等と同じ作法）。

### E-2: 集約バッチ間接追跡

`grep_helper/pipeline.run_full_pipeline` と `grep_helper/dispatcher.main` を 3 フェーズ構造に組み替える。

```
フェーズ1（直接分類）:
  for grep_file in grep_files:
    direct_by_keyword[grep_file.stem] = process_grep_file(grep_file)
    print(f"  処理中: {grep_file.name} ...")  # 既存ログを維持

フェーズ2（間接追跡, ハンドラ毎に 1 回）:
  all_direct = chain(*direct_by_keyword.values())
  for handler in unique_handlers:
    indirect_all.extend(
        handler.batch_track_indirect(all_direct, src_dir, encoding,
                                     workers=workers, use_mmap=use_mmap)
    )

フェーズ3（keyword で振り分け / TSV 出力）:
  indirect_by_keyword = group_by_keyword(indirect_all)
  for keyword, direct in direct_by_keyword.items():
    write_tsv(direct + indirect_by_keyword.get(keyword, []),
              output_dir / f"{keyword}.tsv")
```

設計判断:

- ハンドラ層 `batch_track_indirect` のシグネチャは維持。既存実装は `direct_records` 内の各 `record.keyword` を間接追跡レコードに引き継いでいるため、複数 keyword 分の direct を 1 回で渡しても元の 1 keyword ずつ呼んだ場合と同じ結果集合が返る。
- 振り分けは戻り値の `record.keyword` で行う。`keyword` が未設定の record は仕様外として捨てる（現コードでは発生しないが防御的に）。
- 進捗ログ:
  - フェーズ 1: 既存通り「処理中: foo.grep」を grep ファイル毎に出す。
  - フェーズ 2: 既存の `_batch_track_combined` 内の「Java 追跡(統合): N ファイル中 M 完了」相当を全体 1 系列で残す。
- `ProcessStats` は全 keyword で 1 個共有（フェーズ 1 で `total_lines` `valid_lines` `skipped_lines` が積算され、フェーズ 2 で `encoding_errors` `fallback_files` が積算される）。`print_report` はプロセス終端で 1 回。

シグネチャ変更（追加のみ）:

```python
# grep_helper/dispatcher.py
def apply_indirect_tracking(
    direct_records: list[GrepRecord],   # 全 grep ファイル分の集約済み
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
    use_mmap: bool = True,              # 新規
) -> list[GrepRecord]: ...

# grep_helper/languages/<each>.py（12 ハンドラ全部）
def batch_track_indirect(
    direct_records, src_dir, encoding,
    *, workers=1, use_mmap=True,        # use_mmap を追加
) -> list[GrepRecord]: ...
```

`use_mmap` はハンドラ内部で `grep_filter_files(..., use_mmap=use_mmap)` に渡す。

### E-3: mmap 自動フォールバック + `--no-mmap`

`grep_helper/source_files.grep_filter_files`:

```python
def grep_filter_files(names, src_dir, extensions, label="", *, use_mmap=True):
    candidates = iter_source_files(src_dir, extensions)
    patterns = [n.encode("ascii") for n in names if n.isascii()]
    if not patterns:
        return candidates

    result = []
    for f in candidates:
        try:
            if f.stat().st_size == 0:
                continue
            if use_mmap:
                try:
                    hit = _mmap_find(f, patterns)
                except (OSError, ValueError, mmap.error):
                    hit = _read_based_find(f, patterns)
            else:
                hit = _read_based_find(f, patterns)
            if hit:
                result.append(f)
        except OSError:
            result.append(f)  # 既存「セーフ側」フォールバック
    ...
```

`_read_based_find(path, patterns)` の挙動:

- ファイルを 1 MB チャンクで `read()` しつつ `bytes.find` で検索
- 各チャンク末尾 `max(len(p) for p in patterns) - 1` バイトを次チャンクへ前送り（境界またぎ防止）
- メモリ上限はチャンク 1 MB + オーバーラップで O(1)

CLI 側:

- `grep_helper/dispatcher.build_parser` に `--no-mmap` を追加
- 環境変数 `GREP_HELPER_NO_MMAP=1` でも有効化（運用ラッパーから設定しやすくする）
- 優先順: CLI フラグ > 環境変数 > デフォルト True

`use_mmap` は以下のパスで dispatch される:

```
CLI args / env → dispatcher.main → apply_indirect_tracking →
  handler.batch_track_indirect → grep_filter_files
```

### C-1: Python 3.7 互換ガード

現コードは `from __future__ import annotations` 配下で PEP 604 / PEP 585 を使っており、ランタイム評価される 3.8+ 構文（walrus, pos-only, `functools.cache`, `TypedDict`, `match/case`）は AST スキャンで検出ゼロ。本タスクではこの状態を**維持する**ためのガードを設置する。

新規 `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py37"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "UP"]
```

`ruff check grep_helper/ analyze_*.py` を実装計画のチェックリストに入れる。CI 自動化は本タスク範囲外（手動運用）。

`requirements.txt` の各エントリは現状版下限が 3.7 互換なので据え置き。Python バージョン要件のコメントを追記する:

```
# Python >=3.7 で動作する版の組み合わせ:
javalang>=0.13.0,<1.0.0
chardet>=5.0.0,<6.0.0
pyahocorasick>=2.0.0,<3.0.0   # Solaris では _aho_corasick.py の pure Python フォールバックに任せる
```

`requirements-dev.txt` には `# Python >= 3.9（pytest 9.x）— Solaris 10 ランタイム互換の対象外` を追記する。

### C-2: Solaris スモーク手順

`scripts/smoke_solaris.md`（新規）に運用側向けの手順を記録する。

```
1. Python 3.7.17 ビルド
   $ tar xzf Python-3.7.17.tgz
   $ cd Python-3.7.17 && ./configure --prefix=$HOME/py37 --enable-shared
   $ make -j4 && make install

2. venv 作成
   $ $HOME/py37/bin/python3 -m venv $HOME/grep_helper_venv
   $ source $HOME/grep_helper_venv/bin/activate

3. 依存インストール（cp312 wheel は Solaris で使えないため source build）
   $ pip install --no-binary=:all: chardet javalang
   # pyahocorasick はビルド失敗する可能性あり。失敗時はインストールせず、
   # _aho_corasick.py の pure Python フォールバックに任せる

4. スモーク実行
   $ python analyze_all.py --source-dir <path> \
       --input-dir input --output-dir output --no-mmap

5. 既知の制約
   - Solaris + NFS では --no-mmap または GREP_HELPER_NO_MMAP=1 を推奨
   - --workers >= 2 を使う場合は ulimit -n を 1024 以上に上げてから起動
```

---

## データフロー（断面）

E-2 の組み替えを既存関数の責務にマップする:

| フェーズ | 旧呼び出し | 新呼び出し |
|---|---|---|
| 1. 直接分類 | `pipeline.process_grep_file(grep, ...)` を grep ごとに呼ぶ | 同上（無変更） |
| 2. 集約 | （存在しない） | `dispatcher` / `pipeline` が `dict[keyword] = direct_records` を蓄積 |
| 3. 間接追跡 | `handler.batch_track_indirect(direct, ...)` を grep × handler 回 呼ぶ | `handler.batch_track_indirect(all_direct, ...)` を handler 回のみ呼ぶ |
| 4. 振り分け | （keyword は元から direct と一緒に同 grep の TSV へ） | 戻り値を `record.keyword` でグルーピング |
| 5. TSV 出力 | `write_tsv(direct + indirect, output / f"{stem}.tsv")` | 同左、ただし indirect は振り分け結果 |

`scripts/measure_kpi.py` は `pipeline.run_full_pipeline` を呼ぶため、戻り値（`list[str]` の処理ファイル名）と出力 TSV の中身が改造前後で同一であることが要件 §2 の必須条件となる。

---

## エラー処理

| 局面 | 旧挙動 | 新挙動 |
|---|---|---|
| 1 grep の直接分類で例外 | プロセス中断（`return 2`）、それまでに出した TSV のみ残る | **個別 grep だけスキップ**して他を処理。`stderr` にエラー出力 |
| 間接追跡で例外 | プロセス中断 | 同左（中断）。E-2 で 1 回しか呼ばれないため、ここで失敗するとプロジェクト全体が失敗する |
| `mmap` で `OSError`/`ValueError`/`mmap.error` | フィルタ無効化（候補に残す = セーフ側） | (E-3) `_read_based_find` でリトライ。それでも失敗したら従来通り「セーフ側」候補に残す |
| `cached_file_lines` の `OSError` | 空 list 返却 + `stats.encoding_errors` に積む | 同左（無変更） |

**直接分類エラー時の挙動変更について**: 旧実装は 1 grep の例外で全体中断していたが、新実装は集約後に間接追跡を 1 回しか走らせないので、直接フェーズで早期中断すると残りの grep の出力が一切作られなくなる（旧は早期 grep の TSV だけは残っていた）。差し引きで「個別 grep の例外は残りに巻き込まない」方が運用上良いと判断した。これは挙動変更の明示項目として実装計画にも記録する。

---

## テスト戦略

`feedback_test_style.md` / `feedback_tdd_stance.md` 準拠。WHAT 検証、日本語メソッド名、古典学派、Red → Green → Refactor。

### E-1: encoding キャッシュ

新規 `tests/test_encoding.py`。

ブラックボックス:

- `def test_同じパスを2回呼ぶとファイル変更後も古い結果が返る`: tmp_path に cp932 由来バイト列のファイル → `detect_encoding` 呼び出し → 中身を utf-8 由来バイト列に上書き → 再度呼んでも 1 回目と同じ結果が返る（キャッシュ効果の観察可能事実）
- `def test_override指定時はキャッシュを使わずそのまま返す`: 同じパスに override="utf-8" → 結果 utf-8、その後 override=None → ファイル本来のエンコーディング
- `def test_存在しないパスでもcp932にフォールバックする`: 既存挙動の維持確認
- `def test_クリア関数を呼ぶとキャッシュが空になる`: `_encoding_cache_clear()` の存在と動作

### E-2: 集約バッチ間接追跡

`tests/test_pipeline_run.py` に追加。

ブラックボックス（出力等価性）:

- `def test_複数grepを集約処理しても旧経路と同じTSVが出力される`: 2 つ以上の `.grep` を含む input dir。新 `run_full_pipeline` で出力した TSV 群と、旧経路（grep 単独で 1 本ずつ処理）で出した TSV 群を行単位で完全一致比較（要件 §2 / §V-1 に整合）
- `def test_1つのgrepが壊れていても他のgrepのTSVは出力される`: 1 つの grep を不正フォーマットに → 残りの TSV ファイルは存在し中身が正しい

ホワイトボックス補完（中核性能改善の観察、許容範囲内）:

- `def test_間接追跡はハンドラ毎に1回しか呼ばれない`: ダミーハンドラを差し込み、`batch_track_indirect` の呼び出し回数を観察。grep ファイル数 N に関わらず呼び出しがハンドラ数（テストでは 1）であることを確認

### E-3: mmap フォールバック

新規 `tests/test_source_files.py`。

ブラックボックス（`_read_based_find` 単体）:

- `def test_パターンが先頭で見つかる`
- `def test_パターンが末尾で見つかる`
- `def test_パターンがチャンク境界をまたいでも見つかる`: チャンクサイズを小さく設定 → 境界を越える位置にパターン配置 → 検出される
- `def test_複数パターンのいずれか1つでもヒットすればtrue`
- `def test_空ファイルではfalse`

積分（`grep_filter_files`）:

- `def test_use_mmap_TrueとFalseで結果ファイル集合が一致する`
- `def test_no_mmapフラグはCLI環境変数経由で有効化できる`: dispatcher の引数解析だけ観察

### C-1: ruff py37 ガード

pytest 範囲外。実装計画のチェックリスト項目として「`ruff check grep_helper/ analyze_*.py` がエラーゼロで通る」ことを確認する。CI 自動化は本タスクでは入れない。

### 既存テストへの影響

`test_pipeline_run.py`、`test_all_analyzer.py`、`test_analyze.py` の中で「1 grep ファイル処理直後の中間状態」を観察しているテストがあれば、間接追跡が「全 grep の処理後」に走るタイミング変更で挙動が変わる。実装計画段階で 1 本ずつ確認し、HOW を観察しているテストがあれば WHAT 観察に書き換える。

TSV の最終内容は要件 §2 で完全一致が要求されているので、出力比較系のテストは無変更で通る前提。

---

## 検証 (V-1: KPI before/after)

実装計画のクロージング条件として以下を行う:

```bash
# before（main ブランチ）
$ python scripts/measure_kpi.py --lang all > /tmp/kpi_before.txt
$ time python analyze_all.py --source-dir tests/golden/<lang> \
    --input-dir tests/golden/<lang>/inputs \
    --output-dir /tmp/before/ 2>&1 | tee /tmp/time_before.txt

# after（feature ブランチ）
$ python scripts/measure_kpi.py --lang all > /tmp/kpi_after.txt
$ time python analyze_all.py --source-dir tests/golden/<lang> \
    --input-dir tests/golden/<lang>/inputs \
    --output-dir /tmp/after/ 2>&1 | tee /tmp/time_after.txt
```

クロージング条件:

- `kpi_before.txt` と `kpi_after.txt` の網羅率・分類精度が同一
- 出力 TSV の中身が行単位で同一（`diff -r /tmp/before/ /tmp/after/` が空）
- `time_after` の wall clock が `time_before` と同等以上（speedup 数値を spec のクロージングノートに追記）

---

## 後方互換と移行

- ハンドラ層 `classify_usage` は無変更
- ハンドラ層 `batch_track_indirect` は新キーワード引数 `use_mmap=True` の追加のみ。既存呼び出しコード（`scripts/measure_kpi.py` 含む）はキーワード引数を渡さなければ旧挙動と等価
- `pipeline.run_full_pipeline` の戻り値型・出力 TSV の中身は完全互換
- `dispatcher.main` の終了コード仕様は維持（直接フェーズの個別 grep 失敗は警告に降格、間接フェーズ失敗は引き続き中断）

---

## 実装順序（writing-plans 用ヒント）

writing-plans 段階で以下の順序を提案する:

1. C-1 ガード設置（`pyproject.toml` + `ruff check` ベースライン）— 以後の差分が混入しないよう先に置く
2. E-1 encoding キャッシュ（独立、TDD で実装）
3. E-3 `_read_based_find` 単体（独立、TDD で実装）
4. E-3 `grep_filter_files(use_mmap=...)` 積分 + 各ハンドラへの `use_mmap` 引数伝播
5. E-2 dispatcher / pipeline の 3 フェーズ化（既存テストへの影響を見ながら段階的に）
6. CLI フラグ + 環境変数（`analyze_all.py` の引数追加）
7. C-2 `scripts/smoke_solaris.md` 作成
8. V-1 KPI before/after 計測 + spec 末尾に数値追記
