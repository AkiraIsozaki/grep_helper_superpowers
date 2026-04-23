# パフォーマンス改善・進捗表示 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 60GB ソースディレクトリへの間接追跡を mmap 事前フィルタで高速化し、全バッチ処理に進捗表示を追加する

**Architecture:** `analyze_common.py` に `grep_filter_files()`（mmap バイト列検索による高速事前フィルタ）を追加し、`analyze.py` / `analyze_all.py` の全バッチスキャン関数でこれを利用する。Java の定数・getter・setter 追跡は単一の `grep_filter_files()` 呼び出しで rglob を共有し3回→1回に削減する。AST キャッシュを 300→2000 に拡大する。

**Tech Stack:** Python 3.12+, `mmap`（標準ライブラリ）, `unittest`

---

## ファイル構成

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `analyze_common.py` | 修正 | `grep_filter_files()` 追加、`mmap` / `sys` import 追加 |
| `tests/test_common.py` | 修正 | `grep_filter_files()` のテストを追加 |
| `analyze.py` | 修正 | `_MAX_AST_CACHE_SIZE` 拡大、`_batch_track_*` 3関数に `file_list` 引数と進捗表示追加、`main()` に rglob 集約・処理開始メッセージ追加 |
| `analyze_all.py` | 修正 | 8バッチ関数を `grep_filter_files()` + 進捗表示に更新、`_apply_indirect_tracking()` で Java rglob 集約、`main()` に処理開始メッセージ追加 |

---

## Task 1: `grep_filter_files()` の実装

**Files:**
- Modify: `analyze_common.py`
- Modify: `tests/test_common.py`

---

- [ ] **Step 1-1: テストを追加（失敗することを確認）**

`tests/test_common.py` の末尾（`if __name__ == "__main__":` の直前）に追加：

```python
class TestGrepFilterFiles(unittest.TestCase):
    def test_includes_matching_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "Foo.java"
            f.write_bytes(b"public static final String FOO_CONST = \"value\";\n")
            result = grep_filter_files(["FOO_CONST"], p, [".java"])
            self.assertIn(f, result)

    def test_excludes_non_matching_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "Bar.java"
            f.write_bytes(b"public class Bar {}\n")
            result = grep_filter_files(["FOO_CONST"], p, [".java"])
            self.assertNotIn(f, result)

    def test_excludes_wrong_extension(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "script.sh"
            f.write_bytes(b"FOO_CONST=value\n")
            result = grep_filter_files(["FOO_CONST"], p, [".java"])
            self.assertNotIn(f, result)

    def test_empty_names_returns_all_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f1 = p / "A.java"; f1.write_bytes(b"class A {}\n")
            f2 = p / "B.java"; f2.write_bytes(b"class B {}\n")
            result = grep_filter_files([], p, [".java"])
            self.assertEqual(set(result), {f1, f2})

    def test_empty_file_excluded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "Empty.java"; f.write_bytes(b"")
            result = grep_filter_files(["FOO"], p, [".java"])
            self.assertNotIn(f, result)

    def test_multiple_extensions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            kt  = p / "Foo.kt";    kt.write_bytes(b"val FOO = 1\n")
            kts = p / "Build.kts"; kts.write_bytes(b"val FOO = 2\n")
            java = p / "Other.java"; java.write_bytes(b"FOO\n")
            result = grep_filter_files(["FOO"], p, [".kt", ".kts"])
            self.assertIn(kt, result)
            self.assertIn(kts, result)
            self.assertNotIn(java, result)

    def test_result_is_sorted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            b = p / "b.java"; b.write_bytes(b"PATTERN\n")
            a = p / "a.java"; a.write_bytes(b"PATTERN\n")
            result = grep_filter_files(["PATTERN"], p, [".java"])
            self.assertEqual(result, sorted(result))

    def test_label_prints_to_stderr(self):
        import tempfile, io
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "X.java"; f.write_bytes(b"FOO\n")
            buf = io.StringIO()
            import sys as _sys
            old, _sys.stderr = _sys.stderr, buf
            try:
                grep_filter_files(["FOO"], p, [".java"], label="テスト")
            finally:
                _sys.stderr = old
            self.assertIn("テスト", buf.getvalue())
            self.assertIn("事前フィルタ完了", buf.getvalue())
```

