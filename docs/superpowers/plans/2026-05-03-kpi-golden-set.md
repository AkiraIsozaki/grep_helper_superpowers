# KPI ゴールデンセット・計測スクリプト Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全12言語の KPI（網羅率・分類精度）を継続計測する独立スクリプトとゴールデンセット（Java深堀り + 他11言語スモーク）を構築する

**Architecture:** `scripts/measure_kpi.py` を新規作成し、`grep_helper.pipeline.run_full_pipeline()` を in-process で起動して actual TSV を生成、`tests/golden/<lang>/expected/*.tsv` と突合して網羅率・分類精度を算出する。レポートは Markdown で `output/kpi/` に書き出し、しきい値割れは WARN 表示するが exit code は 0（CIゲートしない）

**Tech Stack:** Python 3.7+, unittest, csv (stdlib), importlib (stdlib), tempfile (stdlib)。新規外部依存なし

**Spec:** `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md`

---

## File Structure

### 新規作成

| パス | 責務 |
|---|---|
| `scripts/measure_kpi.py` | CLI エントリ、TSV ロード、`compare()`、レポート整形、`run()` |
| `tests/test_measure_kpi.py` | `compare`/`load_*`/`format_*`/`assert_coverage_distribution`/E2E の単体テスト |
| `tests/golden/java/` | Java 深堀りゴールデンセット（src/inputs/expected/README.md） |
| `tests/golden/{c,proc,sql,sh,kotlin,plsql,ts,python,perl,dotnet,groovy}/` | 他11言語スモーク |
| `pytest.ini` | `norecursedirs = tests/golden`（pytest 収集除外） |

### 既存変更

| パス | 内容 |
|---|---|
| `grep_helper/pipeline.py` | `run_full_pipeline()` を追加（既存 `process_grep_file` の下） |
| `.gitignore` | `output/kpi/` を追加 |
| `README.md` | KPI 計測の使い方を追記 |

---

## 実装の段階化

spec §実装の段階化 に従い、以下6 Step + 任意 Step に分けて進める。各 Step 内のタスクは TDD（test-first）で実装する。**Step 3 が検証ゲート**：Java の KPI 計測が完全に動くことを確認してから Step 4 以降に進む。

---

# Step 1: 基盤整備

## Task 1: `pytest.ini` を新規作成

**Files:**
- Create: `pytest.ini`

- [ ] **Step 1.1: ファイル作成**

```ini
[pytest]
norecursedirs = tests/golden
```

- [ ] **Step 1.2: pytest が現状通り動くことを確認**

Run: `python -m pytest tests/ -q --collect-only 2>&1 | tail -5`
Expected: 既存テストの数が変わらず、エラーが出ない

- [ ] **Step 1.3: コミット**

```bash
git add pytest.ini
git commit -m "test: add pytest.ini to exclude tests/golden from collection"
```

---

## Task 2: `.gitignore` に `output/kpi/` を追加

**Files:**
- Modify: `.gitignore`

- [ ] **Step 2.1: 既存 `.gitignore` を読む**

Run: `cat .gitignore | grep output`
Expected: `output/*.tsv` の1行のみ

- [ ] **Step 2.2: `output/kpi/` を追記**

`.gitignore` の `output/*.tsv` の下の行に追加：

```
output/*.tsv
output/kpi/
```

- [ ] **Step 2.3: コミット**

```bash
git add .gitignore
git commit -m "chore: ignore output/kpi/ for KPI measurement reports"
```

---

## Task 3: `grep_helper/pipeline.py` に `run_full_pipeline()` を追加（テスト先行）

`cli.run()` の本体（process_grep_file → handler.batch_track_indirect → write_tsv）を関数として切り出す。argparse 非依存。

**Files:**
- Modify: `grep_helper/pipeline.py`
- Create: `tests/test_pipeline_run.py`

- [ ] **Step 3.1: 失敗するテストを書く**

Create `tests/test_pipeline_run.py`:

```python
"""run_full_pipeline の最小契約テスト。

handler を渡すと、grep ファイル群を処理して output_dir に <stem>.tsv を書く。
in-process 呼び出しで argparse を介さない。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile

from grep_helper.languages import sql as sql_handler  # 既存ハンドラを借りる
from grep_helper.pipeline import run_full_pipeline


class TestRunFullPipeline(unittest.TestCase):
    """run_full_pipeline は in-process で呼べる完全パイプライン。"""

    def test_grepファイルを与えると同名のtsvが出力される(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            input_dir = tmp_path / "input"
            output_dir = tmp_path / "output"
            src_dir.mkdir()
            input_dir.mkdir()
            sample_sql = src_dir / "sample.sql"
            sample_sql.write_text("SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8")
            grep_path = input_dir / "A.grep"
            grep_path.write_text("src/sample.sql:1:SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8")

            run_full_pipeline(
                source_dir=src_dir,
                input_dir=input_dir,
                output_dir=output_dir,
                handler=sql_handler,
                workers=1,
            )

            self.assertTrue((output_dir / "A.tsv").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3.2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_pipeline_run.py -v`
Expected: FAIL（`ImportError: cannot import name 'run_full_pipeline'`）

- [ ] **Step 3.3: 最小実装**

Modify `grep_helper/pipeline.py`. 既存の `process_grep_file` の下に追加：

```python
def run_full_pipeline(
    source_dir: Path,
    input_dir: Path,
    output_dir: Path,
    handler: ModuleType,
    *,
    encoding: str | None = None,
    workers: int = 1,
    stats: ProcessStats | None = None,
) -> list[str]:
    """input_dir/*.grep を処理し、output_dir/<stem>.tsv を書き出す（in-process 完全版）。

    grep_helper.cli.run() の本体（argparse 抜き）と等価。
    KPI 計測スクリプト・将来の cli.run() リファクタの両方から再利用される。

    Returns: 処理した grep ファイル名のリスト。
    """
    from grep_helper.tsv_output import write_tsv  # noqa: PLC0415

    if stats is None:
        stats = ProcessStats()

    output_dir.mkdir(parents=True, exist_ok=True)

    grep_files = sorted(input_dir.glob("*.grep"))
    processed_files: list[str] = []

    for grep_path in grep_files:
        keyword = grep_path.stem
        direct_records = process_grep_file(
            grep_path, source_dir, handler,
            keyword=keyword, encoding=encoding, stats=stats,
        )
        indirect_fn = getattr(handler, "batch_track_indirect", None)
        indirect_records: list = []
        if indirect_fn is not None:
            indirect_records = indirect_fn(
                direct_records, source_dir, encoding, workers=workers,
            )
        all_records = list(direct_records) + list(indirect_records)
        output_path = output_dir / f"{keyword}.tsv"
        write_tsv(all_records, output_path)
        processed_files.append(grep_path.name)

    return processed_files
```

- [ ] **Step 3.4: テストが通ることを確認**

Run: `python -m pytest tests/test_pipeline_run.py -v`
Expected: PASS

- [ ] **Step 3.5: 既存テストへのリグレッションがないか確認**

Run: `python -m pytest tests/ -q`
Expected: 既存テストはすべて pass

- [ ] **Step 3.6: コミット**

```bash
git add grep_helper/pipeline.py tests/test_pipeline_run.py
git commit -m "feat(pipeline): add run_full_pipeline() for in-process invocation

Extracted from cli.run() body so KPI measurement script and the future
cli.run() refactor can share one entry point."
```

---

# Step 2: 計測スクリプト本体 + 単体テスト

## Task 4: `scripts/measure_kpi.py` の骨格と Record/ComparisonResult 型

**Files:**
- Create: `scripts/measure_kpi.py`
- Create: `tests/test_measure_kpi.py`

- [ ] **Step 4.1: 失敗するテスト（型存在チェック）を書く**

Create `tests/test_measure_kpi.py`:

```python
"""KPI 計測スクリプト measure_kpi.py の単体テスト。

プロジェクトのテスト方針（古典学派・ブラックボックス起点・WHATを検証・
日本語メソッド名・TDD）に従う。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# scripts/ を import path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import measure_kpi


class TestRecord(unittest.TestCase):
    """Record は期待TSV / actual TSV をパースしたあとの軽量レコード。"""

    def test_Recordは9カラムの値を保持する(self):
        r = measure_kpi.Record(
            keyword="K", ref_type="直接", usage_type="その他",
            filepath="f.sql", lineno="1", code="c",
            src_var="", src_file="", src_lineno="",
        )
        self.assertEqual(r.keyword, "K")
        self.assertEqual(r.lineno, "1")
        self.assertEqual(r.src_var, "")


class TestComparisonResult(unittest.TestCase):
    """ComparisonResult は KPI 値と diff 詳細を持つ。"""

    def test_空のresultは網羅率も精度も0で初期化される(self):
        result = measure_kpi.ComparisonResult(
            expected_total=0, matched_rows=0, classified_correctly=0,
            coverage_rate=0.0, classification_accuracy=0.0,
            missing_rows=[], false_positives=[], misclassified=[], detail_diffs=[],
        )
        self.assertEqual(result.expected_total, 0)
        self.assertEqual(result.coverage_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4.2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'measure_kpi'`）

- [ ] **Step 4.3: 最小実装**

Create `scripts/measure_kpi.py`:

```python
"""KPI ゴールデンセット計測スクリプト。

使い方:
    python scripts/measure_kpi.py --lang java
    python scripts/measure_kpi.py --lang all

詳細は docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md を参照。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


class Record(NamedTuple):
    """期待TSV / actual TSV からロードしたレコード（grep_helper.model.GrepRecord 互換の9カラム）。"""
    keyword:    str
    ref_type:   str
    usage_type: str
    filepath:   str
    lineno:     str
    code:       str
    src_var:    str = ""
    src_file:   str = ""
    src_lineno: str = ""


@dataclass
class ComparisonResult:
    """compare() の出力。KPI 値と diff 詳細を保持する。"""
    expected_total: int
    matched_rows: int
    classified_correctly: int
    coverage_rate: float
    classification_accuracy: float
    missing_rows: list[Record] = field(default_factory=list)
    false_positives: list[Record] = field(default_factory=list)
    misclassified: list[tuple[Record, Record]] = field(default_factory=list)
    detail_diffs: list[tuple[Record, Record]] = field(default_factory=list)
```

