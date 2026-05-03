# Test Style Rework — Sweep Wave 1 Phase 1 (test_analyze.py) 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スイープ第一弾 `tests/test_analyze.py` の **準備フェーズ** を完了する：(1) 機械的な低リスク作業（パターン F = メソッド docstring 削除）を全 26 クラスに適用し、(2) 残るスタイル翻訳が必要なクラス群について a/b/c/keep の **判定マトリクス** を作成する。**翻訳本体は本プランの範囲外**（Phase 2 プランで実施）。

**Architecture:** 判定根拠を曖昧にしたまま削除しない、というパイロット G スパイク所見を厳格に守るため、本プランでは **判定 ≠ 実行** を分離する。Phase 1 の成果物は (a) docstring のないクリーンな test_analyze.py と (b) 全 26 クラスの判定が表で読める Markdown 1 枚。Phase 2 はこの表を入力に動く。

**Tech Stack:** Python 3, `unittest`, `ast` (静的検査用)。

**Reference:**
- パイロット仕様: `docs/superpowers/specs/2026-05-03-test-style-rework-design.md`
- パイロット結果: `tests/test_common.py`（全 7 パターン適用済み）
- パイロットプラン: `docs/superpowers/plans/2026-05-03-test-style-rework-pilot.md`

---

## Phase 1 の対象棚卸し

`tests/test_analyze.py`（1771 行・26 クラス・99 メソッド・全メソッド日本語名・全メソッド docstring あり）。

| 行 | クラス | メソッド数 | 判定の事前推測 |
|---|---|---|---|
| 79 | TestGrepParser | 6 | keep（公開関数 `parse_grep_line` のテスト） |
| 126 | TestUsageClassifier | 10 | keep（公開関数 `classify_usage` のテスト） |
| 178 | TestTsvWriter | 6 | keep |
| 268 | TestIndirectTracker | 8 | keep |
| 332 | TestReporter | 4 | keep |
| 380 | TestIntegration | 1 | keep（E2E） |
| 451 | TestProcessGrepFile | 5 | keep |
| 527 | TestGetAst | 4 | keep（公開関数 `_get_ast` 周辺の WHAT） |
| 572 | TestClassifyUsage | 5 | keep |
| 656 | TestResolveJavaFile | 4 | 要判定（`resolve_java_file` の公開度を確認） |
| 688 | TestGetMethodScope | 3 | **b 案（削除）** — スパイクで判定済み |
| 727 | TestSearchInLines | 3 | 要判定（spike 候補） |
| 813 | TestTrackConstant | 2 | 要判定（spike 候補） |
| 863 | TestTrackField | 2 | 要判定（spike 候補） |
| 919 | TestTrackLocal | 2 | 要判定（spike 候補） |
| 983 | TestFindGetterNames | 4 | 要判定 |
| 1030 | TestFindSetterNames | 3 | 要判定 |
| 1067 | TestTrackGetterCalls | 2 | 要判定 |
| 1123 | TestBuildParser | 3 | 要判定 |
| 1157 | TestMain | 5 | keep（CLI smoke） |
| 1255 | TestGetAstExceptionHandling | 1 | keep |
| 1284 | TestIntenseE2E | 10 | keep（大規模 E2E） |
| 1666 | TestBatchTrackSetters | 1 | 要判定 |
| 1694 | TestBatchTrackOnePass | 2 | 要判定 |
| 1728 | TestNoModuleGlobalEncoding | 1 | keep（モジュール契約） |
| 1735 | TestParallelBatchTrack | 2 | keep |

**注:** 「判定の事前推測」は呼び水。実際の判定は Task 3 で各クラスのコードと production を読んで再決定する。

---

## File Structure

- **Modify:** `tests/test_analyze.py`（Task 2 で docstring 一括削除）
- **Create:** `docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md`（Task 3 の成果物）
- **No changes:** `grep_helper/`、他のテストファイル

---

### Task 1: ベースライン確認

**Files:**
- Verify only: `tests/test_analyze.py`

- [ ] **Step 1: 現状の test_analyze.py がグリーンであることを確認**

```bash
python -m unittest tests.test_analyze 2>&1 | tail -3
```

Expected: 末尾に `OK` を含むサマリ。失敗があればここで停止し、原因を報告する（このプラン外の問題）。

