# Test Style Rework — Sweep Wave 1 Phase 2 (test_analyze.py 翻訳本体) 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1 で作成した判定マトリクスに従い、`tests/test_analyze.py` の 11 件（c 案 7 + b 案 2 + a 案 2）を実適用 + keep 軽微修正 2 件を整理する。production コード変更は b 案 mutation の一時的な歪めのみで、最終 diff には含めない。

**Architecture:** 推奨着手順 (`c 案 → b 案 → a 案 → keep 軽微`) を厳守。c 案は影響範囲ゼロの rename + docstring のみ、b 案は E2E mutation 確認をゲートに削除、a 案は E2E カバレッジ検証で削除可否を再判定、keep 軽微は最後に Whitebox 抽出。

**Tech Stack:** Python 3, `unittest`, `ast`、`tempfile`。

**References:**
- 判定マトリクス: `docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md`
- パイロット仕様: `docs/superpowers/specs/2026-05-03-test-style-rework-design.md`
- Phase 1 プラン: `docs/superpowers/plans/2026-05-03-sweep-wave1-phase1-test-analyze.md`

---

## File Structure

- **Modify:** `tests/test_analyze.py`（全 Task）
- **Touch (一時的・コミットしない):** `grep_helper/languages/java_track.py`（b 案 mutation スポットチェックのみ、各 Task 完了時に必ず復元）
- **No Changes:** その他の `grep_helper/`、`docs/`

---

## 共通の事前確認事項

- すべての Whitebox クラスは **元の位置に rename in-place** で済ませる（ファイル末尾への移送はしない — diff を最小化、レビュアビリティ優先）。
- クラス docstring は **3 行のテンプレ** で統一する：

```python
"""<クラス名>: <対象関数> の <Whitebox 理由> を観察するテスト。
<実装契約の中身を 1 行で>。
実装変更時は本クラスも同期更新が必要。
"""
```

- 各 b 案 Task の mutation スポットチェック完了時は必ず `git diff grep_helper/` で「差分なし」を確認してから次に進む。

---

### Task 1: ベースライン確認

**Files:**
- Verify only

- [ ] **Step 1: 現在のテストグリーンを確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 383 tests ... OK`。

- [ ] **Step 2: Phase 1 完了 SHA を控える**

```bash
git rev-parse HEAD && git log --oneline -1
```

Expected: 直近コミットが `93393cb docs(specs): polish sweep wave 1 judgment matrix per code review` であること（または直系の派生）。違う場合は基底ブランチを確認して停止。

- [ ] **Step 3: 判定マトリクスをロード**

```bash
test -f docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md && echo "matrix exists"
```

Expected: `matrix exists`。

---

### Task 2: c 案バッチ A — `_search_in_lines` / `track_constant` / `track_getter_calls` を Whitebox 化

**Files:**
- Modify: `tests/test_analyze.py` の 3 クラス
  - `TestSearchInLines`（class header at line 671）
  - `TestTrackConstant`（class header at line 754）
  - `TestTrackGetterCalls`（class header at line 995）

**WHY:** 判定マトリクス row 12, 13, 18。private 関数 (`_search_in_lines`) または「公開 API だがプロダクション未走行」(`track_constant` / `track_getter_calls`) のテスト。プロダクションパスは `_batch_track_combined` 経由のみで、これら直接テストは「参照実装」として Whitebox 隔離する。

- [ ] **Step 1: TestSearchInLines を rename**

`tests/test_analyze.py` 内の以下を置換：

Before:
```python
class TestSearchInLines(unittest.TestCase):
    """F-03 内部: _search_in_lines() のテスト。"""
```

After:
```python
class TestSearchInLinesWhitebox(unittest.TestCase):
    """TestSearchInLinesWhitebox: _search_in_lines() の単語境界マッチと origin スキップ契約を観察するテスト。
    private helper であり、プロダクションパスは track_constant / track_field / track_getter_calls 内部経由のみ。
    実装変更時は本クラスも同期更新が必要。
    """
```

- [ ] **Step 2: TestTrackConstant を rename**

Before:
```python
class TestTrackConstant(unittest.TestCase):
    """F-03: track_constant() のテスト。"""
```

After:
```python
class TestTrackConstantWhitebox(unittest.TestCase):
    """TestTrackConstantWhitebox: track_constant() の参照実装テスト。
    public 関数だがオーケストレータは _batch_track_combined 経由でしか定数追跡を行わず、
    本関数の単独経路はプロダクション未走行。バッチパスとの等価性確認のため Whitebox として残す。
    実装変更時は本クラスも同期更新が必要。
    """
