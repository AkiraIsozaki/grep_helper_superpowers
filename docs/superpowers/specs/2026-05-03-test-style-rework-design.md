# テスト書き換え方針 — WHAT 検証への移行

## 目的

既存テスト群を「WHAT を検証する古典派テスト」へ移行する。最終ゴールは全テストが「良いテスト」と呼べる状態。パイロット（`tests/test_common.py`）でパターン集を確立し、それを根拠に他ファイルへ展開する。

## 背景・動機

既存テスト群は概ね以下の状態：

- メソッド名はほぼ全て日本語化済み
- 多くの分類テスト・E2E テストは入力 → 出力ベースで WHAT を検証している
- ゴールデン TSV 比較は WHAT 検証の典型例

一方で、以下の HOW スメルが散見される：

- 内部キャッシュ dict の直接 peek（`_ast_cache`, `_file_lines_cache`, `_define_map_cache`）
- バックエンド実装の選択を `scanner.backend == "ahocorasick"` のように検証
- アンダースコア付き private helper を直接ユニットテストする塊（`_get_method_scope`, `_search_in_lines`, `_batch_track_setters` など）
- `Path.read_bytes` や `open` を patch して「呼ばれない／4KB しか読まない」を verify するロンドン学派的なインタラクションテスト
- `assertIsInstance(it, types.GeneratorType)` のような型 instance 検証

これらは内部リファクタで容易に壊れる。古典派 TDD の立場ではテストの変更耐性を犠牲にしている。

## スコープ

### 対象

- `tests/` 配下のテストファイル群
- 第一弾（パイロット）：`tests/test_common.py`
- 第二弾以降（スイープ）：`test_analyze.py` → `test_analyze_proc.py` → `test_all_analyzer.py` → 言語別 analyzer テスト群

### 非目標

- 新機能の追加（あくまでテスト群のスタイル統一）
- production code（`grep_helper/`）の変更（テスト見直し中にバグが見つかった場合は別 PR で扱う）
- E2E ゴールデン TSV の差し替え（既に WHAT 検証になっているため温存）
- カバレッジを増やすこと自体（ただしホワイトボックス点検段階で穴が見えれば埋める）
- ミューテーションテスト等の機械的等価検証

## 原則

このリファクタを律する 6 原則：

1. **WHAT 検証**：公開された関数・型・出力を経由して、入出力を比較する。private 関数や内部 dict の peek は WHAT に翻訳できる場合は必ず翻訳する
2. **古典派**：実物のオブジェクトを使う。モックは「ファイルシステム書き換え」のような実物が用意できない場合のみ
3. **ブラックボックス先行 → ホワイトボックス点検**：まずブラックボックスでケースを書く。その後「if 分岐や条件のうち振る舞いに現れていないもの」を点検し、不足があれば**実装を知らないつもりで**ブラックボックス的にケースを足す
4. **ホワイトボックス隔離**：振る舞いに翻訳できないもの（純粋な性能・効率契約）は同一ファイル末尾の `class Test...Whitebox` に隔離し、クラス docstring で「リファクタ時に同期更新が必要」と明示する
5. **テストメソッド名は日本語で WHAT を 1 行で表現する**。**メソッドの docstring は原則書かない**（メソッド名が WHAT を語っているなら冗長）。例外は前提条件・既知のバグ番号・WHY が非自明な場合。**クラスの docstring は残す**（特にホワイトボックス隔離クラスでは「リファクタ時に同期更新が必要」というシグナルそのもの）
6. **テスト変更耐性を犠牲にしない**：内部リファクタだけで壊れるテストは原則書かない

## HOW スメル別の翻訳パターン

### パターン A：キャッシュ存在 peek → ソース改変による振る舞い検証

```python
# Before（HOW: 内部 dict を直接覗く）
cached_file_lines(p, "utf-8")
self.assertIn(str(p), _file_lines_cache)

# After（WHAT: ソースを書き換えても古い値が返る＝キャッシュが効いている）
first = cached_file_lines(p, "utf-8")
p.write_text("DIFFERENT\n", encoding="utf-8")
second = cached_file_lines(p, "utf-8")
self.assertEqual(first, second)
```

適用対象：`test_サイズ上限内ならキャッシュされる`、`test_解決結果がキャッシュされる`（後者は既に近い形）。