- [ ] **Step 4.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py -v`
Expected: PASS（2件）

- [ ] **Step 4.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add Record and ComparisonResult skeleton"
```

---

## Task 5: `load_expected_tsv()` / `load_actual_tsv()` の TSV ロード

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 5.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾（`if __name__` の前）に追加：

```python
import csv
import tempfile


class TestLoadTsv(unittest.TestCase):
    """load_expected_tsv / load_actual_tsv は UTF-8 BOM 付きタブ区切り TSV をパースする。"""

    def _write_tsv(self, path: Path, rows: list[list[str]]) -> None:
        headers = ["文言", "参照種別", "使用タイプ", "ファイルパス", "行番号", "コード行",
                   "参照元変数名", "参照元ファイル", "参照元行番号"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(headers)
            for r in rows:
                w.writerow(r)

    def test_BOM付きTSVをパースしてRecord列を返す(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.tsv"
            self._write_tsv(p, [
                ["K", "直接", "その他", "f.sql", "10", "code1", "", "", ""],
                ["K", "間接", "条件判定", "g.sql", "20", "code2", "V", "f.sql", "10"],
            ])
            records = measure_kpi.load_expected_tsv(p)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].keyword, "K")
            self.assertEqual(records[0].lineno, "10")
            self.assertEqual(records[1].src_var, "V")

    def test_空ファイル(ヘッダのみ)は空リストを返す(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.tsv"
            self._write_tsv(p, [])
            records = measure_kpi.load_expected_tsv(p)
            self.assertEqual(records, [])

    def test_load_actual_tsvもload_expected_tsvと同じ動作(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.tsv"
            self._write_tsv(p, [["K", "直接", "その他", "f.sql", "1", "c", "", "", ""]])
            self.assertEqual(
                measure_kpi.load_actual_tsv(p),
                measure_kpi.load_expected_tsv(p),
            )
```

- [ ] **Step 5.2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestLoadTsv -v`
Expected: FAIL（`AttributeError: module 'measure_kpi' has no attribute 'load_expected_tsv'`）

- [ ] **Step 5.3: 最小実装**

`scripts/measure_kpi.py` の末尾に追加：

```python
import csv
from pathlib import Path


def load_expected_tsv(path: Path) -> list[Record]:
    """期待TSV をパースして Record 列を返す。UTF-8 BOM・タブ区切り・9カラム。"""
    return _load_tsv(path)


def load_actual_tsv(path: Path) -> list[Record]:
    """actual TSV をパースして Record 列を返す。スキーマは expected と同じ。"""
    return _load_tsv(path)


def _load_tsv(path: Path) -> list[Record]:
    records: list[Record] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader, None)  # ヘッダをスキップ
        for row in reader:
            # 9カラム未満ならパディング
            padded = list(row) + [""] * max(0, 9 - len(row))
            records.append(Record(
                keyword=padded[0],
                ref_type=padded[1],
                usage_type=padded[2],
                filepath=padded[3],
                lineno=padded[4],
                code=padded[5],
                src_var=padded[6],
                src_file=padded[7],
                src_lineno=padded[8],
            ))
    return records
```

- [ ] **Step 5.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestLoadTsv -v`
Expected: PASS（3件）

- [ ] **Step 5.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add load_expected_tsv / load_actual_tsv"
```

---

## Task 6: `compare()` の網羅率計算

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 6.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
def _rec(filepath: str, lineno: str, ref_type: str = "直接", usage: str = "その他", keyword: str = "K") -> "measure_kpi.Record":
    return measure_kpi.Record(
        keyword=keyword, ref_type=ref_type, usage_type=usage,
        filepath=filepath, lineno=lineno, code="c",
    )


class TestCompareCoverage(unittest.TestCase):
    """compare() の網羅率: (file, line) ベースで expected が actual に含まれる割合。"""

    def test_完全一致なら網羅率は1_0(self):
        expected = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        actual = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertEqual(result.matched_rows, 2)

    def test_片方だけ取りこぼすと網羅率は0_5(self):
        expected = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        actual = [_rec("f.sql", "1")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 0.5)
        self.assertEqual(result.matched_rows, 1)
        self.assertEqual(len(result.missing_rows), 1)
        self.assertEqual(result.missing_rows[0].lineno, "2")
```

- [ ] **Step 6.2: 失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestCompareCoverage -v`
Expected: FAIL

- [ ] **Step 6.3: 最小実装**

`scripts/measure_kpi.py` の末尾に追加：

```python
def compare(expected: list[Record], actual: list[Record]) -> ComparisonResult:
    """expected と actual を突合し、網羅率・分類精度・diff を算出する。

    マッチング基準キー = (filepath, lineno)。
    網羅率: matched_rows / expected_total
    分類精度: classified_correctly / matched_rows（後続タスクで実装）
    """
    expected_by_key: dict[tuple[str, str], Record] = {(r.filepath, r.lineno): r for r in expected}
    actual_by_key: dict[tuple[str, str], Record] = {(r.filepath, r.lineno): r for r in actual}

    matched_keys = expected_by_key.keys() & actual_by_key.keys()
    missing_keys = expected_by_key.keys() - actual_by_key.keys()

    expected_total = len(expected)
    matched_rows = len(matched_keys)

    coverage_rate = matched_rows / expected_total if expected_total > 0 else 1.0

    return ComparisonResult(
        expected_total=expected_total,
        matched_rows=matched_rows,
        classified_correctly=0,  # Task 7
        coverage_rate=coverage_rate,
        classification_accuracy=0.0,  # Task 7
        missing_rows=[expected_by_key[k] for k in missing_keys],
        false_positives=[],  # Task 8
        misclassified=[],
        detail_diffs=[],
    )
```

- [ ] **Step 6.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestCompareCoverage -v`
Expected: PASS

- [ ] **Step 6.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add compare() coverage_rate calculation"
```

---

## Task 7: `compare()` の分類精度

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 7.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestCompareClassificationAccuracy(unittest.TestCase):
    """compare() の分類精度: matched 行のうち (参照種別, 使用タイプ) も一致する割合。"""

    def test_全行で分類が一致すると精度は1_0(self):
        expected = [_rec("f.sql", "1", ref_type="直接", usage="定数定義")]
        actual = [_rec("f.sql", "1", ref_type="直接", usage="定数定義")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.classification_accuracy, 1.0)
        self.assertEqual(result.classified_correctly, 1)

    def test_使用タイプが違うと誤分類として記録される(self):
        expected = [_rec("f.sql", "1", usage="定数定義"), _rec("f.sql", "2", usage="条件判定")]
        actual = [_rec("f.sql", "1", usage="定数定義"), _rec("f.sql", "2", usage="その他")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.classification_accuracy, 0.5)
        self.assertEqual(len(result.misclassified), 1)
        exp_rec, act_rec = result.misclassified[0]
        self.assertEqual(exp_rec.usage_type, "条件判定")
        self.assertEqual(act_rec.usage_type, "その他")

    def test_参照種別が違うと誤分類として記録される(self):
        expected = [_rec("f.sql", "1", ref_type="直接")]
        actual = [_rec("f.sql", "1", ref_type="間接")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.classification_accuracy, 0.0)
        self.assertEqual(len(result.misclassified), 1)
```

- [ ] **Step 7.2: 失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestCompareClassificationAccuracy -v`
Expected: FAIL（精度 0.0 のまま）

- [ ] **Step 7.3: `compare()` を更新**

`scripts/measure_kpi.py` の `compare()` の中身を以下に置き換える：

```python
def compare(expected: list[Record], actual: list[Record]) -> ComparisonResult:
    """expected と actual を突合し、網羅率・分類精度・diff を算出する。

    マッチング基準キー = (filepath, lineno)。
    網羅率: matched_rows / expected_total
    分類精度: classified_correctly / matched_rows
    """
    expected_by_key: dict[tuple[str, str], Record] = {(r.filepath, r.lineno): r for r in expected}
    actual_by_key: dict[tuple[str, str], Record] = {(r.filepath, r.lineno): r for r in actual}

    matched_keys = expected_by_key.keys() & actual_by_key.keys()
    missing_keys = expected_by_key.keys() - actual_by_key.keys()

    expected_total = len(expected)
    matched_rows = len(matched_keys)

    classified_correctly = 0
    misclassified: list[tuple[Record, Record]] = []
    for key in matched_keys:
        exp = expected_by_key[key]
        act = actual_by_key[key]
        if exp.ref_type == act.ref_type and exp.usage_type == act.usage_type:
            classified_correctly += 1
        else:
            misclassified.append((exp, act))

    coverage_rate = matched_rows / expected_total if expected_total > 0 else 1.0
    classification_accuracy = (
        classified_correctly / matched_rows if matched_rows > 0 else 0.0
    )

    return ComparisonResult(
        expected_total=expected_total,
        matched_rows=matched_rows,
        classified_correctly=classified_correctly,
        coverage_rate=coverage_rate,
        classification_accuracy=classification_accuracy,
        missing_rows=[expected_by_key[k] for k in missing_keys],
        false_positives=[],  # Task 8
        misclassified=misclassified,
        detail_diffs=[],  # Task 9
    )
```

- [ ] **Step 7.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestCompareClassificationAccuracy -v`
Expected: PASS（3件）