```

- [ ] **Step 3: TestTrackGetterCalls を rename**

Before:
```python
class TestTrackGetterCalls(unittest.TestCase):
    """F-04: track_getter_calls() のテスト。"""
```

After:
```python
class TestTrackGetterCallsWhitebox(unittest.TestCase):
    """TestTrackGetterCallsWhitebox: track_getter_calls() の参照実装テスト。
    public 関数だがオーケストレータは _batch_track_combined 経由でしか getter 呼び出し追跡を行わず、
    本関数の単独経路はプロダクション未走行。バッチパスとの等価性確認のため Whitebox として残す。
    実装変更時は本クラスも同期更新が必要。
    """
```

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest tests.test_analyze.TestSearchInLinesWhitebox tests.test_analyze.TestTrackConstantWhitebox tests.test_analyze.TestTrackGetterCallsWhitebox -v 2>&1 | tail -10
```

Expected: 該当テスト（合計 8 件: 3 + 2 + 2 + 1）すべて OK。

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 383 tests ... OK`。テスト件数は不変（rename のみ）。

- [ ] **Step 5: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): isolate _search_in_lines / track_constant / track_getter_calls to Whitebox (c 案 batch A)

判定マトリクス row 12, 13, 18 の c 案を実適用：
- TestSearchInLines → TestSearchInLinesWhitebox (private helper)
- TestTrackConstant → TestTrackConstantWhitebox (公開 API だがプロダクション未走行)
- TestTrackGetterCalls → TestTrackGetterCallsWhitebox (同上)

各クラスに「Whitebox 理由 + 実装変更時は同期更新が必要」のクラス docstring を統一形式で付与。
旧命名・docstring を Whitebox 命名・3 行 docstring に置換、テスト本体は不変。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: c 案バッチ B — `_batch_track_setters` / `_batch_track_combined` workers 引数を Whitebox 化

**Files:**
- Modify: `tests/test_analyze.py` の 2 クラス
  - `TestBatchTrackSetters`（class header at line 1573）
  - `TestParallelBatchTrack`（class header at line 1638）

**WHY:** 判定マトリクス row 23, 26。`_batch_track_setters` はプロダクション未到達、`TestParallelBatchTrack` は `inspect.signature` peek を含む並列性不変条件のテスト。両方 Whitebox 化が妥当。

- [ ] **Step 1: TestBatchTrackSetters を rename**

Before:
```python
class TestBatchTrackSetters(unittest.TestCase):
    """Java-4: _batch_track_setters() のテスト。"""
```

After:
```python
class TestBatchTrackSettersWhitebox(unittest.TestCase):
    """TestBatchTrackSettersWhitebox: _batch_track_setters() の単独パスを観察するテスト。
    プロダクションコードからの呼び出しなし（_batch_track_combined の setter 部分の参照実装）。
    将来未到達コードとして削除も検討するが、当面 Whitebox として保持。
    実装変更時は本クラスも同期更新が必要。
    """
```

- [ ] **Step 2: TestParallelBatchTrack に **クラス docstring を追加**して rename**

Before:
```python
class TestParallelBatchTrack(unittest.TestCase):
    def test_batch_track_combinedはworkers引数を受け取る(self):
```

After:
```python
class TestParallelBatchTrackWhitebox(unittest.TestCase):
    """TestParallelBatchTrackWhitebox: _batch_track_combined の workers 引数とワーカー間結果一致を観察するテスト。
    並列性の不変条件は E2E TSV では観察不能なため Whitebox として保持。
    実装変更時は本クラスも同期更新が必要。
    """

    def test_batch_track_combinedはworkers引数を受け取る(self):
```

注: 旧 `TestParallelBatchTrack` はクラス docstring を持っていなかった。本 step で初めて追加する。

- [ ] **Step 3: グリーン確認**

```bash
python -m unittest tests.test_analyze.TestBatchTrackSettersWhitebox tests.test_analyze.TestParallelBatchTrackWhitebox -v 2>&1 | tail -10
```

Expected: 3 件 (1 + 2) すべて OK。

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 383 tests ... OK`。

- [ ] **Step 4: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): isolate _batch_track_setters / parallel batch track to Whitebox (c 案 batch B)

