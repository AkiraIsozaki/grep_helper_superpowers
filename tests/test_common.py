import sys, unittest, unittest.mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from grep_helper.model import GrepRecord, ProcessStats, RefType
from grep_helper.grep_input import parse_grep_line
from grep_helper.tsv_output import write_tsv
from grep_helper.source_files import grep_filter_files
import tempfile, csv

class TestCommonImports(unittest.TestCase):
    """TestCommonImports: model / grep_input / tsv_output 横断の公開 API smoke test。
    `GrepRecord` のフィールド既定値、`parse_grep_line` の返り値、`write_tsv` の BOM /
    ソート出力という、複数モジュールの最小限の WHAT を 1 箇所で観察する sanity layer。
    """

    def test_GrepRecord初期化でsrc_varは空文字に既定設定される(self):
        r = GrepRecord("kw", "直接", "その他", "f.sql", "1", "code")
        self.assertEqual(r.keyword, "kw")
        self.assertEqual(r.src_var, "")

    def test_grep行はfilepathとlinenoとcodeに分解される(self):
        result = parse_grep_line("src/sample.sql:10:WHERE code = 'A';")
        self.assertEqual(result["filepath"], "src/sample.sql")
        self.assertEqual(result["lineno"], "10")
        self.assertEqual(result["code"], "WHERE code = 'A';")

    def test_バイナリファイル行はNoneになる(self):
        self.assertIsNone(parse_grep_line("Binary file ./obj/sample.o matches"))

    def test_write_tsvがBOM付きで書き出す(self):
        records = [GrepRecord("K", "直接", "その他", "f.sql", "1", "code")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.tsv"
            write_tsv(records, out)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))

    def test_write_tsvが直接を間接より先にソートする(self):
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
    """TestGrepFilterFiles: grep_filter_files の事前フィルタ結果を観察するテスト。
    拡張子フィルタ・空キーワード・ソート・stderr label 出力という公開契約を網羅する。
    E2E fixture は単一言語のみのため、拡張子バリエーションは本クラスで補う。
    """

    def test_マッチするファイルが結果に含まれる(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "Foo.java"
            f.write_bytes(b"public static final String FOO_CONST = \"value\";\n")
            result = grep_filter_files(["FOO_CONST"], p, [".java"])
            self.assertIn(f, result)

    def test_マッチしないファイルは結果から除外される(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "Bar.java"
            f.write_bytes(b"public class Bar {}\n")
            result = grep_filter_files(["FOO_CONST"], p, [".java"])
            self.assertNotIn(f, result)

    def test_対象拡張子以外のファイルは除外される(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "script.sh"
            f.write_bytes(b"FOO_CONST=value\n")
            result = grep_filter_files(["FOO_CONST"], p, [".java"])
            self.assertNotIn(f, result)

    def test_キーワード空なら全ファイルを返す(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f1 = p / "A.java"; f1.write_bytes(b"class A {}\n")
            f2 = p / "B.java"; f2.write_bytes(b"class B {}\n")
            result = grep_filter_files([], p, [".java"])
            self.assertEqual(set(result), {f1, f2})

    def test_空ファイルは結果に含まれない(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "Empty.java"; f.write_bytes(b"")
            result = grep_filter_files(["FOO"], p, [".java"])
            self.assertNotIn(f, result)

    def test_複数拡張子を指定できる(self):
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

    def test_結果がソート済みで返る(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            b = p / "b.java"; b.write_bytes(b"PATTERN\n")
            a = p / "a.java"; a.write_bytes(b"PATTERN\n")
            result = grep_filter_files(["PATTERN"], p, [".java"])
            self.assertEqual(result, sorted(result))

    def test_labelが標準エラー出力に表示される(self):
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


class TestIterGrepLines(unittest.TestCase):
    """TestIterGrepLines: iter_grep_lines のストリーミング読込を観察するテスト。
    順序保証・デコードエラー時の置換継続・巨大ファイル時の早期 yield 契約を観察。
    streaming 性能は非機能要件で E2E では計測しないため、本クラスで担保する。
    """

    def test_grep行は入力順のままyieldされる(self):
        from grep_helper.grep_input import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_text("a:1:foo\nb:2:bar\n", encoding="utf-8")
            self.assertEqual(list(iter_grep_lines(p, "utf-8")), ["a:1:foo", "b:2:bar"])

    def test_デコードエラーを置換して継続する(self):
        from grep_helper.grep_input import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.grep"
            p.write_bytes(b"good\n\xff\xfe\xfd\nmore\n")
            self.assertEqual(list(iter_grep_lines(p, "utf-8")), ["good", "���", "more"])

    def test_巨大ファイルでも先頭数行だけ消費して短時間で返る(self):
        import itertools, time
        from grep_helper.grep_input import iter_grep_lines
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "huge.grep"
            # 数十 MB 相当を生成 (300_000 行 × ~30 byte/line ≒ 9MB)
            with open(p, "w", encoding="utf-8") as f:
                for i in range(300_000):
                    f.write(f"src/file.py:{i}:line content here\n")
            t0 = time.monotonic()
            head = list(itertools.islice(iter_grep_lines(p, "utf-8"), 5))
            elapsed = time.monotonic() - t0
            self.assertEqual(len(head), 5)
            self.assertEqual(head[0], "src/file.py:0:line content here")
            self.assertLess(elapsed, 2.0, f"ストリーミングが効いていない疑い: {elapsed:.3f}s")


class TestIterSourceFiles(unittest.TestCase):
    """TestIterSourceFiles: iter_source_files のキャッシュ挙動を観察するテスト。
    拡張子セット単位の keying と、後から追加された file が再列挙されない契約を観察。
    `_source_files_cache_clear` は前提条件リセット用で観測対象は公開戻り値のみ。
    """

    def test_同じ拡張子セットでは追加ファイルが再列挙されない(self):
        from grep_helper.source_files import iter_source_files, _source_files_cache_clear
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

    def test_拡張子が異なればキャッシュも別になる(self):
        from grep_helper.source_files import iter_source_files, _source_files_cache_clear
        _source_files_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.java").write_text("x")
            (p / "b.kt").write_text("x")
            self.assertEqual(len(iter_source_files(p, [".java"])), 1)
            self.assertEqual(len(iter_source_files(p, [".kt"])), 1)
            self.assertEqual(len(iter_source_files(p, [".java", ".kt"])), 2)


class TestResolveFileCached(unittest.TestCase):
    """TestResolveFileCached: resolve_file_cached のキャッシュ挙動を観察するテスト。
    存在ファイル解決・None 返却・hit 後の削除でも同一結果という公開契約を観察。
    `_resolve_file_cache_clear` は前提条件リセット用途で観測対象は公開戻り値のみ。
    """

    def test_src_dir相対パスは絶対Pathに解決される(self):
        from grep_helper.source_files import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "sub").mkdir()
            f = p / "sub" / "x.txt"
            f.write_text("x")
            self.assertEqual(resolve_file_cached("sub/x.txt", p), f)

    def test_存在しないファイルはNoneを返す(self):
        from grep_helper.source_files import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(resolve_file_cached("missing.txt", Path(d)))

    def test_解決結果がキャッシュされる(self):
        from grep_helper.source_files import resolve_file_cached, _resolve_file_cache_clear
        _resolve_file_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "x.txt"
            f.write_text("x")
            r1 = resolve_file_cached("x.txt", p)
            f.unlink()  # ファイル削除
            r2 = resolve_file_cached("x.txt", p)
            self.assertEqual(r1, r2)  # キャッシュから同じ結果が返る


class TestCachedFileLines(unittest.TestCase):
    """TestCachedFileLines: cached_file_lines の LRU キャッシュ挙動を観察するテスト。
    行リスト返却・キャッシュ hit 時の古値返却・容量上限超過時の追い出し再読込という
    公開契約を観察。LRU の eviction は E2E では再現性が低いため本クラスで担保する。
    """

    def test_ファイル各行が文字列リストとして返る(self):
        from grep_helper.file_cache import cached_file_lines, _file_lines_cache_clear
        _file_lines_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_text("a\nb\nc\n", encoding="utf-8")
            self.assertEqual(cached_file_lines(p, "utf-8"), ["a", "b", "c"])

    def test_キャッシュ済みファイルは書き換えても古い値が返る(self):
        from grep_helper.file_cache import cached_file_lines, _file_lines_cache_clear
        _file_lines_cache_clear()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_text("first\n", encoding="utf-8")
            first = cached_file_lines(p, "utf-8")
            p.write_text("second\n", encoding="utf-8")
            second = cached_file_lines(p, "utf-8")
            self.assertEqual(first, ["first"])
            self.assertEqual(second, ["first"])  # キャッシュ hit で古い値

    def test_容量上限を超えると古いエントリが追い出されて再読込される(self):
        from grep_helper.file_cache import (
            cached_file_lines,
            _file_lines_cache_clear,
            set_file_lines_cache_limit,
        )
        _file_lines_cache_clear()
        set_file_lines_cache_limit(100)  # 100 byte 上限
        try:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d)
                early = []
                for i in range(3):
                    f = p / f"early{i}.txt"
                    f.write_text("X" * 50, encoding="utf-8")
                    cached_file_lines(f, "utf-8")
                    early.append(f)
                for i in range(5):  # 容量上限を確実に超過
                    f = p / f"later{i}.txt"
                    f.write_text("X" * 50, encoding="utf-8")
                    cached_file_lines(f, "utf-8")
                # 初期エントリの中身を書き換え、再読込が起きていることを観察
                re_read = []
                for f in early:
                    f.write_text("CHANGED", encoding="utf-8")
                    if cached_file_lines(f, "utf-8") == ["CHANGED"]:
                        re_read.append(f)
                self.assertGreaterEqual(len(re_read), 1)
        finally:
            set_file_lines_cache_limit(256 * 1024 * 1024)  # 復元


class TestBatchScannerSelector(unittest.TestCase):
    """TestBatchScannerSelector: build_batch_scanner の公開マッチ結果を観察するテスト。
    単語境界 findall と、パターン数規模に依らない結果同一性という公開契約を観察。
    backend 切替の内部実装は対の Whitebox クラスで別途固定する。
    """

    def test_findallが単語境界でマッチする(self):
        from grep_helper.scanner import build_batch_scanner
        scanner = build_batch_scanner(["FOO"])
        line = "x = FOO + FOOBAR;"
        results = [name for _, name in scanner.findall(line)]
        self.assertEqual(results, ["FOO"])

    def test_数パターンでも数百パターンでも同じマッチ結果になる(self):
        from grep_helper.scanner import build_batch_scanner
        small = build_batch_scanner(["A", "B", "C"])
        large_patterns = [f"NAME{i:04d}" for i in range(200)] + ["A", "B", "C"]
        large = build_batch_scanner(large_patterns)
        line = "use A and B and C here"
        small_hits = sorted(name for _, name in small.findall(line))
        large_hits = sorted(name for _, name in large.findall(line) if name in {"A", "B", "C"})
        self.assertEqual(small_hits, ["A", "B", "C"])
        self.assertEqual(large_hits, ["A", "B", "C"])


class TestDetectEncoding(unittest.TestCase):
    """TestDetectEncoding: detect_encoding の公開戻り値を観察するテスト。
    override 引数の short-circuit と、存在しないファイルでの cp932 fallback という
    公開契約を観察。streaming 読込の実装契約は対の Whitebox クラスで別途固定する。
    """

    def test_overrideを与えるとそのまま返る(self):
        from grep_helper.encoding import detect_encoding
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "any.txt"
            p.write_bytes(b"\xe3\x81\x82\xe3\x81\x84")
            self.assertEqual(detect_encoding(p, override="utf-16"), "utf-16")

    def test_存在しないファイルはcp932にフォールバックする(self):
        from grep_helper.encoding import detect_encoding
        result = detect_encoding(Path("/nonexistent/path/x.txt"))
        self.assertEqual(result, "cp932")


class TestBatchScannerSelectorWhitebox(unittest.TestCase):
    """TestBatchScannerSelectorWhitebox: build_batch_scanner の backend 選択を観察するテスト。
    `scanner.backend` 内部 attribute を直接 peek し、閾値 100 を境に regex / ahocorasick が
    選ばれる実装契約を固定。性能非機能要件（大量パターン時の AC 切替）を担保する。
    実装変更時は本クラスも同期更新が必要。
    """

    def test_パターン数が閾値以上ならahocorasickバックエンドが選ばれる(self):
        from grep_helper.scanner import build_batch_scanner
        scanner = build_batch_scanner([f"NAME{i:04d}" for i in range(200)])
        self.assertEqual(scanner.backend, "ahocorasick")

    def test_パターン数が閾値未満ならregexバックエンドが選ばれる(self):
        from grep_helper.scanner import build_batch_scanner
        scanner = build_batch_scanner(["A", "B", "C"])
        self.assertEqual(scanner.backend, "regex")


class TestDetectEncodingStreamingWhitebox(unittest.TestCase):
    """TestDetectEncodingStreamingWhitebox: detect_encoding のストリーミング読込を観察するテスト。
    `Path.read_bytes` を未呼出に固定し、`open().read(n)` を spy して `n <= 4096` を観測する
    密結合 coupling test。巨大ファイル時のメモリ・レイテンシ非機能要件を担保する。
    実装変更時は本クラスも同期更新が必要。
    """

    def test_read_bytesを呼ばない(self):
        from grep_helper.encoding import detect_encoding
        from unittest.mock import patch
        # chardet のモデル遅延ロードが read_bytes を使うため、先に初期化しておく
        try:
            import chardet as _cd
            _cd.detect(b"warmup")
        except Exception:
            pass
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_bytes(b"hello world\n" * 100)
            orig_read_bytes = Path.read_bytes
            def boom(self_path):
                if str(self_path) == str(p):
                    raise AssertionError("read_bytes should not be called on target file")
                return orig_read_bytes(self_path)
            with patch.object(Path, "read_bytes", boom):
                enc = detect_encoding(p)
                self.assertIsInstance(enc, str)

    def test_最大4KBまでしか読まない(self):
        from grep_helper.encoding import detect_encoding
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
            import grep_helper.encoding
            with unittest.mock.patch.object(grep_helper.encoding, "open", tracking_open, create=True):
                detect_encoding(p)
            self.assertTrue(len(sizes) > 0, "tracking_open was never called")
            self.assertTrue(all(n <= 4096 for n in sizes), sizes)


if __name__ == "__main__":
    unittest.main()
