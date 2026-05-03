# Test Style Rework — Sweep Wave 2 (test_analyze.py 以外 14 ファイル) 統合プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wave 1 で `tests/test_analyze.py` に適用した「keep / Whitebox / 削除 / keep+rename」のテストスタイル整理を、残り 14 のテストファイル（合計 ~2693 行・約 60 クラス・約 290 テストメソッド）に適用する。各ファイルで Phase 1（実態調査 + 判定）と Phase 2（適用）を 1 タスクに統合する。

**Architecture:** ファイル単位で「(a) クラス棚卸し → (b) 各クラスの assertion shape 観察 → (c) 判定 → (d) 適用 → (e) green 確認 → (f) commit」を 1 タスクに閉じる。判定ルールは Wave 1 で確立したものを共通の事前確認事項として上に置き、各タスクはそれを参照する。b 案候補は必ず mutation gate を通す。production への変更は b 案 mutation の一時的な歪めのみで、最終 diff には含めない。

**Tech Stack:** Python 3, `unittest`, `tempfile`, `git`.

**References:**
- Wave 1 判定マトリクス: `docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md`
- Wave 1 Phase 2 プラン: `docs/superpowers/plans/2026-05-03-sweep-wave1-phase2-test-analyze.md`
- パターン定義: `docs/superpowers/specs/2026-05-03-test-style-rework-design.md`

---

## File Structure

- **Modify:** 各テストファイル（一度に 1 ファイル単位）。
- **Touch (一時的・コミットしない):** 対応する production ファイル（`grep_helper/...`）— b 案 mutation スポットチェックのみ、各 Task 完了時に必ず復元.
- **No Changes:** その他の `grep_helper/`、`docs/`、Wave 1 で整理済みの `tests/test_analyze.py`。

各ファイルの規模:

| Task | ファイル | 行数 | クラス数 | テストメソッド数 |
|---|---|---|---|---|
| 2 | tests/test_aho_corasick.py | 37 | 1 | 4 |
| 3 | tests/test_python_analyzer.py | 79 | 2 | 9 |
| 4 | tests/test_sh_analyzer.py | 59 | 2 | 15 |
| 5 | tests/test_sql_analyzer.py | 75 | 2 | 13 |
| 6 | tests/test_ts_analyzer.py | 83 | 2 | 10 |
| 7 | tests/test_perl_analyzer.py | 91 | 2 | 12 |
| 8 | tests/test_plsql_analyzer.py | 99 | 2 | 12 |
| 9 | tests/test_kotlin_analyzer.py | 158 | 4 | 15 |
| 10 | tests/test_dotnet_analyzer.py | 181 | 4 | 22 |
| 11 | tests/test_groovy_analyzer.py | 197 | 7 | 23 |
| 12 | tests/test_c_analyzer.py | 260 | 7 | 28 |
| 13 | tests/test_common.py | 372 | 10 | 32 |
| 14 | tests/test_analyze_proc.py | 430 | 9 | 38 |
| 15 | tests/test_all_analyzer.py | 472 | 6 | 51 |
| **合計** | | **2593** | **60** | **284** |

着手順は **小さい順 → 大きい順**（Task 2 → Task 15）。判定ロジックを小さいファイルで習熟してから大きいファイルに進む。

---

## 共通の事前確認事項

**重要:** 各 Task はこのセクションを必ず参照する。Task 内では参照のみ、ロジックの再記述はしない。

### A. 判定タクソノミー (Wave 1 で確立)

各クラスを以下の 4 区分のいずれかに分類する：

1. **純 keep** — 公開 API の WHAT 観察 (返り値・stdout・ファイル内容等を等値比較)。`assertIn`/`assertEqual` 主体、内部 dict / `inspect.signature` / `hasattr` peek なし。**アクション:** 触らない。クラス docstring が `F-XX:` 形式や `<関数名> のテスト` 程度なら任意で WHAT 中心へ書き換えてもよいが、必須ではない。
2. **a 案 (公開 API keep + docstring 整理)** — 公開関数のテストで既に WHAT 観察。E2E 包摂が弱い場合は最小ケースとして残す。**アクション:** Whitebox 化せず docstring を WHAT 中心 + 保持理由を明示する形に書き換え。クラス名は変更しない。
3. **b 案 (削除)** — private helper または「公開関数だが E2E が当該経路を確実に踏む」もの。**アクション:** 後述の Mutation Gate を通過した場合のみクラス全削除。precondition 不成立なら **c 案 fallback**（Wave 1 Task 7 と同じ）。
4. **c 案 (Whitebox 化)** — private helper、または `hasattr` / `inspect.signature` / 内部 dict peek 等、WHAT では観察不能な実装契約のテスト。**アクション:** `TestXxx` → `TestXxxWhitebox` に rename + 3 行 docstring 付与。

**判定の signal (assertion shape の見方):**