判定マトリクス row 23, 26 の c 案を実適用：
- TestBatchTrackSetters → TestBatchTrackSettersWhitebox (プロダクション未到達)
- TestParallelBatchTrack → TestParallelBatchTrackWhitebox (signature peek を含む並列性不変条件)

旧 TestParallelBatchTrack はクラス docstring を持っていなかったため、本コミットで Whitebox 理由
docstring を新規追加。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: c 案 + 再判定 — TestBatchTrackOnePass の hasattr 削除と tuple peek 再判定

**Files:**
- Modify: `tests/test_analyze.py` の `TestBatchTrackOnePass`（class header at line 1600）
- Read only: `tests/fixtures/expected/SAMPLE.tsv`

**WHY:** 判定マトリクス row 24 の override 注記に従い、(a) hasattr メソッドは削除、(b) tuple peek メソッドは E2E ref_type 観察可能性で再判定する。観察可能なら b 案へ戻して削除、不可能なら Whitebox 化。

- [ ] **Step 1: ref_type 混合性が E2E で観察可能か確認**

E2E ゴールデン `tests/fixtures/expected/SAMPLE.tsv` を確認：

```bash
cat tests/fixtures/expected/SAMPLE.tsv
```

確認すべき点：
- 「直接」以外の ref_type（`間接`、`間接（getter経由）`、`間接（setter経由）`）が **3 種すべて** ゴールデンに登場するか。
- それぞれ `Constants.java` / `Service.java` / `Entity.java` 等のフィクスチャを横断して検証されているか。

判定：
- **3 種すべて含まれる場合** → ref_type 混合性は E2E で観察可能 → b 案へ戻し、tuple peek メソッドも削除する（Step 3 へ）。
- **欠けている ref_type がある場合** → Whitebox として保持（Step 4 へ）。

```bash
grep -c "間接" tests/fixtures/expected/SAMPLE.tsv
grep -c "getter経由" tests/fixtures/expected/SAMPLE.tsv
grep -c "setter経由" tests/fixtures/expected/SAMPLE.tsv
```

- [ ] **Step 2: hasattr メソッド `test_batch_track_combinedが1パスで定数とgetterとsetterを処理する` を削除**

`tests/test_analyze.py` 内の以下の 2 行（メソッド定義 + 本体）を削除：

```python
    def test_batch_track_combinedが1パスで定数とgetterとsetterを処理する(self):
        from grep_helper.languages import java_track
        self.assertTrue(hasattr(java_track, "_batch_track_combined"))
```

理由: `hasattr` チェックは import 文で既に保証されているため冗長な HOW テスト。

- [ ] **Step 3 (条件分岐 A — Step 1 で b 案戻し判定の場合): クラス全体を削除**

クラス `TestBatchTrackOnePass` 全体を削除する（Step 2 削除後の残メソッド `test_combinedが定数とgetterとsetterのレコードを混合で返す` 含む）。

mutation スポットチェック：
- `grep_helper/languages/java_track.py:606-` の `_batch_track_combined` 内、ref_type 文字列を一時的に書き換える（例: `"間接（getter経由）"` を `"GETTER"` に置換）。
- E2E を実行し落ちることを確認:
  ```bash
  python -m unittest tests.test_analyze.TestIntegration tests.test_analyze.TestIntenseE2E 2>&1 | tail -5
  ```
- production を git diff で復元、グリーン確認。
- クラス削除をコミット。

- [ ] **Step 3' (条件分岐 B — Step 1 で Whitebox 化判定の場合): クラスを Whitebox 化**

Before（Step 2 後の状態）:
```python
class TestBatchTrackOnePass(unittest.TestCase):
    def test_combinedが定数とgetterとsetterのレコードを混合で返す(self):
```

After:
```python
class TestBatchTrackOnePassWhitebox(unittest.TestCase):
    """TestBatchTrackOnePassWhitebox: _batch_track_combined の ref_type 混合出力を観察するテスト。
    E2E ゴールデンで一部の ref_type 混合が観察できないため、最小ケースで直接検証する。
    実装変更時は本クラスも同期更新が必要。
    """

    def test_combinedが定数とgetterとsetterのレコードを混合で返す(self):
```