また `test_common.py` 先頭の import 行を更新：

```python
from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv, grep_filter_files
```

- [ ] **Step 1-2: テストを実行して失敗を確認**

```bash
cd /workspaces/grep_helper_superpowers
python -m pytest tests/test_common.py::TestGrepFilterFiles -v
```

期待結果: `ImportError: cannot import name 'grep_filter_files'`

- [ ] **Step 1-3: `grep_filter_files()` を `analyze_common.py` に実装**

`analyze_common.py` の先頭 import ブロックに追加：

```python
import mmap
import sys
```

（既存の `import csv` の前に追加）

ファイル末尾の `def write_tsv(...)` の後に追加：

```python
def grep_filter_files(
    names: list[str],
    src_dir: Path,
    extensions: list[str],
    label: str = "",
) -> list[Path]:
    """mmap によるバイト列検索でスキャン対象ファイルを絞り込む。

    names に含まれる識別子（ASCII）を1つでも含むファイルのみ返す。
    エラー時は安全側（スキャン対象に含める）でフォールバック。
    Solaris 10 / Windows を含む全 OS で動作する（標準ライブラリのみ）。

    label が指定された場合は事前フィルタ結果を stderr に出力する。
    """
    patterns = [n.encode("ascii") for n in names if n.isascii()]

    if not patterns:
        result: list[Path] = []
        for ext in extensions:
            result.extend(src_dir.rglob(f"*{ext}"))
        return sorted(result)

    total = 0
    result = []
    for ext in extensions:
        for f in src_dir.rglob(f"*{ext}"):
            total += 1
            try:
                if f.stat().st_size == 0:
                    continue
                with open(f, "rb") as fh, \
                     mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    if any(mm.find(p) != -1 for p in patterns):
                        result.append(f)
            except (OSError, ValueError, mmap.error):
                result.append(f)

    if label:
        print(
            f"  [{label}] 事前フィルタ完了: {total} → {len(result)} ファイルに絞り込み",
            file=sys.stderr, flush=True,
        )

    return sorted(result)
```

- [ ] **Step 1-4: テストを実行してパスを確認**

```bash
python -m pytest tests/test_common.py::TestGrepFilterFiles -v
```

期待結果: 8件全て PASS

- [ ] **Step 1-5: 既存テストが壊れていないことを確認**

```bash
python -m pytest tests/test_common.py -v
```

期待結果: 全て PASS

- [ ] **Step 1-6: コミット**

```bash
git add analyze_common.py tests/test_common.py
git commit -m "feat: analyze_common に grep_filter_files() を追加（mmap 事前フィルタ）"
```

---

## Task 2: `analyze.py` の更新（AST キャッシュ拡大 + バッチ関数 + main）

**Files:**
- Modify: `analyze.py:63` (`_MAX_AST_CACHE_SIZE`)
- Modify: `analyze.py:21-27` (import に `grep_filter_files` 追加)
- Modify: `analyze.py:931-989` (`_batch_track_constants`)
- Modify: `analyze.py:992-1048` (`_batch_track_getters`)
- Modify: `analyze.py:1051-1103` (`_batch_track_setters`)
- Modify: `analyze.py:1261-1273` (main の batch 呼び出し部分)
- Modify: `analyze.py:1206` (main のループ先頭)

---

- [ ] **Step 2-1: `_MAX_AST_CACHE_SIZE` を拡大**

`analyze.py` の 63 行目付近：

```python
# 変更前
_MAX_AST_CACHE_SIZE = 300    # ASTオブジェクトは大きいため厳しめ

# 変更後
_MAX_AST_CACHE_SIZE = 2000   # 60GB規模のソースに対応（~2-6GB使用。メモリ不足時は500〜1000に調整）
```

- [ ] **Step 2-2: `grep_filter_files` を import に追加**

`analyze.py` の `from analyze_common import (...)` ブロックに `grep_filter_files` を追加：