- [ ] **Step 7.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add classification accuracy to compare()"
```

---

## Task 8: `compare()` の false positive 検出

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 8.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestCompareFalsePositive(unittest.TestCase):
    """compare() の FP: actual のみに存在する行は false_positives に入る（KPI不算入）。"""

    def test_actualのみに存在する行はfalse_positivesに入る(self):
        expected = [_rec("f.sql", "1")]
        actual = [_rec("f.sql", "1"), _rec("g.sql", "5")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(len(result.false_positives), 1)
        self.assertEqual(result.false_positives[0].filepath, "g.sql")

    def test_FP件数は網羅率と分類精度に影響しない(self):
        expected = [_rec("f.sql", "1")]
        actual = [_rec("f.sql", "1"), _rec("g.sql", "5"), _rec("h.sql", "9")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertEqual(result.classification_accuracy, 1.0)
        self.assertEqual(len(result.false_positives), 2)
```

- [ ] **Step 8.2: 失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestCompareFalsePositive -v`
Expected: FAIL

- [ ] **Step 8.3: `compare()` を更新（FP 検出を追加）**

`scripts/measure_kpi.py` の `compare()` 内、`misclassified` を計算するブロックの後に追加：

```python
    fp_keys = actual_by_key.keys() - expected_by_key.keys()
    false_positives = [actual_by_key[k] for k in fp_keys]
```

そして `return ComparisonResult(...)` の `false_positives=[]` を `false_positives=false_positives,` に変更。

- [ ] **Step 8.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestCompareFalsePositive -v`
Expected: PASS（2件）

- [ ] **Step 8.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): detect false positives in compare()"
```

---

## Task 9: `compare()` のゼロ除算エッジケース

**Files:**
- Modify: `tests/test_measure_kpi.py`

`compare()` は Task 6/7 で既に `if expected_total > 0` / `if matched_rows > 0` のガードを入れているため、テストで挙動を確定させる。

- [ ] **Step 9.1: テストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestCompareEdgeCases(unittest.TestCase):
    """compare() のゼロ除算エッジケース。spec §ゼロ除算エッジケース に準拠。"""

    def test_期待TSVが空なら網羅率は1_0扱い(self):
        result = measure_kpi.compare([], [])
        self.assertEqual(result.coverage_rate, 1.0)
        self.assertEqual(result.expected_total, 0)

    def test_全件取りこぼしなら網羅率も精度も0_0(self):
        expected = [_rec("f.sql", "1"), _rec("f.sql", "2")]
        actual = []
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 0.0)
        self.assertEqual(result.classification_accuracy, 0.0)
        self.assertEqual(result.matched_rows, 0)
```

- [ ] **Step 9.2: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestCompareEdgeCases -v`
Expected: PASS（2件、既存実装で通る）

- [ ] **Step 9.3: コミット**

```bash
git add tests/test_measure_kpi.py
git commit -m "test(measure_kpi): pin down compare() zero-division behavior"
```

---

## Task 10: `assert_coverage_distribution()` でゴールデンセット分布チェック

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 10.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestAssertCoverageDistribution(unittest.TestCase):
    """assert_coverage_distribution: ゴールデンセットが各使用タイプ・参照種別を満たすかを警告列で返す。"""

    def _spec(self) -> dict:
        return {
            "usage_types": ["定数定義", "条件判定", "その他"],
            "min_per_type": 1,
            "reference_kinds_required": ["直接"],
        }

    def test_全使用タイプが1件以上ある場合は警告ゼロ(self):
        expected = [
            _rec("f.sql", "1", usage="定数定義"),
            _rec("f.sql", "2", usage="条件判定"),
            _rec("f.sql", "3", usage="その他"),
        ]
        warnings = measure_kpi.assert_coverage_distribution(expected, self._spec())
        self.assertEqual(warnings, [])

    def test_使用タイプ不足なら警告が出る(self):
        expected = [_rec("f.sql", "1", usage="定数定義")]
        warnings = measure_kpi.assert_coverage_distribution(expected, self._spec())
        self.assertTrue(any("条件判定" in w for w in warnings))
        self.assertTrue(any("その他" in w for w in warnings))

    def test_必要な参照種別が無いと警告が出る(self):
        expected = [_rec("f.sql", "1", ref_type="間接", usage="定数定義")]
        spec = {**self._spec(), "usage_types": ["定数定義"]}
        warnings = measure_kpi.assert_coverage_distribution(expected, spec)
        self.assertTrue(any("直接" in w for w in warnings))
```

- [ ] **Step 10.2: 失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestAssertCoverageDistribution -v`
Expected: FAIL

- [ ] **Step 10.3: 最小実装**

`scripts/measure_kpi.py` の末尾に追加：

```python
def assert_coverage_distribution(records: list[Record], lang_spec: dict) -> list[str]:
    """ゴールデンセットが lang_spec の網羅要件を満たすか検証し、警告メッセージ列を返す。

    Args:
        records:    期待TSV からロードしたレコード列
        lang_spec:  {"usage_types": [...], "min_per_type": int, "reference_kinds_required": [...]}

    Returns: 警告文字列のリスト。空なら OK。
    """
    warnings: list[str] = []
    usage_types = lang_spec["usage_types"]
    min_per_type = lang_spec["min_per_type"]
    ref_kinds = lang_spec["reference_kinds_required"]

    # 使用タイプの件数チェック
    counts: dict[str, int] = {ut: 0 for ut in usage_types}
    for r in records:
        if r.usage_type in counts:
            counts[r.usage_type] += 1
    for ut, c in counts.items():
        if c < min_per_type:
            warnings.append(
                f"使用タイプ「{ut}」: {c} 件 (要 {min_per_type} 件以上)"
            )

    # 参照種別の存在チェック
    seen_kinds = {r.ref_type for r in records}
    for kind in ref_kinds:
        if kind not in seen_kinds:
            warnings.append(f"参照種別「{kind}」のサンプルが1件もない")

    return warnings
```

- [ ] **Step 10.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestAssertCoverageDistribution -v`
Expected: PASS（3件）

- [ ] **Step 10.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add assert_coverage_distribution()"
```

---

## Task 11: `format_summary()` の主要数値存在チェック

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 11.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestFormatSummary(unittest.TestCase):
    """format_summary: 完全一致のスナップショットは取らず、主要数値とラベルの存在を検証する
    （feedback_test_style §5 変更耐性と整合）。
    """

    def _result(self, coverage: float = 1.0, accuracy: float = 1.0,
                missing: int = 0, fp: int = 0) -> "measure_kpi.ComparisonResult":
        return measure_kpi.ComparisonResult(
            expected_total=10, matched_rows=int(10 * coverage),
            classified_correctly=int(10 * coverage * accuracy),
            coverage_rate=coverage, classification_accuracy=accuracy,
            missing_rows=[_rec("f", str(i)) for i in range(missing)],
            false_positives=[_rec("g", str(i)) for i in range(fp)],
        )

    def test_網羅率と分類精度の数値が含まれる(self):
        out = measure_kpi.format_summary(self._result(coverage=0.9, accuracy=0.85))
        self.assertIn("90.0%", out)
        self.assertIn("85.0%", out)

    def test_網羅率100未満ならWARNラベル(self):
        out = measure_kpi.format_summary(self._result(coverage=0.9))
        self.assertIn("WARN", out)

    def test_網羅率100ならOKラベル(self):
        out = measure_kpi.format_summary(self._result(coverage=1.0, accuracy=1.0))
        self.assertNotIn("WARN", out)
        self.assertIn("OK", out)

    def test_FP件数が表示される(self):
        out = measure_kpi.format_summary(self._result(fp=5))
        self.assertIn("5", out)
        self.assertIn("false positive", out.lower() if "false" in out.lower() else out)
```

- [ ] **Step 11.2: 失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestFormatSummary -v`
Expected: FAIL

- [ ] **Step 11.3: 最小実装**

`scripts/measure_kpi.py` の末尾に追加：

```python
# しきい値定数（spec §出力フォーマット 参照）
COVERAGE_THRESHOLD = 1.0
ACCURACY_THRESHOLD = 0.9


def format_summary(result: ComparisonResult) -> str:
    """ComparisonResult から stdout 用の短いサマリ文字列を生成する。
    完全一致のスナップショットは取らず、主要数値の存在で検証される設計。
    """
    cov_pct = result.coverage_rate * 100
    acc_pct = result.classification_accuracy * 100
    cov_label = "OK" if result.coverage_rate >= COVERAGE_THRESHOLD else "WARN"
    acc_label = "OK" if result.classification_accuracy >= ACCURACY_THRESHOLD else "WARN"

    lines = [
        f"網羅率: {result.matched_rows}/{result.expected_total} ({cov_pct:.1f}%) [{cov_label}]",
        f"分類精度: {result.classified_correctly}/{result.matched_rows} ({acc_pct:.1f}%) [{acc_label}]",
        f"false positive: {len(result.false_positives)}件 (KPI算入なし)",
    ]
    if result.missing_rows:
        lines.append(f"取りこぼし: {len(result.missing_rows)}件")
    if result.misclassified:
        lines.append(f"誤分類: {len(result.misclassified)}件")
    return "\n".join(lines)
```

- [ ] **Step 11.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestFormatSummary -v`
Expected: PASS（4件）

