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

### パターン B：キャッシュ容量 peek → 退避後の再読込で観察

```python
# Before（HOW: dict のサイズで判定）
self.assertLessEqual(len(_file_lines_cache), 3)

# After（WHAT: 上限超過後、古いファイルは再読込される）
old = p / "f0.txt"; old.write_text("X" * 50)
cached_file_lines(old, "utf-8")
for i in range(1, 5):  # 上限超過させる
    f = p / f"f{i}.txt"; f.write_text("X" * 50)
    cached_file_lines(f, "utf-8")
old.write_text("CHANGED")
self.assertEqual(cached_file_lines(old, "utf-8"), ["CHANGED"])  # 再読込された
```

適用対象：`test_合計サイズが上限超過で古いものを破棄する`。

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

「メモリに全行ロードしない」という性能契約を守りたい場合のみ、ホワイトボックス側に 1 本書く。基本は型 assertion を**消す**。

### パターン F（横串）：メソッドの docstring を削除

書き直したテストでは原則 docstring を書かない。残すのは前提条件や WHY が非自明な場合のみ。

## ホワイトボックス隔離の規約

- **同一ファイル末尾**に `class Test{対象}Whitebox(unittest.TestCase):` を切る
- **クラス docstring** で「これは実装契約のテスト。リファクタ時に同期更新が必要」と明記
- メソッド docstring は他のテスト同様、原則書かない
- 別ファイル化・別ディレクトリ化は行わない（局所性を優先）

## パイロット内の実行順序（`test_common.py`）

各ステップ後に `python -m unittest tests.test_common -v` をグリーンに保つ。

1. **既存テストの WHAT 契約をクラスごとに棚卸し**（一覧化、削除/書き直し/移送 の 3 ラベル付け）
2. **パターン F（docstring 削除）を一括適用** — メカニカル変更、レビュー軽量
3. **パターン A・B（キャッシュ peek → 振る舞い検証）の書き直し**
4. **パターン E（型 assertion 削除）の書き直し**
5. **パターン C・D（隔離対象）を `class Test...Whitebox` に移送**
6. **ホワイトボックス点検**：書き直し後のテスト群を実装と突き合わせ、明らかに不足している分岐があれば**実装を知らないつもりで**ブラックボックス的にケースを足す。ただし追加したケースが内部リファクタで容易に壊れる形にしかならないなら、原則 6 に従い追加を諦めるか、ホワイトボックス隔離側に書く

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
5. パイロット完了時、`tests/` 全体を 1 度だけ実行してリグレッションがないことを確認

ミューテーションテスト等の機械的検証は今回はやらない（YAGNI）。やるなら別タスクで。

## スイープ順序（パイロット完了後）

ファイルごとの HOW スメル密度で優先順位を決める：

| 順 | ファイル | 主な HOW スメル | 行数 |
|---|---|---|---|
| 1 | `test_analyze.py` | `_ast_cache` peek、`_search_in_lines`/`_get_method_scope`/`_batch_track_*` の private helper 直接ユニットテスト、`patch("sys.argv"...)`、`patch("sys.stdout"...)` | 1771 |
| 2 | `test_analyze_proc.py` | `_define_map_cache` peek、private helper のユニットテスト | 430 |
| 3 | `test_all_analyzer.py` | dispatcher 内部の `inspect` でシグネチャ検証している箇所（あれば）、その他軽微 | 472 |
| 4 | `test_aho_corasick.py` および `test_*_analyzer.py`（言語別） | 既にほぼ WHAT。ざっと点検し docstring 削除 | 各 < 200 |

各ファイルでパイロットの 6 ステップを繰り返す。スイープは個別 PR／個別コミット。

## 終状態（このリファクタ完了時）

- 全テストファイルでメソッド名は日本語、docstring は原則なし
- 公開 API・E2E 出力ベースの WHAT 検証が主体
- 真にホワイトボックスなテストは `Test...Whitebox` クラスに隔離されラベリングされている
- 内部リファクタ（private helper の名前変更、cache 実装の差し替え、backend 選択ロジック変更）でも、ホワイトボックス隔離クラス以外は壊れない
- ガイドラインドキュメントに 5 パターンと隔離規約が成文化されている

## 想定リスクと緩和

| リスク | 緩和策 |
|---|---|
| 書き直しで WHAT 契約が暗黙に弱くなる | コミットごとに「元のテストが捕まえていたバグを新テストも捕まえるか」をメッセージに記す |
| `_ast_cache` 等の peek を全部 behavioral に翻訳できないケースが出る | パターン D の判定基準（タイミングが必要・観察対象が曖昧）に該当すればホワイトボックス隔離を許容 |
| パイロットで決めたパターンが他ファイルに合わない | スイープ第一弾（`test_analyze.py`）で違和感が出たら設計に戻る。ガイドラインは「成長するもの」とする |
| パイロット中に production バグが見つかる | テスト見直しは止めず、別 PR で扱う旨をコミットメッセージに残す |