| 観察対象 | 判定 |
|---|---|
| 返り値の等値・順序・部分集合 (`assertEqual`, `assertIn`, `assertGreater`) | keep / a 案 |
| stdout / ファイル内容 / argparse Namespace 等の I/O 観察 | keep |
| `_xxx_cache` / `_xxx_map` 等の private dict を `assertIn` で peek | **c 案** |
| `hasattr(module, "_xxx")` / `assertFalse(hasattr(...))` | **c 案** |
| `inspect.signature(...).parameters` で引数存在確認 | **c 案** |
| private 関数 (`_xxx`) の単独テスト | **b 案 候補** (E2E 包摂を mutation で確認) |
| 公開関数だがプロダクションが orchestrator 経由でしか呼ばない (grep で確認) | **c 案** (参照実装) |

判定保留する場合は Task 内で stop & report し、ユーザに判断を仰ぐ。

### B. Whitebox docstring 統一形式

Whitebox 化 (c 案) するクラスは以下の 3 行 docstring を付与する：

```python
"""<クラス名>: <対象関数> の <Whitebox 理由> を観察するテスト。
<実装契約の中身を 1 行で>。
実装変更時は本クラスも同期更新が必要。
"""
```

例 (Wave 1 から):

```python
"""TestSearchInLinesWhitebox: _search_in_lines() の単語境界マッチと origin スキップ契約を観察するテスト。
private helper であり、プロダクションパスは track_constant / track_field / track_getter_calls 内部経由のみ。
実装変更時は本クラスも同期更新が必要。
"""
```

行幅: flake8 `max-line-length = 120` を厳守。長い説明は途中改行する（Wave 1 Task 7 で line-length 違反を経験済）。

### C. a 案 / keep の docstring 整理パターン

```python
"""<ClassName>: <対象関数> の <観察対象> を観察するテスト。
<E2E 包摂の弱さ等、保持理由を 1 行で>。
"""
```

例 (Wave 1 から):

```python
"""TestTrackLocal: track_local() の公開 API としてローカル変数追跡の振る舞いを観察するテスト。
E2E ゴールデンは method スコープ経路を弱くしか踏まないため、最小ケースで保持する。
"""
```

クラス名は変更しない。`Whitebox` 接尾辞も付けない。

### D. Mutation Gate 共通手順 (b 案候補)

1. **対象関数の特定:** 当該テストクラスがテストしている関数を `grep_helper/...` 内で grep。private helper (`_xxx`) か public か、どこから呼ばれているかを確認。
2. **production 呼び出しの確認:** orchestrator (典型的には `grep_helper/languages/<lang>.py` や `grep_helper/dispatcher.py`) から直接呼ばれているか grep で確認。呼ばれていなければ **直ちに c 案** (mutation gate スキップ可)。
3. **mutation 適用:** 対象関数本体を「最小限の wrong return」で置換。docstring と signature は不変。
   - 戻り値が list → `return []`
   - 戻り値が Optional[X] → `return None`
   - 戻り値が dict → `return {}`
   - 戻り値が tuple → `return (None, None)` 相当の壊し方
   - 副作用関数（mutation）→ 早期 `return` で何もせず終わらせる
4. **E2E 走行:** 当該 production を踏む E2E テストクラスを実行 (各ファイルで命名規約から特定する。例: `TestE2EProc`, `TestE2EAll`, `TestE2EC`, `TestIntenseE2E`)。
   ```bash
   python -m unittest tests.<test_file>.<E2E_class_name> 2>&1 | tail -10
   ```
5. **判定:**
   - **赤化した** → b 案成立。次へ。
   - **赤化しない** → 別 mutation を 1〜2 通り試す (e.g., 異なる返り値、副作用ありの値)。それでも全 pass なら **b 案不成立 → c 案 fallback**。
6. **production 復元:**
   ```bash
   git checkout grep_helper/<file>.py
   git diff grep_helper/
   ```
   `git diff grep_helper/` が空であることを必ず確認。
7. **全テスト green 確認:**
   ```bash
   python -m unittest discover -s tests 2>&1 | tail -3
   ```
8. **テスト削除を実施。**

### E. Banner deletion policy (Wave 1 から踏襲)

各テストファイルでクラス間に以下のような ASCII バナーが存在することがある:

```python
# ---------------------------------------------------------------------------
# TestXxx
# ---------------------------------------------------------------------------
```

ルール:
- **削除するクラスのバナーはクラスごと削除する** (3 行 + 直後の空行)。
- **次のクラスのバナーは残す** (ファイル内ナビゲーション landmark)。
- **rename だけのクラス (Whitebox 化) のバナーは旧名のまま残す** (Wave 1 と一貫した policy)。

### F. b 案削除時の commit message テンプレート

```
test(<file>): delete <ClassName> after E2E mutation confirm (b 案)

判定: <ClassName> は private helper / public 関数だが E2E に包摂、削除可能と判定。
- 対象関数: <function_name> at grep_helper/<path>:<line>
- mutation 確認: 関数本体を `<mutation>` に置換すると <E2EClassName> が
  赤くなることを確認、production を復元してから削除
- <N> メソッドすべて E2E に包摂されているため削除可能

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### G. c 案 (Whitebox 化) commit message テンプレート

```
test(<file>): isolate <ClassName> to Whitebox (c 案)

