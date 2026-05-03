# Sweep Wave 1 — test_analyze.py 判定マトリクス

**作成日:** 2026-05-03
**対象:** `tests/test_analyze.py`（パターン F 適用後、26 クラス・99 メソッド、1672 行）
**目的:** Phase 2 プランの入力。各クラスを a/b/c/keep に分類し、Phase 2 で取るアクションを確定する。
**参照:** `docs/superpowers/specs/2026-05-03-test-style-rework-design.md` のパターン定義 + パイロット G スパイク所見。

## 判定の凡例

- **keep** — 既に WHAT 検証として機能している。Phase 2 で触らない（または軽微な命名修正のみ）。
- **a 案** — 公開 API 経由のテストへ統合可能。Phase 2 で書き換え。
- **b 案** — E2E ゴールデンに包摂されており、当該クラス削除で代替可能。Phase 2 で削除（事前 mutation 確認必須）。
- **c 案** — Whitebox 隔離が必要。Phase 2 で `TestXxxWhitebox` クラスへ移送。
- **判定保留** — 情報不足。spec で先に解像度を上げる必要あり（Phase 2 の前段に追加タスクが入る）。

## 調査の前提（共通根拠）

- import 行: `tests/test_analyze.py:17-50`
- E2E ゴールデン (直接参照のみ): `tests/fixtures/expected/SAMPLE.tsv:1-4`
- 重厚 E2E (直接 + 間接 + getter + ソート + CLI): `tests/test_analyze.py:1201-1567` の `TestIntenseE2E` 9 メソッド
- 統合テスト (subprocess + ゴールデン比較): `tests/test_analyze.py:346-409` の `TestIntegration`
- オーケストレータ呼び出し元: `grep_helper/languages/java.py`（直接呼ぶ private は `_resolve_java_file` / `_get_method_scope` / `_batch_track_combined` のみ）
- Public な簡易 track 関数 (`track_constant` / `track_getter_calls` / `track_setter_calls`) は **オーケストレータからは直接呼ばれていない** — `_batch_track_combined` 経由でしか実プロダクションパスは通らない（`grep_helper/languages/java.py:138, 330` のみが呼び出し元）。
- `_batch_track_setters` / `_batch_track_constants` / `_batch_track_getters` (combined 抜きのバッチ) はプロダクションコードからの呼び出しなし、テスト専用の隔離ヘルパー（grep 確認: `grep_helper/languages/java_track.py:711, 776, 842` のみ存在、java.py からは未参照）。

## マトリクス