```python
from analyze_common import (
    GrepRecord,
    ProcessStats,
    RefType,
    detect_encoding,
    parse_grep_line,
    write_tsv,
    grep_filter_files,
)
```

- [ ] **Step 2-3: `_batch_track_constants` を更新**

`analyze.py` の `_batch_track_constants` 関数を以下に置き換える（`file_list` 引数追加 + 進捗表示）：

```python
def _batch_track_constants(
    tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
) -> list[GrepRecord]:
    """複数の定数をプロジェクト全体で一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする（rglob 共有）。
    """
    if not tasks:
        return []

    java_files = file_list if file_list is not None else grep_filter_files(
        list(tasks.keys()), source_dir, [".java"], label="Java定数追跡",
    )

    combined = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in tasks) + r")\b"
    )
    records: list[GrepRecord] = []
    total = len(java_files)

    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Java定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = _cached_read_lines(filepath_abs, stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            for m in combined.finditer(line):
                matched_name = m.group(1)
                origins = tasks.get(matched_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage(
                    code=code,
                    filepath=filepath_str,
                    lineno=i,
                    source_dir=source_dir,
                    stats=stats,
                )
                for origin in origins:
                    if filepath_str == origin.filepath and str(i) == origin.lineno:
                        continue
                    records.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=usage_type,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=matched_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Java定数追跡] 完了: {total} ファイルスキャン / 参照 {len(records)} 件発見", file=sys.stderr, flush=True)
    return records
```

- [ ] **Step 2-4: `_batch_track_getters` を更新**

```python
def _batch_track_getters(
    tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
) -> list[GrepRecord]:
    """複数のgetterをプロジェクト全体で一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする（rglob 共有）。
    """
    if not tasks:
        return []

    java_files = file_list if file_list is not None else grep_filter_files(
        list(tasks.keys()), source_dir, [".java"], label="Javaゲッター追跡",
    )

    combined = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in tasks) + r")\s*\("
    )
    records: list[GrepRecord] = []
    total = len(java_files)

    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Javaゲッター追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = _cached_read_lines(filepath_abs, stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            for m in combined.finditer(line):
                getter_name = m.group(1)
                origins = tasks.get(getter_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage(
                    code=code,
                    filepath=filepath_str,
                    lineno=i,
                    source_dir=source_dir,
                    stats=stats,
                )
                for origin in origins:
                    records.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.GETTER.value,
                        usage_type=usage_type,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=getter_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Javaゲッター追跡] 完了: {total} ファイルスキャン / 参照 {len(records)} 件発見", file=sys.stderr, flush=True)
    return records
```

- [ ] **Step 2-5: `_batch_track_setters` を更新**

```python
def _batch_track_setters(
    tasks: dict[str, list[GrepRecord]],
    source_dir: Path,
    stats: ProcessStats,
    file_list: list[Path] | None = None,
) -> list[GrepRecord]:
    """複数のsetterをプロジェクト全体で一括追跡する。

    file_list が指定された場合はそのリストをスキャン対象にする（rglob 共有）。
    """
    if not tasks:
        return []

    java_files = file_list if file_list is not None else grep_filter_files(
        list(tasks.keys()), source_dir, [".java"], label="Javaセッター追跡",
    )

    combined = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in tasks) + r")\s*\("
    )
    records: list[GrepRecord] = []
    total = len(java_files)

    for idx, java_file in enumerate(java_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Javaセッター追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        filepath_abs = str(java_file)
        try:
            filepath_str = str(java_file.relative_to(source_dir))
        except ValueError:
            filepath_str = filepath_abs
        lines = _cached_read_lines(filepath_abs, stats)
        if not lines:
            continue

        for i, line in enumerate(lines, start=1):
            for m in combined.finditer(line):
                setter_name = m.group(1)
                origins = tasks.get(setter_name)
                if not origins:
                    continue
                code = line.strip()
                usage_type = classify_usage(
                    code=code,
                    filepath=filepath_str,
                    lineno=i,
                    source_dir=source_dir,
                    stats=stats,
                )
                for origin in origins:
                    records.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.SETTER.value,
                        usage_type=usage_type,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=code,
                        src_var=setter_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Javaセッター追跡] 完了: {total} ファイルスキャン / 参照 {len(records)} 件発見", file=sys.stderr, flush=True)
    return records
```