判定: <ClassName> は <理由 (private / 公開だが orchestrator 未経由 / 内部 dict peek 等)>。
- TestXxx → TestXxxWhitebox に rename
- Whitebox 理由 + 「実装変更時は本クラスも同期更新が必要」の docstring を付与

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### H. a 案 / keep の docstring 整理 commit message テンプレート

```
test(<file>): refine <ClassName> docstring (<a 案 → keep / 純 keep>)

<対象関数> の公開 API テストとして keep。docstring を WHAT 中心 + 保持理由を
明示する形に書き換え。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### I. 1 ファイル = 1 タスク内の commit 単位

各 Task 内で行う commit は判定区分ごとに分ける（Wave 1 と同じ粒度）：
- c 案クラス群 → 1 commit (まとめてもバラしてもよい。同ファイル内 c 案が複数あればまとめる)
- b 案クラス → クラス 1 つにつき 1 commit (mutation gate ごと)
- a 案 / keep の docstring 整理 → 1 commit (まとめる)

判定区分が単一なら 1 commit でもよい。

### J. Mutation 取り残しの最終チェック

各 Task の最終 commit 直前に必ず:
```bash
git diff grep_helper/
```
を実行し空であることを確認。空でなければ mutation の取り残しがある（**絶対にコミットしない**）。`git checkout grep_helper/` で復元してから commit。

### K. テストメソッド名 WHAT 改善 (selective)

**目的:** WHAT が現状のメソッド名で obscure になっている箇所のみ改名し、テストの読み手が「何を観察するテストか」を一目で把握できるようにする。

**理想形 (spec-as-collection):** `grep "def test_" <file>.py` の出力（メソッド名の集合）だけを読んで、対象 module / class の振る舞い仕様（仕様書）になっている状態が理想。すなわち：
- 各名前は **観察可能な振る舞いの 1 行 spec**（input → output / cause → effect）。
- 集合として **対象の振る舞い表面を網羅** している（重複に見える名前は実は意味的差分があるか、または 1 件に集約すべきか、判断する）。
- テストコードを読まなくても、名前列だけで「何が保証されているか」がわかる。

この理想に **近づける改名のみ** を実施する（個々の名前が WHAT を表現していても、集合として読みづらい・重複している場合は調整する）。

**改名トリガー (改名する):**

| 兆候 | 例 (改名前 → 改名後) |
|---|---|
| 末尾「こと」が冗長で WHAT 表現を弱める | `test_TSV出力の列数が9列であること` → `test_TSV出力の列数が9列である` |
| HOW / WHY 漏れ (WHAT に絞ると簡潔になる) | `test_UTF8_BOM付きで出力されExcelで文字化けしない` → `test_TSV出力がUTF8_BOMで始まる` |
| 漠然動詞 (`正しく` / `適切に` / `ちゃんと`) | `test_AST使用時に定数定義を正しく分類する` → `test_AST使用時の定数定義は定数_変数宣言に分類される` |
| 同一 WHAT を別表現で複数件 (重複疑い) | 3 件で文言だけ差分 → 統一名 1 件に集約か、意味的差分があるなら明示 |
| 関数名のみで WHAT 不明 | `test_findall` → `test_findallが全マッチ位置のリストを返す` |
| `test_basic` / `test_works` / `test_simple` 等の generic | 観察対象を明示した名前へ |

**改名禁止 (触らない):**

- 既に WHAT を明示しており、表現の好み程度の違いしかない場合 (e.g. 「〜に分類する」と「〜と分類される」の能動受動だけの差) — これは stylistic につき触らない。
- 同じファイル内で揃ってないだけで、各々は WHAT を表現できている場合 — mass standardize はしない。
- WHAT 観察ではなく Whitebox/keep の判定で削除されるクラスのメソッド — 削除するなら改名不要。

**改名手順:**

1. 対象ファイルの `def test_xxx(self):` 行を grep して全メソッド名を一覧。
2. 改名トリガーに該当するものだけマーキング (table 形式で内部メモ)。
3. メソッド名を Edit で変更。**メソッド本体は変更しない**。
4. 同名参照がないか念のため確認 (テスト名は通常 self-reference のみで他から呼ばれないが、`unittest` の test selector で specific 名指しされている可能性も考慮):
   ```bash
   grep -rn "<旧メソッド名>" tests/ scripts/ docs/ 2>/dev/null
   ```
5. テスト実行で全メソッドが run/pass することを確認.

**コミット粒度:** メソッド名改名は **判定アクション (c/b/a) とは別の独立コミット** にする。1 ファイル内で 1 コミット。コミットメッセージ:

```
test(<file>): rename test methods for clearer WHAT (selective)

WHAT が obscure になっていた N 件のメソッド名を改善：
- <旧名> → <新名> (理由: <冗長「こと」/HOW 漏れ/重複/...>)
- ...