- [ ] **Step 2: 全体テストグリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 383 tests ... OK`。

- [ ] **Step 3: 開始 SHA を控える**

```bash
git rev-parse HEAD
```

控えた SHA は Task 4 のステップ 2 でレポートに含める。

---

### Task 2: パターン F 一括適用 — test_analyze.py 全メソッドの docstring 削除

**Files:**
- Modify: `tests/test_analyze.py`（全 99 メソッド）

**WHY:** メソッド名が日本語で WHAT を表現しているため docstring は完全に冗長（例：`def test_バイナリ通知行はNoneを返す(self):` の直下に `"""バイナリ通知行はNoneを返すこと。"""`）。仕様パターン F に従う。**クラス docstring（`class Test...:` 直下）は据え置き** — クラスレベルの分類タグ（"F-01"・"F-03 内部" 等）が含まれる場合があるため触らない。

- [ ] **Step 1: 削除対象を ast で機械抽出して正確に削除する**

`scripts/_drop_method_docstrings.py` のような一時スクリプトは使わず、Python のワンライナーで安全に置換する：

```bash
python3 - <<'PY'
import ast, io, tokenize, pathlib

path = pathlib.Path("tests/test_analyze.py")
src = path.read_text(encoding="utf-8")
tree = ast.parse(src)

# 削除対象: テストメソッド直下の string-only Expr 文
ranges = []
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                if item.body and isinstance(item.body[0], ast.Expr) and isinstance(item.body[0].value, ast.Constant) and isinstance(item.body[0].value.value, str):
                    ds = item.body[0]
                    ranges.append((ds.lineno, ds.end_lineno))

# 行ベースで削除（後ろから消すことで行番号がズレない）
lines = src.splitlines(keepends=True)
for start, end in sorted(ranges, reverse=True):
    del lines[start - 1 : end]

path.write_text("".join(lines), encoding="utf-8")
print(f"Removed {len(ranges)} method docstrings.")
PY
```

Expected: `Removed 99 method docstrings.`。

- [ ] **Step 2: 構文・スタイル健全性を確認**

```bash
python -m py_compile tests/test_analyze.py && echo "syntax ok"
```

Expected: `syntax ok`。

```bash
python3 -c "
import ast
tree = ast.parse(open('tests/test_analyze.py').read())
remaining = 0
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name.startswith('Test'):
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name.startswith('test_'):
                if item.body and isinstance(item.body[0], ast.Expr) and isinstance(item.body[0].value, ast.Constant) and isinstance(item.body[0].value.value, str):
                    remaining += 1
print(f'method docstrings remaining: {remaining}')"
```

Expected: `method docstrings remaining: 0`。

- [ ] **Step 3: クラス docstring が消えていないことを確認**

```bash
python3 -c "
import ast
tree = ast.parse(open('tests/test_analyze.py').read())
class_ds = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name.startswith('Test') and ast.get_docstring(n))
print(f'class docstrings remaining: {class_ds}')"
```

Expected: 26（全クラスがクラス docstring を保持）。**26 未満なら Step 1 のスクリプトが過剰削除している** ので Stop & Report。

- [ ] **Step 4: グリーン確認**

```bash
python -m unittest tests.test_analyze 2>&1 | tail -3
```

Expected: `Ran 99 tests ... OK`（docstring 削除はテスト挙動を変えない）。

- [ ] **Step 5: 全体グリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 383 tests ... OK`。

- [ ] **Step 6: コミット**