| # | 行 | クラス | 対象関数（公開度） | 判定 | 根拠（要 file:line） | Phase 2 アクション |
|---|---|---|---|---|---|---|
| 1 | 79 | TestGrepParser | `parse_grep_line` (public, `tests/test_analyze.py:21`) | keep | 公開 API のテスト (`tests/test_analyze.py:79-113`)。assert は dict 値や None など WHAT を観察、内部 dict のキー詰め込み等 implementation peek なし。 | 触らない。 |
| 2 | 120 | TestUsageClassifier | `classify_usage_regex` (public, `tests/test_analyze.py:31`) | keep | 公開 API のテスト (`tests/test_analyze.py:120-155`)。返り値文字列を等値比較するだけの素直な WHAT 観察。 | 触らない。 |
| 3 | 162 | TestTsvWriter | `write_tsv` (public, `tests/test_analyze.py:22`) | keep | 公開 API のテスト (`tests/test_analyze.py:162-239`)。TSV ファイル内容（BOM・ヘッダ・ソート順）を観察、外部 I/O 副作用を WHAT として確認。 | 触らない。 |
| 4 | 246 | TestIndirectTracker | `determine_scope`, `extract_variable_name` (public, `tests/test_analyze.py:32-33`) | keep | 公開 API のテスト (`tests/test_analyze.py:246-295`)。返り値文字列の等値比較、内部状態 peek なし。 | 触らない。 |
| 5 | 302 | TestReporter | `print_report` (public, `tests/test_analyze.py:17`) | keep | 公開 API のテスト (`tests/test_analyze.py:302-339`)。stdout のキャプチャ後 `assertIn` で観察。WHAT 観察として妥当。 | 触らない。 |
| 6 | 346 | TestIntegration | `analyze.py` CLI (subprocess, public) | keep | E2E ゴールデン比較テスト (`tests/test_analyze.py:346-409`)。`tests/fixtures/expected/SAMPLE.tsv` を期待値とした最大粒度の WHAT 観察。 | 触らない。 |
| 7 | 416 | TestProcessGrepFile | `process_grep_file` (public、`tests/test_analyze.py:48` で `_pgf` から alias) | keep | 公開 API のテスト (`tests/test_analyze.py:416-480`)。GrepRecord フィールドと ProcessStats カウンタを観察。WHAT 検証として妥当。 | 触らない。 |
| 8 | 487 | TestGetAst | `get_ast` (public, `tests/test_analyze.py:27`) と `_ast_cache` (private dict) | keep + 軽微な命名修正 | 公開 API のテスト (`tests/test_analyze.py:487-521`)。ただし 4 番目のテスト (`test_存在しないファイルはNoneとしてキャッシュされる`, `tests/test_analyze.py:516-521`) は `_ast_cache` dict を直接 peek しており Whitebox 寄り。残り 3 つは WHAT 観察。 | クラス全体は keep。Phase 2 の任意で `test_存在しないファイルはNoneとしてキャッシュされる` を Whitebox 隔離するかは別途判断（影響軽微）。 |
| 9 | 528 | TestClassifyUsage | `classify_usage` (public ラッパー `tests/test_analyze.py:59-68`、`_java_handler.classify_usage` 経由) | keep | 公開 API のテスト (`tests/test_analyze.py:528-600`)。ProcessStats の `fallback_files` 観察も WHAT として妥当。 | 触らない。 |
| 10 | 607 | TestResolveJavaFile | `_resolve_java_file` (private, `tests/test_analyze.py:36`) | b 案 | 公開 helper でなく `grep_helper/languages/java.py:108, 291` から直接呼ばれるパス解決ロジック。`TestIntenseE2E` (`tests/test_analyze.py:1398-1416` フィールド経路) が source_dir 相対 + 絶対パスを踏む。歪めば E2E が壊れる蓋然性が高い。**Phase 2 Task 6 mutation 実測:** `_resolve_java_file` を `return None` に置換すると `TestIntenseE2E.test_getter経由参照が検出される` と `test_フィールドの間接参照が同一クラス内で検出される` が赤化（`TestIntegration` は SAMPLE.grep の usage_type が CONSTANT/CONDITION/RETURN のみで `java.py:92-96` のガードに弾かれ class スコープ経路に到達せず、対象外）。 | E2E mutation 確認後にクラス全削除（`_resolve_java_file` を意図的に壊して E2E が落ちるかを検証）。 |
| 11 | 635 | TestGetMethodScope | `_get_method_scope` (private, `tests/test_analyze.py:37`) | b 案 | パイロット G スパイク所見（`docs/superpowers/specs/2026-05-03-test-style-rework-design.md` 末尾）参照。`grep_helper/languages/java.py:119, 309` から直接呼ばれる。`TestIntenseE2E` (`tests/test_analyze.py:1361-1392`) で track_local 経路が踏まれる。 | クラス全削除前に E2E mutation 確認 |
| 12 | 671 | TestSearchInLines | `_search_in_lines` (private, `tests/test_analyze.py:38`) | c 案 | private で `grep_helper/languages/java.py` から **直接は呼ばれない**（`grep_helper/languages/java_track.py:223, 269, 316` 内部で `track_constant` / `track_field` / `track_getter_calls` 経由のみ）。E2E は通るが、変数名の単語境界マッチ等の内部不変条件は表層 TSV ではブラックボックスのため、Whitebox 隔離が安全。 | `TestSearchInLinesWhitebox` へ移送、命名で Whitebox を明示。 |
| 13 | 754 | TestTrackConstant | `track_constant` (public, `tests/test_analyze.py:39`) | c 案 | 公開関数だが、オーケストレータ (`grep_helper/languages/java.py`) は `_batch_track_combined` 経由でしか定数追跡を行わず、**`track_constant` の単独経路はプロダクションでは未走行** (grep 確認: java.py に `track_constant` 呼び出しなし)。テストは Whitebox 隔離して残す価値はある（バッチパスとの等価性確認の参照実装）。 | `TestTrackConstantWhitebox` へ移送。クラス doc に「`_batch_track_combined` の参照実装。プロダクションパスは Combined 側」と注記。 |
| 14 | 802 | TestTrackField | `track_field` (public, `tests/test_analyze.py:40`) | a 案 | 公開関数。`grep_helper/languages/java.py:110, 293` から直接呼ばれている（フィールドスコープ経路の主流）。テストは GrepRecord の filepath/code/ref_type を観察しており既に WHAT 寄り。 | 命名・doc を整え `TestTrackField` のまま keep でもよいが、E2E の `test_フィールドの間接参照が同一クラス内で検出される` (`tests/test_analyze.py:1398`) との重複が大きいため、クラスは E2E 経由テストへ統合（a 案）。残すなら keep + 命名修正でも許容範囲。 |
| 15 | 856 | TestTrackLocal | `track_local` (public, `tests/test_analyze.py:41`) | a 案 | 公開関数。`grep_helper/languages/java.py:124, 315` から直接呼ばれている（method スコープの主流）。テストは tmp Java ファイルを書き起こす重め fixture を使用。 | E2E の TestIntenseE2E は局所変数経路を直接検証していない（method スコープのテストは少ない）が、`extract_variable_name` + `determine_scope` が public で通る。Whitebox にせず、`track_local` を直接呼ぶ最小ケースを残しつつ a 案として整理（公開 API 同等経路で表現）。 |
| 16 | 918 | TestFindGetterNames | `find_getter_names` (public, `tests/test_analyze.py:42`) | keep | 公開 API のテスト (`tests/test_analyze.py:918-954`)。返り値リストの `assertIn`/重複検査は WHAT 観察。`grep_helper/languages/java.py:114, 299` で直接呼ばれているプロダクションパス。 | 触らない（または命名軽微修正）。 |
| 17 | 961 | TestFindSetterNames | `find_setter_names` (public, `tests/test_analyze.py:43`) | keep | 公開 API のテスト (`tests/test_analyze.py:961-988`)。返り値リストの `assertIn`/重複検査は WHAT 観察。`grep_helper/languages/java.py:116, 303` で直接呼ばれているプロダクションパス。 | 触らない（または命名軽微修正）。 |
| 18 | 995 | TestTrackGetterCalls | `track_getter_calls` (public, `tests/test_analyze.py:44`) | c 案 | 公開関数だが、オーケストレータは `_batch_track_combined` 経由で getter 呼び出し追跡を行うため、`track_getter_calls` 単独経路はプロダクションでは未走行 (grep 確認: java.py に `track_getter_calls` 呼び出しなし。`_batch_track_combined` のみ呼ばれる、`grep_helper/languages/java.py:138, 330`)。`TestIntenseE2E` の getter 経路 (`test_getter経由参照が検出される`, `tests/test_analyze.py:1428-1443`) は Combined 側を踏む。 | `TestTrackGetterCallsWhitebox` へ移送。 |
| 19 | 1049 | TestBuildParser | `build_parser` (public, `tests/test_analyze.py:17`) | keep | 公開 API のテスト (`tests/test_analyze.py:1049-1073`)。argparse の Namespace 属性を観察、WHAT として妥当。 | 触らない。 |
| 20 | 1080 | TestMain | `analyze.main` (public, `tests/test_analyze.py:16`) | keep | 公開 API（CLI エントリ）のテスト (`tests/test_analyze.py:1080-1166`)。終了コード・stdout/stderr・ファイル生成を観察、WHAT として妥当。 | 触らない。 |
| 21 | 1173 | TestGetAstExceptionHandling | `get_ast` (public) と `_ast_cache` (private dict) | keep + 軽微な命名修正 | 公開 API + 例外処理 (`tests/test_analyze.py:1173-1194`)。1 メソッドのみで `_ast_cache` を peek (`tests/test_analyze.py:1193-1194`) し Whitebox 寄り。Row 8 と同様。 | クラス全体は keep。任意で `_ast_cache` peek 部分を Whitebox 隔離するかは別判断。 |
| 22 | 1201 | TestIntenseE2E | `analyze.main` + `process_grep_file` 全パイプライン (public) | keep | 重厚 E2E テスト (`tests/test_analyze.py:1201-1567`、9 メソッド)。最大粒度の WHAT 観察。直接参照、間接参照、getter 経由、ソート、CLI、統計の全側面をカバー。 | 触らない。Phase 2 では b 案削除候補の mutation 確認の中心となる。 |
| 23 | 1573 | TestBatchTrackSetters | `_batch_track_setters` (private, `tests/test_analyze.py:46`) | c 案 | private で **プロダクションコードからの呼び出しなし** (`grep_helper/languages/java_track.py:842` 定義のみ、`grep -rn '_batch_track_setters' grep_helper/` で `java.py` 等にヒットなし、テスト専用の隔離ヘルパー)。E2E は `_batch_track_combined` の setter 機能を踏むため、当該テストは未到達コードを単独検証している。 | `TestBatchTrackSettersWhitebox` へ移送。クラス doc に「`_batch_track_combined` の setter 部分の参照実装テスト」と注記。プロダクション未到達ならテスト削除も検討。 |
| 24 | 1600 | TestBatchTrackOnePass | `_batch_track_combined` (private, `tests/test_analyze.py:45`) | c 案 | private だが `grep_helper/languages/java.py:138, 330` から直接呼ばれるオーケストレータ主経路。テストは `hasattr` チェック (`tests/test_analyze.py:1601-1603`) と内部ロジックの単独検証 (`tests/test_analyze.py:1605-1629`) を含み、`(ref_type, src_var)` タプルの集合を peek している。E2E (`TestIntenseE2E`) で当該パスが踏まれるが、ref_type の混合性を最小ケースで確認する Whitebox の価値はある。 **(注: 厳密ルール適用なら b 案。本マトリクスは hasattr/tuple peek が test method レベルで Whitebox shape のため c 案へ override。Phase 2 で hasattr メソッドは削除候補、tuple peek メソッドは ref_type 混合性が E2E ゴールデンで観察可能か再判定し、観察可能なら b 案へ戻す。)** | `TestBatchTrackOnePassWhitebox` へ移送、`hasattr` チェックは命名・doc で Whitebox を明示。 |
| 25 | 1632 | TestNoModuleGlobalEncoding | `analyze` モジュールのグローバル属性 (`hasattr(analyze, "_encoding_override")`) | c 案 | リファクタ後の不変条件（モジュールグローバル不在）を `assertFalse(hasattr(...))` で確認 (`tests/test_analyze.py:1632-1635`)。リグレッションガード用の Whitebox。E2E では検証不可能な内部不変条件。 | `TestNoModuleGlobalEncodingWhitebox` へ移送、クラス doc に「リファクタ後の不変条件ガード」と注記。 |
| 26 | 1638 | TestParallelBatchTrack | `_batch_track_combined` の workers 引数 (private) | c 案 | `inspect.signature` で workers パラメータ存在確認 (`tests/test_analyze.py:1639-1642`)、workers 1/2 の結果一致確認 (`tests/test_analyze.py:1644-1668`)。並列性の不変条件は E2E TSV では観察不能。Whitebox の価値あり。 | `TestParallelBatchTrackWhitebox` へ移送、`signature` peek は Whitebox であることを明示。 |