- [ ] **Step 4: 採用した分岐に応じてグリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 382 tests ... OK`（hasattr メソッド 1 件削除、Step 3 採用なら更に 1 件削減で 381）。

- [ ] **Step 5: コミット（採用分岐を明記）**

分岐 A（クラス全削除、b 案戻し）の場合：

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): delete TestBatchTrackOnePass after E2E ref_type mutation confirm (b 案 reverted)

判定マトリクス row 24 の override 注記に従い再判定：
- hasattr メソッドは import で保証済みのため削除（HOW テスト）
- tuple peek メソッドは E2E SAMPLE.tsv に間接/getter経由/setter経由 ref_type が
  すべて登場し E2E で観察可能と確認、b 案 (削除) へ戻した
- mutation 確認: _batch_track_combined の ref_type 文字列を歪めると
  TestIntegration / TestIntenseE2E が赤くなることを確認、production を復元してから削除

合計 2 メソッド削減（383 → 381）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

分岐 B（Whitebox 化、c 案維持）の場合：

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): isolate TestBatchTrackOnePass to Whitebox (c 案 — hasattr deleted, tuple peek preserved)

判定マトリクス row 24 の override 注記に従い再判定：
- hasattr メソッドは import で保証済みのため削除（HOW テスト）
- tuple peek メソッドは E2E に欠けている ref_type [<実際に欠けたものを記載>] があり
  Whitebox 保持が妥当と判定、c 案維持
- TestBatchTrackOnePass → TestBatchTrackOnePassWhitebox に rename + 理由 docstring 付与

合計 1 メソッド削減（383 → 382）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: c 案単独 — TestNoModuleGlobalEncoding を Whitebox 化

**Files:**
- Modify: `tests/test_analyze.py` の `TestNoModuleGlobalEncoding`（class header at line 1632）

**WHY:** 判定マトリクス row 25。リファクタ後の不変条件（モジュールグローバル不在）を `assertFalse(hasattr(...))` で確認するリグレッションガード。E2E では検証不可能。

- [ ] **Step 1: TestNoModuleGlobalEncoding に **クラス docstring を追加**して rename**

Before:
```python
class TestNoModuleGlobalEncoding(unittest.TestCase):
    def test_encoding_overrideモジュールグローバルは廃止されている(self):
```

After:
```python
class TestNoModuleGlobalEncodingWhitebox(unittest.TestCase):
    """TestNoModuleGlobalEncodingWhitebox: analyze モジュールから _encoding_override
    グローバル属性が削除されている不変条件を観察するリグレッションガード。
    E2E では検証不可能な内部不変条件のため Whitebox として保持。
    実装変更時は本クラスも同期更新が必要。
    """

    def test_encoding_overrideモジュールグローバルは廃止されている(self):
```

- [ ] **Step 2: グリーン確認**

```bash
python -m unittest tests.test_analyze.TestNoModuleGlobalEncodingWhitebox -v 2>&1 | tail -5
```

Expected: 1 件 OK。

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 4 後の件数> tests ... OK`。

- [ ] **Step 3: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): isolate module-global-encoding regression guard to Whitebox (c 案)

判定マトリクス row 25 の c 案を実適用：
- TestNoModuleGlobalEncoding → TestNoModuleGlobalEncodingWhitebox
- 旧クラスは docstring を持っていなかったため、Whitebox 理由 + リグレッションガード
  注記の docstring を新規追加

E2E では観察不可能な「モジュールグローバル属性の不在」契約を Whitebox として保持。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: b 案 — TestResolveJavaFile を E2E mutation 確認後に削除

**Files:**
- Modify: `tests/test_analyze.py` の `TestResolveJavaFile`（class header at line 607、4 メソッド）
- Touch (一時的): `grep_helper/languages/java_track.py` の `_resolve_java_file`（line 31-48）

**WHY:** 判定マトリクス row 10。`_resolve_java_file` は private で `grep_helper/languages/java.py:108, 291` から呼ばれ、E2E (`TestIntegration` + `TestIntenseE2E`) が両経路（相対 + 絶対）を踏む。歪めば E2E で必ず壊れる。

- [ ] **Step 1: production を一時的に歪めて E2E が落ちることを確認**

`grep_helper/languages/java_track.py:31-48` の `_resolve_java_file` 関数本体を以下に置換：

Before:
```python
def _resolve_java_file(filepath: str, source_dir: Path) -> Path | None:
    """filepathをPathオブジェクトに解決する。
    ...
    """
    candidate = Path(filepath)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    resolved = source_dir / filepath
    if resolved.exists():
        return resolved
    return None
```

