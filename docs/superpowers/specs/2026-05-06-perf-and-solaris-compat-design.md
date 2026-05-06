# パフォーマンス改善 + Solaris 10 互換 設計書

**日付**: 2026-05-06
**対象ファイル**（テスト追加分も含む完全リスト）:

本体:

- `grep_helper/encoding.py`（変更）
- `grep_helper/source_files.py`（変更）
- `grep_helper/dispatcher.py`（変更）
- `grep_helper/pipeline.py`（変更）
- `grep_helper/languages/*.py`（対象ハンドラ全体: `batch_track_indirect` のキーワード引数追加）
- `analyze_all.py`（CLI フラグ `--no-mmap` 追加）

設定:

- `pyproject.toml`（新規 / ruff 設定）
- `requirements.txt`（Python バージョンコメント追記）
- `requirements-dev.txt`（Python バージョンコメント追記）

ドキュメント:

- `scripts/smoke_solaris.md`（新規）

テスト（§テスト戦略 で詳述）:

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
   - Solaris 用 Python 3.7 build / `pyahocorasick` cp37 wheel 等の**ビルド成果物**を本リポジトリに持つこと（手順は §C-2 `scripts/smoke_solaris.md` に書くが、artifact は持ち込まない）
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

- キャッシュキーは `str(path)` のみ。`override` は早期 return 済みなのでキーから除外する。`Path.resolve()` 等での正規化はしない（NFS で `realpath` 解決のコストが効くため）。同一ファイルへ相対パス・絶対パスで届く経路があると 2 エントリ持つことになるが、実害はキャッシュヒット率が下がるだけで、`source_files._resolve_file_cache` も同じ流儀。
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

- ハンドラ層 `batch_track_indirect` のシグネチャは維持。既存実装は `direct_records` 内の各 `record.keyword` を間接追跡レコードに引き継いでいるため、複数 keyword 分の direct を 1 回で渡しても元の 1 keyword ずつ呼んだ場合と**同じ結果リスト**（要素・順序）が keyword 毎に得られる。
- 振り分けは戻り値の `record.keyword` で行う。`keyword` が未設定の record は仕様外として捨てる（現コードでは発生しないが防御的に）。
- 進捗ログ:
  - フェーズ 1: 既存通り「処理中: foo.grep」を grep ファイル毎に出す。
  - フェーズ 2: 既存の `_batch_track_combined` 内の「Java 追跡(統合): N ファイル中 M 完了」相当を全体 1 系列で残す。
- `ProcessStats` は全 keyword で 1 個共有（フェーズ 1 で `total_lines` `valid_lines` `skipped_lines` が積算され、フェーズ 2 で `encoding_errors` `fallback_files` が積算される）。プロセス終端で 1 回サマリ出力。`grep_helper/dispatcher.main` の現行終端出力（`print(f"処理ファイル: ...")` 等の単純 print）は既存維持。`grep_helper/languages/java.print_report` 形式の詳細レポートを呼ぶ責務は本タスクで dispatcher 側には持ち込まない。
- 集約キーは `grep_path.stem`。`run_full_pipeline` / `dispatcher.main` は単一 `input_dir` から `*.grep` を取るため stem 衝突は仕様上発生しない（複数 input dir をマージして渡すユースケースは要件外）。

#### 順序保証の根拠（TSV バイト一致のため）

要件 §2 の「行単位完全一致」を満たすには、新経路で生成される `<keyword>.tsv` の中身が旧経路と**バイト単位**で同じである必要がある。直接フェーズの順序は無変更なので、間接フェーズの per-keyword 順序が維持されることを以下 4 点で示す:

1. **ファイル走査順序**: `grep_helper/source_files.iter_source_files` は `sorted(...)` で結果を返す。新旧で同じ source_dir に対し同じ順序のファイルリストが得られる。
2. **行内マッチ順序**: `grep_helper/scanner._BatchScanner.findall` は regex バックエンドで `re.finditer`、Aho-Corasick バックエンドで `iter` の position 順に yield。どちらも左→右で決定的。
3. **同名 var の origins ループ**: `_batch_track_combined` 内 `for origin in origins` の順序は、旧では 1 keyword 分の direct から構築された `tasks[name]` のみで origins が単一だった。新では複数 keyword 分の direct から構築されるため `origins = [keyword_A_origin, keyword_B_origin, ...]` と並ぶ。各 origin から生成される record は `record.keyword = origin.keyword` で振り分けられるため、後段の per-keyword リストには **同じ位置に同じ record** が入る（origin の挿入順は keyword 内では旧と同じ）。
4. **同 var が複数 keyword の direct から登場するケース**: 同一 const を 2 つの grep が拾った場合、旧では keyword A 単独・B 単独でそれぞれ「ソース全件を走査して該当行を発見」していた。新ではソース全件を 1 回走査し、各該当行から keyword A 用・B 用の record を 2 つ生成する。生成順は origins ループ順だが、後段の振り分けで A.tsv には keyword A の record だけが旧と同じ順序で並ぶ。

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

- API 契約: `patterns` は**非空**を前提（呼び出し元 `grep_filter_files` で空 patterns は早期 return 済み）。空 patterns で呼ばれた場合の挙動は未定義（`max(len(p) for p in patterns)` で `ValueError`）。ユニットテストもこの契約に従う。
- ファイルを 1 MB チャンクで `read()` しつつ `bytes.find` で検索。
- **prepend 方式**で境界またぎを防止する: 前チャンク末尾 `max(len(p) for p in patterns) - 1` バイトを保持し、次チャンクの先頭に貼り付けてから `find` を実行する。`seek` は使わない（NFS の `seek + read` でキャッシュ整合が崩れる事例があるため）。
- パターン長 1 の場合 overlap=0 となるが、1 バイトパターンは「境界またぎ」自体が概念上発生しないので結果は正しい。
- メモリ上限はチャンク 1 MB + オーバーラップで O(1)。

CLI 側:

- `grep_helper/dispatcher.build_parser` に `--no-mmap` を追加（`store_true`、デフォルト False）
- 環境変数 `GREP_HELPER_NO_MMAP=1` でも有効化（運用ラッパーから設定しやすくする）
- 優先順: CLI フラグ明示時はそれを採用、CLI 未指定（=デフォルト False）時のみ環境変数を参照、両方無ければデフォルト `use_mmap=True`

```python
# dispatcher.main の擬似コード
no_mmap = args.no_mmap or os.environ.get("GREP_HELPER_NO_MMAP") == "1"
use_mmap = not no_mmap
```

`store_true` は CLI で True/False を区別できないので、「明示的に `--use-mmap` で env を上書きする」要件が将来出たら再設計する（本タスクでは不要）。

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
select = ["E", "F", "UP", "FA"]
# UP: pyupgrade — py37 ターゲットで walrus / pos-only / match/case 等を検出
# FA: flake8-future-annotations — `from __future__ import annotations` を強制
```

#### ruff py37 ガードの守備範囲

`target-version = "py37"` で確実に検出できるのは以下:

- 構文レベル: walrus `:=`, pos-only `/`, `match/case`, `*` 単独引数（3.8+）
- ランタイム呼び出し: `functools.cache`（3.9+）等の API 利用箇所

検出**できない**もの（注意点）:

- `from __future__ import annotations` 配下の PEP 604 (`X | None`) / PEP 585 (`dict[...]`) は string annotation として扱われるため、ruff py37 ターゲットでも基本的にスルーされる。実害は新規ファイルで `from __future__ import annotations` を入れ忘れたときに発生する（モジュールトップレベルの型注釈が即時評価されて 3.7 で `TypeError`）。これを守るため `FA` ルール（flake8-future-annotations）を併用し、PEP 604/585 を含むファイルでの import 強制を担保する。
- `typing.get_type_hints()` のように annotation を文字列→オブジェクトに評価する API を新たに使い始めた場合は ruff では検出できない。この種のリスクは導入時に手動レビューで弾く。

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

`scripts/smoke_solaris.md`（新規）に運用側向けの手順を記録する。コピペで動くレベルにするため、Solaris 10 同梱の Studio cc では Python 3.7 のビルドが通りにくい点・OpenSSL/zlib/libffi が不在だと `pip install` が即死する点を前提に書く。

```
0. 前提パッケージ（OpenCSW から導入）
   $ /opt/csw/bin/pkgutil -y -i gcc4core gcc4g++ libssl_dev zlib_dev libffi_dev \
                                gnumake coreutils