**注記**：本パターンは「キャッシュは自動無効化しない（mtime/inode を見ない）」という現状契約に依存する。将来 mtime ベース無効化を導入する場合、契約変更を反映してテストを更新する必要がある。逆に言うと、テストが赤くなれば契約違反が検出される。

### パターン B：キャッシュ容量 peek → 退避後の再読込で観察

```python
# Before（HOW: dict のサイズで判定）
self.assertLessEqual(len(_file_lines_cache), 3)

# After（WHAT: 上限超過後、初期エントリのうち少なくとも 1 つは再読込される）
early = []
for i in range(3):
    f = p / f"early{i}.txt"; f.write_text("X" * 50)
    cached_file_lines(f, "utf-8")
    early.append(f)
for i in range(5):  # 容量上限を確実に超過させる
    f = p / f"later{i}.txt"; f.write_text("X" * 50)
    cached_file_lines(f, "utf-8")
# 初期エントリの中身を書き換え、再読込が起きていることを確認
re_read = []
for f in early:
    f.write_text("CHANGED")
    if cached_file_lines(f, "utf-8") == ["CHANGED"]:
        re_read.append(f)
self.assertGreaterEqual(len(re_read), 1)  # 退避ポリシーは問わない
```

適用対象：`test_合計サイズが上限超過で古いものを破棄する`。

**注記**：「どれが追い出されるか」は LRU/FIFO/LFU 等の退避ポリシーに依存する。原則 6（変更耐性）を守るため、本パターンは**特定エントリの追い出し**ではなく**少なくとも 1 つは追い出される**ことを WHAT として観察する。退避ポリシーの具体は実装詳細としてホワイトボックス側で別途固定したい場合のみテストする。

### パターン C：バックエンド選択 → 削除＋ホワイトボックス 1 本に集約

`TestBatchScannerSelector` の 3 テストを以下のように扱う：

- `test_findallが単語境界でマッチする` → 純粋な WHAT。**残す**（むしろ強化：1〜数百パターンの代表点で同一の振る舞いを確認）
- `test_パターン数が多いとAhoCorasickを選ぶ` / `test_パターン数が少ないとregexを選ぶ` → 内部最適化の選択。振る舞いとしては「両方とも同じマッチ結果を返す」だけ。**ホワイトボックス隔離**して 1 クラスにまとめる（性能劣化の早期検知用）

### パターン D：モック・インタラクション検証 → ホワイトボックス隔離

```python
# Before（HOW: read_bytes が呼ばれないことをモックで検証）
with patch.object(Path, "read_bytes", boom):
    enc = detect_encoding(p)
```

振る舞いに翻訳できるかを検討した結果：

- 「100MB ファイルでも 1 秒以内に返る」→ タイミングテストはフレーキー。NG
- 「先頭 4KB だけで判定したエンコーディングと全体読みのエンコーディングが一致」→ 同値だが間接的すぎ、観察対象が曖昧

→ 翻訳を諦め、ホワイトボックス隔離する。

`test_read_bytesを呼ばない` と `test_最大4KBまでしか読まない` は **`TestDetectEncodingStreamingWhitebox`** に移し、クラス docstring で「`detect_encoding` が先頭 4KB のみ読む実装契約をテストする。実装変更時に同期更新が必要」と明記。

### パターン E：型 instance 検証 → 観察可能な振る舞いだけ残す

```python
# Before（HOW: ジェネレータ型であることを検証）
self.assertIsInstance(it, types.GeneratorType)
self.assertEqual(list(it), ["a:1:foo", "b:2:bar"])

# After（WHAT: 行順に取り出せる。ジェネレータかどうかは実装詳細）
self.assertEqual(list(iter_grep_lines(p, "utf-8")), ["a:1:foo", "b:2:bar"])
```

ただし `iter_grep_lines` という関数名は「ストリーミング処理する」ことを公開契約として示している。型 assertion を単純に消すと、名前と振る舞いの乖離が検出されなくなる。

そこで以下の二段構えとする：
- **ブラックボックス側**：「行順に取り出せる」WHAT を `assertEqual(list(...), [...])` で検証する（型 assertion は消す）。加えて「**先頭 N 行だけ消費して break しても全行を読まない**」型の smoke test を 1 本残す。これは大きな入力（数十 MB 相当を `tempfile` で生成）で、`itertools.islice` で先頭数行だけ消費し、関数が **timeout なく返ってくる**ことを assert する。タイミング閾値は緩く（数秒）取り、フレーキーを回避する
- **ホワイトボックス側**（必要なら）：実装契約「全行を一度に list 化していないこと」を patch ベースで verify する 1 本。基本はブラックボックス側だけで足りるはず