- [ ] **Step 11.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add format_summary() with WARN/OK labels"
```

---

## Task 12: `format_detail_report()` の Markdown 章構成

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 12.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestFormatDetailReport(unittest.TestCase):
    """format_detail_report: Markdown レポート。章タイトルと主要数値の存在で検証する。"""

    def test_主要章が含まれる(self):
        result = measure_kpi.ComparisonResult(
            expected_total=2, matched_rows=1, classified_correctly=1,
            coverage_rate=0.5, classification_accuracy=1.0,
            missing_rows=[_rec("f", "2")],
            false_positives=[_rec("g", "5")],
            misclassified=[],
        )
        out = measure_kpi.format_detail_report(result)
        self.assertIn("# KPI", out)
        self.assertIn("## サマリ", out)
        self.assertIn("## 取りこぼし", out)
        self.assertIn("## false positive", out)

    def test_取りこぼし行のファイルパスと行番号が含まれる(self):
        result = measure_kpi.ComparisonResult(
            expected_total=1, matched_rows=0, classified_correctly=0,
            coverage_rate=0.0, classification_accuracy=0.0,
            missing_rows=[_rec("missing.sql", "42")],
        )
        out = measure_kpi.format_detail_report(result)
        self.assertIn("missing.sql", out)
        self.assertIn("42", out)
```

- [ ] **Step 12.2: 失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestFormatDetailReport -v`
Expected: FAIL

- [ ] **Step 12.3: 最小実装**

`scripts/measure_kpi.py` の末尾に追加：

```python
def format_detail_report(result: ComparisonResult, *, lang: str = "", timestamp: str = "") -> str:
    """Markdown 詳細レポートを生成する。spec §詳細レポート の章構成に準拠。"""
    header = f"# KPI 計測レポート"
    if lang:
        header += f" ({lang})"
    if timestamp:
        header += f" — {timestamp}"

    parts = [header, "", "## サマリ", "", format_summary(result), ""]

    parts.append("## 取りこぼし行（網羅率を下げている要因）")
    if result.missing_rows:
        parts.append("| ファイルパス | 行番号 | 期待コード行 | 期待使用タイプ |")
        parts.append("|---|---|---|---|")
        for r in result.missing_rows:
            parts.append(f"| {r.filepath} | {r.lineno} | {r.code} | {r.usage_type} |")
    else:
        parts.append("（なし）")
    parts.append("")

    parts.append("## 誤分類行（分類精度を下げている要因）")
    if result.misclassified:
        parts.append("| ファイル | 行 | 期待 | 実際 |")
        parts.append("|---|---|---|---|")
        for exp, act in result.misclassified:
            parts.append(f"| {exp.filepath} | {exp.lineno} | {exp.ref_type}/{exp.usage_type} | {act.ref_type}/{act.usage_type} |")
    else:
        parts.append("（なし）")
    parts.append("")

    parts.append("## false positive（参考、KPI算入なし）")
    if result.false_positives:
        parts.append("| ファイル | 行 | 実際の使用タイプ |")
        parts.append("|---|---|---|")
        for r in result.false_positives:
            parts.append(f"| {r.filepath} | {r.lineno} | {r.usage_type} |")
    else:
        parts.append("（なし）")

    return "\n".join(parts) + "\n"
```

- [ ] **Step 12.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestFormatDetailReport -v`
Expected: PASS（2件）

- [ ] **Step 12.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add format_detail_report() in Markdown"
```

---

## Task 13: `JAVA_SPEC` 定数 + `run()` メイン処理 + CLI

`lang_spec` のスキーマを Java で確定する。`tool-overview.md §4-2` の Java 使用タイプを参照（アノテーション・定数定義・変数代入・条件判定・return文・メソッド引数・その他）。

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 13.1: `LANG_SPECS` 定数を追加**

`scripts/measure_kpi.py` の `Record` クラス定義の上（import の下）に追加：

```python
LANG_SPECS: dict[str, dict] = {
    "java": {
        "module": "grep_helper.languages.java",
        "usage_types": [
            "アノテーション", "定数定義", "変数代入", "条件判定",
            "return文", "メソッド引数", "その他",
        ],
        "min_per_type": 10,  # Java 深堀り
        "reference_kinds_required": [
            "直接", "間接", "間接（getter経由）", "間接（setter経由）",
        ],
    },
    # 他言語は Step 5 (Task 19) で追加
}
```

- [ ] **Step 13.2: `run()` の最小実装（Java単言語のみ）**

`scripts/measure_kpi.py` の末尾に以下を追加する。**ただし `import` 文（最初の7行）は Python の慣例に従って必ずファイルの先頭の他の import と一緒に置くこと**（既存の `import csv` / `from pathlib import Path` などの近く）。本タスクが終わった時点で全 import がファイル先頭にまとまっている状態にする。

```python
import argparse
import datetime
import importlib
import sys
import tempfile

from grep_helper.pipeline import run_full_pipeline


def run(argv: list[str] | None = None) -> int:
    """CLI エントリポイント。

    Returns:
        0: 計測完了（しきい値割れでも 0）
        1: 入力エラー（ディレクトリ欠損、ペアリング不一致、未対応 lang）
        2: 実行時例外
    """
    parser = argparse.ArgumentParser(description="KPI ゴールデンセット計測スクリプト")
    parser.add_argument("--lang", required=True, help="計測対象言語（または all）")
    parser.add_argument("--samples-dir", default="tests/golden", help="ゴールデンセットのルート")
    parser.add_argument("--output-dir", default="output/kpi", help="レポート出力先")
    parser.add_argument("--quiet", action="store_true", help="stdout サマリを抑制")
    args = parser.parse_args(argv)

    samples_dir = Path(args.samples_dir)
    output_dir = Path(args.output_dir)

    if args.lang == "all":
        return _run_all(samples_dir, output_dir, quiet=args.quiet)
    if args.lang not in LANG_SPECS:
        print(f"エラー: 未対応の --lang: {args.lang}", file=sys.stderr)
        return 1

    try:
        return _run_single(args.lang, samples_dir, output_dir, quiet=args.quiet)
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        return 2