メソッド本体は不変、件数も不変。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

該当が 0 件なら commit 不要。

---

### Task 1: ベースライン確認 & Wave 2 棚卸し

**Files:**
- Verify only

- [ ] **Step 1: 現在のテストグリーンを確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 376 tests ... OK` (Wave 1 完了時点の件数)。

- [ ] **Step 2: Wave 1 完了 SHA を控える**

```bash
git rev-parse HEAD && git log --oneline -1
```

Expected: 直近コミットが Wave 1 の最終コミット (`0a319d9` 系) であることを確認。違う場合は基底ブランチを確認して停止。

- [ ] **Step 3: 各 14 ファイルの現クラス数を控える**

```bash
for f in tests/test_aho_corasick.py tests/test_all_analyzer.py tests/test_analyze_proc.py tests/test_c_analyzer.py tests/test_common.py tests/test_dotnet_analyzer.py tests/test_groovy_analyzer.py tests/test_kotlin_analyzer.py tests/test_perl_analyzer.py tests/test_plsql_analyzer.py tests/test_python_analyzer.py tests/test_sh_analyzer.py tests/test_sql_analyzer.py tests/test_ts_analyzer.py; do
  echo "=== $f ==="
  grep -nE "^class Test" "$f"
done
```

Expected: 14 ファイルの全 60 クラスが出力される。

- [ ] **Step 4: Wave 2 開始 SHA を記録する** (Task 16 で diff 検算に使用)

控えた SHA をメモする (例: `WAVE2_BASE=$(git rev-parse HEAD)`)。

---

### Task 2: tests/test_aho_corasick.py (37L, 1 class, 4 methods)

**Files:**
- Modify: `tests/test_aho_corasick.py`
- Touch (一時的): なし想定 (純 keep の可能性が高い、aho-corasick はライブラリラッパーで public API テスト)

- [ ] **Step 1: クラス棚卸し**

```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_aho_corasick.py | head -30
cat tests/test_aho_corasick.py
```

37 行と短いので全文を読み、各 assertion の shape を確認する。

- [ ] **Step 2: 判定**

`共通の事前確認事項 A` の判定ロジックに従って `TestAhoCorasick` を分類する。

判定の選択肢:
- 公開 API (`AhoCorasick` クラスや関数) を `assertEqual` で観察しているなら **純 keep**。
- 内部 trie 構造や private state を peek しているなら **c 案** Whitebox。
- private helper で E2E 包摂可能性があるなら **b 案** 候補 (まれ)。

判定結果を以下のフォーマットで内部メモする:
```
TestAhoCorasick: <判定> (理由: ...)
```

- [ ] **Step 3: アクション適用**

判定に応じて：
- **純 keep:** 触らない (またはクラス docstring が薄ければ任意で `共通の事前確認事項 C` の形に整える)。
- **a 案:** docstring を `共通の事前確認事項 C` の形に書き換え。
- **c 案:** クラス名 + docstring を `共通の事前確認事項 B` の形に変更 (`TestAhoCorasick` → `TestAhoCorasickWhitebox`)。
- **b 案:** `共通の事前確認事項 D` の Mutation Gate を通す → 削除。

- [ ] **Step 4: 全テスト green 確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <件数> tests ... OK`. b 案削除した場合のみ件数が減る。

- [ ] **Step 5: production 差分なし確認**

```bash
git diff grep_helper/
```

Expected: 空。

- [ ] **Step 6: コミット**

判定区分に応じて `共通の事前確認事項 F/G/H` のテンプレートでコミット。判定区分が「純 keep で何も変更なし」なら commit を打たずに次の Task へ。

例 (純 keep で docstring 軽微整理だった場合):
```bash
git add tests/test_aho_corasick.py
git commit -m "$(cat <<'EOF'
test(test_aho_corasick): refine TestAhoCorasick docstring (純 keep)

Aho-Corasick の公開 API テスト。判定マトリクス Wave 2 で純 keep と確認、
docstring を WHAT 中心に整理。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: tests/test_python_analyzer.py (79L, 2 classes, 9 methods)

**Files:**
- Modify: `tests/test_python_analyzer.py`
- Touch (一時的): `grep_helper/languages/python.py` (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**

```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_python_analyzer.py
grep -nE "^from grep_helper" tests/test_python_analyzer.py
```

- [ ] **Step 2: 各クラスの判定**

`共通の事前確認事項 A` の判定ロジックを 2 クラスに適用。

各クラスについて以下を確認:
- assertion shape (WHAT 観察 vs 内部 peek)
- テスト対象が public/private か (`grep_helper/languages/python.py` を grep)
- E2E (TestE2EPython など命名規約) が当該経路を踏んでいるか

判定結果を以下のフォーマットで内部メモする:
```
ClassA: <判定> (理由: ...)
ClassB: <判定> (理由: ...)
```

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば)

c 案と判定したクラスを `共通の事前確認事項 B` の形で rename + docstring 付与。複数あればまとめて 1 commit。

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば)

`共通の事前確認事項 D` の Mutation Gate 共通手順を実行。クラスごとに 1 mutation + 1 削除 + 1 commit。

各 mutation 後に必ず `git checkout grep_helper/languages/python.py` + `git diff grep_helper/` が空であることを確認。

precondition 不成立なら c 案 fallback（Step 3 と同じパターンで rename 化、commit message には fallback と明記）。

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば)

`共通の事前確認事項 C` の形で docstring を書き換え、まとめて 1 commit。

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <件数> tests ... OK`。b 案削除した場合のみ件数が減る。