### パターン F（横串）：メソッドの docstring を削除

書き直したテストでは原則 docstring を書かない。残すのは前提条件や WHY が非自明な場合のみ。

### パターン G：private helper 直接ユニットテスト → 公開 API 経由、または E2E カバーで削除

```python
# Before（HOW: アンダースコア付き private helper を直接呼ぶ）
class TestSearchInLines(unittest.TestCase):
    def test_変数名を含む行がGrepRecordとして返る(self):
        records = _search_in_lines(lines=..., var_name=..., start_line=..., ...)
        self.assertEqual(len(records), 1)
```

選択肢：
- **a) 公開 API 経由に持ち上げる**：`track_constant` / `track_field` などの上位公開関数を呼び、同じ入力空間の代表点を**経由的に**検証する。private helper の細かい引数アリティから解放される
- **b) E2E でカバーされていれば削除**：`tests/fixtures/` の E2E 比較がその分岐を踏んでいるなら、private helper の直接ユニットテストは冗長として削除する
- **c) ホワイトボックス側に隔離**：a) も b) も難しい場合のみ、`Test...Whitebox` クラスに移して「内部 API のテスト」と明示

判定の優先順は **b → a → c**。E2E カバーの有無は `coverage.py` 等で機械的に確認するのではなく、フィクスチャを読んで該当パスを踏むかを目視で判断する（YAGNI）。

適用対象（スイープ第一弾）：`test_analyze.py:688-806` 周辺の `TestGetMethodScope`、`TestSearchInLines`、`TestBatchTrackSetters`、`TestBatchTrackOnePass`。これらは `_get_method_scope`、`_search_in_lines`、`_batch_track_setters`、`_batch_track_combined` を直接テストしており、リファクタ脆性が高い。

## ホワイトボックス隔離の規約

- **同一ファイル末尾**に `class Test{対象}Whitebox(unittest.TestCase):` を切る
- **クラス docstring** で「これは実装契約のテスト。リファクタ時に同期更新が必要」と明記
- メソッド docstring は他のテスト同様、原則書かない
- 別ファイル化・別ディレクトリ化は行わない（局所性を優先）
- **インタラクション検証（モックで「呼ばれた／呼ばれない」「読み取りバイト数」等を verify する形）は本クラス内に限り許容**する。本クラス外で `unittest.mock.patch` を使った interaction 検証を書かない（boundary としてのモック — `sys.stdout` キャプチャ等 — は別。これは出力という観察可能な振る舞いの取得手段にすぎない）

なお、**ホワイトボックス隔離クラス以外**のテストクラスについては、**クラス docstring も任意**とする（メソッド docstring と同じ原則）。意味のないグルーピング用クラスにまで docstring を強制しない。

## パイロット内の実行順序（`test_common.py`）

各ステップ後に `python -m unittest tests.test_common -v` をグリーンに保つ。

1. **既存テストの WHAT 契約をクラスごとに棚卸し**（一覧化、削除/書き直し/移送 の 3 ラベル付け）
2. **パターン F（docstring 削除）を一括適用** — メカニカル変更、レビュー軽量
3. **パターン A・B（キャッシュ peek → 振る舞い検証）の書き直し**
4. **パターン E（型 assertion 削除）の書き直し**
5. **パターン C・D（隔離対象）を `class Test...Whitebox` に移送**
6. **ホワイトボックス点検**：書き直し後のテスト群を実装と突き合わせ、明らかに不足している分岐があれば**実装を知らないつもりで**ブラックボックス的にケースを足す。ただし追加したケースが内部リファクタで容易に壊れる形にしかならないなら、原則 6 に従い追加を諦めるか、ホワイトボックス隔離側に書く
7. **パターン G の試験翻訳**（スパイク）：`test_analyze.py:688-806` から 1 テスト（例：`TestGetMethodScope` の 1 メソッド）を選び、公開 API 経由 or 削除に変換可能か手で確認する。スイープ第一弾で躓かないための先行検証。試験翻訳は本パイロット PR には含めず、知見のみ spec に追記する（必要なら別途 issue 化）