- [ ] **Step 2-6: `main()` に処理開始メッセージ + Java rglob 集約を追加**

`analyze.py` の `main()` 内、`for grep_path in grep_files:` ループの先頭に処理開始メッセージを追加：

```python
    for grep_path in grep_files:
        keyword = grep_path.stem  # 拡張子なしのファイル名 = 検索文言
        print(f"  処理中: {grep_path.name} ...", file=sys.stderr, flush=True)
```

同じく `main()` 内、`# 定数・getter・setter をプロジェクト全体に対して各1パスで一括スキャン` の直前を以下に置き換え：

```python
            # 定数・getter・setter の事前フィルタを1回の rglob で共有
            java_candidates: list[Path] | None = None
            if project_scope_tasks or getter_tasks or setter_tasks:
                all_java_names = (
                    list(project_scope_tasks.keys())
                    + list(getter_tasks.keys())
                    + list(setter_tasks.keys())
                )
                java_candidates = grep_filter_files(
                    all_java_names, source_dir, [".java"], label="Java追跡",
                )

            if project_scope_tasks:
                all_records.extend(
                    _batch_track_constants(project_scope_tasks, source_dir, stats, file_list=java_candidates)
                )
            if getter_tasks:
                all_records.extend(
                    _batch_track_getters(getter_tasks, source_dir, stats, file_list=java_candidates)
                )
            if setter_tasks:
                all_records.extend(
                    _batch_track_setters(setter_tasks, source_dir, stats, file_list=java_candidates)
                )
```

- [ ] **Step 2-7: 既存テストでリグレッションがないことを確認**

```bash
python -m pytest test_analyze.py tests/test_common.py -v
```

期待結果: 全て PASS

- [ ] **Step 2-8: コミット**

```bash
git add analyze.py tests/test_common.py
git commit -m "feat: analyze.py のバッチ関数に grep_filter_files・進捗表示・rglob集約を追加"
```

---

## Task 3: `analyze_all.py` 非 Java バッチ関数の更新（5関数）

**Files:**
- Modify: `analyze_all.py:10-13` (import に `grep_filter_files` 追加)
- Modify: `analyze_all.py:249-285` (`_batch_track_kotlin_const`)
- Modify: `analyze_all.py:288-326` (`_batch_track_dotnet_const`)
- Modify: `analyze_all.py:329-367` (`_batch_track_groovy_static_final`)
- Modify: `analyze_all.py:370-423` (`_batch_track_define_c_all`)
- Modify: `analyze_all.py:426-480` (`_batch_track_define_proc_all`)

---

- [ ] **Step 3-1: `grep_filter_files` を import に追加**

`analyze_all.py` の `from analyze_common import (...)` ブロックに追加：

```python
from analyze_common import (
    GrepRecord, ProcessStats, RefType,
    detect_encoding, parse_grep_line, write_tsv,
    grep_filter_files,
)
```

- [ ] **Step 3-2: `_batch_track_kotlin_const` を更新**

```python
def _batch_track_kotlin_const(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """Kotlin const val をプロジェクト全体に対して1パスでバッチスキャンする。"""
    if not tasks:
        return []
    combined = re.compile(r'\b(' + '|'.join(re.escape(k) for k in tasks) + r')\b')
    results: list[GrepRecord] = []
    src_files = grep_filter_files(list(tasks.keys()), src_dir, [".kt", ".kts"], label="Kotlin定数追跡")
    total = len(src_files)

    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Kotlin定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        lines = _read_lines(src_file, encoding)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                name = m.group(1)
                for origin in tasks[name]:
                    def_path = _resolve_file(origin.filepath, src_dir)
                    if def_path and src_file.resolve() == def_path.resolve() and i == int(origin.lineno):
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage_kotlin(line.strip()),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=line.strip(),
                        src_var=name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Kotlin定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results
```