After (mutation):
```python
def _resolve_java_file(filepath: str, source_dir: Path) -> Path | None:
    """filepathをPathオブジェクトに解決する。
    ...
    """
    return None  # mutation: always fail to resolve
```

E2E を実行：

```bash
python -m unittest tests.test_analyze.TestIntegration tests.test_analyze.TestIntenseE2E 2>&1 | tail -10
```

Expected: **FAIL**（少なくとも 1 件落ちる。Java 解析が一切できなくなるため、SAMPLE.tsv との比較が落ちる）。

- [ ] **Step 2: production を元に戻し、グリーンを確認**

```bash
git checkout grep_helper/languages/java_track.py
git diff grep_helper/languages/java_track.py
```

Expected: 差分なし。

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 5 後の件数> tests ... OK`。

- [ ] **Step 3: TestResolveJavaFile クラスを削除**

`tests/test_analyze.py` の `class TestResolveJavaFile(unittest.TestCase):` から次のクラス開始（`class TestGetMethodScope`）の直前のセパレータコメント `# ----- TestGetMethodScope -----` までを削除する。**セパレータコメント自体は残す**（次のクラスへの導線）。

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 5 後 - 4> tests ... OK`（4 メソッド削減）。

- [ ] **Step 5: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): delete TestResolveJavaFile after E2E mutation confirm (b 案)

判定マトリクス row 10 の b 案を実適用：
- _resolve_java_file は private helper、grep_helper/languages/java.py:108, 291 から呼ばれる
- mutation 確認: _resolve_java_file 本体を `return None` に置換すると
  TestIntegration / TestIntenseE2E が赤くなることを確認、production を復元してから削除
- 4 メソッドすべて E2E (SAMPLE.tsv 比較) に包摂されているため削除可能

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: b 案 — TestGetMethodScope を E2E mutation 確認後に削除

**Files:**
- Modify: `tests/test_analyze.py` の `TestGetMethodScope`（class header at line 635、3 メソッド）
- Touch (一時的): `grep_helper/languages/java_track.py` の `_get_method_scope`（line 54-115）

**WHY:** 判定マトリクス row 11、パイロット G スパイク所見の判定。`_get_method_scope` は `grep_helper/languages/java.py:119, 309` から呼ばれ、`TestIntenseE2E` (line 1361-1392 の track_local 経路) で踏まれる。

- [ ] **Step 1: production を一時的に歪めて E2E が落ちることを確認**

`grep_helper/languages/java_track.py:109-110`（**成功経路の戻り値**）を以下に置換：

Before (line 109-110):
```python
        if found_open and brace_count <= 0:
            return (method_start, i)
```

After (mutation):
```python
        if found_open and brace_count <= 0:
            return (1, 99999)  # mutation: 過大な範囲を返す
```

注: 早期 `return None` ではなく **成功経路の戻り値** を歪める（パイロット G スパイク所見の指示）。

E2E を実行：

```bash
python -m unittest tests.test_analyze.TestIntenseE2E 2>&1 | tail -10
```

Expected: **FAIL**（メソッドスコープが過大になることで track_local が誤動作し、間接参照の検出範囲が変わってゴールデン差分が出る）。

**赤くならない場合:** mutation 値を変えて再試行（例: `(method_start + 1000, i)`）。それでも赤くならない場合は b 案不成立 → **Stop & Report**（c 案フォールバック）。

- [ ] **Step 2: production を元に戻し、グリーンを確認**

```bash
git checkout grep_helper/languages/java_track.py
git diff grep_helper/languages/java_track.py
```

Expected: 差分なし。

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 6 後の件数> tests ... OK`。

- [ ] **Step 3: TestGetMethodScope クラスを削除**