## TDD ディシプリン（このリファクタにおける適用）

- 既存テストの**書き直し**部分は厳密な意味の TDD ではない（テストを書いてから実装する流れではない）。ただし「rewrite 前後で全テストグリーン」を保つ＝**安全網としての TDD 同等の規律**は維持
- **ステップ 6（不足ケース追加）**にだけ、本来の TDD を適用：
  - 新ケースを書く → 実行 → 落ちるか通るか観察
  - 落ちれば production の問題か、テストの誤りか判別して対処
  - 通れば既存実装が偶然カバーしている。コミットして次へ
- 既存の production code には**触らない**（テスト見直し中にバグが見つかった場合は別 PR で）

## 書き直しの等価性検証

毎回の書き直しで以下を行う：

1. **書き直し前**にテスト単体を実行してグリーン確認
2. 書き直し
3. **書き直し後**にテスト単体を実行してグリーン確認
4. 自問：「元のテストが捕まえていたバグを、新しいテストも捕まえるか？」を 1 行で言語化（コミットメッセージに残す）
5. **手動 mutation スポットチェック**：書き直したテストが対応する production コードの代表的な 1 行（条件分岐・正規表現・キー判定など）を**手で一時コメントアウト**し、新テストが赤くなることを 1 度だけ確認する（赤くならない場合、新テストが WHAT を捕まえていない徴候）。確認後は production を元に戻す
6. パイロット完了時、`tests/` 全体を 1 度だけ実行してリグレッションがないことを確認

ミューテーションテスト等の機械的検証は今回はやらない（YAGNI）。やるなら別タスクで。

## スイープ順序（パイロット完了後）

ファイルごとの HOW スメル密度で優先順位を決める：

| 順 | ファイル | 主な HOW スメル | 行数 |
|---|---|---|---|
| 1 | `test_analyze.py` | `_ast_cache` peek、`_search_in_lines`/`_get_method_scope`/`_batch_track_*` の private helper 直接ユニットテスト、`patch("sys.argv"...)`、`patch("sys.stdout"...)` | 1771 |
| 2 | `test_analyze_proc.py` | `_define_map_cache` peek、private helper のユニットテスト | 430 |
| 3 | `test_all_analyzer.py` | dispatcher 内部の `inspect` でシグネチャ検証している箇所（あれば）、その他軽微 | 472 |
| 4 | `test_aho_corasick.py` および `test_*_analyzer.py`（言語別） | 既にほぼ WHAT。ざっと点検し docstring 削除 | 各 < 200 |

各ファイルでパイロットの 1〜6 ステップを繰り返す（ステップ 7 はパイロット限定の試験翻訳なので不要）。スイープは個別 PR／個別コミット。

## 終状態（このリファクタ完了時）

- 全テストファイルでメソッド名は日本語、docstring は原則なし
- 公開 API・E2E 出力ベースの WHAT 検証が主体
- 真にホワイトボックスなテストは `Test...Whitebox` クラスに隔離されラベリングされている
- 内部リファクタ（private helper の名前変更、cache 実装の差し替え、backend 選択ロジック変更）でも、ホワイトボックス隔離クラス以外は壊れない
- ガイドラインドキュメントに 7 パターン（A〜G）と隔離規約が成文化されている

## 想定リスクと緩和

| リスク | 緩和策 |
|---|---|
| 書き直しで WHAT 契約が暗黙に弱くなる | コミットごとに「元のテストが捕まえていたバグを新テストも捕まえるか」をメッセージに記す。加えてステップ 5 の手動 mutation チェックで該当行コメントアウト時に新テストが赤くなることを 1 度確認する |
| `_ast_cache` 等の peek を全部 behavioral に翻訳できないケースが出る | パターン D の判定基準（タイミングが必要・観察対象が曖昧）に該当すればホワイトボックス隔離を許容 |
| パイロットで決めたパターンが他ファイルに合わない | スイープ第一弾（`test_analyze.py`）で違和感が出たら設計に戻る。ガイドラインは「成長するもの」とする。なおパターン G の試験翻訳をパイロット内で行うことで、第一弾の躓きを前倒しで検出する |
| パイロット中に production バグが見つかる | テスト見直しは止めず、別 PR で扱う旨をコミットメッセージに残す |
| パターン A が将来の mtime/inode ベースのキャッシュ無効化導入を阻害する | パターン A 自体に「自動無効化なし契約」依存である注記を残す。将来契約を変える場合はテスト群を更新する手間が必要なことを受容する |
| パターン B が退避ポリシー変更で壊れる | 「特定エントリの追い出し」ではなく「**少なくとも 1 つは追い出される**」を WHAT として観察するように緩めて記述（パターン B 本文）。ポリシー固定が必要ならホワイトボックス側で扱う |