- [ ] **Step 3-3: `_batch_track_dotnet_const` を更新**

```python
def _batch_track_dotnet_const(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """.NET const/static readonly をプロジェクト全体に対して1パスでバッチスキャンする。"""
    if not tasks:
        return []
    combined = re.compile(r'\b(' + '|'.join(re.escape(k) for k in tasks) + r')\b')
    results: list[GrepRecord] = []
    src_files = grep_filter_files(list(tasks.keys()), src_dir, [".cs", ".vb"], label=".NET定数追跡")
    total = len(src_files)

    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [.NET定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        lines = _read_lines(src_file, encoding)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                name = m.group(1)
                for origin in tasks[name]:
                    def_path = _resolve_file(origin.filepath, src_dir)
                    if def_path and src_file.resolve() == def_path.resolve() and i == int(origin.lineno):
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage_dotnet(line.strip()),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=line.strip(),
                        src_var=name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [.NET定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results
```

- [ ] **Step 3-4: `_batch_track_groovy_static_final` を更新**

```python
def _batch_track_groovy_static_final(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """Groovy static final 定数をプロジェクト全体に対して1パスでバッチスキャンする。"""
    if not tasks:
        return []
    combined = re.compile(r'\b(' + '|'.join(re.escape(k) for k in tasks) + r')\b')
    results: list[GrepRecord] = []
    src_files = grep_filter_files(list(tasks.keys()), src_dir, [".groovy", ".gvy"], label="Groovy定数追跡")
    total = len(src_files)

    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Groovy定数追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        lines = _read_lines(src_file, encoding)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                name = m.group(1)
                for origin in tasks[name]:
                    def_path = _resolve_file(origin.filepath, src_dir)
                    if def_path and src_file.resolve() == def_path.resolve() and i == int(origin.lineno):
                        continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage_groovy(line.strip()),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=line.strip(),
                        src_var=name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Groovy定数追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results
```

- [ ] **Step 3-5: `_batch_track_define_c_all` を更新**

既存関数内で `src_dir.rglob("*.c")` 等を行っている部分を `grep_filter_files()` に置き換える。既存の `define_map` 構築（`_build_define_map_c()`）と `scan_tasks` 構築ロジックはそのまま保持し、ファイルリスト生成部分のみ変更する。

```python
def _batch_track_define_c_all(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """C #define をエイリアス解決込みで1パスでバッチスキャンする。"""
    if not tasks:
        return []
    define_map = _build_define_map_c(src_dir, stats, encoding)

    scan_tasks: dict[str, list[tuple[bool, str, GrepRecord]]] = {}
    for var_name, records in tasks.items():
        aliases = _collect_define_aliases(var_name, define_map)
        for scan_name in [var_name] + aliases:
            is_primary = (scan_name == var_name)
            for record in records:
                scan_tasks.setdefault(scan_name, []).append((is_primary, var_name, record))

    if not scan_tasks:
        return []

    combined = re.compile(r'\b(' + '|'.join(re.escape(k) for k in scan_tasks) + r')\b')
    results: list[GrepRecord] = []
    src_files = grep_filter_files(list(scan_tasks.keys()), src_dir, [".c", ".h", ".pc"], label="C #define追跡")
    total = len(src_files)

    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [C #define追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        lines = _read_lines(src_file, encoding)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                scan_name = m.group(1)
                for is_primary, _var_name, origin in scan_tasks[scan_name]:
                    if is_primary:
                        def_path = _resolve_file(origin.filepath, src_dir)
                        if def_path and src_file.resolve() == def_path.resolve() and i == int(origin.lineno):
                            continue
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=classify_usage_c(line.strip()),
                        filepath=filepath_str,
                        lineno=str(i),
                        code=line.strip(),
                        src_var=scan_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [C #define追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results
```

- [ ] **Step 3-6: `_batch_track_define_proc_all` を更新**