```bash
git add tests/test_analyze.py
git commit -m "$(cat <<'EOF'
test(test_analyze): drop redundant method docstrings (pattern F)

メソッド名が日本語で WHAT を表現しているため docstring は冗長。
spec パターン F に従い 99 メソッド分を ast 経由で機械削除。
クラス docstring（"F-01" 等の分類タグを含む）は据え置き。

スイープ第一弾 (test_analyze.py) Phase 1 の機械的低リスク作業。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 判定マトリクス作成 — 26 クラスを a/b/c/keep に分類

**Files:**
- Create: `docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md`

**目的:** Phase 2 プランの **入力** となる判定表を作る。各クラスについて、現状のテストが (a) 公開 API 経由テストへ統合可能 / (b) E2E ゴールデンに包摂されており削除可能 / (c) Whitebox 隔離が必要 / **keep** = 既に WHAT 検証で問題なし のいずれかを判定し、根拠と次の Phase 2 アクションを記す。

**判定基準（パイロット G スパイク所見より）:**

クラスごとに以下 3 点を確認して判定する：

1. **テストが叩いている関数の公開度** — `from grep_helper... import` 行を読み、private (`_` 始まり) か public か。
2. **公開 API が同じ private を直接呼ぶか** — `grep -n "_xxx" grep_helper/.../*.py` で呼び出し元を確認。直接呼ぶ public があれば **a 案**。
3. **E2E ゴールデンが該当パスを踏むか** — `tests/fixtures/expected/SAMPLE.tsv` 等を確認、本テストが歪めば E2E でも壊れるかを推定。踏むなら **b 案**。

どちらも該当しなければ **c 案** (Whitebox 隔離)、現状で既に WHAT を観察していれば **keep**。

- [ ] **Step 1: 判定マトリクス doc の骨格を作成**

`docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md` を新規作成、以下の内容で書く：

```markdown
# Sweep Wave 1 — test_analyze.py 判定マトリクス

**作成日:** 2026-05-03
**対象:** `tests/test_analyze.py`（パターン F 適用後、26 クラス・99 メソッド）
**目的:** Phase 2 プランの入力。各クラスを a/b/c/keep に分類し、Phase 2 で取るアクションを確定する。
**参照:** `docs/superpowers/specs/2026-05-03-test-style-rework-design.md` のパターン定義 + パイロット G スパイク所見。

## 判定の凡例

- **keep** — 既に WHAT 検証として機能している。Phase 2 で触らない（または軽微な命名修正のみ）。
- **a 案** — 公開 API 経由のテストへ統合可能。Phase 2 で書き換え。
- **b 案** — E2E ゴールデンに包摂されており、当該クラス削除で代替可能。Phase 2 で削除（事前 mutation 確認必須）。
- **c 案** — Whitebox 隔離が必要。Phase 2 で `TestXxxWhitebox` クラスへ移送。
- **判定保留** — 情報不足。spec で先に解像度を上げる必要あり（Phase 2 の前段に追加タスクが入る）。

## マトリクス

| # | 行 | クラス | 対象関数（公開度） | 判定 | 根拠（要 file:line） | Phase 2 アクション |
|---|---|---|---|---|---|---|
| 1 | 79 | TestGrepParser | （Step 2 で埋める） | | | |
| 2 | 126 | TestUsageClassifier | | | | |
| 3 | 178 | TestTsvWriter | | | | |
| 4 | 268 | TestIndirectTracker | | | | |
| 5 | 332 | TestReporter | | | | |
| 6 | 380 | TestIntegration | | | | |
| 7 | 451 | TestProcessGrepFile | | | | |
| 8 | 527 | TestGetAst | | | | |
| 9 | 572 | TestClassifyUsage | | | | |
| 10 | 656 | TestResolveJavaFile | | | | |
| 11 | 688 | TestGetMethodScope | `_get_method_scope` (private) | b 案 | パイロット G スパイク所見（spec 末尾）参照 | クラス全削除前に E2E mutation 確認 |
| 12 | 727 | TestSearchInLines | | | | |
| 13 | 813 | TestTrackConstant | | | | |
| 14 | 863 | TestTrackField | | | | |
| 15 | 919 | TestTrackLocal | | | | |
| 16 | 983 | TestFindGetterNames | | | | |
| 17 | 1030 | TestFindSetterNames | | | | |
| 18 | 1067 | TestTrackGetterCalls | | | | |
| 19 | 1123 | TestBuildParser | | | | |
| 20 | 1157 | TestMain | | | | |
| 21 | 1255 | TestGetAstExceptionHandling | | | | |
| 22 | 1284 | TestIntenseE2E | | | | |
| 23 | 1666 | TestBatchTrackSetters | | | | |
| 24 | 1694 | TestBatchTrackOnePass | | | | |
| 25 | 1728 | TestNoModuleGlobalEncoding | | | | |
| 26 | 1735 | TestParallelBatchTrack | | | | |

## 集計

（Step 4 で記入）

## Phase 2 への引き継ぎ

（Step 4 で記入）
```

- [ ] **Step 2: 各クラスを 1 つずつ判定して行を埋める**

クラスごとに以下を 1 セットずつ実行する。**26 行すべて埋める**（プレースホルダ `（Step 2 で埋める）` のまま残さない）。

参考コマンド：

```bash
# クラスのテストコードを読む
sed -n '<開始行>,<次のクラス開始行 - 1>p' tests/test_analyze.py

# どこから import しているかを確認
sed -n '1,80p' tests/test_analyze.py | grep -E "^from grep_helper|^import grep_helper"

# 対象関数が public か private か（`_` 始まりかどうか）を import 文または使用箇所で判定

# 対象関数を public 関数が直接呼ぶかを確認
grep -n "<関数名>" grep_helper/languages/<モジュール>.py grep_helper/<モジュール>.py 2>/dev/null

# E2E ゴールデンに該当する振る舞いがあるか
grep -n "<キーワード>" tests/fixtures/expected/*.tsv
```

判定ロジック（spec のパターン G 判定基準を踏襲）：
- public 関数のテスト → **keep**（既に WHAT 観察）。命名や assert を読んで明らかな型 assertion / 内部 dict peek があれば **keep + Phase 2 で軽微な命名修正** と注記。
- private helper のテスト → 公開関数が直接呼ぶ？ Yes → **a 案**。No → E2E に行が出る？ Yes → **b 案**。No → **c 案**。
- 情報不足 → **判定保留**（理由を明記）。

各行の **根拠** 列は file:line 形式で 1〜3 個の事実を挙げる（推測でなく確認した事実）。

- [ ] **Step 3: マトリクスのセルフレビュー**

書き込み後、以下を確認：

1. 26 行すべての「判定」「根拠」「Phase 2 アクション」が埋まっている（空白なし）。
2. b 案・c 案の根拠に file:line アンカーがある（推測のみで断定していない）。
3. keep 判定でも「既に WHAT を観察している証拠」を 1 行書いている。
4. 判定保留があれば、解消に必要な調査内容を明記している。

```bash
# 空セル検出
python3 -c "
import re
content = open('docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md').read()
matrix_section = content.split('## マトリクス')[1].split('## 集計')[0]
rows = [l for l in matrix_section.split('\n') if l.startswith('| ') and not l.startswith('|---') and not l.startswith('| #')]
for i, row in enumerate(rows, 1):
    cells = [c.strip() for c in row.split('|')[1:-1]]
    empty = [j for j, c in enumerate(cells) if not c]
    if empty:
        print(f'row {i}: empty cells at index {empty} -> {cells}')
        break
else:
    print(f'all {len(rows)} rows filled')"
```

Expected: `all 26 rows filled`。

- [ ] **Step 4: 集計セクションと Phase 2 引き継ぎを記入**

`## 集計` 以降に以下のテンプレートで実数を埋める：

```markdown
## 集計

- **keep:** N 件
- **a 案（公開 API 統合）:** N 件
- **b 案（E2E 包摂で削除）:** N 件
- **c 案（Whitebox 隔離）:** N 件
- **判定保留:** N 件（合計 26）

## Phase 2 への引き継ぎ

### 着手順の推奨

1. b 案 → c 案 → a 案 → keep の順で進める（影響範囲が小さい順、確信度が高い順）。ただし b 案削除前に E2E mutation 確認を 1 度だけ実施。
2. 判定保留があれば、それを最初に解消する spike を Phase 2 の Task 1 とする。
3. 同類の private helper（例：Track*, FindGetter/Setter*）はバッチで処理可能だが、各クラスごとに mutation 確認を 1 度ずつ行う。

### Phase 2 で必要な情報の事前収集

（マトリクス作成中に発見した、Phase 2 で追加で必要そうな情報をここに列挙。なければ「なし」と書く。）
```

実数で埋め、推奨着手順は実際の判定分布に合わせて調整する（保留が多ければ「保留解消が先」など）。

- [ ] **Step 5: コミット**

```bash
git add docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md
git commit -m "$(cat <<'EOF'
docs(specs): add sweep wave 1 judgment matrix for test_analyze.py

test_analyze.py 全 26 クラスについて a/b/c/keep を判定し、
各クラスの根拠 (file:line) と Phase 2 アクションを表にまとめた。
Phase 2 プランの入力として使用する。

判定根拠を曖昧にしたまま削除しない、というパイロット G スパイク所見を
踏襲し、Phase 1 では「判定」と「実行」を分離。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Phase 1 完了確認 & Phase 2 着手準備

**Files:**
- Verify only: `tests/`、`docs/superpowers/specs/2026-05-03-sweep-wave1-judgment.md`

- [ ] **Step 1: 全体テストグリーン確認**

```bash
python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `Ran 383 tests ... OK`。失敗があれば該当テストを特定して報告（Phase 1 のいずれかのタスクで壊れた可能性）。

- [ ] **Step 2: 直近のコミット履歴確認**

```bash
git log --oneline -5
```

Expected: 直近 2 コミットが（新しい順に）：
1. `docs(specs): add sweep wave 1 judgment matrix for test_analyze.py`
2. `test(test_analyze): drop redundant method docstrings (pattern F)`

- [ ] **Step 3: 判定マトリクスのプレビューをユーザーに報告**

報告に含める：
- パターン F の適用件数（99 件削除済み）
- 判定マトリクスの集計（keep / a / b / c / 保留 の件数）
- 注目すべき判定（例：「保留が 3 件出た」「TestGetMethodScope 含む 5 件が b 案」「想定外に keep が多かった」など）
- 全テストグリーン状態
- Phase 2 プラン作成の準備が整った旨

これで Phase 1 完了。Phase 2 プラン作成（writing-plans スキルで再起動）はユーザー判断。

---

## 自己レビュー結果

- パイロット 7 パターン (A〜G) のうち F のみを本プランで適用、残り (A/B/C/D/E + 個別の G 案件) は Phase 2 へ。
- 判定 ≠ 実行を分離するスパイク所見の原則を踏襲。
- 全タスクが verifiable な expected output を持つ（行カウント・grep 結果・ast 検査）。
- production コードへの変更はゼロ。tests/test_analyze.py への変更は docstring 削除のみで挙動不変。
- 成果物は (a) クリーンな test_analyze.py、(b) 判定マトリクス doc 1 枚、(c) Phase 2 着手判断材料。
- TestGetMethodScope の判定はパイロットで確定済みのため、マトリクス Step 1 のテンプレートで先行記入。