## パイロットでのスパイク所見（パターン G）

`tests/test_analyze.py:688-720` の `TestGetMethodScope` を試験翻訳した結果：

- **対象**: `test_メソッド内の行番号からスタートとエンドのタプルが返る`（および同クラス内の `test_get_method_scopeは存在しないファイルでNoneを返す` / `test_メソッドより前の行はNoneを返す`）
- **判定**: **b 案（E2E ゴールデンに包摂されているため削除可能）**
- **理由**:
  - `_get_method_scope` は `grep_helper/languages/java_track.py:54` に定義されている private helper。
  - `grep_helper/languages/java_track.py` 内の公開関数 (`track_constant` / `track_field` / `track_local` / `find_getter_names`) は `_get_method_scope` を**直接は呼んでいない**。呼び出しは一段上の orchestrator (`grep_helper/languages/java.py:119`、`:309`) にあり、`scope == "method"` のとき `_get_method_scope` の結果を `track_local` に渡す経路として使われる。
  - したがって「公開 API（`track_local` 等）を直接叩く a 案」は本当の意味では成立せず、`_get_method_scope` の振る舞いを観察する自然な公開境界は **`java.py` 経由の analyze フロー = E2E** になる。
  - E2E ゴールデン `tests/fixtures/expected/SAMPLE.tsv` には `Constants.java` の 9 行目（定数定義）・13 行目（条件判定）・19 行目（return 文）の 3 行が登録されている。試験翻訳対象の `lineno=13` の振る舞い（メソッド内部行 → `(start, end)` を返す）はこの「条件判定」行で踏まれ、9 行目と 19 行目もメソッド境界を含む同じ scope 計算経路に依存している。`_get_method_scope` が誤った値を返せば 3 行いずれかでゴールデン差分が発生する。
  - 「存在しないファイルで `None`」「メソッドより前の行で `None`」という 2 ケースは E2E ゴールデンに直接の対応行を**確認していない**（ヘッダコメント行や不正記録を通る経路は本パイロット内では fixture で実証していない）。defensive な早期 return として他の経路でも踏まれるという推定はあるが根拠は弱い。よってまず b 案で削除し、回帰が出たり「scope=method なのに記録が落ちる」類のバグが現場で発生した場合は c 案（Whitebox 隔離）に 1 ケース戻す方針とする。
- **スイープ第一弾への影響**:
  - `TestGetMethodScope` クラス全体（`tests/test_analyze.py:688-720` の 3 メソッド）は **削除候補**。代替カバレッジは E2E ゴールデン (`SAMPLE.tsv`) と、`_get_method_scope` が `None` を返したときに `track_local` が呼ばれないこと（＝ゴールデン行が増えないこと）で間接観察される。
  - 同ファイルの `_search_in_lines` / `_batch_track_*` 直接ユニットテストも同類の構造（private helper を fixture 直叩き）と想定されるが、各クラス開始時に「公開 API が直接呼ぶか／orchestrator 経由か／E2E に行が出るか」の 3 点を再確認してから a / b / c を判定する。判定根拠を曖昧にしたまま削除しない。
  - 削除前に手動 mutation スポットチェック（パイロット原則ステップ 5）を E2E テスト側に対して 1 度実施する：対象は `_get_method_scope` 末尾の **メソッド検出後の戻り値**（`return start, end` 行）を `return 1, 99999` のように **明らかに過大な範囲**へ歪める。ファイル不在側の早期 `return None` ではなく成功経路を歪めること。ゴールデンが赤くなれば b 案成立。赤くならない場合は (a) E2E が成功経路を踏んでいない（= b 案不成立、c 案へフォールバック）、または (b) 選んだ mutation がたまたま同じ TSV 出力に round-trip した、のいずれかなので、別 mutation も試した上で判定する。