```python
def _batch_track_define_proc_all(
    tasks: dict[str, list[GrepRecord]],
    src_dir: Path,
    stats: ProcessStats,
    encoding: str | None,
) -> list[GrepRecord]:
    """Pro*C #define をエイリアス解決込みで1パスでバッチスキャンする。"""
    if not tasks:
        return []
    define_map = _build_define_map_proc(src_dir, stats, encoding)

    scan_tasks: dict[str, list[tuple[bool, str, GrepRecord]]] = {}
    for var_name, records in tasks.items():
        aliases = _collect_define_aliases(var_name, define_map)
        for scan_name in [var_name] + aliases:
            is_primary = (scan_name == var_name)
            for record in records:
                scan_tasks.setdefault(scan_name, []).append((is_primary, var_name, record))

    if not scan_tasks:
        return []

    combined = re.compile(r'\b(' + '|'.join(re.escape(k) for k in scan_tasks) + r')\b')
    results: list[GrepRecord] = []
    src_files = grep_filter_files(list(scan_tasks.keys()), src_dir, [".pc", ".c", ".h"], label="Pro*C #define追跡")
    total = len(src_files)

    for idx, src_file in enumerate(src_files, 1):
        if total >= 100 and idx % 100 == 0:
            pct = idx * 100 // total
            print(f"  [Pro*C #define追跡] {idx}/{total} ファイル処理済み ({pct}%)", file=sys.stderr, flush=True)
        try:
            filepath_str = str(src_file.relative_to(src_dir))
        except ValueError:
            filepath_str = str(src_file)
        ext = src_file.suffix.lower()
        lines = _read_lines(src_file, encoding)
        for i, line in enumerate(lines, 1):
            for m in combined.finditer(line):
                scan_name = m.group(1)
                for is_primary, _var_name, origin in scan_tasks[scan_name]:
                    if is_primary:
                        def_path = _resolve_file(origin.filepath, src_dir)
                        if def_path and src_file.resolve() == def_path.resolve() and i == int(origin.lineno):
                            continue
                    usage = classify_usage_c(line.strip()) if ext in (".c", ".h") else classify_usage_proc(line.strip())
                    results.append(GrepRecord(
                        keyword=origin.keyword,
                        ref_type=RefType.INDIRECT.value,
                        usage_type=usage,
                        filepath=filepath_str,
                        lineno=str(i),
                        code=line.strip(),
                        src_var=scan_name,
                        src_file=origin.filepath,
                        src_lineno=origin.lineno,
                    ))

    print(f"  [Pro*C #define追跡] 完了: {total} ファイルスキャン / 参照 {len(results)} 件発見", file=sys.stderr, flush=True)
    return results
```

- [ ] **Step 3-7: 既存テストでリグレッションがないことを確認**

```bash
python -m pytest tests/ test_analyze.py test_analyze_proc.py -v
```

期待結果: 全て PASS

- [ ] **Step 3-8: コミット**

```bash
git add analyze_all.py
git commit -m "feat: analyze_all.py の非Javaバッチ関数に grep_filter_files・進捗表示を追加"
```

---

## Task 4: `analyze_all.py` Java rglob 集約 + 処理開始メッセージ

**Files:**
- Modify: `analyze_all.py:629-648` (`_apply_indirect_tracking` の Java バッチ呼び出し部分)
- Modify: `analyze_all.py:689` (`main()` のループ先頭)

---

- [ ] **Step 4-1: `_apply_indirect_tracking()` の Java バッチ呼び出し部分を更新**

`analyze_all.py` の `_apply_indirect_tracking()` 末尾にある以下のブロックを置き換える：

変更前：
```python
    # Java バッチ処理（プロジェクト全体を各1パスでスキャン）
    if java_project_tasks:
        result.extend(_batch_track_constants(java_project_tasks, source_dir, stats))
    if java_getter_tasks:
        result.extend(_batch_track_getters(java_getter_tasks, source_dir, stats))
    if java_setter_tasks:
        result.extend(_batch_track_setters(java_setter_tasks, source_dir, stats))
```