def _run_single(lang: str, samples_dir: Path, output_dir: Path, *, quiet: bool) -> int:
    """単一言語の KPI 計測。Step 5 (Task 20) で _run_all から呼ばれる形に再利用する。"""
    spec = LANG_SPECS[lang]
    lang_dir = samples_dir / lang
    inputs_dir = lang_dir / "inputs"
    expected_dir = lang_dir / "expected"
    src_dir = lang_dir / "src"

    if not lang_dir.is_dir():
        raise FileNotFoundError(f"言語ディレクトリが存在しません: {lang_dir}")
    if not inputs_dir.is_dir() or not expected_dir.is_dir() or not src_dir.is_dir():
        raise FileNotFoundError(f"inputs/expected/src いずれかが存在しません: {lang_dir}")

    # ペアリング検証
    grep_files = sorted(inputs_dir.glob("*.grep"))
    expected_files = {p.stem for p in expected_dir.glob("*.tsv")}
    actual_stems = {p.stem for p in grep_files}
    if actual_stems != expected_files:
        raise FileNotFoundError(
            f"inputs/expected の対応不一致: only-input={actual_stems - expected_files}, "
            f"only-expected={expected_files - actual_stems}"
        )

    handler = importlib.import_module(spec["module"])

    # 各 grep ファイルを処理
    aggregated = ComparisonResult(
        expected_total=0, matched_rows=0, classified_correctly=0,
        coverage_rate=0.0, classification_accuracy=0.0,
    )
    per_file: list[tuple[str, ComparisonResult]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_full_pipeline(
            source_dir=src_dir,
            input_dir=inputs_dir,
            output_dir=tmp_path,
            handler=handler,
            workers=1,
        )
        for grep_path in grep_files:
            stem = grep_path.stem
            actual = load_actual_tsv(tmp_path / f"{stem}.tsv")
            expected = load_expected_tsv(expected_dir / f"{stem}.tsv")
            res = compare(expected, actual)
            per_file.append((stem, res))
            aggregated.expected_total += res.expected_total
            aggregated.matched_rows += res.matched_rows
            aggregated.classified_correctly += res.classified_correctly
            aggregated.missing_rows.extend(res.missing_rows)
            aggregated.false_positives.extend(res.false_positives)
            aggregated.misclassified.extend(res.misclassified)

    aggregated.coverage_rate = (
        aggregated.matched_rows / aggregated.expected_total
        if aggregated.expected_total > 0 else 1.0
    )
    aggregated.classification_accuracy = (
        aggregated.classified_correctly / aggregated.matched_rows
        if aggregated.matched_rows > 0 else 0.0
    )

    # 分布チェック
    all_expected: list[Record] = []
    for _, r in per_file:
        all_expected.extend([m for m in r.missing_rows] + [])  # missing は expected の一部
    # 簡易: 全 expected を改めてロード
    all_expected = []
    for grep_path in grep_files:
        all_expected.extend(load_expected_tsv(expected_dir / f"{grep_path.stem}.tsv"))
    distribution_warnings = assert_coverage_distribution(all_expected, spec)

    # レポート出力
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{lang}-{timestamp}.md"
    report_path.write_text(
        format_detail_report(aggregated, lang=lang, timestamp=timestamp),
        encoding="utf-8",
    )

    if not quiet:
        print(f"=== KPI 計測結果 ({lang}) ===")
        for stem, res in per_file:
            print(f"\n[{stem}.grep]")
            print(format_summary(res))
        print(f"\n=== 合計 ({lang}) ===")
        print(format_summary(aggregated))
        if distribution_warnings:
            print("\nサンプル分布警告:")
            for w in distribution_warnings:
                print(f"  - {w}")
        print(f"\n詳細レポート: {report_path}")

    return 0


def _run_all(samples_dir: Path, output_dir: Path, *, quiet: bool) -> int:
    """全言語ループ（Task 20 で実装）。"""
    raise NotImplementedError("--lang all は Task 20 で実装")


if __name__ == "__main__":
    raise SystemExit(run())
```

- [ ] **Step 13.3: 未対応言語で exit 1 を返すテスト**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestRunCli(unittest.TestCase):
    """run() の CLI 振る舞い。"""

    def test_未対応のlangを指定するとexit_1(self):
        result = measure_kpi.run(["--lang", "doesnotexist"])
        self.assertEqual(result, 1)

    def test_存在しないsamples_dirを指定するとexit_1(self):
        result = measure_kpi.run([
            "--lang", "java",
            "--samples-dir", "/tmp/__nonexistent_samples__",
            "--quiet",
        ])
        self.assertEqual(result, 1)
```

- [ ] **Step 13.4: 上記テストを実行して PASS を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestRunCli -v`
Expected: PASS（2件）

- [ ] **Step 13.5: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): add run() CLI with single-language support"
```

---

# Step 3: Java ゴールデンセット + Java E2E ★検証ゲート

## Task 14: Java ゴールデンセット — 最小サンプル（直接参照のみ、各使用タイプ1件）

**目的**: まず E2E が動く最小セットを作って、Step 2 のスクリプトが正しく動くことを検証する。本格的な500件超サンプルは Task 15 で増やす。

**Files:**
- Create: `tests/golden/java/src/Demo.java`
- Create: `tests/golden/java/inputs/777.grep`
- Create: `tests/golden/java/expected/777.tsv`
- Create: `tests/golden/java/README.md`

- [ ] **Step 14.1: Java サンプルソース作成**

Create `tests/golden/java/src/Demo.java`:

```java
package demo;

public class Demo {
    public static final String CODE = "777";

    @Deprecated
    public String process(String input) {
        if (input.equals("777")) {
            return "777";
        }
        String local = "777";
        return local;
    }

    public void other() {
        System.out.println("777");
    }
}
```

- [ ] **Step 14.2: grep ファイル作成**

Create `tests/golden/java/inputs/777.grep`:

```
src/Demo.java:4:    public static final String CODE = "777";
src/Demo.java:8:        if (input.equals("777")) {
src/Demo.java:9:            return "777";
src/Demo.java:11:        String local = "777";
src/Demo.java:16:        System.out.println("777");
```

- [ ] **Step 14.3: 期待TSV をツール出力ベースで作成**

`scripts/measure_kpi.py` を実行する前にツールで actual を取得：

```bash
mkdir -p /tmp/kpi_bootstrap
cd /workspaces/grep_helper_superpowers
python analyze.py \
    --source-dir tests/golden/java/src \
    --input-dir tests/golden/java/inputs \
    --output-dir /tmp/kpi_bootstrap
cat /tmp/kpi_bootstrap/777.tsv
```

出力を**人間がレビュー**して、各行が「正解」か確認する。ここで分類が間違っていたら、それは expected ではなくバグ報告になる。

レビューが通ったら期待TSV としてコピー:

```bash
cp /tmp/kpi_bootstrap/777.tsv tests/golden/java/expected/777.tsv
```

期待TSV は手書きで `tests/golden/java/expected/777.tsv` に置く（ツール出力をそのまま正解にしたわけではなく、人間レビュー後に確定したもの）。

- [ ] **Step 14.4: README 作成**

Create `tests/golden/java/README.md`:

```markdown
# Java ゴールデンセット

## 役割
このディレクトリは Java の KPI 計測用ゴールデンセット。区分: **深堀り**（要件 §成功指標 を満たす規模）。

## 状態
- Task 14 で最小サンプル（各使用タイプ1件、直接参照のみ）を投入済み
- Task 15 で各使用タイプ10件以上 + 間接参照 + getter/setter 追加予定

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプルファイル | 該当行 | 件数 |
|---|---|---|---|
| 定数定義 | Demo.java | 4 | 1 |
| アノテーション | Demo.java | 6 | 1 |
| 条件判定 | Demo.java | 8 | 1 |
| return文 | Demo.java | 9 | 1 |
| 変数代入 | Demo.java | 11 | 1 |
| メソッド引数 | Demo.java | 16 | 1 |

## grep ファイル一覧
| ファイル | 文言 | 役割 |
|---|---|---|
| 777.grep | 777 | 使用タイプ網羅（最小、Task 14） |

## 期待TSV 手書きルール
共通 spec を参照: `docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` §期待TSV の手書きルール

## サンプル追加手順
1. `src/` に新パターンの Java を追加
2. `grep -rn "<文言>" src/` または手書きで grep ファイル更新
3. ツール（`analyze.py`）で actual を生成し、人間がレビューして expected に確定
4. `python scripts/measure_kpi.py --lang java` で網羅率 100% を確認

## 50ファイル目安の独自解釈
要件 §成功指標 「テスト用Javaソース50ファイル」は、件数を分散させる目安として解釈する。
実装上は使用タイプ別件数しきい値（各10件以上）を主、ファイル数を従として扱う。
```

- [ ] **Step 14.5: コミット**

```bash
git add tests/golden/java/
git commit -m "test(golden/java): add minimum bootstrap sample for KPI script validation"
```

---

## Task 15: Java E2E テスト

**Files:**
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 15.1: テストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestRunCliEndToEndJava(unittest.TestCase):
    """E2E: tests/golden/java/ の最小サブセットで run() がクラッシュせず coverage 1.0 を返す。
    フルセット 100% は §成功条件 5/6（手動確認）で別途規定。
    """

    def test_javaの最小ゴールデンセットで例外なくrunが完了する(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = measure_kpi.run([
                "--lang", "java",
                "--samples-dir", "tests/golden",
                "--output-dir", tmp,
                "--quiet",
            ])
            self.assertEqual(exit_code, 0)
            # レポートが書き出されていること
            reports = list(Path(tmp).glob("java-*.md"))
            self.assertEqual(len(reports), 1)

    def test_javaの最小ゴールデンセットで網羅率は1_0(self):
        # ロード&compare を直接呼んで coverage を assert
        expected = measure_kpi.load_expected_tsv(
            Path("tests/golden/java/expected/777.tsv")
        )
        with tempfile.TemporaryDirectory() as tmp:
            from grep_helper.languages import java as java_handler
            from grep_helper.pipeline import run_full_pipeline
            tmp_path = Path(tmp)
            run_full_pipeline(
                source_dir=Path("tests/golden/java/src"),
                input_dir=Path("tests/golden/java/inputs"),
                output_dir=tmp_path,
                handler=java_handler,
                workers=1,
            )
            actual = measure_kpi.load_actual_tsv(tmp_path / "777.tsv")
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 1.0,
                         f"missing_rows={result.missing_rows}")
```

- [ ] **Step 15.2: テストを実行**

Run: `python -m pytest tests/test_measure_kpi.py::TestRunCliEndToEndJava -v`
Expected: PASS（2件）

もし FAIL する場合: 
- `coverage_rate < 1.0` なら expected と actual が乖離している → expected を見直す（人間レビュー）
- 例外が出るなら `run_full_pipeline` か `run` のバグ → デバッグして修正

- [ ] **Step 15.3: コミット**

```bash
git add tests/test_measure_kpi.py
git commit -m "test(measure_kpi): add Java E2E with bootstrap golden sample"
```

---

## Task 16: Java ゴールデンセットを本番規模に拡張

**目的**: 各使用タイプ10件以上、間接参照（field/local/constant）、getter/setter経由の各シナリオを `777.grep` + `CODE.grep` でカバーし、合計500件以上を達成する。

これは spec §Java 深堀り の要件を満たす作業。Step 14 の最小セットと差し替える形で増強する。

**Files:**
- Modify (大規模追加): `tests/golden/java/src/*.java`（複数ファイル）
- Modify (大規模追加): `tests/golden/java/inputs/777.grep`, `tests/golden/java/inputs/CODE.grep`
- Modify (大規模追加): `tests/golden/java/expected/777.tsv`, `tests/golden/java/expected/CODE.tsv`
- Modify: `tests/golden/java/README.md`（マトリクス更新）

- [ ] **Step 16.1: サンプル設計を README に書き起こす**

README のマトリクスを「使用タイプ × 件数 × ファイル」の表に更新する。例：

```markdown
## 使用タイプ × サンプルファイル マトリクス（本番）
| 使用タイプ | 件数 | 主な配置先 |
|---|---|---|
| 定数定義 | 10 | Constants.java, Status.java |
| アノテーション | 10 | Annotated.java |
| 条件判定 | 10+ | Service.java, Validator.java |
| 変数代入 | 10+ | Setter.java, Mutator.java |
| return文 | 10+ | Returner.java |
| メソッド引数 | 10+ | Caller.java |
| その他 | 10+ | Comments.java |

## 参照種別シナリオ
| シナリオ | 配置 |
|---|---|
| 直接 | 上記すべて |
| 間接（定数経由） | Constants.CODE → Service で使用 |
| 間接（フィールド経由） | Entity.type → 同一クラス内 |
| 間接（ローカル変数経由） | Service.process() 内 |
| 間接（getter経由） | Entity.getType() → Handler |
| 間接（setter経由） | Entity.setType() → Mutator |
```

- [ ] **Step 16.2: Java ファイル群を作成**

`tests/golden/java/src/` の下に上記マトリクスを満たす Java ファイル群を作成する。各ファイルは20-50行程度。1ファイルで複数の使用タイプを混ぜてよいが、責務が明確になるよう分散する。

**重要**: 「同じパターンのコピペで件数を稼ぐ」のではなく、**現実のコーディングパターンに近いバリエーション**を持たせる（クラス名・変数名・コメント・空行などを変える）。これによってアナライザの汎用性が検証できる。

- [ ] **Step 16.3: grep ファイル作成**

`grep -rn "777" tests/golden/java/src/ > tests/golden/java/inputs/777.grep`
`grep -rn "CODE" tests/golden/java/src/ > tests/golden/java/inputs/CODE.grep`

ヘッダ行や絶対パスが入る場合は手で整形する（`tests/golden/java/src/...` の相対パスにする）。

- [ ] **Step 16.4: 期待TSV を半自動生成 → 人間レビュー**

```bash
mkdir -p /tmp/kpi_bootstrap
python analyze.py \
    --source-dir tests/golden/java/src \
    --input-dir tests/golden/java/inputs \
    --output-dir /tmp/kpi_bootstrap
```

`/tmp/kpi_bootstrap/777.tsv` と `CODE.tsv` を**人間が1行ずつレビュー**：
- 使用タイプの分類が「人間の判断」と一致しているか
- 不一致があればそれは「アナライザのバグ」候補なので、別途 issue として記録するか、期待TSV を「人間正解」に書き換える

レビュー後 `tests/golden/java/expected/` に確定版を配置。

- [ ] **Step 16.5: 件数チェック**

```bash
wc -l tests/golden/java/expected/777.tsv tests/golden/java/expected/CODE.tsv
```

合計 500行 + ヘッダ2行 = 502 行以上を目標。

- [ ] **Step 16.6: 計測スクリプトで網羅率 100% / 分類精度 90% 以上を確認**

```bash
python scripts/measure_kpi.py --lang java
```

Expected stdout:
```
網羅率: 500+/500+ (100.0%) [OK]
分類精度: ?/500+ (≥90.0%) [OK]
false positive: ?件
```

もし 100% / 90% 未満なら、原因を分析して expected または lang_spec を修正（あるいはアナライザのバグなら別 issue）。

- [ ] **Step 16.7: 既存の Java E2E テスト（Task 15）が引き続き pass することを確認**

Run: `python -m pytest tests/test_measure_kpi.py -v`
Expected: 全件 pass

- [ ] **Step 16.8: コミット**

```bash
git add tests/golden/java/
git commit -m "test(golden/java): expand to full deep-dive set (500+ samples)

Covers each of the 7 usage types with 10+ samples and includes scenarios
for direct, indirect (constant/field/local), getter, and setter
references. Manual review confirmed each expected TSV row."
```

---

## ★ 検証ゲート: ここで Java の KPI 計測が動くことを確認 ★

- [ ] **Step: スクリプトが Java で正常動作することを手動確認**

```bash
python scripts/measure_kpi.py --lang java
ls output/kpi/java-*.md  # レポートが書き出されていること
```

問題なければ Step 4 に進む。問題があれば Step 4 に進む前に修正する（早期発見）。

---

# Step 4: 他11言語のスモークサンプル

各言語について同じパターンで作業する。Task 17 (C 言語) を雛形として詳細に書き、Task 18 で残り10言語をサブタスク化（共通手順 + 言語別パラメータ表）してまとめる。

## Task 17: C 言語のスモークセット

**Files:**
- Create: `tests/golden/c/src/sample.c`
- Create: `tests/golden/c/src/header.h`
- Create: `tests/golden/c/inputs/777.grep`
- Create: `tests/golden/c/expected/777.tsv`
- Create: `tests/golden/c/README.md`

- [ ] **Step 17.1: C サンプルを作成**

Create `tests/golden/c/src/header.h`:

```c
#ifndef HEADER_H
#define HEADER_H
#define CODE "777"
#endif
```

Create `tests/golden/c/src/sample.c`:

```c
#include "header.h"
#include <string.h>

int check(const char *input) {
    if (strcmp(input, "777") == 0) {
        return 1;
    }
    return 0;
}

void process(const char *value) {
    char *local = "777";
    log_value(local);
}
```

各 C 使用タイプ（#define定数定義 / 条件判定 / return文 / 変数代入 / 関数引数 / その他）が最低1件含まれるように調整する。

- [ ] **Step 17.2: grep ファイル作成**

Create `tests/golden/c/inputs/777.grep`:

```
src/header.h:3:#define CODE "777"
src/sample.c:5:    if (strcmp(input, "777") == 0) {
... (各使用タイプぶん)
```

- [ ] **Step 17.3: 期待TSV を半自動生成 → レビュー → 確定**

```bash
python analyze_c.py \
    --source-dir tests/golden/c/src \
    --input-dir tests/golden/c/inputs \
    --output-dir /tmp/kpi_bootstrap_c
cat /tmp/kpi_bootstrap_c/777.tsv
```

人間レビュー後 `tests/golden/c/expected/777.tsv` に配置。

- [ ] **Step 17.4: README 作成**

Create `tests/golden/c/README.md`:

```markdown
# C ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数 |
|---|---|---|---|
| #define定数定義 | header.h | 3 | 1 |
| 条件判定 | sample.c | 5 | 1 |
| return文 | sample.c | 6,8 | 2 |
| 変数代入 | sample.c | 11 | 1 |
| 関数引数 | sample.c | 12 | 1 |
| その他 | sample.c | (空白行) | 1 |

## 間接参照シナリオ
- #define CODE → sample.c で間接参照される

## サンプル追加手順
共通テンプレートに従う（spec §言語別 README.md の骨子 を参照）。
```

- [ ] **Step 17.5: 計測スクリプトで網羅率を確認**

注意: この時点で `LANG_SPECS` には Java しか入っていない。`--lang c` を実行するには Task 19（LANG_SPECS 拡張）が必要。よって Task 17.5 は Task 19 の後で全言語まとめて検証する形になる。**ここではサンプルを置いただけでコミット**する。

- [ ] **Step 17.6: コミット**

```bash
git add tests/golden/c/
git commit -m "test(golden/c): add C smoke set (6 usage types + 1 indirect)"
```

---

## Task 18: 他10言語のスモークセット作成

Task 17 (C) で確立した手順を、残り10言語に同じ構造で適用する。**各言語ごとに以下のサブタスクを実施し、言語ごとに1コミット作成する。** タスクを順次（subagent への割り当てがある場合も1サブタスクずつ）実施すること。

### 共通手順（各言語で繰り返す）

各言語について Task 17 と同じ5ステップを実施する：

1. **サンプルソース作成**: `tests/golden/<lang>/src/` に最小ファイル群を作成。下表の使用タイプと参照種別をすべてカバーする
2. **grep ファイル作成**: `tests/golden/<lang>/inputs/777.grep` を手書きまたは `grep -rn "777" tests/golden/<lang>/src/` で生成
3. **期待TSV を半自動生成 → 人間レビュー → 確定**:
   ```bash
   mkdir -p /tmp/kpi_bootstrap_<lang>
   python analyze_<lang>.py \
       --source-dir tests/golden/<lang>/src \
       --input-dir tests/golden/<lang>/inputs \
       --output-dir /tmp/kpi_bootstrap_<lang>
   cat /tmp/kpi_bootstrap_<lang>/777.tsv
   ```
   出力を**人間が1行ずつレビュー**し、正解と確定したものを `tests/golden/<lang>/expected/777.tsv` に配置
4. **README 作成**: 下記テンプレートに沿って `tests/golden/<lang>/README.md` を作成
5. **コミット**: 該当言語のみを add してコミット

### README.md テンプレート（Task 14 の Java README と同型）

```markdown
# <Language> ゴールデンセット

## 役割
区分: **スモーク**（最小カバレッジ）

## 使用タイプ × サンプルファイル マトリクス
| 使用タイプ | サンプル | 行 | 件数 |
|---|---|---|---|
... (各言語の使用タイプを記載)

## 参照種別シナリオ
- 直接参照: ...
- 間接参照: ... (対応言語のみ)

## サンプル追加手順
共通テンプレートに従う（spec §言語別 README.md の骨子 を参照）。
```

### 言語別パラメータ表

各言語の **モジュール名 / CLI / 使用タイプ / 参照種別 / 想定件数 / コミットメッセージ** は以下の通り。これに従ってサンプルを設計する。

| サブタスク | lang | CLI コマンド | 使用タイプ（必須カバー） | 参照種別シナリオ | 想定件数 | コミットメッセージ |
|---|---|---|---|---|---|---|
| 18-1 | `proc` | `python analyze_proc.py` | EXEC SQL文 / #define定数定義 / 条件判定 / return文 / 変数代入 / 関数引数 / その他 | 直接 + #define×1 + 変数×1 | ~9件 | `test(golden/proc): add Pro*C smoke set` |
| 18-2 | `sql` | `python analyze_sql.py` | 例外・エラー処理 / 定数・変数定義 / WHERE条件 / 比較・DECODE / INSERT/UPDATE値 / SELECT/INTO / その他 | 直接 + 同一ファイル内×1 | ~8件 | `test(golden/sql): add Oracle SQL smoke set` |
| 18-3 | `sh` | `python analyze_sh.py` | 環境変数エクスポート / 変数代入 / 条件判定 / echo/print出力 / コマンド引数 / その他 | 直接 + 同一ファイル内×1 | ~7件 | `test(golden/sh): add Shell smoke set` |
| 18-4 | `kotlin` | `python analyze_kotlin.py` | const定数定義 / 変数代入 / 条件判定 / return文 / アノテーション / 関数引数 / その他 | 直接 + const val×1 | ~8件 | `test(golden/kotlin): add Kotlin smoke set` |
| 18-5 | `plsql` | `python analyze_plsql.py` | 定数/変数宣言 / EXCEPTION処理 / 条件判定 / カーソル定義 / INSERT/UPDATE値 / WHERE条件 / その他 | 直接のみ（間接追跡なし） | ~7件 | `test(golden/plsql): add PL/SQL smoke set (direct only)` |
| 18-6 | `ts` | `python analyze_ts.py` | const定数定義 / 変数代入(let/var) / 条件判定 / return文 / デコレータ / 関数引数 / その他 | 直接のみ | ~7件 | `test(golden/ts): add TypeScript/JS smoke set (direct only)` |
| 18-7 | `python` | `python analyze_python.py` | 変数代入 / 条件判定 / return文 / デコレータ / 関数引数 / その他 | 直接のみ | ~6件 | `test(golden/python): add Python smoke set (direct only)` |
| 18-8 | `perl` | `python analyze_perl.py` | use constant定義 / 変数代入 / 条件判定 / print/say出力 / 関数引数 / その他 | 直接のみ | ~6件 | `test(golden/perl): add Perl smoke set (direct only)` |
| 18-9 | `dotnet` | `python analyze_dotnet.py` | 定数定義(Const/readonly) / 変数代入 / 条件判定 / return文 / 属性(Attribute) / メソッド引数 / その他 | 直接 + const×1 + static readonly×1 | ~9件 | `test(golden/dotnet): add C#/VB.NET smoke set` |
| 18-10 | `groovy` | `python analyze_groovy.py` | static final定数定義 / 変数代入 / 条件判定 / return文 / アノテーション / メソッド引数 / その他 | 直接 + static final×1 + フィールド×1 + **getter×1 + setter×1** | ~11件 | `test(golden/groovy): add Groovy smoke set with getter/setter` |

### 言語別の注意点

- **18-1 (Pro*C)**: 拡張子 `.pc` と `.h` の混在をカバー。EXEC SQL 文を必ず含めること
- **18-2 (sql)**: spec §SQL/Shell の間接参照スコープ にある通り、`grep_helper/languages/sql.py` の `batch_track_indirect` を**事前に読んで**実装挙動を確認したうえで間接参照シナリオを設計する
- **18-3 (sh)**: 拡張子 `.sh`、ハンドラモジュール名は `sh`。同様に `grep_helper/languages/sh.py` の `batch_track_indirect` を確認してから設計
- **18-7 (python)**: サンプル `.py` ファイルが pytest に拾われないよう、Task 1 の `norecursedirs = tests/golden` が効いていることを確認：
  ```bash
  python -m pytest tests/ -q --collect-only 2>&1 | grep "tests/golden" || echo "no collect from golden, OK"
  ```
  Expected: `no collect from golden, OK`
- **18-9 (dotnet)**: `.cs` と `.vb` の両方をサンプルに含めること（モジュール名は `dotnet`）
- **18-10 (groovy)**: getter/setter 経由の参照シナリオも必須（Java と同じく全段階対応）

### サブタスクのチェックリスト

- [ ] **18-1: Pro*C** — 上記5ステップ + コミット
- [ ] **18-2: Oracle SQL** — 上記5ステップ + コミット（事前に sql.py の batch_track_indirect を確認）
- [ ] **18-3: Shell** — 上記5ステップ + コミット（事前に sh.py の batch_track_indirect を確認）
- [ ] **18-4: Kotlin** — 上記5ステップ + コミット
- [ ] **18-5: PL/SQL** — 上記5ステップ + コミット（間接追跡なし）
- [ ] **18-6: TypeScript/JS** — 上記5ステップ + コミット（間接追跡なし）
- [ ] **18-7: Python** — 上記5ステップ + コミット + pytest 収集除外確認
- [ ] **18-8: Perl** — 上記5ステップ + コミット（間接追跡なし）
- [ ] **18-9: C#/VB.NET** — 上記5ステップ + コミット（.cs/.vb 両方）
- [ ] **18-10: Groovy** — 上記5ステップ + コミット + getter/setter シナリオ必須

---

# Step 5: `--lang all` 対応

## Task 19: `LANG_SPECS` を全12言語ぶんに拡張

**Files:**
- Modify: `scripts/measure_kpi.py`

- [ ] **Step 28.1: 各言語の使用タイプを `tool-overview.md §4-2` から転記**

`scripts/measure_kpi.py` の `LANG_SPECS` に追加する11言語ぶん：

```python
LANG_SPECS: dict[str, dict] = {
    "java": {  # 既存
        "module": "grep_helper.languages.java",
        "usage_types": [
            "アノテーション", "定数定義", "変数代入", "条件判定",
            "return文", "メソッド引数", "その他",
        ],
        "min_per_type": 10,
        "reference_kinds_required": [
            "直接", "間接", "間接（getter経由）", "間接（setter経由）",
        ],
    },
    "c": {
        "module": "grep_helper.languages.c",
        "usage_types": [
            "#define定数定義", "条件判定", "return文",
            "変数代入", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "proc": {
        "module": "grep_helper.languages.proc",
        "usage_types": [
            "EXEC SQL文", "#define定数定義", "条件判定", "return文",
            "変数代入", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "sql": {
        "module": "grep_helper.languages.sql",
        "usage_types": [
            "例外・エラー処理", "定数・変数定義", "WHERE条件",
            "比較・DECODE", "INSERT/UPDATE値", "SELECT/INTO", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "sh": {
        "module": "grep_helper.languages.sh",
        "usage_types": [
            "環境変数エクスポート", "変数代入", "条件判定",
            "echo/print出力", "コマンド引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "kotlin": {
        "module": "grep_helper.languages.kotlin",
        "usage_types": [
            "const定数定義", "変数代入", "条件判定", "return文",
            "アノテーション", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "plsql": {
        "module": "grep_helper.languages.plsql",
        "usage_types": [
            "定数/変数宣言", "EXCEPTION処理", "条件判定",
            "カーソル定義", "INSERT/UPDATE値", "WHERE条件", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "ts": {
        "module": "grep_helper.languages.ts",
        "usage_types": [
            "const定数定義", "変数代入(let/var)", "条件判定", "return文",
            "デコレータ", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "python": {
        "module": "grep_helper.languages.python",
        "usage_types": [
            "変数代入", "条件判定", "return文", "デコレータ",
            "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "perl": {
        "module": "grep_helper.languages.perl",
        "usage_types": [
            "use constant定義", "変数代入", "条件判定",
            "print/say出力", "関数引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接"],
    },
    "dotnet": {
        "module": "grep_helper.languages.dotnet",
        "usage_types": [
            "定数定義(Const/readonly)", "変数代入", "条件判定", "return文",
            "属性(Attribute)", "メソッド引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": ["直接", "間接"],
    },
    "groovy": {
        "module": "grep_helper.languages.groovy",
        "usage_types": [
            "static final定数定義", "変数代入", "条件判定", "return文",
            "アノテーション", "メソッド引数", "その他",
        ],
        "min_per_type": 1,
        "reference_kinds_required": [
            "直接", "間接", "間接（getter経由）", "間接（setter経由）",
        ],
    },
}
```

**重要**: 上記の使用タイプ文字列が、各言語ハンドラの `classify_usage()` が返す文字列と**完全一致**することを実コードで確認する。`grep_helper/languages/<lang>.py` をそれぞれ開いて、戻り値文字列を grep して照合する。

- [ ] **Step 28.2: 各言語で run() が動くことを smoke 検証（手動）**

```bash
for lang in c proc sql sh kotlin plsql ts python perl dotnet groovy; do
    echo "=== $lang ==="
    python scripts/measure_kpi.py --lang $lang --quiet || echo "FAILED: $lang"
done
```

各言語で網羅率 100% を目指す。100% でない場合は expected を見直すか、サンプルを修正。

- [ ] **Step 28.3: コミット**

```bash
git add scripts/measure_kpi.py
git commit -m "feat(measure_kpi): expand LANG_SPECS to all 12 languages"
```

---

## Task 20: `--lang all` ロジック実装（失敗時規約含む）

**Files:**
- Modify: `scripts/measure_kpi.py`
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 29.1: 失敗するテストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestRunAllSemantics(unittest.TestCase):
    """--lang all の失敗時規約: 続行 / 最終 exit code は max / _summary は常に出力。"""

    def test_lang_allで存在する言語は処理され_summaryが出る(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = measure_kpi.run([
                "--lang", "all",
                "--samples-dir", "tests/golden",
                "--output-dir", tmp,
                "--quiet",
            ])
            # ゴールデンセットが揃っていれば 0、未整備言語があれば 1
            self.assertIn(exit_code, (0, 1))
            summary = list(Path(tmp).glob("_summary-*.md"))
            self.assertEqual(len(summary), 1, "_summary は常に出力される")

    def test_lang_allで未整備言語があっても他言語の処理は継続する(self):
        # 一時的に samples-dir を別の場所にして部分的な状態を作る
        with tempfile.TemporaryDirectory() as samples_tmp, \
             tempfile.TemporaryDirectory() as out_tmp:
            samples_path = Path(samples_tmp)
            # java だけコピー、他言語は欠損状態
            import shutil
            shutil.copytree("tests/golden/java", samples_path / "java")
            exit_code = measure_kpi.run([
                "--lang", "all",
                "--samples-dir", str(samples_path),
                "--output-dir", out_tmp,
                "--quiet",
            ])
            # java は OK だが他11言語は未整備 → exit 1
            self.assertEqual(exit_code, 1)
            # summary は出ている
            summary_files = list(Path(out_tmp).glob("_summary-*.md"))
            self.assertEqual(len(summary_files), 1)
            summary_text = summary_files[0].read_text(encoding="utf-8")
            self.assertIn("java", summary_text)
            # 他言語も「未整備」として記録されている
            self.assertIn("c", summary_text)
```

- [ ] **Step 29.2: 失敗を確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestRunAllSemantics -v`
Expected: FAIL（`NotImplementedError`）

- [ ] **Step 29.3: `_run_all` を実装**

`scripts/measure_kpi.py` の `_run_all` を以下に置き換える：

```python
def _run_all(samples_dir: Path, output_dir: Path, *, quiet: bool) -> int:
    """全12言語ぶん順次実行。失敗時は続行、最終 exit code は max(0, 1, 2)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_lines: list[str] = [f"# KPI 計測サマリ — {timestamp}", ""]
    summary_lines.append("| 言語 | 状態 | 網羅率 | 分類精度 | FP |")
    summary_lines.append("|---|---|---|---|---|")
    final_code = 0

    for lang in LANG_SPECS.keys():
        try:
            code = _run_single(lang, samples_dir, output_dir, quiet=quiet)
            if code == 0:
                # _run_single は内部で stdout を出すが、サマリ用に集計値を再計算するのは
                # 重複するため、ここではレポートファイルから読むか、もしくは戻り値を変える
                # 簡易: サマリ行は「成功」のみ記録（詳細は各言語の <lang>-<ts>.md 参照）
                summary_lines.append(f"| {lang} | 成功 | (詳細レポート参照) | | |")
            else:
                summary_lines.append(f"| {lang} | エラー (exit {code}) | - | - | - |")
                final_code = max(final_code, code)
        except FileNotFoundError as e:
            summary_lines.append(f"| {lang} | 未整備 | - | - | - |")
            if not quiet:
                print(f"[{lang}] 未整備: {e}", file=sys.stderr)
            final_code = max(final_code, 1)
        except Exception as e:
            summary_lines.append(f"| {lang} | 例外 | - | - | - |")
            if not quiet:
                print(f"[{lang}] 例外: {e}", file=sys.stderr)
            final_code = max(final_code, 2)

    summary_path = output_dir / f"_summary-{timestamp}.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    if not quiet:
        print(f"\nサマリレポート: {summary_path}")

    return final_code
```

`_run_single` の側も `FileNotFoundError` を `_run_all` で捕捉できるよう、`run()` 経由ではなく直接呼ぶ形にする（既に上の構造で対応している）。

- [ ] **Step 29.4: テストが通ることを確認**

Run: `python -m pytest tests/test_measure_kpi.py::TestRunAllSemantics -v`
Expected: PASS

- [ ] **Step 29.5: 全件回帰テスト**

Run: `python -m pytest tests/ -q`
Expected: 全件 pass

- [ ] **Step 29.6: 手動実行で `--lang all` を確認**

```bash
python scripts/measure_kpi.py --lang all
ls output/kpi/_summary-*.md
```

- [ ] **Step 29.7: コミット**

```bash
git add scripts/measure_kpi.py tests/test_measure_kpi.py
git commit -m "feat(measure_kpi): implement --lang all with continue-on-failure"
```

---

## Task 21: 11言語ぶんの E2E テスト（パラメタライズ）

**Files:**
- Modify: `tests/test_measure_kpi.py`

- [ ] **Step 30.1: テストを書く**

`tests/test_measure_kpi.py` の末尾に追加：

```python
class TestRunCliEndToEndOtherLanguages(unittest.TestCase):
    """E2E (他11言語): 各言語の run() がクラッシュせず coverage 1.0 を返す。"""

    OTHER_LANGS = ["c", "proc", "sql", "sh", "kotlin", "plsql",
                   "ts", "python", "perl", "dotnet", "groovy"]

    def test_各言語のrunが例外なく完了する(self):
        for lang in self.OTHER_LANGS:
            with self.subTest(lang=lang):
                with tempfile.TemporaryDirectory() as tmp:
                    exit_code = measure_kpi.run([
                        "--lang", lang,
                        "--samples-dir", "tests/golden",
                        "--output-dir", tmp,
                        "--quiet",
                    ])
                    self.assertEqual(exit_code, 0, f"{lang} で exit_code != 0")
                    reports = list(Path(tmp).glob(f"{lang}-*.md"))
                    self.assertEqual(len(reports), 1)

    def test_各言語の網羅率は1_0(self):
        for lang in self.OTHER_LANGS:
            with self.subTest(lang=lang):
                spec = measure_kpi.LANG_SPECS[lang]
                handler = importlib.import_module(spec["module"])
                src_dir = Path(f"tests/golden/{lang}/src")
                inputs_dir = Path(f"tests/golden/{lang}/inputs")
                expected_dir = Path(f"tests/golden/{lang}/expected")
                with tempfile.TemporaryDirectory() as tmp:
                    from grep_helper.pipeline import run_full_pipeline
                    tmp_path = Path(tmp)
                    run_full_pipeline(
                        source_dir=src_dir, input_dir=inputs_dir,
                        output_dir=tmp_path, handler=handler, workers=1,
                    )
                    for grep_path in inputs_dir.glob("*.grep"):
                        stem = grep_path.stem
                        expected = measure_kpi.load_expected_tsv(expected_dir / f"{stem}.tsv")
                        actual = measure_kpi.load_actual_tsv(tmp_path / f"{stem}.tsv")
                        result = measure_kpi.compare(expected, actual)
                        self.assertEqual(
                            result.coverage_rate, 1.0,
                            f"{lang}/{stem}: missing_rows={result.missing_rows}",
                        )


# importlib をテストの先頭インポート群に追加
import importlib  # noqa: E402
```

- [ ] **Step 30.2: テスト実行**

Run: `python -m pytest tests/test_measure_kpi.py::TestRunCliEndToEndOtherLanguages -v`
Expected: PASS（11 subTests × 2 メソッド）

FAIL する言語があれば、その言語の expected が actual と乖離している → expected を見直すか、ゴールデンセットの設計を修正。

- [ ] **Step 30.3: 全件 pass 確認**

Run: `python -m pytest tests/ -q`
Expected: 全件 pass

- [ ] **Step 30.4: コミット**

```bash
git add tests/test_measure_kpi.py
git commit -m "test(measure_kpi): add E2E tests for 11 other languages"
```

---

# Step 6: ドキュメント整備 + 最終確認

## Task 22: README.md に KPI 計測セクション追加

**Files:**
- Modify: `README.md`

- [ ] **Step 31.1: 追記内容を確認**

README の `## テスト` セクションの直前に新セクションを追加する：

```markdown
## KPI 計測（網羅率・分類精度）

ゴールデンセットを使って網羅率・分類精度を計測する。要件 §成功指標 (KPI) を継続的に確認するためのスクリプト。

### 単一言語

```bash
python scripts/measure_kpi.py --lang java
```

stdout に網羅率・分類精度・FP 件数が表示され、`output/kpi/java-<YYYYMMDD-HHMMSS>.md` に詳細レポートが書き出される。

### 全12言語まとめて

```bash
python scripts/measure_kpi.py --lang all
```

各言語ごとに `<lang>-<timestamp>.md` が、全体サマリが `_summary-<timestamp>.md` が出力される。

### しきい値の扱い

要件しきい値（網羅率 100% / 分類精度 90%）に達しない場合は **stdout に WARN 表示**するが、**exit code は 0** を返す（CIゲートしない方針）。

| Exit code | 意味 |
|---|---|
| 0 | 計測完了 |
| 1 | 入力エラー（ゴールデンセット未整備、`--lang` 未対応など） |
| 2 | 実行時例外 |

### ゴールデンセットの場所

`tests/golden/<lang>/` 配下。各言語ディレクトリの `README.md` にサンプル設計の意図と追加手順を記載している。

### 詳細

`docs/superpowers/specs/2026-05-03-kpi-golden-set-design.md` を参照。
```

- [ ] **Step 31.2: 編集**

`README.md` を上記内容で編集。

- [ ] **Step 31.3: コミット**

```bash
git add README.md
git commit -m "docs(README): add KPI measurement usage section"
```

---

## Task 23: 最終確認

- [ ] **Step 32.1: 全件テスト実行**

Run: `python -m pytest tests/ -v`
Expected: 全件 pass

- [ ] **Step 32.2: `--lang all` を実行して全言語のレポートが出ることを確認**

Run: `python scripts/measure_kpi.py --lang all`
Expected: 12言語ぶんの個別レポート + `_summary-*.md` が `output/kpi/` に生成

- [ ] **Step 32.3: spec §成功条件 全項目を点検**

spec の `## 成功条件` の9項目を1つずつチェック：

1. ✅ `--lang java` で Java の KPI が表示される
2. ✅ 他11言語でも実行できる
3. ✅ `--lang all` で全12言語を順次実行できる
4. ✅ レポートが書き出される（タイムスタンプ秒精度）
5. ✅ Java: 網羅率 100% / 分類精度 90% 以上
6. ✅ 他11言語: 網羅率 100%
7. ✅ pytest 全件 pass
8. ✅ ゴールデンセットが各使用タイプを最低1件 + 間接/getter/setter シナリオ
9. ✅ `assert_coverage_distribution()` 警告ゼロ（`python scripts/measure_kpi.py --lang all` で stdout に分布警告が出ないことを確認）

- [ ] **Step 32.4: 任意：cli.py のリファクタを別タスクで切り出す（やらない場合はそのまま終了）**

ユーザー判断。`grep_helper/cli.py` の `run()` を `run_full_pipeline()` 経由にリファクタする場合は、別 plan として writing-plans に渡す。

- [ ] **Step 32.5: 完了コミット**

このタスクで何かファイル変更があれば：

```bash
git add -A
git commit -m "chore: KPI golden set implementation complete"
```

---

# 任意: cli.py のリファクタ（別タスク化推奨）

`grep_helper/cli.py` の `run()` を `grep_helper.pipeline.run_full_pipeline()` 経由にリファクタして重複を削減する。本 plan のスコープ外として、別の writing-plans サイクルで扱う。

---

## 補足: テスト方針リマインダ

本 plan のテストは以下に従う（`feedback_test_style.md` / `feedback_tdd_stance.md`）：

- **古典学派**: モック禁止。実物のオブジェクト（合成 Record / 実ファイル）を渡す
- **ブラックボックス起点**: `compare()` の戻り値を観察し、内部実装を覗かない
- **WHATを検証**: 「網羅率がいくつになるか」を assert する。「`dict[k]` を呼んだか」のような HOW は問わない
- **テストメソッド名は日本語**: `test_期待行と実際の行が完全一致するとき網羅率は1_0`
- **TDD**: Red (failing test) → Green (minimal impl) → 必要に応じて Refactor