## 集計

- **keep:** 15 件 (rows 1-7, 9, 16-17, 19-20, 22 が純 keep, rows 8, 21 が keep + 軽微な命名修正)
  - 厳密内訳: 純 keep = 13 件 (1-7, 9, 16-17, 19-20, 22)、keep + 軽微修正 = 2 件 (8, 21)
  - **合計 keep: 15 件**
- **a 案（公開 API 統合）:** 2 件 (14 TestTrackField, 15 TestTrackLocal)
- **b 案（E2E 包摂で削除）:** 2 件 (10 TestResolveJavaFile, 11 TestGetMethodScope)
- **c 案（Whitebox 隔離）:** 7 件 (12 TestSearchInLines, 13 TestTrackConstant, 18 TestTrackGetterCalls, 23 TestBatchTrackSetters, 24 TestBatchTrackOnePass, 25 TestNoModuleGlobalEncoding, 26 TestParallelBatchTrack)
- **判定保留:** 0 件
- **合計:** 15 + 2 + 2 + 7 + 0 = 26

## Phase 2 への引き継ぎ

### 着手順の推奨

判定分布から、**c 案 7 件 → b 案 2 件 → a 案 2 件 → keep + 軽微修正 2 件** の順で進めるのが最小リスク：

1. **c 案 7 件を先に処理**（影響範囲最小、Whitebox クラス追加で即完了）。
   - `TestSearchInLines` / `TestTrackConstant` / `TestTrackGetterCalls` / `TestBatchTrackSetters` / `TestBatchTrackOnePass` / `TestNoModuleGlobalEncoding` / `TestParallelBatchTrack` をそれぞれ `Test...Whitebox` に rename + クラス doc に Whitebox 理由を追記。
   - 同類 (`_batch_track_*` 系 3 件) はバッチで処理可能。