変更後：
```python
    # Java バッチ処理: 定数・getter・setter の事前フィルタを1回の rglob で共有
    java_candidates: list[Path] | None = None
    if java_project_tasks or java_getter_tasks or java_setter_tasks:
        all_java_names = (
            list(java_project_tasks.keys())
            + list(java_getter_tasks.keys())
            + list(java_setter_tasks.keys())
        )
        java_candidates = grep_filter_files(
            all_java_names, source_dir, [".java"], label="Java追跡",
        )
    if java_project_tasks:
        result.extend(_batch_track_constants(java_project_tasks, source_dir, stats, file_list=java_candidates))
    if java_getter_tasks:
        result.extend(_batch_track_getters(java_getter_tasks, source_dir, stats, file_list=java_candidates))
    if java_setter_tasks:
        result.extend(_batch_track_setters(java_setter_tasks, source_dir, stats, file_list=java_candidates))
```

- [ ] **Step 4-2: `main()` に処理開始メッセージを追加**

`analyze_all.py` の `main()` 内、`for grep_path in grep_files:` ループの先頭に追加：

```python
    for grep_path in grep_files:
        keyword = grep_path.stem
        print(f"  処理中: {grep_path.name} ...", file=sys.stderr, flush=True)
```

- [ ] **Step 4-3: 全テストでリグレッションがないことを確認**

```bash
python -m pytest tests/ test_analyze.py test_analyze_proc.py -v
```

期待結果: 全て PASS

- [ ] **Step 4-4: コミット**

```bash
git add analyze_all.py
git commit -m "feat: analyze_all.py の Java rglob を集約・処理開始メッセージを追加"
```

---

## Task 5: ドキュメント更新

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/functional-design.md`
- Modify: `README.md`

---

- [ ] **Step 5-1: `docs/architecture.md` の tech stack テーブルに `mmap` を追加**

`### フレームワーク・ライブラリ` テーブルの `pathlib` 行の後に追加：

```markdown
| mmap | 標準ライブラリ | バッチスキャン前のファイル事前フィルタ（`analyze_common.grep_filter_files`） | OS のカーネルレベルでファイルをメモリマップし、バイト列検索で不要ファイルを除外。Solaris 10 含む全 OS で動作 |
```

- [ ] **Step 5-2: `docs/architecture.md` のメモリ見積りを更新**

`### リソース使用量` テーブルのメモリ行を変更：

変更前：
```markdown
| メモリ | 2GB | ASTキャッシュ（500ファイル × 推定1MB = 約500MB）+ GrepRecordリスト（4万行 × 間接参照派生 × 推定1KB = 約数百MB）の合計見積もり。grep行はジェネレータで1行ずつ処理するが、結果レコードは全件メモリに蓄積される点に注意 |
```

変更後：
```markdown
| メモリ | 2GB〜8GB | ASTキャッシュ（最大2000ファイル × 推定1〜3MB = 最大6GB）+ GrepRecordリスト（数百MB）の合計見積もり。60GB規模のソースでは AST キャッシュが支配的になるため、メモリ不足時は `_MAX_AST_CACHE_SIZE`（`analyze.py`）を 500〜1000 に下げること |
```

- [ ] **Step 5-3: `docs/architecture.md` のスケーラビリティ節に `grep_filter_files` を追加**

`### データ増加への対応` セクションの `ASTキャッシュ` 行の後に追加：

変更前：
```markdown
- **ASTキャッシュ**: `dict[str, object | None]` で O(1) アクセス。再解析コストをゼロに
- **ジェネレータ**: grep行を1行ずつ処理。全行をメモリに展開しない
```

変更後：
```markdown
- **ASTキャッシュ**: `dict[str, object | None]` で O(1) アクセス。再解析コストをゼロに（上限 2000 件）
- **mmap 事前フィルタ（`grep_filter_files`）**: バッチスキャン前に `mmap.find()` でパターンを含まないファイルを除外。数万ファイルを数百ファイルに絞り込み、間接追跡フェーズを大幅に高速化
- **ジェネレータ**: grep行を1行ずつ処理。全行をメモリに展開しない
```

- [ ] **Step 5-4: `docs/architecture.md` のパフォーマンス制約を更新**

変更前：
```markdown
- シングルコア・シングルプロセス（並列処理なし）
- ASTキャッシュが有効なメモリを上限とする
```