`tests/test_analyze.py` の `class TestGetMethodScope(unittest.TestCase):` から次のクラス開始（`class TestSearchInLinesWhitebox`）の直前のセパレータコメント `# ----- TestSearchInLines -----` までを削除する。**セパレータコメント自体は残す**。

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 6 後 - 3> tests ... OK`（3 メソッド削減）。

- [ ] **Step 5: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): delete TestGetMethodScope after E2E mutation confirm (b 案)

判定マトリクス row 11 + パイロット G スパイク所見の b 案を実適用：
- _get_method_scope は private helper、grep_helper/languages/java.py:119, 309 から呼ばれる
- mutation 確認: 成功経路の戻り値 `return (method_start, i)` を `return (1, 99999)` に置換すると
  TestIntenseE2E が赤くなることを確認、production を復元してから削除
- 3 メソッドすべて E2E (SAMPLE.tsv の Constants.java 13 行目周辺の track_local 経路) に
  包摂されているため削除可能

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: a 案 — TestTrackField を E2E カバレッジで再判定し、削除 or keep+rename

**Files:**
- Modify: `tests/test_analyze.py` の `TestTrackField`（class header at line 802、2 メソッド）
- Touch (一時的): `grep_helper/languages/java_track.py` の `track_field`（line 238-）

**WHY:** 判定マトリクス row 14。`track_field` は public で `grep_helper/languages/java.py:110, 293` から呼ばれる。E2E `test_フィールドの間接参照が同一クラス内で検出される` (line 1398) との重複が大きい可能性がある。

- [ ] **Step 1: E2E mutation 確認で削除可否を判定**

`grep_helper/languages/java_track.py:238` の `track_field` 関数本体を一時的に空リスト返却に置換：

Before:
```python
def track_field(
    field_name: str,
    java_file: Path,
    origin: GrepRecord,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    """..."""
    # （実装）
```

After (mutation):
```python
def track_field(
    field_name: str,
    java_file: Path,
    origin: GrepRecord,
    source_dir: Path,
    stats: ProcessStats,
) -> list[GrepRecord]:
    return []  # mutation: always empty
```

注: 関数本体の実装行をすべてコメントアウトし、`return []` のみ残す。元の実装は git で復元可能。

E2E を実行：

```bash
python -m unittest tests.test_analyze.TestIntenseE2E 2>&1 | tail -10
```

判定：
- **FAIL（フィールド経路の E2E が赤くなる）** → E2E が `track_field` を包摂 → **b 案へ戻して削除**（Step 3 へ）。
- **PASS（赤くならない、または期待ゴールデンと一致）** → E2E は `track_field` 単独経路を観察できない → **keep + rename**（Step 4 へ）。

```bash
git checkout grep_helper/languages/java_track.py
```

production 復元を必ず実行。

- [ ] **Step 2: 全テストグリーンを確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 7 後の件数> tests ... OK`。

- [ ] **Step 3 (分岐 A: E2E で包摂されている場合) — クラス全削除**

`tests/test_analyze.py` の `class TestTrackField(unittest.TestCase):` から次のクラス開始（`class TestTrackLocal`）の直前のセパレータコメントまでを削除する。**セパレータコメントは残す**。

コミットメッセージ：

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): delete TestTrackField after E2E mutation confirm (a 案 → b 案 へ戻し)

判定マトリクス row 14 を再判定：
- track_field は public、grep_helper/languages/java.py:110, 293 から直接呼ばれる
- mutation 確認: track_field 本体を `return []` に置換すると
  TestIntenseE2E のフィールド経路 (test_フィールドの間接参照が同一クラス内で検出される) が
  赤くなることを確認、production を復元してから削除
- 2 メソッドすべて E2E に包摂されているため削除可能

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3' (分岐 B: E2E で観察不可) — クラスを keep して命名整理**

Before:
```python
class TestTrackField(unittest.TestCase):
    """F-03: track_field() のテスト。"""
```

After:
```python
class TestTrackField(unittest.TestCase):
    """TestTrackField: track_field() の公開 API としての振る舞いを観察するテスト。
    E2E SAMPLE.tsv が track_field の単独経路を必ずしも踏まないため、最小ケースで保持する。
    """
```

コミットメッセージ：

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): keep TestTrackField with refined docstring (a 案 → keep)

判定マトリクス row 14 を再判定：
- mutation 確認: track_field を歪めても E2E が必ずしも赤くならず、
  単独経路は E2E で完全には観察できない
- public 関数として最小ケースを保持、Whitebox ではなく通常 keep として整理
- クラス docstring を WHAT 中心に書き換え

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: a 案 — TestTrackLocal の整理（公開 API テストとして keep）

**Files:**
- Modify: `tests/test_analyze.py` の `TestTrackLocal`（class header at line 856、2 メソッド）

**WHY:** 判定マトリクス row 15。`track_local` は public で `grep_helper/languages/java.py:124, 315` から呼ばれるが、E2E の method スコープ経路は弱い。Whitebox 化せず、最小ケースとして保持する。