- [ ] **Step 7: production 差分なし確認**

```bash
git diff grep_helper/
```

Expected: 空。

- [ ] **Step 8: コミット履歴確認**

```bash
git log --oneline | head -5
```

判定区分の数と commit 数が一致することを目視確認。

---

### Task 4: tests/test_sh_analyzer.py (59L, 2 classes, 15 methods)

**Files:**
- Modify: `tests/test_sh_analyzer.py`
- Touch (一時的): `grep_helper/languages/sh.py` (b 案 mutation 該当のみ)

Task 3 と同一構造の 8 ステップを適用。production ファイル名のみ `grep_helper/languages/sh.py` に置き換え。

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_sh_analyzer.py
grep -nE "^from grep_helper" tests/test_sh_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (`共通の事前確認事項 A`)

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -5
```

---

### Task 5: tests/test_sql_analyzer.py (75L, 2 classes, 13 methods)

**Files:**
- Modify: `tests/test_sql_analyzer.py`
- Touch (一時的): `grep_helper/languages/sql.py` (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_sql_analyzer.py
grep -nE "^from grep_helper" tests/test_sql_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (`共通の事前確認事項 A`)

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -5
```

---

### Task 6: tests/test_ts_analyzer.py (83L, 2 classes, 10 methods)

**Files:**
- Modify: `tests/test_ts_analyzer.py`
- Touch (一時的): `grep_helper/languages/ts.py` または対応する production パス (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_ts_analyzer.py
grep -nE "^from grep_helper" tests/test_ts_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (`共通の事前確認事項 A`)

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -5
```

---

### Task 7: tests/test_perl_analyzer.py (91L, 2 classes, 12 methods)

**Files:**
- Modify: `tests/test_perl_analyzer.py`
- Touch (一時的): `grep_helper/languages/perl.py` (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_perl_analyzer.py
grep -nE "^from grep_helper" tests/test_perl_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (`共通の事前確認事項 A`)

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -5
```

---

### Task 8: tests/test_plsql_analyzer.py (99L, 2 classes, 12 methods)

**Files:**
- Modify: `tests/test_plsql_analyzer.py`
- Touch (一時的): `grep_helper/languages/plsql.py` (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_plsql_analyzer.py
grep -nE "^from grep_helper" tests/test_plsql_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (`共通の事前確認事項 A`)

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -5
```

---

### Task 9: tests/test_kotlin_analyzer.py (158L, 4 classes, 15 methods)

**Files:**
- Modify: `tests/test_kotlin_analyzer.py`
- Touch (一時的): `grep_helper/languages/kotlin.py` または対応する production パス (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_kotlin_analyzer.py
grep -nE "^from grep_helper" tests/test_kotlin_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (4 クラス、`共通の事前確認事項 A`)

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -5
```

---

### Task 10: tests/test_dotnet_analyzer.py (181L, 4 classes, 22 methods)

**Files:**
- Modify: `tests/test_dotnet_analyzer.py`
- Touch (一時的): `grep_helper/languages/dotnet.py` または対応する production パス (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_dotnet_analyzer.py
grep -nE "^from grep_helper" tests/test_dotnet_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (4 クラス、`共通の事前確認事項 A`)

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -5
```

---

### Task 11: tests/test_groovy_analyzer.py (197L, 7 classes, 23 methods)

**Files:**
- Modify: `tests/test_groovy_analyzer.py`
- Touch (一時的): `grep_helper/languages/groovy.py` または対応する production パス (b 案 mutation 該当のみ)

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_groovy_analyzer.py
grep -nE "^from grep_helper" tests/test_groovy_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (7 クラス、`共通の事前確認事項 A`)

クラス数が増えるため、判定結果は table 形式で内部メモする:
```
| Class | 判定 | 理由 |
|---|---|---|
| TestX1 | ... | ... |
| TestX2 | ... | ... |
...
```

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

クラスごとに mutation を試行、復元、削除（または fallback）を 1 サイクルとして処理。

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -10
```

---

### Task 12: tests/test_c_analyzer.py (260L, 7 classes, 28 methods)

**Files:**
- Modify: `tests/test_c_analyzer.py`
- Touch (一時的): `grep_helper/languages/c.py` または `grep_helper/languages/c_*.py` (b 案 mutation 該当のみ)

既知の構造（Task 1 の grep 結果から）:
- `TestClassifyUsageC`, `TestExtractDefineName`, `TestExtractVariableNameC`, `TestBuildDefineMap`, `TestCollectDefineAliases`, `TestE2EC`, `TestDefineMapWithReverse`

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_c_analyzer.py
grep -nE "^from grep_helper" tests/test_c_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (7 クラス、`共通の事前確認事項 A`)

`TestE2EC` は判定上 **触らない (純 keep の中核)**。残り 6 クラスを分類。`_extract_define_name`, `_build_define_map`, `_collect_define_aliases` などは private helper 候補のため、b 案候補として精査する。

判定結果は Task 11 同様 table 形式で内部メモ。

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

mutation 対象は `TestE2EC` を中心に走らせる:
```bash
python -m unittest tests.test_c_analyzer.TestE2EC 2>&1 | tail -10
```

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -10
```

---

### Task 13: tests/test_common.py (372L, 10 classes, 32 methods)

**Files:**
- Modify: `tests/test_common.py`
- Touch (一時的): `grep_helper/grep_input.py`, `grep_helper/model.py`, `grep_helper/file_cache.py`, `grep_helper/tsv_output.py`, または各種共通 module (b 案 mutation 該当のみ)

`test_common.py` は複数 module 横断のテストが含まれる可能性あり。Task 1 で得た grep 結果と冒頭の import から各クラスの対応 production module を特定する。

- [ ] **Step 1: クラス棚卸しと production 対応の特定**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_common.py
grep -nE "^from grep_helper" tests/test_common.py
```

各クラスがどの production module をテストしているかを冒頭で内部メモする (e.g. `TestX1 → grep_helper/grep_input.py`).

- [ ] **Step 2: 各クラスの判定** (10 クラス、`共通の事前確認事項 A`)

判定結果は table 形式で内部メモ。

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

mutation 走行先は対象 module に依存。test_common.py の中の E2E 系クラスがあればそれを中心に、なければ整合性のある E2E (e.g. `TestE2EAll` from test_all_analyzer.py や `TestIntegration` from test_analyze.py) を走らせる。複数 mutation を試す場合、production module ごとに `git checkout` で復元する範囲を明示する。

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -10
```

---

### Task 14: tests/test_analyze_proc.py (430L, 9 classes, 38 methods)

**Files:**
- Modify: `tests/test_analyze_proc.py`
- Touch (一時的): `grep_helper/languages/proc.py`, `grep_helper/languages/proc_define_map.py`, `grep_helper/languages/proc_track.py` (b 案 mutation 該当のみ)

既知の構造（Task 1 の grep 結果から）:
- `TestParseGrepLine`, `TestClassifyUsageProc`, `TestExtractDefineName`, `TestBuildDefineMapProc`, `TestExtractVariableNameProc`, `TestWriteTsv`, `TestE2EProc`, `TestDispatch`, `TestE2EMixed`

`TestE2EProc` と `TestE2EMixed` は判定上 **触らない (純 keep の中核)**。

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_analyze_proc.py
grep -nE "^from grep_helper" tests/test_analyze_proc.py
```

- [ ] **Step 2: 各クラスの判定** (9 クラス、`共通の事前確認事項 A`)

判定結果は table 形式で内部メモ。

注: `TestParseGrepLine` と `TestWriteTsv` は `grep_helper/grep_input.py` / `grep_helper/tsv_output.py` の公開 API テスト。Wave 1 の `TestGrepParser` / `TestTsvWriter` (test_analyze.py) と重複の可能性あり。重複している場合は本ファイル側を **a 案** で保持理由を明記、もしくは判定保留してユーザに諮る。

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

`TestExtractDefineName` / `TestBuildDefineMapProc` / `TestExtractVariableNameProc` は private helper のテストの可能性が高い。判定後に Whitebox 化または b 案 Mutation Gate を選択。

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

mutation 走行先:
```bash
python -m unittest tests.test_analyze_proc.TestE2EProc tests.test_analyze_proc.TestE2EMixed 2>&1 | tail -10
```

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -15
```

---

### Task 15: tests/test_all_analyzer.py (472L, 6 classes, 51 methods)

**Files:**
- Modify: `tests/test_all_analyzer.py`
- Touch (一時的): `grep_helper/dispatcher.py`, `grep_helper/languages/__init__.py` (`detect_handler`), または各種 language module (b 案 mutation 該当のみ)

既知の構造（Task 1 の grep 結果から）:
- `TestDetectLanguage`, `TestDirectClassification`, `TestIndirectTracking`, `TestE2EAll`, `TestProcessGrepLinesAllIterable`, `TestMainStreaming`

`TestE2EAll` と `TestMainStreaming` は判定上 **触らない (純 keep の中核)**。

- [ ] **Step 1: クラス棚卸し**
```bash
grep -nE "^class Test|^    def test_|^    \"\"\"" tests/test_all_analyzer.py
grep -nE "^from grep_helper" tests/test_all_analyzer.py
```

- [ ] **Step 2: 各クラスの判定** (6 クラス、`共通の事前確認事項 A`)

判定結果は table 形式で内部メモ。

注: `TestProcessGrepLinesAllIterable` は public 関数 `process_grep_lines` のテストの可能性。dispatcher 経由で E2E が観察するか、最小ケースで残すか（a 案 keep）を判定。

- [ ] **Step 3: c 案クラスの Whitebox 化** (該当があれば、`共通の事前確認事項 B`)

- [ ] **Step 4: b 案候補の Mutation Gate** (該当があれば、`共通の事前確認事項 D`)

mutation 走行先:
```bash
python -m unittest tests.test_all_analyzer.TestE2EAll tests.test_all_analyzer.TestMainStreaming 2>&1 | tail -10
```

- [ ] **Step 5: a 案 / keep の docstring 整理** (該当があれば、`共通の事前確認事項 C`)

- [ ] **Step 5b: テストメソッド名 WHAT 改善 (selective)** (`共通の事前確認事項 K` に従う)

該当があれば、メソッド本体は不変のまま `def test_xxx(self):` 行のみ rename。判定区分とは別の独立 commit。該当 0 件なら commit 不要。

- [ ] **Step 6: 全テスト green 確認**
```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

- [ ] **Step 7: production 差分なし確認**
```bash
git diff grep_helper/
```
Expected: 空。

- [ ] **Step 8: コミット履歴確認**
```bash
git log --oneline | head -15
```

---

### Task 15.5: 遡及メソッド名 WHAT 改善 (test_analyze.py + test_aho_corasick.py)

**Files:**
- Modify: `tests/test_analyze.py` (Wave 1 で整理済、約 92 メソッド)
- Modify: `tests/test_aho_corasick.py` (Wave 2 Task 2 で no-op 判定済、4 メソッド)

**WHY:** Wave 1 (test_analyze.py) と Wave 2 Task 2 (test_aho_corasick.py) はメソッド名 WHAT 改善の指針が確立する前に通過した。本 Task で遡及的に `共通の事前確認事項 K` を適用し、Wave 2 全体で一貫した「メソッド名集合 = 動く仕様」状態に揃える。

- [ ] **Step 1: test_analyze.py のメソッド名一覧を取得**

```bash
grep -nE "^    def test_" tests/test_analyze.py
```

92 件のメソッド名を取得。クラス単位でグループ化して内部メモする。

- [ ] **Step 2: test_aho_corasick.py のメソッド名一覧を取得**

```bash
grep -nE "^    def test_" tests/test_aho_corasick.py
```

4 件のメソッド名を取得。

- [ ] **Step 3: K の改名トリガーで両ファイル全メソッドを評価**

各メソッド名を K の改名トリガー (冗長「こと」/HOW 漏れ/漠然動詞/重複表現/関数名のみ/generic) に照らして評価。改名候補を table 形式で内部メモ:

```
| File | Class | 旧名 | 新名 | 理由 |
|---|---|---|---|---|
| test_analyze.py | TestX | test_old1 | test_new1 | 冗長「こと」 |
| ... |
```

K の「改名禁止」条件に該当するものは触らない（stylistic 違いのみ・揃ってないだけ・削除予定クラスは対象外）。

- [ ] **Step 4: spec-as-collection の観点で全体を見直す**

Step 3 で挙げた候補に加えて、K の理想形「集合として読んで仕様になる」観点でファイルごとにメソッド名一覧を眺め、追加の改名候補がないか確認:
- 同一 WHAT を別表現で書いてある複数件 → 統一名へ
- クラス内で書きぶりが揃っていない (一部は能動、一部は受動 等) で、揃えると集合として読みやすくなる場合 → 統一

ただし「揃ってないが各々が WHAT を表現している」だけならスキップ（K の改名禁止）。

- [ ] **Step 5: test_analyze.py の改名を適用**

候補に挙がったメソッド名を Edit で書き換え。本体は不変。

- [ ] **Step 6: test_analyze.py 単独で green 確認**

```bash
python -m unittest tests.test_analyze 2>&1 | tail -3
```

Expected: テスト件数不変、すべて OK。

- [ ] **Step 7: test_analyze.py コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): rename test methods for clearer WHAT (selective, retroactive)

Wave 1 完了後に Wave 2 で確立した「メソッド名 = spec」原則 (共通事項 K) を
遡及適用。WHAT が obscure になっていた N 件のメソッド名を改善：
- <旧名> → <新名> (理由: ...)
- ...

メソッド本体は不変、件数も不変。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

該当 0 件なら commit 不要。

- [ ] **Step 8: test_aho_corasick.py の改名を適用**

候補に挙がったメソッド名を Edit で書き換え。本体は不変。

- [ ] **Step 9: test_aho_corasick.py 単独で green 確認**

```bash
python -m unittest tests.test_aho_corasick 2>&1 | tail -3
```

Expected: テスト件数不変、すべて OK。

- [ ] **Step 10: test_aho_corasick.py コミット**

```bash
git add tests/test_aho_corasick.py
git commit -m "$(cat <<'EOF'
test(test_aho_corasick): rename test methods for clearer WHAT (selective, retroactive)

Wave 2 Task 2 で no-op 判定したファイルにメソッド名 WHAT 改善を遡及適用。
WHAT が obscure になっていた N 件のメソッド名を改善：
- <旧名> → <新名> (理由: ...)
- ...

メソッド本体は不変、件数も不変。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

該当 0 件なら commit 不要。

- [ ] **Step 11: 全テスト green 確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran <件数> tests ... OK`. メソッド名改名は件数を変えないため、Task 15 後の件数を維持。

- [ ] **Step 12: production 差分なし確認**

```bash
git diff grep_helper/
```

Expected: 空。

---

### Task 16: Wave 2 完了確認 & 報告

**Files:**
- Verify only

- [ ] **Step 1: 全体テストグリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `OK`. 失敗があれば該当を報告して止める。

- [ ] **Step 2: production 差分なし確認** (Wave 2 全体)

```bash
git diff <Task 1 で控えた SHA>..HEAD -- grep_helper/
```

Expected: 差分なし（全 b 案 mutation はすべて復元したはず）。差分があれば mutation の取り残しを修正し、補正コミットを打つ。

- [ ] **Step 3: コミット履歴の連続性確認**

```bash
git log --oneline <Task 1 SHA>..HEAD
```

Expected: Task 2〜15.5 の各 commit が順に並ぶ（純 keep 触らずスキップした Task は commit 0 件もありうる）。判定アクション commit と method-name 改名 commit は別々に並ぶ。

- [ ] **Step 4: 最終クラス棚卸し + メソッド名集合の俯瞰**

```bash
for f in tests/test_aho_corasick.py tests/test_all_analyzer.py tests/test_analyze_proc.py tests/test_c_analyzer.py tests/test_common.py tests/test_dotnet_analyzer.py tests/test_groovy_analyzer.py tests/test_kotlin_analyzer.py tests/test_perl_analyzer.py tests/test_plsql_analyzer.py tests/test_python_analyzer.py tests/test_sh_analyzer.py tests/test_sql_analyzer.py tests/test_ts_analyzer.py; do
  echo "=== $f ==="
  grep -nE "^class Test" "$f"
done
```

各ファイルでの判定結果（純 keep / a 案 / Whitebox / 削除）の最終内訳をまとめる。

加えて、メソッド名集合が「動く仕様」になっているか俯瞰確認:

```bash
for f in tests/test_*.py; do
  echo "=== $f ==="
  grep -nE "^    def test_" "$f"
done
```

ファイル単位で「メソッド名一覧だけを読んで対象 module の振る舞い仕様になっているか」を最終確認。明らかに spec として読みにくい箇所が残っていれば追記コミットも検討。

- [ ] **Step 5: ユーザーへの報告内容**

報告に含める：
- 各 Task ごとの判定内訳 (純 keep / a 案 / Whitebox / 削除 の件数)
- Wave 2 で **Whitebox 化したクラス**の名前と理由
- Wave 2 で **削除したクラス**の名前と mutation 確認結果
- Wave 2 で **b 案不成立 → c 案 fallback** したクラスがあれば名前と mutation 試行履歴
- 各ファイルの **メソッド名改名件数** (Step 5b 由来) と Task 15.5 の遡及改名件数
- 全体テスト件数推移 (376 → 終了時)
- production 差分なし確認
- 全体テストグリーン状態

---

## 自己レビュー結果

- 推奨着手順 (Task 2 → Task 15、小さい順) を厳守する構成。判定ロジックを小さいファイルで習熟してから大きいファイルに進む。
- 全 b 案 Task で E2E mutation 確認をゲートに削除（Wave 1 Task 7 の経験：empirical 確認は必須）。
- production への変更は b 案 mutation のみで、各 Task の Step 7 で `git diff grep_helper/` 空を確認。
- 判定ロジック・Whitebox docstring template・Mutation Gate 手順・banner policy・commit message テンプレートを「共通の事前確認事項」に集約し、各 Task はそれを参照することで本文を short に保った。
- Task 11-15（クラス数 4-10）は table 形式で判定結果を内部メモする指示を明示し、subagent が大きい file で判断を整理しやすくした。
- Task 4-10 は Task 3 と同一構造の 8 ステップで、ファイル名と production パスのみ差し替え。subagent が plan を読みながら同パターンで動ける。
- Task 12-15（中規模・大規模ファイル）は冒頭に既知のクラス構造を明記し、subagent が判定の起点を素早く決められるようにした。
- Wave 1 で発生した「pre-judgment と empirical の乖離」を Mutation Gate 不成立時の **c 案 fallback** として明文化（Wave 1 Task 7 と同じ運用）。
- 報告ステップ (Task 16) で Wave 2 全体の judgment 内訳を集計、次の wave があるとすればそこから引き継げる形にした。