2. **b 案 2 件の削除前に E2E mutation 確認を 1 度だけ実施**（パイロット G スパイク所見の重要原則）。
   - `_resolve_java_file` を意図的に壊す (例: 常に `None` 返却) → `TestIntegration` / `TestIntenseE2E` の少なくとも 1 つが落ちることを確認。
   - `_get_method_scope` を意図的に壊す → 同上。
   - 両方の mutation 確認を 1 度のセッションで完了させ、その後 `TestResolveJavaFile` / `TestGetMethodScope` を削除。
3. **a 案 2 件の書き換え**（`TestTrackField` / `TestTrackLocal`）。
   - 既に `track_field` / `track_local` は public で `java.py` 直接呼び出しのプロダクションパス。E2E でフィールドは検証されているが local は弱いので、ケースを最小化して残すか E2E 強化と引き換えに削除するかは Phase 2 で決める。
4. **keep + 軽微修正 2 件**（`TestGetAst` / `TestGetAstExceptionHandling` の `_ast_cache` peek）。優先度低、Phase 2 末尾で対応。

### Phase 2 で必要な情報の事前収集

- **`_batch_track_setters` のプロダクション到達確認**: row 23 で「未到達」と判定したが、Phase 2 着手前にもう一度 `grep -rn '_batch_track_setters' grep_helper/` で確認し、未到達なら Whitebox ではなく削除も視野。
- **`track_constant` / `track_getter_calls` (row 13, 18) のドキュメント整理**: 公開 API として export しているが、プロダクション経路は `_batch_track_combined`。Whitebox に移すと「公開 API なのに Whitebox」という見た目の矛盾が出るため、Phase 2 で「参照実装」コメントを必ず付けること。
- **E2E mutation 確認の手順**: 一時的に `_resolve_java_file` / `_get_method_scope` を壊すパッチを当て、`python -m unittest tests.test_analyze.TestIntegration tests.test_analyze.TestIntenseE2E -v` を走らせて落ちることを確認。確認後パッチをロールバックしてから削除コミットを作る。
- **`TestTrackField` (row 14) と `TestIntenseE2E.test_フィールドの間接参照が同一クラス内で検出される` の重複度評価**: a 案として書き換える前に、既存 E2E が同等の WHAT を検証しているかを精査する spike を Phase 2 Task 1 に置くと安全。