1. Python 3.7.17 ビルド
   - Solaris 10 同梱の cc (Studio) は Python 3.7 setup.py の前提から外れるため、
     OpenCSW の gcc を使う
   - --with-openssl で OpenCSW の OpenSSL を指定しないと ssl module が無効化され、
     pip の TLS 接続が失敗する
   $ tar xzf Python-3.7.17.tgz && cd Python-3.7.17
   $ CC=/opt/csw/bin/gcc \
     CFLAGS="-I/opt/csw/include" \
     LDFLAGS="-L/opt/csw/lib -R/opt/csw/lib" \
     ./configure --prefix=$HOME/py37 --enable-shared \
                 --with-openssl=/opt/csw \
                 --with-system-ffi
   $ gmake -j4 && gmake install

2. venv 作成
   $ $HOME/py37/bin/python3 -m venv $HOME/grep_helper_venv
   $ source $HOME/grep_helper_venv/bin/activate
   $ pip install --upgrade pip   # SSL が通れば成功

3. 依存インストール（cp312 wheel は Solaris で使えないため source build）
   $ pip install --no-binary=:all: chardet javalang
   # pyahocorasick の C 拡張は Solaris 10 の libc で通らない場合がある。
   # 失敗しても run-time には grep_helper/_aho_corasick.py の pure Python
   # フォールバックがあるので、|| true で無視して構わない。
   $ pip install --no-binary=:all: pyahocorasick || true

4. ulimit 引き上げ（--workers >= 2 を使う場合）
   $ ulimit -n 1024     # ユーザ shell の soft limit
   # それ以上必要なら hard limit (デフォルト 65536) まで上げられる:
   $ ulimit -n 4096
   # zone 内で hard limit が 256 のままに見える場合は projmod / /etc/system の
   #   set rlim_fd_cur = 4096
   # で root 側調整が必要

5. スモーク実行
   $ python analyze_all.py --source-dir <path> \
       --input-dir input --output-dir output --no-mmap

6. 既知の制約・確認ポイント
   - Solaris + NFS では --no-mmap または GREP_HELPER_NO_MMAP=1 を推奨
     （NFS の stat キャッシュ古値で `mmap` 後に EOF を超えるエラーが出る事例あり）
   - 実機の zone 内では os.cpu_count() が物理 CPU を返し psrinfo の制限を無視する
     ので、--workers は明示指定する
   - シンボリックリンクループ（/proc 参照や NFS 自己参照）を踏むと
     Python 3.7 の pathlib.rglob は RecursionError を出す。
     iter_source_files の入力 source_dir に怪しいリンクが無いことを事前に確認
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

性能改善の中核（「間接追跡が grep 数 N ではなくハンドラ数に比例する」）はテストでは直接観察せず、要件 §2 の TSV 完全一致 + §V-1 の wall clock 計測で実質保証する。「内部関数 X が何回呼ばれた」式のテストは `feedback_test_style.md` の方針上書かない。

### E-3: mmap フォールバック

新規 `tests/test_source_files.py`。

ブラックボックス（`_read_based_find` 単体）:

- `def test_パターンが先頭で見つかる`
- `def test_パターンが末尾で見つかる`
- `def test_パターンがチャンク境界をまたいでも見つかる`: チャンクサイズを小さく設定 → 境界を越える位置にパターン配置 → 検出される
- `def test_複数パターンのいずれか1つでもヒットすればtrue`
- `def test_空ファイルではfalse`

積分（`grep_filter_files`）:

- `def test_use_mmap_TrueとFalseで結果ファイルリストが一致する`: `grep_filter_files` は順序保証つき関数なので、リスト（順序込み）で比較する
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
- `dispatcher.apply_indirect_tracking` も `*, use_mmap=True` のキーワード専用引数追加のみで互換。既存テスト（`tests/test_all_analyzer.py` 内のラッパ経由呼び出し含む）はそのまま動く
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

### Solaris 実機で実装前に確認すべき項目（writing-plans のリスク欄に転記）

本タスクの開発は dev container (Linux + Python 3.12) で進めるが、出荷前に以下を Solaris 10 + Python 3.7 実機で確認する:

