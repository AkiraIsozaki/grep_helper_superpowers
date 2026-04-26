import sys, unittest, unittest.mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyze_common import GrepRecord, ProcessStats, RefType, parse_grep_line, write_tsv, grep_filter_files
import tempfile, csv

class TestCommonImports(unittest.TestCase):
    def test_grep_record_fields(self):
        r = GrepRecord("kw", "直接", "その他", "f.sql", "1", "code")
        self.assertEqual(r.keyword, "kw")
        self.assertEqual(r.src_var, "")

    def test_parse_grep_line_valid(self):
        result = parse_grep_line("src/sample.sql:10:WHERE code = 'A';")
        self.assertEqual(result["filepath"], "src/sample.sql")
        self.assertEqual(result["lineno"], "10")
        self.assertEqual(result["code"], "WHERE code = 'A';")

    def test_parse_grep_line_binary(self):
        self.assertIsNone(parse_grep_line("Binary file ./obj/sample.o matches"))

    def test_write_tsv_creates_bom(self):
        records = [GrepRecord("K", "直接", "その他", "f.sql", "1", "code")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            write_tsv(records, out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))

    def test_write_tsv_sort_direct_before_indirect(self):
        records = [
            GrepRecord("K", "間接", "その他", "b.sql", "5", "c",
                       src_var="V", src_file="a.sql", src_lineno="2"),
            GrepRecord("K", "直接", "その他", "a.sql", "2", "c"),
        ]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            write_tsv(records, out)
            with open(out, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter="\t"))[1:]
            self.assertEqual(rows[0][1], "直接")
            self.assertEqual(rows[1][1], "間接")

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


class TestDetectEncodingStreaming(unittest.TestCase):
    def test_does_not_call_read_bytes(self):
        """巨大ファイルでも先頭 4KB だけ読む（read_bytes は使わない）。"""
        from analyze_common import detect_encoding
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_bytes(b"hello world\n" * 100)
            def boom(self):
                raise AssertionError("read_bytes should not be called")
            with patch.object(Path, "read_bytes", boom):
                enc = detect_encoding(p)
                self.assertIsInstance(enc, str)

    def test_reads_at_most_4kb(self):
        """4096 バイト以下しか read しない。"""
        from analyze_common import detect_encoding
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "big.txt"
            p.write_bytes(b"A" * 100_000)
            sizes: list[int] = []
            real_open = open
            def tracking_open(*args, **kwargs):
                f = real_open(*args, **kwargs)
                orig_read = f.read
                def read(n=-1):
                    sizes.append(n if n >= 0 else 10**12)
                    return orig_read(n)
                f.read = read
                return f
            import analyze_common
            with unittest.mock.patch.object(analyze_common, "open", tracking_open, create=True):
                detect_encoding(p)
            self.assertTrue(len(sizes) > 0, "tracking_open was never called")
            self.assertTrue(all(n <= 4096 for n in sizes), sizes)


class TestIterGrepLines(unittest.TestCase):
    def test_yields_lines_without_loading_all(self):
        """iter_grep_lines はジェネレータで返る（list 化されない）。"""
        from analyze_common import iter_grep_lines
        import types
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_text("a:1:foo\nb:2:bar\n", encoding="utf-8")
            it = iter_grep_lines(p, "utf-8")
            self.assertIsInstance(it, types.GeneratorType)
            self.assertEqual(list(it), ["a:1:foo", "b:2:bar"])

    def test_handles_decode_errors(self):
        """不正バイトは errors=replace で継続。"""
        from analyze_common import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_bytes(b"good\n\xff\xfe\xfd\nmore\n")
            self.assertEqual(list(iter_grep_lines(p, "utf-8")), ["good", "���", "more"])


class TestIterSourceFiles(unittest.TestCase):
    def test_caches_per_extension_set(self):
        """同じ (src_dir, extensions) は二度目はディスクを読まない。"""
        from analyze_common import iter_source_files, _source_files_cache_clear
        _source_files_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.java").write_text("x")
            (p / "b.kt").write_text("x")
            r1 = iter_source_files(p, [".java"])
            (p / "c.java").write_text("x")  # 後から追加
            r2 = iter_source_files(p, [".java"])
            self.assertEqual(r1, r2)         # 2 回目もキャッシュから返る
            self.assertEqual(len(r1), 1)     # b.java は無いので 1 件
            self.assertNotIn(p / "c.java", r2)

    def test_different_extensions_separate_cache(self):
        from analyze_common import iter_source_files, _source_files_cache_clear
        _source_files_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.java").write_text("x")
            (p / "b.kt").write_text("x")
            self.assertEqual(len(iter_source_files(p, [".java"])), 1)
            self.assertEqual(len(iter_source_files(p, [".kt"])), 1)
            self.assertEqual(len(iter_source_files(p, [".java", ".kt"])), 2)


class TestResolveFileCached(unittest.TestCase):
    def test_resolves_relative_to_src_dir(self):
        from analyze_common import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "sub").mkdir()
            f = p / "sub" / "x.txt"
            f.write_text("x")
            self.assertEqual(resolve_file_cached("sub/x.txt", p), f)

    def test_returns_none_for_missing(self):
        from analyze_common import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(resolve_file_cached("missing.txt", Path(d)))

    def test_caches_result(self):
        from analyze_common import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "x.txt"
            f.write_text("x")
            r1 = resolve_file_cached("x.txt", p)
            f.unlink()  # ファイル削除
            r2 = resolve_file_cached("x.txt", p)
            self.assertEqual(r1, r2)  # キャッシュから同じ結果が返る


if __name__ == "__main__":
    unittest.main()