- [ ] **Step 1: クラス docstring を WHAT 中心に整理**

Before:
```python
class TestTrackLocal(unittest.TestCase):
    """F-03: track_local() のテスト。"""
```

After:
```python
class TestTrackLocal(unittest.TestCase):
    """TestTrackLocal: track_local() の公開 API としてローカル変数追跡の振る舞いを観察するテスト。
    E2E ゴールデンは method スコープ経路を弱くしか踏まないため、最小ケースで保持する。
    """
```

- [ ] **Step 2: グリーン確認**

```bash
python -m unittest tests.test_analyze.TestTrackLocal -v 2>&1 | tail -5
```

Expected: 2 件 OK。

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 8 後の件数> tests ... OK`。

- [ ] **Step 3: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): refine TestTrackLocal docstring (a 案 → keep with rationale)

判定マトリクス row 15 を実適用：
- track_local は public、grep_helper/languages/java.py:124, 315 から直接呼ばれる
- E2E の method スコープ経路は弱く、track_local 単独テストの保持価値あり
- Whitebox 化せず、公開 API テストとして keep（最小ケース）
- クラス docstring を WHAT 中心 + 保持理由を明示する形に書き換え

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: keep 軽微 — `_ast_cache` peek メソッドを TestAstCacheWhitebox に抽出

**Files:**
- Modify: `tests/test_analyze.py`
  - `TestGetAst`（class header at line 487、4 メソッド中 1 つが peek）
  - `TestGetAstExceptionHandling`（class header at line 1173、1 メソッドのみで peek）

**WHY:** 判定マトリクス row 8, 21。両方とも 1 メソッドだけが `_ast_cache` dict を直接 peek。クラスは keep のままで、peek メソッドのみ Whitebox クラスに抽出することでスタイルを統一する。

- [ ] **Step 1: TestGetAst から peek メソッドを削除**

`tests/test_analyze.py:516-521` の以下のメソッドを **削除**：

```python
    def test_存在しないファイルはNoneとしてキャッシュされる(self):
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        get_ast("ghost.java", self.JAVA_DIR)
        self.assertIn("ghost.java", _ast_cache)
        self.assertIsNone(_ast_cache["ghost.java"])
```

注: Step 3 でこのメソッドの内容を新クラスに移送する。

- [ ] **Step 2: TestGetAstExceptionHandling から peek メソッドを削除（クラスごと削除）**

`tests/test_analyze.py:1173-1194` の `TestGetAstExceptionHandling` クラス全体を **削除**。

注: 唯一のメソッド `test_構文エラーのJavaファイルはNoneを返しキャッシュされる` も `_ast_cache` を peek しているため、Step 3 で新 Whitebox クラスへ移送する。クラスとして残す価値はない（1 メソッドのみ）。

- [ ] **Step 3: TestAstCacheWhitebox を `TestGetAst` の直後に新規追加**

`TestGetAst` クラスの直後（旧 `TestGetAstExceptionHandling` 削除箇所ではなく）に、以下を追加。元の peek メソッド 2 件を移送する：

```python
class TestAstCacheWhitebox(unittest.TestCase):
    """TestAstCacheWhitebox: get_ast() が _ast_cache に None キャッシュを書き込む実装契約を観察するテスト。
    キャッシュ dict の存在は内部実装で、E2E では観察不可能。
    実装変更時は本クラスも同期更新が必要。
    """

    JAVA_DIR = Path(__file__).parent / "fixtures" / "java"

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        _ast_cache.clear()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        _ast_cache.clear()

    def test_存在しないファイルはNoneとしてキャッシュされる(self):
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        get_ast("ghost.java", self.JAVA_DIR)
        self.assertIn("ghost.java", _ast_cache)
        self.assertIsNone(_ast_cache["ghost.java"])

    def test_構文エラーのJavaファイルはNoneを返しキャッシュされる(self):
        if not _JAVALANG_AVAILABLE:
            self.skipTest("javalang が未インストールです。")
        bad_file = Path(self.tmp_dir) / "Bad.java"
        bad_file.write_text("this is not valid java { { {", encoding="utf-8")
        java_dir = Path(self.tmp_dir)
        result = get_ast("Bad.java", java_dir)
        self.assertIsNone(result)
        self.assertIn("Bad.java", _ast_cache)
        self.assertIsNone(_ast_cache["Bad.java"])
