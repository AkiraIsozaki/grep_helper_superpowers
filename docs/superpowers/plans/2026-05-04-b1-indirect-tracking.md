# B-1: 直接参照のみ言語への間接追跡追加 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python / TypeScript / Perl / PL/SQL の 4 言語に kotlin.py 型のクロスファイル間接追跡を追加し、KPI（網羅率 100% / 分類精度 90% 以上）を達成する。

**Architecture:** 各 handler に既存の `kotlin.py` と同じ 5 関数構造（`extract_*_name` / `track_*` / `_scan_files_for_*` / `_batch_track_*` / `batch_track_indirect`）を実装。Perl のみ `extract_*` が 2 系統あり 6 関数。`grep_helper/pipeline.py` の `run_full_pipeline` は無変更（`getattr(handler, "batch_track_indirect", None)` で動的に呼ばれる）。

**Tech Stack:** Python 3.10+ / `re` (regex) / `mmap` (via `grep_filter_files`) / `concurrent.futures.ProcessPoolExecutor` / unittest / `scripts/measure_kpi.py` (KPI 検証)

**Spec:** `docs/superpowers/specs/2026-05-04-b1-indirect-tracking-design.md`

---

## File Structure

| パス | 種別 | 役割 |
|---|---|---|
| `grep_helper/languages/python.py` | 既存改修 | 5 関数追加（25 行 → 約 220 行）|
| `grep_helper/languages/ts.py` | 既存改修 | 5 関数追加（26 行 → 約 220 行）|
| `grep_helper/languages/perl.py` | 既存改修 | 6 関数追加（26 行 → 約 270 行、Tier 1 + Tier 2 + 2 系統呼び分け）|
| `grep_helper/languages/plsql.py` | 既存改修 | 5 関数追加（26 行 → 約 220 行）|
| `scripts/measure_kpi.py` | 既存改修 | `LANG_SPECS` の 4 言語の `reference_kinds_required` に `"間接"` 追加 |
| `tests/test_python_analyzer.py` | 既存改修 | `TestExtractModuleConstName` / `TestTrackModuleConst` / `TestBatchTrackIndirectPython` クラス追記 |
| `tests/test_ts_analyzer.py` | 既存改修 | 同上（`TestExtractTsConstName` / `TestTrackTsConst` / `TestBatchTrackIndirectTs`）|
| `tests/test_perl_analyzer.py` | 既存改修 | 同上 + Tier 2 ハッシュ形式テスト |
| `tests/test_plsql_analyzer.py` | 既存改修 | 同上 |
| `tests/golden/python/src/service.py` | 新規 | クロスファイル使用例 |
| `tests/golden/python/src/worker.py` | 新規 | 別ディレクトリのクロスファイル使用例 |
| `tests/golden/python/expected/777.tsv` | 既存改修 | 間接 3 行追加 |
| `tests/golden/python/README.md` | 既存改修 | 間接サンプル説明追記 |
| `tests/golden/ts/src/service.ts` | 新規 | （Python と同様の構造、TS 版）|
| `tests/golden/ts/src/worker.ts` | 新規 | |
| `tests/golden/ts/expected/777.tsv` | 既存改修 | |
| `tests/golden/ts/README.md` | 既存改修 | |
| `tests/golden/perl/src/Service.pm` | 新規 | （Perl 版）|
| `tests/golden/perl/src/Worker.pm` | 新規 | |
| `tests/golden/perl/expected/777.tsv` | 既存改修 | |
| `tests/golden/perl/README.md` | 既存改修 | |
| `tests/golden/plsql/src/other.pkb` | 新規 | （PL/SQL 版、別パッケージから参照）|
| `tests/golden/plsql/expected/777.tsv` | 既存改修 | |
| `tests/golden/plsql/README.md` | 既存改修 | |
| `README.md` | 既存改修 | L9 言語別追跡能力の記述更新（B-1 完了後）|
| `docs/tool-overview.md` | 既存改修 | L17-28 機能マトリクス更新（4 言語の間接追跡欄）|
| `docs/architecture.md` | 既存改修 | L45 Tracker ボックス + 言語別段階対応表更新 |
| `docs/functional-design.md` | 既存改修 | L102-116 4 言語の受け入れ条件更新 |
| `docs/product-requirements.md` | 既存改修（必要時）| 言語マトリクスの更新（該当箇所がある場合）|

`grep_helper/pipeline.py` は **無変更**。

---

## Step 1: 共通準備（LANG_SPECS 更新 + 4 言語ぶんゴールデンセット拡張）

このステップでは実装は触らない。LANG_SPECS と golden samples を更新して、`measure_kpi.py` で「間接が未実装ゆえ網羅率が落ちる」赤い状態を確認する。

### Task 1.1: `scripts/measure_kpi.py` の Python LANG_SPEC を更新

**Files:**
- Modify: `scripts/measure_kpi.py:111-119`

- [ ] **Step 1: `python` の `reference_kinds_required` を更新**

`scripts/measure_kpi.py` L118 を以下のように変更:

```python
    "python": {
        "module": "grep_helper.languages.python",
        "usage_types": [
            "変数代入", "条件判定", "return文", "デコレータ",
            "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],   # 旧: ["直接"]
    },
```

### Task 1.2: TS / Perl / PL/SQL の LANG_SPEC を更新

**Files:**
- Modify: `scripts/measure_kpi.py:93-128`

- [ ] **Step 1: 3 言語ぶんの `reference_kinds_required` を更新**

`scripts/measure_kpi.py` の以下 3 箇所を `["直接"]` → `["直接", "間接"]` に変更:

```python
    "plsql": {
        ...
        "reference_kinds_required": ["直接", "間接"],   # 旧: ["直接"]
    },
    "ts": {
        ...
        "reference_kinds_required": ["直接", "間接"],   # 旧: ["直接"]
    },
    "perl": {
        ...
        "reference_kinds_required": ["直接", "間接"],   # 旧: ["直接"]
    },
```

### Task 1.3: 赤状態を確認（KPI 警告 = ゴールデンセット未整備）

- [ ] **Step 1: KPI を全 4 言語に対して実行**

Run: `python scripts/measure_kpi.py --lang python --quiet`
Run: `python scripts/measure_kpi.py --lang ts --quiet`
Run: `python scripts/measure_kpi.py --lang perl --quiet`
Run: `python scripts/measure_kpi.py --lang plsql --quiet`

Expected: 各言語で `assert_coverage_distribution()` が `"間接"` 種別不足の警告を出す（exit code 0、サマリレポートには WARN）。実装はまだなので想定通り。

### Task 1.4: Python ゴールデンセット拡張（クロスファイル使用例追加）

**Files:**
- Create: `tests/golden/python/src/service.py`
- Create: `tests/golden/python/src/worker.py`
- Modify: `tests/golden/python/expected/777.tsv`

- [ ] **Step 1: クロスファイル使用例 1 個目を作成**

Create `tests/golden/python/src/service.py`:
```python
from sample import STATUS_CODE


def check(input_value):
    if input_value == STATUS_CODE:
        return True
    return False
```

- [ ] **Step 2: クロスファイル使用例 2 個目を作成（別の位置）**

Create `tests/golden/python/src/worker.py`:
```python
from sample import STATUS_CODE


def emit():
    log_value(STATUS_CODE)
```

- [ ] **Step 3: 期待 TSV に間接行を追加**

Modify `tests/golden/python/expected/777.tsv` を以下の内容で完全置換（UTF-8 BOM 付き、タブ区切り、行末 LF）:

```
文言	参照種別	使用タイプ	ファイルパス	行番号	コード行	参照元変数名	参照元ファイル	参照元行番号
777	直接	変数代入	sample.py	3	"STATUS_CODE = ""777"""			
777	直接	デコレータ	sample.py	6	"@deprecated(""777"")"			
777	直接	条件判定	sample.py	8	"if input_value == ""777"":"			
777	直接	関数引数	sample.py	10	"log_value(""777"")"			
777	直接	return文	sample.py	15	"return ""777"""			
777	直接	その他	sample.py	18	"# ""777"" のコメント — その他に分類されることを期待"			
777	間接	条件判定	service.py	5	if input_value == STATUS_CODE:	STATUS_CODE	sample.py	3
777	間接	関数引数	service.py	5	if input_value == STATUS_CODE:	STATUS_CODE	sample.py	3
777	間接	関数引数	worker.py	5	log_value(STATUS_CODE)	STATUS_CODE	sample.py	3
```

注意: タブ文字必須（`\t` で書く）。`""` は CSV エスケープのダブルダブルクォート。

実装後の検証で行が合わなかったら、行数 / src_var / 内容のいずれかが想定と違うので、その時点で調整する（このステップでは「最終的にこうなるべき」の expected を書いておく）。

- [ ] **Step 4: 期待 TSV のフォーマット検証**

Run: `python -c "from grep_helper.tsv_output import read_tsv; print(read_tsv('tests/golden/python/expected/777.tsv'))"`

`read_tsv` 関数が存在しない場合は省略可能（フォーマット問題は次の KPI 実行で発覚する）。

### Task 1.5: Python ゴールデンセットの README 更新

**Files:**
- Modify: `tests/golden/python/README.md`