変更後：
```markdown
- シングルコア・シングルプロセス（並列処理なし）
- ASTキャッシュが有効なメモリを上限とする（`_MAX_AST_CACHE_SIZE = 2000`、メモリ不足時は縮小可）
- 間接追跡フェーズは `grep_filter_files()` による mmap 事前フィルタで高速化（Solaris 10 対応）
```

- [ ] **Step 5-5: `docs/functional-design.md` の `_MAX_AST_CACHE_SIZE` を更新**

`docs/functional-design.md` の ASTCache セクション（`_MAX_AST_CACHE_SIZE = 300` の行）を変更：

変更前：
```python
# キャッシュ上限（大規模プロジェクトでのOOM防止）
_MAX_AST_CACHE_SIZE = 300   # ASTオブジェクトは大きいため厳しめ
_MAX_FILE_CACHE_SIZE = 800  # ファイル行キャッシュの最大エントリ数
```

変更後：
```python
# キャッシュ上限（大規模プロジェクトでのOOM防止）
_MAX_AST_CACHE_SIZE = 2000  # 60GB規模対応（~2-6GB使用。メモリ不足時は500〜1000に調整）
_MAX_FILE_CACHE_SIZE = 800  # ファイル行キャッシュの最大エントリ数
```

- [ ] **Step 5-6: `docs/functional-design.md` に `grep_filter_files()` の説明を追加**

`FileCache` セクションの後（`### F-07` の直前）に追加：

```markdown
---

### grep_filter_files（`analyze_common.py`）

**責務**:
- バッチスキャン前に `mmap` バイト列検索で対象ファイルを絞り込む
- 識別子名（ASCII）をバイト列として検索し、1つでもヒットするファイルのみ返す（スーパーセット、false negative ゼロ）
- Solaris 10 / Windows を含む全 OS で動作（Python 標準ライブラリのみ）

```python
def grep_filter_files(
    names: list[str],      # 検索する識別子のリスト（ASCII）
    src_dir: Path,         # 検索対象ルートディレクトリ
    extensions: list[str], # 対象拡張子 例: [".java"], [".kt", ".kts"]
    label: str = "",       # 指定時は事前フィルタ結果を stderr に出力
) -> list[Path]:           # 絞り込み済みファイルリスト（ソート済み）
```

**呼び出し元**: `analyze.py` の `_batch_track_constants/getters/setters`、`analyze_all.py` の全8バッチ関数  
**エラー時**: OSError / mmap.error が発生したファイルはスキャン対象に含める（安全側フォールバック）
```

- [ ] **Step 5-7: `README.md` に進捗出力の説明を追加**

`### 2. アナライザーを実行する` セクションの引数テーブルの後に追加：

変更前：
```markdown
### 3. 出力を確認する
```

変更後：
```markdown
> **大規模ソースディレクトリの場合**  
> `--source-dir` 配下のファイル数が多い場合（数万ファイル以上）、間接追跡フェーズの進捗が標準エラー出力（stderr）に表示される。
> ```
>   処理中: TARGET.grep ...
>   [Java追跡] 事前フィルタ完了: 82000 → 134 ファイルに絞り込み
>   [Java定数追跡] 100/134 ファイル処理済み (75%)
>   [Java定数追跡] 完了: 134 ファイルスキャン / 参照 128 件発見
> ```
> TSV が出力されていなくても処理は継続中。stdout のみ取得する場合は `2>/dev/null` で抑制できる。

### 3. 出力を確認する
```

- [ ] **Step 5-8: 全テストが引き続きパスすることを確認**

```bash
python -m pytest tests/ test_analyze.py test_analyze_proc.py -v
```

期待結果: 全て PASS

- [ ] **Step 5-9: コミット**

```bash
git add docs/architecture.md docs/functional-design.md README.md
git commit -m "docs: パフォーマンス改善に伴うアーキテクチャ・機能設計・README の更新"
```

---

## 完了確認

全タスク完了後、以下で全テストが通ることを確認する：

```bash
python -m pytest tests/ test_analyze.py test_analyze_proc.py -v
```

期待結果: 全て PASS（失敗なし）