```

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest tests.test_analyze.TestGetAst tests.test_analyze.TestAstCacheWhitebox -v 2>&1 | tail -10
```

Expected: 5 件（TestGetAst の残 3 件 + TestAstCacheWhitebox の 2 件）すべて OK。

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <Task 9 後の件数> tests ... OK`（件数不変。peek 2 件は新クラスに移送したのみ、TestGetAstExceptionHandling のクラスごと削除も内訳は同じ）。

- [ ] **Step 5: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): extract _ast_cache peek tests to TestAstCacheWhitebox (keep + 軽微修正)

判定マトリクス row 8, 21 を実適用：
- TestGetAst の 1 メソッド (test_存在しないファイルはNoneとしてキャッシュされる) と
  TestGetAstExceptionHandling の 1 メソッドが共に _ast_cache dict を直接 peek
- 両者を新規 TestAstCacheWhitebox クラスへ統合
- TestGetAst は WHAT 観察 3 件のみ残し純 keep に整理
- TestGetAstExceptionHandling はクラスごと削除（1 メソッドのみで Whitebox 寄り）

スタイル統一: 同じ Whitebox shape のテストは Whitebox クラスにまとめる。
テスト件数は不変（移送のみ）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Phase 2 完了確認 & 報告

**Files:**
- Verify only

- [ ] **Step 1: 全体テストグリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `OK`。失敗があれば該当を報告して止める。

- [ ] **Step 2: production 差分なしを確認**

```bash
git diff <Task 1 で控えた SHA>..HEAD -- grep_helper/
```

Expected: 差分なし（b 案 mutation はすべて復元したはず）。差分があれば mutation の取り残しを修正し、補正コミットを打つ。

- [ ] **Step 3: コミット履歴の連続性確認**

```bash
git log --oneline <Task 1 SHA>..HEAD
```

Expected: Task 2〜10 の各コミットが順に並ぶ（Task 4 / Task 8 は採用分岐で 1 コミット）。

- [ ] **Step 4: 最終クラス棚卸し**

```bash
grep -nE "^class Test" tests/test_analyze.py
```

Expected: 以下の構成（Task 4・Task 8 の分岐次第で件数が変動）：
- 純 keep: 13 件（TestGrepParser / TestUsageClassifier / TestTsvWriter / TestIndirectTracker / TestReporter / TestIntegration / TestProcessGrepFile / TestGetAst / TestClassifyUsage / TestFindGetterNames / TestFindSetterNames / TestBuildParser / TestMain / TestIntenseE2E）
- a 案 / 軽微 keep: TestTrackField (or 削除) / TestTrackLocal
- Whitebox: TestSearchInLinesWhitebox / TestTrackConstantWhitebox / TestTrackGetterCallsWhitebox / TestBatchTrackSettersWhitebox / TestParallelBatchTrackWhitebox / TestNoModuleGlobalEncodingWhitebox / TestAstCacheWhitebox / (条件で TestBatchTrackOnePassWhitebox)

- [ ] **Step 5: ユーザーへの報告内容**

報告に含める：
- 実適用したパターンと件数（c 案 7、b 案 2、a 案 2、keep 軽微 2 のうち分岐後の最終内訳）
- Task 4・Task 8 でどちらの分岐を採用したか + 理由
- 削除されたテスト件数（合計、内訳）
- 最終クラス構成（純 keep / Whitebox / その他の件数）
- 全体テストグリーン状態
- production 差分なし確認
- 次の wave（test_pl* / test_ts_* / test_dotnet_* / test_kotlin_* など）への準備状況

---

## 自己レビュー結果

- 推奨着手順 (c → b → a → keep 軽微) に厳密に従う構成
- 全 b 案 Task で E2E mutation 確認をゲートに削除（パイロット G スパイク所見の原則）
- production への変更は b 案 mutation のみで、必ず `git checkout grep_helper/` で復元
- 各 Task の Step が 2-5 分粒度、コミットも Task ごとに 1 個（Task 4 / Task 8 は 2 経路あるが採用分岐で 1 個）
- Whitebox クラスはすべて 3 行 docstring テンプレで統一
- Task 4 の override 再判定 / Task 8 の a 案再判定が分岐構造で記述、各分岐のコミットメッセージが事前定義されている
- production 差分の最終確認が Task 11 Step 2 に組み込まれている
- 判定マトリクス（Phase 1 成果物）を Task 1 でロード確認、各 Task 冒頭で row 番号を引用