- [ ] **Step 1: 間接サンプルの説明を追記**

`tests/golden/python/README.md` の「## サンプル一覧」セクション末尾に以下を追記:

```markdown
## 間接参照サンプル

- `src/service.py` / `src/worker.py`: `sample.py` の `STATUS_CODE` を別ファイルから参照する。
  クロスファイル間接追跡（B-1）の検証用。
- 期待行: `expected/777.tsv` に間接行 3 件あり（service.py の if 行 / 関数引数行、worker.py の log_value 行）。
```

### Task 1.6: TypeScript ゴールデンセット拡張

**Files:**
- Create: `tests/golden/ts/src/service.ts`
- Create: `tests/golden/ts/src/worker.ts`
- Modify: `tests/golden/ts/expected/777.tsv`
- Modify: `tests/golden/ts/README.md`

- [ ] **Step 1: クロスファイル使用例を作成**

Create `tests/golden/ts/src/service.ts`:
```typescript
import { STATUS_CODE } from './sample';

export function check(input: string): boolean {
    if (input === STATUS_CODE) {
        return true;
    }
    return false;
}
```

Create `tests/golden/ts/src/worker.ts`:
```typescript
import { STATUS_CODE } from './sample';

export function emit() {
    logValue(STATUS_CODE);
}
```

- [ ] **Step 2: 期待 TSV に間接行を追加**

Modify `tests/golden/ts/expected/777.tsv` の末尾（直接行のあと）に以下 3 行を追加:

```
777	間接	その他	service.ts	1	import { STATUS_CODE } from './sample';	STATUS_CODE	sample.ts	1
777	間接	条件判定	service.ts	4	if (input === STATUS_CODE) {	STATUS_CODE	sample.ts	1
777	間接	関数引数	worker.ts	4	logValue(STATUS_CODE);	STATUS_CODE	sample.ts	1
```

注意: ts.py の classify_usage では `import { STATUS_CODE } from './sample';` は `\w+\s*\(` を含まず、`\bif\(|\bswitch\(|===|...` も含まないため「その他」に分類される。

- [ ] **Step 3: README 更新**

`tests/golden/ts/README.md` に上記と同等の「間接参照サンプル」セクションを追加。

### Task 1.7: Perl ゴールデンセット拡張

**Files:**
- Create: `tests/golden/perl/src/Service.pm`
- Create: `tests/golden/perl/src/Worker.pm`
- Modify: `tests/golden/perl/expected/777.tsv`
- Modify: `tests/golden/perl/README.md`

- [ ] **Step 1: クロスファイル使用例を作成**

Create `tests/golden/perl/src/Service.pm`:
```perl
package Service;
use Sample qw(STATUS_CODE);

sub check {
    my $input = shift;
    if ($input eq STATUS_CODE) {
        return 1;
    }
    return 0;
}

1;
```

Create `tests/golden/perl/src/Worker.pm`:
```perl
package Worker;
use Sample qw(STATUS_CODE);

sub emit {
    do_notify(STATUS_CODE);
}

1;
```

- [ ] **Step 2: 期待 TSV に間接行を追加**

Modify `tests/golden/perl/expected/777.tsv` の末尾に以下 3 行を追加:

```
777	間接	条件判定	Service.pm	6	if ($input eq STATUS_CODE) {	STATUS_CODE	Sample.pm	4
777	間接	関数引数	Worker.pm	5	do_notify(STATUS_CODE);	STATUS_CODE	Sample.pm	4
777	間接	その他	Service.pm	2	use Sample qw(STATUS_CODE);	STATUS_CODE	Sample.pm	4
```

注意: `use Sample qw(STATUS_CODE);` は perl.py classify_usage の `\bif\s*\(|\bunless\s*\(|==|\bne\b|\beq\b` にも `\$\w+\s*=...` にも `\bprint\b...` にもマッチしないが、`\w+\s*\(` (関数引数) には注意。`use Sample qw(STATUS_CODE);` は `Sample qw(...)` なので関数呼び出しっぽいが厳密には `qw\s*\(` の単語境界での括弧。Perl の use 文は通常マッチしないため「その他」を期待。実装後の actual と齟齬があれば期待 TSV を実態に合わせ調整する。

- [ ] **Step 3: README 更新**

`tests/golden/perl/README.md` に間接サンプル説明を追加。

### Task 1.8: PL/SQL ゴールデンセット拡張

**Files:**
- Create: `tests/golden/plsql/src/other.pkb`
- Modify: `tests/golden/plsql/expected/777.tsv`
- Modify: `tests/golden/plsql/README.md`

- [ ] **Step 1: クロスファイル使用例を作成**

Create `tests/golden/plsql/src/other.pkb`:
```sql
PACKAGE BODY other_pkg AS
    PROCEDURE process(p_input IN VARCHAR2) IS
    BEGIN
        IF p_input = sample_pkg.c_default_code THEN
            INSERT INTO log_table (code) VALUES (sample_pkg.c_default_code);
        END IF;
        RETURN sample_pkg.c_default_code;
    END;
END other_pkg;
```

- [ ] **Step 2: 期待 TSV に間接行を追加**

Modify `tests/golden/plsql/expected/777.tsv` の末尾に以下 3 行を追加（`c_default_code` は case-insensitive のため大文字小文字どちらでも検出されるが、ソース通り小文字で記載）:

```
777	間接	条件判定	other.pkb	4	IF p_input = sample_pkg.c_default_code THEN	c_default_code	sample.pkb	2
777	間接	INSERT/UPDATE値	other.pkb	5	INSERT INTO log_table (code) VALUES (sample_pkg.c_default_code);	c_default_code	sample.pkb	2
777	間接	その他	other.pkb	7	RETURN sample_pkg.c_default_code;	c_default_code	sample.pkb	2
```

注意: PL/SQL classify_usage の `\bRAISE_APPLICATION_ERROR\b|\bEXCEPTION\b` / `\bIF\b.*\bTHEN\b|\bCASE\s+WHEN\b` / `\bCURSOR\b.*\bIS\b` / `\bINSERT\b|\bUPDATE\b.*\bSET\b` / `\bWHERE\b` のいずれかにマッチした順に分類される。`RETURN sample_pkg.c_default_code;` は `\bRETURN\b` パターンが存在しないので「その他」に分類される（plsql.py L11-16 で `return文` パターンが PL/SQL 版には無い）。

- [ ] **Step 3: README 更新**

`tests/golden/plsql/README.md` に間接サンプル説明を追加。

### Task 1.9: 4 言語ぶんの赤状態を最終確認

- [ ] **Step 1: KPI を再実行して期待行が増えたことを確認**

Run: `python scripts/measure_kpi.py --lang python`

Expected: 網羅率が 6/9 = 66.7% 程度に低下（直接 6 行は出るが、間接 3 行が actual に無いため WARN）。

Run: `python scripts/measure_kpi.py --lang ts`
Run: `python scripts/measure_kpi.py --lang perl`
Run: `python scripts/measure_kpi.py --lang plsql`

それぞれ網羅率が 100% を割っていることを確認。これは想定通りの「赤」状態。

### Task 1.10: コミット（Step 1 完了）

- [ ] **Step 1: 変更をコミット**