- `scripts/smoke_solaris.md` の Python ビルド手順を実機で 1 回流す（OpenSSL/libffi/zlib リンクが通るか、`pip install` が SSL で詰まらないか）
- `pyahocorasick` の C 拡張ビルドが失敗しても `_aho_corasick.py` の pure Python フォールバックが正しく `import` されるか（`grep_helper/scanner.py` の try/except 経路）
- `iter_source_files` の入力に **シンボリックリンクループ** を含めても `pathlib.rglob` で `RecursionError` が出ないか（出るなら Python 3.7 では `os.walk(followlinks=False)` ベースに切り替えるか、入力前に確認をかける運用にする）
- `os.cpu_count()` が zone 内で物理 CPU 数を返すケースがあるので、`--workers` のデフォルト値が無指定で過大にならないか（現実装は `default=1` で `os.cpu_count()` をヘルプ文言にしか使っていないので問題なし、と確認だけする）
- NFS 上で `mmap` が初回失敗 → `_read_based_find` に落ちる経路が実機で実行されることのスモーク（`--no-mmap` 無しで動かして、ハングせず完了するか）
- `analyze_*.py` の shebang が `#!/usr/bin/env python3` で venv 内 python3 が PATH に通っている前提で動くか（直接 `python analyze_all.py` で起動するなら shebang は無関係）

---

## クロージングノート（2026-05-06 計測）

### TSV / KPI 同等性

- `diff -r` の `.tsv` 比較（12 言語の golden set 全 16 ファイル）: **完全一致**（0 differences, before/after 各 16 TSV）
- `diff /tmp/kpi_before.txt /tmp/kpi_after.txt`: **メトリクスは完全一致**。差分は (1) レポート出力先のタイムスタンプ部分（`123928` vs `123904`）と (2) 間接追跡フェーズのログ行のみ。網羅率・分類精度の数値（`網羅率: N/N (100.0%) [OK]` 行）は `diff` で 0 件。ログ差は Task 5 の `batch_track_indirect` 集約で per-file ループ → バッチ呼び出しに切り替わったための表示変化（C / Pro*C / Kotlin で「参照 1 件発見 × 2 回」が「参照 2 件発見 × 1 回」になった等）であり、TSV が完全一致であることから網羅率に対しては no-op。

要件 §2 「網羅率維持」と §V-1 「`diff -r` 完全一致」のクロージング条件を **満たす**。

### 速度比較（dev container, Python 3.12, tests/golden/）

| 言語 | before (real) | after (real) |
|---|---|---|
| java | 0m0.762s | 0m0.506s |
| c | 0m0.251s | 0m0.252s |
| proc | 0m0.277s | 0m0.243s |
| sql | 0m0.259s | 0m0.238s |
| sh | 0m0.250s | 0m0.238s |
| kotlin | 0m0.239s | 0m0.236s |
| plsql | 0m0.235s | 0m0.243s |
| ts | 0m0.245s | 0m0.244s |
| python | 0m0.236s | 0m0.233s |
| perl | 0m0.246s | 0m0.248s |
| dotnet | 0m0.320s | 0m0.239s |
| groovy | 0m0.353s | 0m0.251s |

合計 wall clock: before 3.673s / after 3.171s（-13.7%、-0.502s）。java / dotnet / groovy では実測で改善が確認でき、他言語は ±数 ms の測定ノイズ範囲。

dev container 上の golden set は規模が小さく、改造の効果（encoding cache hit、間接追跡集約による N→1 圧縮）はほぼ可視化されない。本タスクの主目的「網羅率を落とさず重複作業を削った」は TSV/KPI 完全一致で達成されている。**真のスループット改善は出荷先の 60GB 級ソースで再計測する別タスク**で扱う（KPI 設計書 §E-性能・スケール 4 項目目「60GB 級ソースでのプロファイリング」と整合）。

### 残課題

- Solaris 10 実機でのスモークは出荷前に `scripts/smoke_solaris.md` の手順で実施。
- 60GB 級ソースでの本番計測 / 第 1 段階並列化 / 増分処理 / AST キャッシュ永続化 は別 spec で扱う。
- `tests/test_all_analyzer.py` には `tests/` ディレクトリ全体をスコープから外したことに伴う pre-existing ruff 警告（E401/F401/FA102/E741）が残っている。Task 1 の C-1 ガードは `grep_helper/ analyze_*.py` のみが対象なのでブロッカーではないが、テスト側の追従は別タスクで。