```bash
git add scripts/measure_kpi.py tests/golden/python/ tests/golden/ts/ tests/golden/perl/ tests/golden/plsql/
git commit -m "$(cat <<'EOF'
test(golden): expand 4 langs with cross-file indirect samples

Added cross-file usage source files (service.* and worker.*) and
corresponding expected indirect rows to Python / TypeScript / Perl /
PL/SQL golden sets. Updated LANG_SPECS to require "間接" reference
kind. Coverage rates intentionally fall to <100% until B-1 handlers
are implemented.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Run: `git status`
Expected: clean working tree、コミットハッシュが新規作成された。

---

## Step 2: Python 実装 + 単体テスト + KPI 確認 ★検証ゲート

ここで設計バグが出たら他 3 言語に展開する前に止める。Python から始める理由: 文法が単純（regex も簡単）で、既存 `kotlin.py` パターンの最小コピーで済むため。

### Task 2.1: ブラックボックス E2E テストを追加（TDD red）

**Files:**
- Modify: `tests/test_python_analyzer.py`

- [ ] **Step 1: TestBatchTrackIndirectPython クラスを追加**

`tests/test_python_analyzer.py` のファイル末尾（`if __name__ == "__main__":` の直前）に以下を追加:

```python
from grep_helper.languages.python import (
    extract_module_const_name,
    track_module_const,
    batch_track_indirect,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractModuleConstName(unittest.TestCase):
    """TestExtractModuleConstName: extract_module_const_name の抽出有無を観察するテスト。
    None 返却（小文字代入や非代入行）の WHAT は E2E TSV からは観察できないため keep。
    """

    def test_全大文字定数定義から名前を抽出する(self):
        self.assertEqual(extract_module_const_name('STATUS_CODE = "777"'), "STATUS_CODE")

    def test_型注釈付き全大文字定数定義から名前を抽出する(self):
        self.assertEqual(extract_module_const_name('MAX_RETRY: int = 5'), "MAX_RETRY")

    def test_インデント付き全大文字定数からも名前を抽出する(self):
        self.assertEqual(extract_module_const_name('    MY_CONST = 1'), "MY_CONST")

    def test_小文字シングルトンからは抽出しない(self):
        self.assertIsNone(extract_module_const_name('app = Flask(__name__)'))

    def test_小文字インデントなし代入からは抽出しない(self):
        self.assertIsNone(extract_module_const_name('db = SQLAlchemy()'))

    def test_dunder名は抽出しない(self):
        self.assertIsNone(extract_module_const_name('__all__ = ["x"]'))

    def test_等価比較は抽出しない(self):
        self.assertIsNone(extract_module_const_name('if x == STATUS_CODE:'))

    def test_非代入行は抽出しない(self):
        self.assertIsNone(extract_module_const_name('return STATUS_CODE'))


class TestTrackModuleConst(unittest.TestCase):
    """TestTrackModuleConst: track_module_const の間接参照検出と定義行除外を観察するテスト。"""

    def test_別ファイルでの参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            (src / "service.py").write_text('if x == STATUS_CODE:\n    pass\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(src / "constants.py"),
                lineno="1",
                code='STATUS_CODE = "777"',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_module_const("STATUS_CODE", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.py" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_定義行自身は間接レコードに含まれない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(src / "constants.py"),
                lineno="1",
                code='STATUS_CODE = "777"',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_module_const("STATUS_CODE", src, record, stats)
            self.assertEqual(results, [])


class TestBatchTrackIndirectPython(unittest.TestCase):
    """TestBatchTrackIndirectPython: batch_track_indirect の起点フィルタ・集約を観察するテスト。
    主要な公開 API のブラックボックステスト。
    """

    def test_変数代入usage_typeのレコードのみ起点となる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            (src / "service.py").write_text('if x == STATUS_CODE:\n    pass\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "constants.py"),
                    lineno="1",
                    code='STATUS_CODE = "777"',
                ),
                # この条件判定レコードは起点にならないはず
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="条件判定",
                    filepath=str(src / "service.py"),
                    lineno="1",
                    code='if x == STATUS_CODE:',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.py" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_小文字シングルトンは起点にならない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "app_init.py").write_text('app = Flask(__name__)\n')
            (src / "service.py").write_text('app.run()\n')
            records = [
                GrepRecord(
                    keyword="app",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "app_init.py"),
                    lineno="1",
                    code='app = Flask(__name__)',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect(records, src, None, workers=1)
            self.assertEqual(results, [])

    def test_workers_2と1で同じレコード集合を返す(self):
        """Linux fork 前提の並列テスト（spawn 環境はスコープ外）。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.py").write_text('STATUS_CODE = "777"\n')
            (src / "service.py").write_text('if x == STATUS_CODE:\n    pass\n')
            (src / "worker.py").write_text('process(STATUS_CODE)\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "constants.py"),
                    lineno="1",
                    code='STATUS_CODE = "777"',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))
```

### Task 2.2: テストを実行して赤を確認

- [ ] **Step 1: テスト実行**

Run: `python -m pytest tests/test_python_analyzer.py::TestExtractModuleConstName -v`
Expected: FAIL with `ImportError: cannot import name 'extract_module_const_name'`

Run: `python -m pytest tests/test_python_analyzer.py::TestBatchTrackIndirectPython -v`
Expected: FAIL with `ImportError: cannot import name 'batch_track_indirect'`

### Task 2.3: `python.py` に extract_module_const_name + 必要な import を実装

**Files:**
- Modify: `grep_helper/languages/python.py`

- [ ] **Step 1: `python.py` を全面改造**

Replace `grep_helper/languages/python.py` with:

```python
"""Python grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding
from grep_helper.source_files import grep_filter_files, iter_source_files, resolve_file_cached

EXTENSIONS: tuple[str, ...] = (".py",)

_PYTHON_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^\s*\w+\s*='),                          "変数代入"),
    (re.compile(r'\bif\b|\belif\b|==|!=|\bin\b'),         "条件判定"),
    (re.compile(r'\breturn\b'),                            "return文"),
    (re.compile(r'@\w+'),                                  "デコレータ"),
    (re.compile(r'\w+\s*\('),                              "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Pythonコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PYTHON_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_PYTHON_CONST_PAT = re.compile(r'^\s*(\w+)\s*(?::\s*[^=]+?)?\s*=(?!=)')


def extract_module_const_name(code: str) -> str | None:
    """モジュール定数名（ALL_CAPS命名のみ）を抽出する。型注釈付き(MAX: int = 5)も対応。"""
    m = _PYTHON_CONST_PAT.match(code)
    if not m:
        return None
    name = m.group(1)
    if name.isupper():
        return name
    return None


def track_module_const(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """Python モジュール定数の使用箇所を src_dir 配下の .py ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = iter_source_files(src_dir, [".py"])
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=const_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def _scan_files_for_python_const(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: Python モジュール定数を一括スキャン。"""
    scanner = build_batch_scanner(names)
    results: list[GrepRecord] = []
    for src_file in files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for _pos, name in scanner.findall(line):
                for origin, def_resolved, def_lineno in tasks_ext[name]:
                    if def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))
    return results


def _batch_track_python_const(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Python モジュール定数をプロジェクト全体に対して 1 パスでバッチスキャンする。

    workers >= 2 のとき ProcessPoolExecutor で並列化する（Linux fork 前提）。
    """
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, [".py"], label="Python定数追跡")
    if not src_files:
        return []
    total = len(src_files)

    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]] = {}
    for name, origins in tasks.items():
        ext_list = []
        for origin in origins:
            def_path = resolve_file_cached(origin.filepath, src_dir)
            ext_list.append((origin, def_path.resolve() if def_path else None, int(origin.lineno)))
        tasks_ext[name] = ext_list

    if workers >= 2 and total >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [src_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(_scan_files_for_python_const, chunk, src_dir, encoding, names, tasks_ext)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [Python定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    scanner = build_batch_scanner(names)
    results = []
    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Python定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for _pos, name in scanner.findall(line):
                for origin, def_resolved, def_lineno in tasks_ext[name]:
                    if def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Python定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Python の間接参照（モジュール定数経由）をバッチ追跡する。

    direct_records から .py ファイルかつ usage_type "変数代入" の
    レコードだけを内部で抽出し、_batch_track_python_const に委譲する。
    """
    from grep_helper.languages import detect_handler
    self_module = sys.modules[__name__]

    tasks: dict[str, list[GrepRecord]] = {}
    for r in direct_records:
        if detect_handler(r.filepath, src_dir) is not self_module:
            continue
        if r.usage_type != "変数代入":
            continue
        name = extract_module_const_name(r.code)
        if name:
            tasks.setdefault(name, []).append(r)
    if not tasks:
        return []
    stats = ProcessStats()
    return _batch_track_python_const(tasks, src_dir, stats, encoding, workers=workers)
```

### Task 2.4: テストを実行して緑を確認

- [ ] **Step 1: extract / track テスト実行**

Run: `python -m pytest tests/test_python_analyzer.py::TestExtractModuleConstName -v`
Expected: PASS（8 tests）

Run: `python -m pytest tests/test_python_analyzer.py::TestTrackModuleConst -v`
Expected: PASS（2 tests）

- [ ] **Step 2: batch_track_indirect テスト実行**

Run: `python -m pytest tests/test_python_analyzer.py::TestBatchTrackIndirectPython -v`
Expected: PASS（3 tests）

- [ ] **Step 3: 全 Python テスト実行**

Run: `python -m pytest tests/test_python_analyzer.py -v`
Expected: 既存テスト + 新規テスト全件 PASS

### Task 2.5: KPI を実行して網羅率 100% を確認

- [ ] **Step 1: 単言語 KPI 実行**

Run: `python scripts/measure_kpi.py --lang python`

Expected:
- `=== 合計 (python) ===` 配下に網羅率 9/9 (100.0%) [OK]
- 分類精度 9/9 (100.0%) [OK]
- false positive 件数: 状況による（許容範囲内）
- サンプル分布: ✅ OK（直接 / 間接 両方カバー）

ズレた場合のデバッグ手順:
1. `output/kpi/python-*.md` の「取りこぼし行」セクションを確認
2. expected と actual の差分（filepath / lineno / usage_type）を見て、期待 TSV の調整 or 実装の修正
3. 調整後再実行

### Task 2.6: コミット（Step 2 完了）

- [ ] **Step 1: 変更をコミット**

```bash
git add grep_helper/languages/python.py tests/test_python_analyzer.py
git commit -m "$(cat <<'EOF'
feat(languages/python): add cross-file indirect tracking for ALL_CAPS module constants

Implemented batch_track_indirect for Python following kotlin.py pattern.
Origin filter: usage_type=="変数代入" AND name.isupper(). Lowercase
singletons (e.g. app = Flask()) are intentionally excluded to avoid
false-positive explosion in real projects.

KPI for python now hits 100% coverage / 100% classification accuracy
on the expanded golden set (3 indirect samples added in Step 1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Step 3: TypeScript / JS 実装 + 単体テスト + KPI 確認

Step 2 と同じ構造。Python と異なり大文字命名フィルタが不要（const のみ）。

### Task 3.1: ブラックボックステストを追加（TDD red）

**Files:**
- Modify: `tests/test_ts_analyzer.py`

- [ ] **Step 1: テストクラスを追加**

`tests/test_ts_analyzer.py` のファイル末尾（`if __name__ == "__main__":` の直前）に以下を追加:

```python
from grep_helper.languages.ts import (
    extract_const_name as extract_const_name_ts,
    track_const as track_const_ts,
    batch_track_indirect as batch_track_indirect_ts,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractConstNameTs(unittest.TestCase):
    """TestExtractConstNameTs: extract_const_name の抽出有無を観察するテスト。"""

    def test_const宣言から定数名を抽出する(self):
        self.assertEqual(extract_const_name_ts('const STATUS_CODE = "777";'), "STATUS_CODE")

    def test_export_constから定数名を抽出する(self):
        self.assertEqual(extract_const_name_ts('export const STATUS_CODE = "777";'), "STATUS_CODE")

    def test_型注釈付きconstから名前を抽出する(self):
        self.assertEqual(extract_const_name_ts('const COUNT: number = 5;'), "COUNT")

    def test_let宣言からは抽出しない(self):
        self.assertIsNone(extract_const_name_ts('let x = STATUS_CODE;'))

    def test_var宣言からは抽出しない(self):
        self.assertIsNone(extract_const_name_ts('var x = STATUS_CODE;'))

    def test_分割代入は抽出しない(self):
        self.assertIsNone(extract_const_name_ts('const { a, b } = obj;'))


class TestTrackConstTs(unittest.TestCase):
    """TestTrackConstTs: track_const_ts の間接参照検出と定義行除外を観察する。"""

    def test_別tsファイルでの参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            (src / "service.ts").write_text('if (x === STATUS_CODE) { return; }\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "constants.ts"),
                lineno="1",
                code='const STATUS_CODE = "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_const_ts("STATUS_CODE", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.ts" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_定義行自身は間接レコードに含まれない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="const定数定義",
                filepath=str(src / "constants.ts"),
                lineno="1",
                code='const STATUS_CODE = "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_const_ts("STATUS_CODE", src, record, stats)
            self.assertEqual(results, [])


class TestBatchTrackIndirectTs(unittest.TestCase):
    """TestBatchTrackIndirectTs: batch_track_indirect の起点フィルタ・集約を観察する。"""

    def test_const定数定義のレコードのみ起点となる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            (src / "service.ts").write_text('if (x === STATUS_CODE) { return; }\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="const定数定義",
                    filepath=str(src / "constants.ts"),
                    lineno="1",
                    code='const STATUS_CODE = "777";',
                ),
                # let は起点にならない
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入(let/var)",
                    filepath=str(src / "service.ts"),
                    lineno="1",
                    code='let local = STATUS_CODE;',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_ts(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("service.ts" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_workers_2と1で同じレコード集合を返す(self):
        """Linux fork 前提の並列テスト。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "constants.ts").write_text('const STATUS_CODE = "777";\n')
            (src / "service.ts").write_text('if (x === STATUS_CODE) { return; }\n')
            (src / "worker.ts").write_text('process(STATUS_CODE);\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="const定数定義",
                    filepath=str(src / "constants.ts"),
                    lineno="1",
                    code='const STATUS_CODE = "777";',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect_ts(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect_ts(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))
```

### Task 3.2: テストを実行して赤を確認

- [ ] **Step 1: テスト実行**

Run: `python -m pytest tests/test_ts_analyzer.py::TestExtractConstNameTs -v`
Expected: FAIL with `ImportError`

### Task 3.3: `ts.py` を実装

**Files:**
- Modify: `grep_helper/languages/ts.py`

- [ ] **Step 1: ts.py を全面改造**

Replace `grep_helper/languages/ts.py` with:

```python
"""TypeScript/JavaScript grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding
from grep_helper.source_files import grep_filter_files, iter_source_files, resolve_file_cached

EXTENSIONS: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx")

_TS_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bconst\s+\w+\s*='),                          "const定数定義"),
    (re.compile(r'\b(?:let|var)\s+\w+\s*='),                    "変数代入(let/var)"),
    (re.compile(r'\bif\s*\(|\bswitch\s*\(|===|!==|==(?!=)|!=(?!=)'), "条件判定"),
    (re.compile(r'\breturn\b'),                                  "return文"),
    (re.compile(r'@\w+'),                                        "デコレータ"),
    (re.compile(r'\w+\s*\('),                                    "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """TypeScript/JavaScriptコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _TS_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_TS_CONST_PAT = re.compile(r'\b(?:export\s+)?const\s+(\w+)\s*(?::\s*[^=]+?)?\s*=(?!=)')


def extract_const_name(code: str) -> str | None:
    """TS const 定数名を抽出する。型注釈付き(const X: number = 5)も対応。
    分割代入 const {a, b} = obj は最初の \\w+ にマッチしないため None を返す。"""
    m = _TS_CONST_PAT.search(code)
    return m.group(1) if m else None


def track_const(
    const_name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """TS const 定数の使用箇所を src_dir 配下の .ts/.tsx/.js/.jsx ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(const_name) + r'\b')
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = iter_source_files(src_dir, [".ts", ".tsx", ".js", ".jsx"])
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=const_name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def _scan_files_for_ts_const(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: TS const を一括スキャン。"""
    scanner = build_batch_scanner(names)
    results: list[GrepRecord] = []
    for src_file in files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for _pos, name in scanner.findall(line):
                for origin, def_resolved, def_lineno in tasks_ext[name]:
                    if def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))
    return results


def _batch_track_ts_const(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """TS const をプロジェクト全体に対して 1 パスでバッチスキャンする。"""
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, [".ts", ".tsx", ".js", ".jsx"], label="TS定数追跡")
    if not src_files:
        return []
    total = len(src_files)

    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]] = {}
    for name, origins in tasks.items():
        ext_list = []
        for origin in origins:
            def_path = resolve_file_cached(origin.filepath, src_dir)
            ext_list.append((origin, def_path.resolve() if def_path else None, int(origin.lineno)))
        tasks_ext[name] = ext_list

    if workers >= 2 and total >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [src_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(_scan_files_for_ts_const, chunk, src_dir, encoding, names, tasks_ext)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [TS定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    scanner = build_batch_scanner(names)
    results = []
    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [TS定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for _pos, name in scanner.findall(line):
                for origin, def_resolved, def_lineno in tasks_ext[name]:
                    if def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [TS定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """TS の間接参照（const 経由）をバッチ追跡する。"""
    from grep_helper.languages import detect_handler
    self_module = sys.modules[__name__]

    tasks: dict[str, list[GrepRecord]] = {}
    for r in direct_records:
        if detect_handler(r.filepath, src_dir) is not self_module:
            continue
        if r.usage_type != "const定数定義":
            continue
        name = extract_const_name(r.code)
        if name:
            tasks.setdefault(name, []).append(r)
    if not tasks:
        return []
    stats = ProcessStats()
    return _batch_track_ts_const(tasks, src_dir, stats, encoding, workers=workers)
```

### Task 3.4: テストを実行して緑を確認

- [ ] **Step 1: TS テスト実行**

Run: `python -m pytest tests/test_ts_analyzer.py -v`
Expected: 既存 + 新規 全件 PASS

### Task 3.5: KPI を実行

- [ ] **Step 1: 単言語 KPI 実行**

Run: `python scripts/measure_kpi.py --lang ts`

Expected:
- 網羅率 100% [OK]
- 分類精度 90% 以上 [OK]
- サンプル分布 ✅ OK

### Task 3.6: コミット（Step 3 完了）

- [ ] **Step 1: 変更をコミット**

```bash
git add grep_helper/languages/ts.py tests/test_ts_analyzer.py
git commit -m "$(cat <<'EOF'
feat(languages/ts): add cross-file indirect tracking for const declarations

Implemented batch_track_indirect for TypeScript/JS following kotlin.py
pattern. Origin filter: usage_type=="const定数定義". Supports type
annotations (const X: number = 5). Lexical destructuring (const { a, b }
= obj) is intentionally out of scope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Step 4: Perl 実装 + 単体テスト + KPI 確認

Perl は 2 系統（`use constant FOO` と `our $FOO`）+ Tier 2（ハッシュ形式）があるため、`_batch_track_perl_constant` を `kind` パラメータ付きで 2 回呼ぶ構造。

### Task 4.1: ブラックボックステストを追加（TDD red）

**Files:**
- Modify: `tests/test_perl_analyzer.py`

- [ ] **Step 1: テストクラスを追加**

`tests/test_perl_analyzer.py` のファイル末尾（`if __name__ == "__main__":` の直前）に以下を追加:

```python
from grep_helper.languages.perl import (
    extract_perl_constant_name,
    extract_perl_our_name,
    extract_perl_constant_hash_names,
    track_perl_constant,
    batch_track_indirect as batch_track_indirect_perl,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractPerlConstantName(unittest.TestCase):
    """TestExtractPerlConstantName: extract_perl_constant_name の抽出有無を観察する。"""

    def test_use_constantから定数名を抽出する(self):
        self.assertEqual(extract_perl_constant_name('use constant STATUS_CODE => "777";'), "STATUS_CODE")

    def test_use_constantのハッシュ形式は単体抽出ではNoneを返す(self):
        self.assertIsNone(extract_perl_constant_name('use constant {A => 1, B => 2};'))

    def test_非constant行はNoneを返す(self):
        self.assertIsNone(extract_perl_constant_name('our $FOO = "x";'))


class TestExtractPerlOurName(unittest.TestCase):
    """TestExtractPerlOurName: extract_perl_our_name の抽出有無を観察する。"""

    def test_our宣言から変数名を抽出する(self):
        self.assertEqual(extract_perl_our_name('our $FOO = "x";'), "FOO")

    def test_my宣言からは抽出しない(self):
        self.assertIsNone(extract_perl_our_name('my $FOO = "x";'))

    def test_use_constant行からは抽出しない(self):
        self.assertIsNone(extract_perl_our_name('use constant FOO => "x";'))


class TestExtractPerlConstantHashNames(unittest.TestCase):
    """TestExtractPerlConstantHashNames: ハッシュ形式から複数キー抽出を観察する。"""

    def test_use_constantのハッシュ形式から複数の名前を抽出する(self):
        names = extract_perl_constant_hash_names('use constant {A => 1, B => 2, C => 3};')
        self.assertEqual(set(names), {"A", "B", "C"})

    def test_単一形式のuse_constantからは空リストを返す(self):
        self.assertEqual(extract_perl_constant_hash_names('use constant FOO => "x";'), [])

    def test_非use_constant行からは空リストを返す(self):
        self.assertEqual(extract_perl_constant_hash_names('our $FOO = "x";'), [])


class TestTrackPerlConstant(unittest.TestCase):
    """TestTrackPerlConstant: track_perl_constant の間接参照検出と定義行除外を観察する。"""

    def test_別pmファイルでの定数参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('package Sample;\nuse constant STATUS_CODE => "777";\n1;\n')
            (src / "Service.pm").write_text('if ($x eq STATUS_CODE) { return 1; }\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="use constant定義",
                filepath=str(src / "Sample.pm"),
                lineno="2",
                code='use constant STATUS_CODE => "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_perl_constant("STATUS_CODE", src, record, stats, kind="bareword")
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.pm" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_our_scalar変数の参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('package Sample;\nour $FOO = "777";\n1;\n')
            (src / "Service.pm").write_text('print $Sample::FOO;\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(src / "Sample.pm"),
                lineno="2",
                code='our $FOO = "777";',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_perl_constant("FOO", src, record, stats, kind="scalar")
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.pm" in fp for fp in filepaths))


class TestBatchTrackIndirectPerl(unittest.TestCase):
    """TestBatchTrackIndirectPerl: batch_track_indirect の起点フィルタ・集約を観察する。"""

    def test_use_constantとour両方のレコードから間接追跡する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text(
                'package Sample;\n'
                'use constant STATUS_CODE => "777";\n'
                'our $FOO = "x";\n'
                '1;\n'
            )
            (src / "Service.pm").write_text(
                'if ($x eq STATUS_CODE) { return 1; }\n'
                'print $Sample::FOO;\n'
            )
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="use constant定義",
                    filepath=str(src / "Sample.pm"),
                    lineno="2",
                    code='use constant STATUS_CODE => "777";',
                ),
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "Sample.pm"),
                    lineno="3",
                    code='our $FOO = "x";',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_perl(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("Service.pm" in fp for fp in filepaths))

    def test_my宣言は起点にならない(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('my $LOCAL = "x";\n')
            (src / "other.pm").write_text('print $LOCAL;\n')
            records = [
                GrepRecord(
                    keyword="x",
                    ref_type=RefType.DIRECT.value,
                    usage_type="変数代入",
                    filepath=str(src / "Sample.pm"),
                    lineno="1",
                    code='my $LOCAL = "x";',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_perl(records, src, None, workers=1)
            self.assertEqual(results, [])

    def test_workers_2と1で同じレコード集合を返す(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Sample.pm").write_text('use constant STATUS_CODE => "777";\n')
            (src / "Service.pm").write_text('if ($x eq STATUS_CODE) { return 1; }\n')
            (src / "Worker.pm").write_text('do_notify(STATUS_CODE);\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="use constant定義",
                    filepath=str(src / "Sample.pm"),
                    lineno="1",
                    code='use constant STATUS_CODE => "777";',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect_perl(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect_perl(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))
```

### Task 4.2: テストを実行して赤を確認

- [ ] **Step 1: テスト実行**

Run: `python -m pytest tests/test_perl_analyzer.py::TestExtractPerlConstantName -v`
Expected: FAIL with `ImportError`

### Task 4.3: `perl.py` を実装

**Files:**
- Modify: `grep_helper/languages/perl.py`

- [ ] **Step 1: perl.py を全面改造**

Replace `grep_helper/languages/perl.py` with:

```python
"""Perl grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding
from grep_helper.source_files import grep_filter_files, iter_source_files, resolve_file_cached

EXTENSIONS: tuple[str, ...] = (".pl", ".pm")
SHEBANGS: tuple[str, ...] = ("perl",)

_PERL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\buse\s+constant\b'),                          "use constant定義"),
    (re.compile(r'\bif\s*\(|\bunless\s*\(|==|\bne\b|\beq\b'),   "条件判定"),
    (re.compile(r'\$\w+\s*=|\bmy\b.*=|\bour\b.*='),             "変数代入"),
    (re.compile(r'\bprint\b|\bsay\b|\bprintf\b'),                "print/say出力"),
    (re.compile(r'\w+\s*\('),                                    "関数引数"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """Perlコード行の使用タイプを分類する（6種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PERL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_PERL_USE_CONSTANT_PAT = re.compile(r'\buse\s+constant\s+(\w+)\s*=>')
_PERL_USE_CONSTANT_HASH_PAT = re.compile(r'\buse\s+constant\s*\{([^}]*)\}', re.DOTALL)
_PERL_HASH_KEY_PAT = re.compile(r'(\w+)\s*=>')
_PERL_OUR_SCALAR_PAT = re.compile(r'\bour\s+\$(\w+)\s*=')


def extract_perl_constant_name(code: str) -> str | None:
    """単一形式 use constant FOO => ... から名前を抽出する。"""
    m = _PERL_USE_CONSTANT_PAT.search(code)
    return m.group(1) if m else None


def extract_perl_constant_hash_names(code: str) -> list[str]:
    """ハッシュ形式 use constant {A => 1, B => 2} から名前リストを抽出する。"""
    m = _PERL_USE_CONSTANT_HASH_PAT.search(code)
    if not m:
        return []
    return _PERL_HASH_KEY_PAT.findall(m.group(1))


def extract_perl_our_name(code: str) -> str | None:
    """our $FOO = ... から変数名（シジル除く）を抽出する。"""
    m = _PERL_OUR_SCALAR_PAT.search(code)
    return m.group(1) if m else None


def _make_search_pattern(name: str, kind: str) -> re.Pattern:
    """検索パターンを kind に応じて生成する。bareword=`\\bNAME\\b`, scalar=`\\$NAME\\b`."""
    if kind == "scalar":
        return re.compile(r'\$' + re.escape(name) + r'\b')
    return re.compile(r'\b' + re.escape(name) + r'\b')


def track_perl_constant(
    name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
    *,
    kind: str = "bareword",
) -> list[GrepRecord]:
    """Perl 定数 / our scalar の使用箇所を src_dir 配下の .pl/.pm ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = _make_search_pattern(name, kind)
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = iter_source_files(src_dir, [".pl", ".pm"])
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def _scan_files_for_perl_constant(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
    kind: str,
) -> list[GrepRecord]:
    """ProcessPool worker: Perl 定数 / our scalar を一括スキャン。"""
    # build_batch_scanner で多名前検索（bareword 文字列マッチ）。
    # scalar の場合は $ プレフィックスを付けたスキャナで検索する。
    if kind == "scalar":
        prefixed_names = [f"${n}" for n in names]
        scanner = build_batch_scanner(prefixed_names)
        name_map = {f"${n}": n for n in names}
    else:
        scanner = build_batch_scanner(names)
        name_map = {n: n for n in names}

    results: list[GrepRecord] = []
    for src_file in files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for _pos, found in scanner.findall(line):
                base_name = name_map.get(found)
                if base_name is None:
                    continue
                for origin, def_resolved, def_lineno in tasks_ext[base_name]:
                    if def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage(code),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=base_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))
    return results


def _batch_track_perl_constant(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    kind: str = "bareword",
    workers: int = 1,
) -> list[GrepRecord]:
    """Perl 定数 / our scalar をプロジェクト全体に対して 1 パスでバッチスキャンする。

    kind: "bareword"（use constant FOO の裸名）または "scalar"（our $FOO のシジル付き）。
    """
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, [".pl", ".pm"], label=f"Perl{kind}追跡")
    if not src_files:
        return []
    total = len(src_files)

    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]] = {}
    for name, origins in tasks.items():
        ext_list = []
        for origin in origins:
            def_path = resolve_file_cached(origin.filepath, src_dir)
            ext_list.append((origin, def_path.resolve() if def_path else None, int(origin.lineno)))
        tasks_ext[name] = ext_list

    if workers >= 2 and total >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [src_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(_scan_files_for_perl_constant, chunk, src_dir, encoding, names, tasks_ext, kind)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [Perl{kind}追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    # 直列実行（worker 関数を直接呼ぶ）
    results = _scan_files_for_perl_constant(src_files, src_dir, encoding, names, tasks_ext, kind)
    print(f"  [Perl{kind}追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """Perl の間接参照（use constant / our $）をバッチ追跡する。
    
    use constant 系統と our scalar 系統で検索パターンが違うため、
    _batch_track_perl_constant を 2 回呼び分ける。
    """
    from grep_helper.languages import detect_handler
    self_module = sys.modules[__name__]

    constant_tasks: dict[str, list[GrepRecord]] = {}
    our_tasks: dict[str, list[GrepRecord]] = {}

    for r in direct_records:
        if detect_handler(r.filepath, src_dir) is not self_module:
            continue
        if r.usage_type == "use constant定義":
            # 単一形式
            name = extract_perl_constant_name(r.code)
            if name:
                constant_tasks.setdefault(name, []).append(r)
            # ハッシュ形式（同じ行から複数名前）
            for hash_name in extract_perl_constant_hash_names(r.code):
                constant_tasks.setdefault(hash_name, []).append(r)
        elif r.usage_type == "変数代入":
            # our $FOO のみ。my は除外（パターンに `\bour\b` のみマッチ）。
            name = extract_perl_our_name(r.code)
            if name:
                our_tasks.setdefault(name, []).append(r)

    stats = ProcessStats()
    results: list[GrepRecord] = []
    if constant_tasks:
        results.extend(_batch_track_perl_constant(constant_tasks, src_dir, stats, encoding, kind="bareword", workers=workers))
    if our_tasks:
        results.extend(_batch_track_perl_constant(our_tasks, src_dir, stats, encoding, kind="scalar", workers=workers))
    return results
```

### Task 4.4: テストを実行して緑を確認

- [ ] **Step 1: Perl テスト実行**

Run: `python -m pytest tests/test_perl_analyzer.py -v`
Expected: 既存 + 新規 全件 PASS

### Task 4.5: KPI を実行

- [ ] **Step 1: 単言語 KPI 実行**

Run: `python scripts/measure_kpi.py --lang perl`

Expected:
- 網羅率 100% [OK]
- 分類精度 90% 以上 [OK]
- サンプル分布 ✅ OK

### Task 4.6: コミット（Step 4 完了）

- [ ] **Step 1: 変更をコミット**

```bash
git add grep_helper/languages/perl.py tests/test_perl_analyzer.py
git commit -m "$(cat <<'EOF'
feat(languages/perl): add cross-file indirect tracking for use constant and our \$

Implemented batch_track_indirect for Perl following kotlin.py pattern,
extended with two-way dispatch for the use constant bareword (\bFOO\b)
and our \$ scalar (\$FOO\b) origin systems. Supports both single-form
and hash-form use constant declarations on a single line.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Step 5: PL/SQL 実装 + 単体テスト + KPI 確認

PL/SQL は case-insensitive で、CONSTANT キーワード必須。

### Task 5.1: ブラックボックステストを追加（TDD red）

**Files:**
- Modify: `tests/test_plsql_analyzer.py`

- [ ] **Step 1: テストクラスを追加**

`tests/test_plsql_analyzer.py` のファイル末尾に以下を追加:

```python
from grep_helper.languages.plsql import (
    extract_plsql_constant_name,
    track_plsql_constant,
    batch_track_indirect as batch_track_indirect_plsql,
)
from grep_helper.model import GrepRecord, RefType


class TestExtractPlsqlConstantName(unittest.TestCase):
    """TestExtractPlsqlConstantName: extract_plsql_constant_name の抽出有無を観察する。"""

    def test_constant宣言から名前を抽出する(self):
        self.assertEqual(extract_plsql_constant_name('c_x CONSTANT VARCHAR2(8) := \'777\';'), "c_x")

    def test_大文字混在のCONSTANT宣言から名前を抽出する(self):
        self.assertEqual(extract_plsql_constant_name('C_X Constant Number := 1;'), "C_X")

    def test_インデント付き宣言からも抽出する(self):
        self.assertEqual(extract_plsql_constant_name('    c_y CONSTANT NUMBER := 5;'), "c_y")

    def test_constantキーワード無しの変数宣言は抽出しない(self):
        self.assertIsNone(extract_plsql_constant_name('v_count NUMBER := 0;'))

    def test_条件判定行は抽出しない(self):
        self.assertIsNone(extract_plsql_constant_name('IF p_input = c_x THEN'))


class TestTrackPlsqlConstant(unittest.TestCase):
    """TestTrackPlsqlConstant: track_plsql_constant の間接参照検出と定義行除外を観察する。"""

    def test_別pkbファイルでの参照を間接レコードとして記録する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('PACKAGE BODY sample IS\n  c_x CONSTANT NUMBER := 777;\nEND;\n')
            (src / "other.pkb").write_text('IF p_input = sample.c_x THEN\n  NULL;\nEND IF;\n')
            record = GrepRecord(
                keyword="777",
                ref_type=RefType.DIRECT.value,
                usage_type="定数/変数宣言",
                filepath=str(src / "sample.pkb"),
                lineno="2",
                code='  c_x CONSTANT NUMBER := 777;',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_plsql_constant("c_x", src, record, stats)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("other.pkb" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_大文字小文字を区別せず参照を検出する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('  C_X CONSTANT NUMBER := 1;\n')
            (src / "other.pkb").write_text('  RETURN c_x;\n')
            record = GrepRecord(
                keyword="1",
                ref_type=RefType.DIRECT.value,
                usage_type="定数/変数宣言",
                filepath=str(src / "sample.pkb"),
                lineno="1",
                code='  C_X CONSTANT NUMBER := 1;',
            )
            stats = ProcessStats()
            _file_lines_cache_clear()
            results = track_plsql_constant("C_X", src, record, stats)
            self.assertTrue(any("other.pkb" in r.filepath for r in results))


class TestBatchTrackIndirectPlsql(unittest.TestCase):
    """TestBatchTrackIndirectPlsql: batch_track_indirect の起点フィルタ・集約を観察する。"""

    def test_constantキーワードのレコードのみ起点となる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('  c_x CONSTANT NUMBER := 777;\n')
            (src / "other.pkb").write_text('  IF p = sample.c_x THEN NULL; END IF;\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="定数/変数宣言",
                    filepath=str(src / "sample.pkb"),
                    lineno="1",
                    code='  c_x CONSTANT NUMBER := 777;',
                ),
                # CONSTANT 無しの普通の変数宣言は起点にならない
                GrepRecord(
                    keyword="0",
                    ref_type=RefType.DIRECT.value,
                    usage_type="定数/変数宣言",
                    filepath=str(src / "sample.pkb"),
                    lineno="2",
                    code='  v_count NUMBER := 0;',
                ),
            ]
            _file_lines_cache_clear()
            results = batch_track_indirect_plsql(records, src, None, workers=1)
            filepaths = [r.filepath for r in results]
            self.assertTrue(any("other.pkb" in fp for fp in filepaths))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in results))

    def test_workers_2と1で同じレコード集合を返す(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "sample.pkb").write_text('  c_x CONSTANT NUMBER := 777;\n')
            (src / "a.pkb").write_text('  IF p = sample.c_x THEN NULL; END IF;\n')
            (src / "b.pkb").write_text('  RETURN sample.c_x;\n')
            records = [
                GrepRecord(
                    keyword="777",
                    ref_type=RefType.DIRECT.value,
                    usage_type="定数/変数宣言",
                    filepath=str(src / "sample.pkb"),
                    lineno="1",
                    code='  c_x CONSTANT NUMBER := 777;',
                ),
            ]
            _file_lines_cache_clear()
            serial = batch_track_indirect_plsql(records, src, None, workers=1)
            _file_lines_cache_clear()
            parallel = batch_track_indirect_plsql(records, src, None, workers=2)
            key = lambda r: (r.filepath, r.lineno, r.ref_type)
            self.assertEqual(sorted(serial, key=key), sorted(parallel, key=key))
```

### Task 5.2: テストを実行して赤を確認

- [ ] **Step 1: テスト実行**

Run: `python -m pytest tests/test_plsql_analyzer.py::TestExtractPlsqlConstantName -v`
Expected: FAIL with `ImportError`

### Task 5.3: `plsql.py` を実装

**Files:**
- Modify: `grep_helper/languages/plsql.py`

- [ ] **Step 1: plsql.py を全面改造**

Replace `grep_helper/languages/plsql.py` with:

```python
"""PL/SQL grep結果 自動分類・使用箇所洗い出しハンドラ。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from grep_helper.model import ClassifyContext, GrepRecord, ProcessStats, RefType
from grep_helper.scanner import build_batch_scanner
from grep_helper.file_cache import cached_file_lines
from grep_helper.encoding import detect_encoding
from grep_helper.source_files import grep_filter_files, iter_source_files, resolve_file_cached

EXTENSIONS: tuple[str, ...] = (".pls", ".pck", ".prc", ".pkb", ".pks", ".fnc", ".trg")

_PLSQL_USAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bCONSTANT\b|:=', re.IGNORECASE),                    "定数/変数宣言"),
    (re.compile(r'\bWHEN\b.*\bTHEN\b|\bRAISE\b', re.IGNORECASE),       "EXCEPTION処理"),
    (re.compile(r'\bIF\b.*\bTHEN\b|\bCASE\s+WHEN\b', re.IGNORECASE),   "条件判定"),
    (re.compile(r'\bCURSOR\b.*\bIS\b', re.IGNORECASE),                  "カーソル定義"),
    (re.compile(r'\bINSERT\b|\bUPDATE\b.*\bSET\b', re.IGNORECASE),     "INSERT/UPDATE値"),
    (re.compile(r'\bWHERE\b', re.IGNORECASE),                           "WHERE条件"),
]


def classify_usage(code: str, *, ctx: ClassifyContext | None = None) -> str:  # noqa: ARG001
    """PL/SQLコード行の使用タイプを分類する（7種）。"""
    stripped = code.strip()
    for pattern, usage_type in _PLSQL_USAGE_PATTERNS:
        if pattern.search(stripped):
            return usage_type
    return "その他"


_PLSQL_CONSTANT_PAT = re.compile(r'^\s*(\w+)\s+CONSTANT\b', re.IGNORECASE)


def extract_plsql_constant_name(code: str) -> str | None:
    """PL/SQL CONSTANT 宣言から定数名を抽出する。同一行マルチステートメントは取りこぼし許容。"""
    m = _PLSQL_CONSTANT_PAT.match(code)
    return m.group(1) if m else None


def track_plsql_constant(
    name: str,
    src_dir: Path,
    record: GrepRecord,
    stats: ProcessStats,
    encoding_override: str | None = None,
) -> list[GrepRecord]:
    """PL/SQL 定数の使用箇所を src_dir 配下の .pls/.pkb/.pks/etc ファイルでスキャンする。"""
    results: list[GrepRecord] = []
    pattern = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
    def_file = resolve_file_cached(record.filepath, src_dir)

    src_files = iter_source_files(src_dir, list(EXTENSIONS))
    for src_file in src_files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)

        lines = cached_file_lines(Path(src_file), detect_encoding(Path(src_file), encoding_override), stats)
        for i, line in enumerate(lines, 1):
            if (def_file is not None
                    and src_file.resolve() == def_file.resolve()
                    and i == int(record.lineno)):
                continue
            if pattern.search(line):
                results.append(GrepRecord(
                    keyword=record.keyword,
                    ref_type=RefType.INDIRECT.value,
                    usage_type=classify_usage(line.strip()),
                    filepath=filepath_str,
                    lineno=str(i),
                    code=line.strip(),
                    src_var=name,
                    src_file=record.filepath,
                    src_lineno=record.lineno,
                ))
    return results


def _scan_files_for_plsql_constant(
    files: list[Path],
    src_dir: Path,
    encoding: str | None,
    names: list[str],
    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]],
) -> list[GrepRecord]:
    """ProcessPool worker: PL/SQL 定数を一括スキャン。

    case-insensitive 検索のため、build_batch_scanner ではなく re で個別に検索する。
    （build_batch_scanner は文字列リテラル一致前提で、case-insensitive 非対応のため）
    """
    name_patterns = [(n, re.compile(r'\b' + re.escape(n) + r'\b', re.IGNORECASE)) for n in names]
    results: list[GrepRecord] = []
    for src_file in files:
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        src_resolved = src_file.resolve()
        lines = cached_file_lines(src_file, detect_encoding(src_file, encoding))
        for i, line in enumerate(lines, 1):
            code = line.strip()
            for name, pattern in name_patterns:
                if pattern.search(line):
                    for origin, def_resolved, def_lineno in tasks_ext[name]:
                        if def_resolved is not None and src_resolved == def_resolved and i == def_lineno:
                            continue
                        results.append(GrepRecord(
                            keyword=origin.keyword,
                            ref_type=RefType.INDIRECT.value,
                            usage_type=classify_usage(code),
                            filepath=filepath_str,
                            lineno=str(i),
                            code=code,
                            src_var=name,
                            src_file=origin.filepath,
                            src_lineno=origin.lineno,
                        ))
    return results


def _batch_track_plsql_constant(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """PL/SQL CONSTANT 名をプロジェクト全体に対して 1 パスでバッチスキャンする。"""
    if not tasks:
        return []
    names = list(tasks.keys())
    src_files = grep_filter_files(names, src_dir, list(EXTENSIONS), label="PL/SQL定数追跡")
    if not src_files:
        return []
    total = len(src_files)

    tasks_ext: dict[str, list[tuple[GrepRecord, Path | None, int]]] = {}
    for name, origins in tasks.items():
        ext_list = []
        for origin in origins:
            def_path = resolve_file_cached(origin.filepath, src_dir)
            ext_list.append((origin, def_path.resolve() if def_path else None, int(origin.lineno)))
        tasks_ext[name] = ext_list

    if workers >= 2 and total >= 2:
        from concurrent.futures import ProcessPoolExecutor
        chunks = [src_files[i::workers] for i in range(workers)]
        results: list[GrepRecord] = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(_scan_files_for_plsql_constant, chunk, src_dir, encoding, names, tasks_ext)
                for chunk in chunks if chunk
            ]
            for fut in futures:
                results.extend(fut.result())
        print(f"  [PL/SQL定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
        return results

    results = _scan_files_for_plsql_constant(src_files, src_dir, encoding, names, tasks_ext)
    print(f"  [PL/SQL定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results


def batch_track_indirect(
    direct_records: list[GrepRecord],
    src_dir: Path,
    encoding: str | None,
    *,
    workers: int = 1,
) -> list[GrepRecord]:
    """PL/SQL の間接参照（CONSTANT 経由）をバッチ追跡する。"""
    from grep_helper.languages import detect_handler
    self_module = sys.modules[__name__]

    tasks: dict[str, list[GrepRecord]] = {}
    for r in direct_records:
        if detect_handler(r.filepath, src_dir) is not self_module:
            continue
        if r.usage_type != "定数/変数宣言":
            continue
        # CONSTANT キーワード必須（普通の変数宣言は除外）
        if not re.search(r'\bCONSTANT\b', r.code, re.IGNORECASE):
            continue
        name = extract_plsql_constant_name(r.code)
        if name:
            tasks.setdefault(name, []).append(r)
    if not tasks:
        return []
    stats = ProcessStats()
    return _batch_track_plsql_constant(tasks, src_dir, stats, encoding, workers=workers)
```

### Task 5.4: テストを実行して緑を確認

- [ ] **Step 1: PL/SQL テスト実行**

Run: `python -m pytest tests/test_plsql_analyzer.py -v`
Expected: 既存 + 新規 全件 PASS

### Task 5.5: KPI を実行

- [ ] **Step 1: 単言語 KPI 実行**

Run: `python scripts/measure_kpi.py --lang plsql`

Expected:
- 網羅率 100% [OK]
- 分類精度 90% 以上 [OK]
- サンプル分布 ✅ OK

### Task 5.6: コミット（Step 5 完了）

- [ ] **Step 1: 変更をコミット**

```bash
git add grep_helper/languages/plsql.py tests/test_plsql_analyzer.py
git commit -m "$(cat <<'EOF'
feat(languages/plsql): add cross-file indirect tracking for CONSTANT declarations

Implemented batch_track_indirect for PL/SQL following kotlin.py pattern.
Origin filter: usage_type=="定数/変数宣言" AND \bCONSTANT\b in code.
Search is case-insensitive (PL/SQL convention). Multi-statement single
lines are out of scope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Step 6: 全体統合確認 + ドキュメント

### Task 6.1: `--lang all` で全 12 言語が引き続き動くこと確認

- [ ] **Step 1: 全言語 KPI 実行**

Run: `python scripts/measure_kpi.py --lang all`

Expected:
- exit code 0
- 全 12 言語で網羅率 100% / 分類精度 90% 以上
- `_summary-<timestamp>.md` が `output/kpi/` に出力される
- 既存 8 言語（java / c / proc / sql / sh / kotlin / dotnet / groovy）の数値が変わらないこと

### Task 6.2: pytest 全件 pass を確認

- [ ] **Step 1: 全テスト実行**

Run: `python -m pytest tests/ -v`

Expected: 全テスト PASS。失敗があれば、Step 2-5 で見落としがあるか、既存テストへの影響があるかを確認して修正。

### Task 6.3: `tests/golden/<lang>/README.md` を最終確認

- [ ] **Step 1: 4 言語の README が間接サンプル説明を含むこと確認**

Run: `grep -l "間接参照サンプル" tests/golden/python/README.md tests/golden/ts/README.md tests/golden/perl/README.md tests/golden/plsql/README.md`

Expected: 4 ファイルすべてヒットする。ヒットしない場合は Step 1 の Task で追加忘れがあるので追加。

### Task 6.4: ドキュメント（docs/ 配下と README.md）の最新化

B-1 完了に伴い「PL/SQL / TypeScript・JS / Python / Perl は直接参照のみ」と書かれている箇所がすべて嘘になる。これらをまとめて修正する。

**Files:**
- Modify: `README.md`
- Modify: `docs/tool-overview.md`
- Modify: `docs/architecture.md`
- Modify: `docs/functional-design.md`
- Modify: `docs/product-requirements.md`

- [ ] **Step 1: `README.md` L9 の言語別追跡能力の記述を修正**

`README.md` L9 の以下の文を:
```
（Java/Groovy: 4段階（直接 + 間接 + getter/setter経由）、C/Pro*C/Kotlin/C#・VB.NET: 直接参照 + 定数・変数経由の間接参照、Shell/SQL: 直接参照 + 同一ファイル内変数代入の間接参照、PL/SQL/TypeScript・JS/Python/Perl: 直接参照のみ）
```

以下に修正:
```
（Java/Groovy: 4段階（直接 + 間接 + getter/setter経由）、C/Pro*C/Kotlin/C#・VB.NET/PL/SQL/TypeScript・JS/Python/Perl: 直接参照 + 定数経由の間接参照、Shell/SQL: 直接参照 + 同一ファイル内変数代入の間接参照）
```

- [ ] **Step 2: `docs/tool-overview.md` の機能マトリクスを修正**

L17-28 の表で 4 言語の「間接追跡」欄を `—` から `✓ (定数経由)` に変更:

```markdown
| 言語 | スクリプト | 間接追跡 | getter/setter追跡 |
|---|---|---|---|
| ...
| PL/SQL | `analyze_plsql.py` | ✓ (CONSTANT経由) | — |
| TypeScript / JavaScript | `analyze_ts.py` | ✓ (const経由) | — |
| Python | `analyze_python.py` | ✓ (ALL_CAPS定数経由) | — |
| Perl | `analyze_perl.py` | ✓ (use constant / our \$ 経由) | — |
```

- [ ] **Step 3: `docs/architecture.md` の「直接参照のみ」記述を修正**

L37 の見出し「Java 以外の言語 — 直接参照 + 言語別の間接追跡」は変更不要（包括表現）。

L45 の Tracker ボックス内テキストを修正。以下を:
```
Tracker["間接追跡（言語別）\nC/Pro*C: batch_track_indirect（#define追跡）\nShell: batch_track_indirect（変数追跡）\nSQL: batch_track_indirect（変数追跡）\nKotlin: batch_track_indirect（const val追跡）\n.NET: batch_track_indirect（const/readonly追跡）\nGroovy: batch_track_indirect（static final/getter/setter追跡）\n（PL/SQL / TS / Python / Perl は直接参照のみ）"]
```

以下に修正:
```
Tracker["間接追跡（言語別）\nC/Pro*C: batch_track_indirect（#define追跡）\nShell: batch_track_indirect（変数追跡）\nSQL: batch_track_indirect（変数追跡）\nKotlin: batch_track_indirect（const val追跡）\n.NET: batch_track_indirect（const/readonly追跡）\nGroovy: batch_track_indirect（static final/getter/setter追跡）\nPL/SQL: batch_track_indirect（CONSTANT追跡）\nTS: batch_track_indirect（const追跡）\nPython: batch_track_indirect（ALL_CAPS定数追跡）\nPerl: batch_track_indirect（use constant / our \$追跡）"]
```

L413 と L478 周辺に言語別段階対応表があるので、4 言語の「第2段階（間接）」欄を「✓」に更新:

```bash
# まず現状を確認
grep -nE "PL/SQL|TypeScript|Python|Perl" /workspaces/grep_helper_superpowers/docs/architecture.md | grep -E "—|なし|無し"
```

ヒットした行を「✓ (クロスファイル)」のような表現に書き換える（既存の表現に合わせる）。

- [ ] **Step 4: `docs/functional-design.md` の受け入れ条件を修正**

L102-116 周辺の以下 4 ブロックを修正:

```markdown
**受け入れ条件（PL/SQL: `analyze_plsql.py`）**:
- ...
- [ ] 直接参照のみ（間接追跡なし）   ← この行を以下に置換
```

各言語ぶん以下に変更:

```markdown
**受け入れ条件（PL/SQL: `analyze_plsql.py`）**:
- ...
- [x] CONSTANT 宣言行から定数名を抽出し、`.pls`/`.pkb`/`.pks`/etc ファイルを対象にプロジェクト全体を追跡する（間接参照、case-insensitive）

**受け入れ条件（TypeScript/JavaScript: `analyze_ts.py`）**:
- ...
- [x] `const` 定義行から定数名を抽出し、`.ts`/`.tsx`/`.js`/`.jsx` ファイルを対象にプロジェクト全体を追跡する（間接参照）

**受け入れ条件（Python: `analyze_python.py`）**:
- ...
- [x] ALL_CAPS 命名のモジュール定数定義行から定数名を抽出し、`.py` ファイルを対象にプロジェクト全体を追跡する（間接参照、小文字シングルトンは除外）

**受け入れ条件（Perl: `analyze_perl.py`）**:
- ...
- [x] `use constant` および `our \$` 定義行から名前を抽出し、`.pl`/`.pm` ファイルを対象にプロジェクト全体を追跡する（間接参照、`my` レキシカルは除外）
```

- [ ] **Step 5: `docs/product-requirements.md` の言語マトリクスを確認**

```bash
grep -nE "PL/SQL|TypeScript|Python|Perl" /workspaces/grep_helper_superpowers/docs/product-requirements.md | grep -E "直接参照のみ|—|なし|無し"
```

ヒットした行があれば、`docs/functional-design.md` と同様に「直接参照 + 定数経由の間接参照」と修正する。ヒットしなければスキップ。

- [ ] **Step 6: 修正後の整合性確認**

Run: `grep -rn "直接参照のみ" /workspaces/grep_helper_superpowers/docs/ /workspaces/grep_helper_superpowers/README.md`

Expected: 4 言語（PL/SQL / TS / Python / Perl）に紐づく「直接参照のみ」記述が**ゼロ件**になっている。残っている場合は該当ファイルを修正。

ただし、Shell / SQL は「直接参照 + 同一ファイル内変数代入の間接参照」と表現される箇所があり、これは正しい記述なのでヒットしてよい（誤検知）。

### Task 6.5: spec の §成功条件を点検

- [ ] **Step 1: spec の成功条件 8 項目を1つずつ確認**

`docs/superpowers/specs/2026-05-04-b1-indirect-tracking-design.md` の §成功条件 を読みながら 1 つずつチェック:

1. ☐ `grep_helper/languages/{python,ts,perl,plsql}.py` に `batch_track_indirect` が実装されている
2. ☐ `python scripts/measure_kpi.py --lang python` で網羅率 100%・分類精度 90% 以上を達成
3. ☐ 他 3 言語（ts / perl / plsql）でも同様に網羅率 100% を達成
4. ☐ `python scripts/measure_kpi.py --lang all` で全 12 言語が成功（exit code 0）
5. ☐ `tests/test_{python,ts,perl,plsql}_analyzer.py` の追記分も含めて pytest 全件 pass する
6. ☐ `assert_coverage_distribution()` が 4 言語のゴールデンセットに対して `"間接"` 種別を含めて警告ゼロ
7. ☐ ProcessPool 並列化が動く（`workers=2` 以上で直列と同じレコード集合を返す）
8. ☐ F の既存 KPI（Java / C / proc / SQL / Shell / Kotlin / dotnet / groovy）が引き続き網羅率 100% / 分類精度 90% 以上を維持

すべてチェックついたら次のタスクへ。

### Task 6.6: 最終コミット（Step 6 完了 = B-1 完了）

- [ ] **Step 1: ドキュメント更新分をコミット**

```bash
git add README.md docs/tool-overview.md docs/architecture.md docs/functional-design.md docs/product-requirements.md
git status
git commit -m "$(cat <<'EOF'
docs(b1): update language capability matrix after indirect tracking added

After B-1 lands, PL/SQL / TS / Python / Perl handlers all support
cross-file indirect tracking. Updated:
- README.md: feature description
- docs/tool-overview.md: language matrix
- docs/architecture.md: tracker diagram and stage matrix
- docs/functional-design.md: per-language acceptance criteria
- docs/product-requirements.md: where applicable

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: 残った差分があれば追加コミット**

`git status` を確認し、`tests/golden/<lang>/README.md` 追記など Step 1 で漏れた変更があればコミット。

```bash
git status
# 差分があれば
git add -A
git commit -m "$(cat <<'EOF'
docs(b1): add indirect-sample notes to 4 golden README files

Final B-1 documentation update: each golden README now describes
the cross-file indirect samples added in Step 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

差分が無ければスキップ。

- [ ] **Step 3: 完了確認**

Run: `git log --oneline -12`

Expected: B-1 関連のコミットが 6-7 本（Step 1 共通準備、Step 2-5 各言語、Step 6 ドキュメント、+ 任意で golden README 追記）並んでいる。

B-1 実装完了。次の B-4（Java 慣用句追加）は別 spec として brainstorming-skill から始める。
