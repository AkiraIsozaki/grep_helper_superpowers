# tests/test_all_analyzer.py
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.model import GrepRecord, ProcessStats, RefType
from grep_helper.grep_input import parse_grep_line
from grep_helper.tsv_output import write_tsv
from grep_helper.languages import detect_handler
from grep_helper.dispatcher import (
    process_grep_lines_all,
    apply_indirect_tracking,
    main,
)
import grep_helper.dispatcher as _dispatcher
import inspect


def detect_language(filepath: str, source_dir: Path) -> str:
    """旧 API compat: returns language key string."""
    h = detect_handler(filepath, source_dir)
    name = h.__name__.rsplit(".", 1)[-1]
    return "other" if name == "_none" else name


def _apply_indirect_tracking(direct_records, source_dir, stats, encoding, workers=1):
    """旧 API compat: old positional signature."""
    return apply_indirect_tracking(direct_records, source_dir, encoding, workers=workers)


def process_grep_lines_all_compat(lines, keyword, source_dir, stats, encoding=None):
    """旧 API compat: accepts positional encoding arg."""
    return _dispatcher.process_grep_lines_all(lines, keyword, source_dir, stats, encoding=encoding)


class TestDetectLanguage(unittest.TestCase):
    """TestDetectLanguage: detect_handler の言語判定戻り値を観察するテスト。
    E2E は 5 fixture しか通らず、30 種超の拡張子/シェバン分岐を観察できないため keep。
    """

    def test_java拡張子はjavaと判定される(self):
        self.assertEqual(detect_language("src/Foo.java", Path(".")), "java")

    def test_kt拡張子はkotlinと判定される(self):
        self.assertEqual(detect_language("src/Foo.kt", Path(".")), "kotlin")

    def test_kts拡張子はkotlinと判定される(self):
        self.assertEqual(detect_language("src/build.kts", Path(".")), "kotlin")

    def test_c拡張子はc言語と判定される(self):
        self.assertEqual(detect_language("src/util.c", Path(".")), "c")

    def test_h拡張子はc言語と判定される(self):
        self.assertEqual(detect_language("src/util.h", Path(".")), "c")

    def test_pc拡張子はprocと判定される(self):
        """.pc 拡張子は proc(Pro*C)として判定される。"""
        self.assertEqual(detect_language("src/proc.pc", Path(".")), "proc")

    def test_sql拡張子はsqlと判定される(self):
        self.assertEqual(detect_language("src/query.sql", Path(".")), "sql")

    def test_sh拡張子はshと判定される(self):
        """.sh 拡張子は sh(シェル)として判定される。"""
        self.assertEqual(detect_language("src/run.sh", Path(".")), "sh")

    def test_bash拡張子はshと判定される(self):
        """.bash 拡張子は sh(シェル)として判定される。"""
        self.assertEqual(detect_language("src/run.bash", Path(".")), "sh")

    def test_ts拡張子はtsと判定される(self):
        """.ts 拡張子は ts(TypeScript)として判定される。"""
        self.assertEqual(detect_language("src/app.ts", Path(".")), "ts")

    def test_js拡張子はtsと判定される(self):
        """.js 拡張子も ts カテゴリとして判定される。"""
        self.assertEqual(detect_language("src/app.js", Path(".")), "ts")

    def test_tsx拡張子はtsと判定される(self):
        """.tsx 拡張子は ts カテゴリとして判定される。"""
        self.assertEqual(detect_language("src/app.tsx", Path(".")), "ts")

    def test_jsx拡張子はtsと判定される(self):
        """.jsx 拡張子は ts カテゴリとして判定される。"""
        self.assertEqual(detect_language("src/app.jsx", Path(".")), "ts")

    def test_py拡張子はpythonと判定される(self):
        self.assertEqual(detect_language("src/util.py", Path(".")), "python")

    def test_pl拡張子はperlと判定される(self):
        self.assertEqual(detect_language("src/script.pl", Path(".")), "perl")

    def test_pm拡張子はperlと判定される(self):
        """.pm 拡張子は perl モジュールとして判定される。"""
        self.assertEqual(detect_language("src/Mod.pm", Path(".")), "perl")

    def test_cs拡張子はdotnetと判定される(self):
        """.cs 拡張子は dotnet(C#)として判定される。"""
        self.assertEqual(detect_language("src/App.cs", Path(".")), "dotnet")

    def test_vb拡張子はdotnetと判定される(self):
        """.vb 拡張子は dotnet(VB.NET)として判定される。"""
        self.assertEqual(detect_language("src/App.vb", Path(".")), "dotnet")

    def test_groovy拡張子はgroovyと判定される(self):
        self.assertEqual(detect_language("src/Svc.groovy", Path(".")), "groovy")

    def test_gvy拡張子はgroovyと判定される(self):
        self.assertEqual(detect_language("src/Svc.gvy", Path(".")), "groovy")

    def test_pls拡張子はplsqlと判定される(self):
        self.assertEqual(detect_language("src/pkg.pls", Path(".")), "plsql")

    def test_pck拡張子はplsqlと判定される(self):
        self.assertEqual(detect_language("src/pkg.pck", Path(".")), "plsql")

    def test_xml拡張子はotherと判定される(self):
        """.xml 拡張子はサポート対象外で other に分類される。"""
        self.assertEqual(detect_language("src/config.xml", Path(".")), "other")

    def test_yaml拡張子はotherと判定される(self):
        """.yaml 拡張子はサポート対象外で other に分類される。"""
        self.assertEqual(detect_language("src/app.yaml", Path(".")), "other")

    def test_拡張子なしperlシェバンはperlと判定される(self):
        """拡張子なしファイルでも #!/usr/bin/perl のシェバンで perl と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "myscript"
            f.write_text("#!/usr/bin/perl\nprint 1;\n")
            self.assertEqual(detect_language("myscript", src), "perl")

    def test_拡張子なしenv_perlシェバンはperlと判定される(self):
        """拡張子なしファイルでも #!/usr/bin/env perl のシェバンで perl と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "myscript"
            f.write_text("#!/usr/bin/env perl\nprint 1;\n")
            self.assertEqual(detect_language("myscript", src), "perl")

    def test_拡張子なしbashシェバンはshと判定される(self):
        """拡張子なしファイルでも #!/bin/bash のシェバンで sh と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/bash\necho hi\n")
            self.assertEqual(detect_language("run", src), "sh")

    def test_拡張子なしshシェバンはshと判定される(self):
        """拡張子なしファイルでも #!/bin/sh のシェバンで sh と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/sh\necho hi\n")
            self.assertEqual(detect_language("run", src), "sh")

    def test_拡張子なしcshシェバンはshと判定される(self):
        """拡張子なしファイルでも #!/bin/csh のシェバンで sh と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/csh\necho hi\n")
            self.assertEqual(detect_language("run", src), "sh")

    def test_拡張子なしtcshシェバンはshと判定される(self):
        """拡張子なしファイルでも #!/bin/tcsh のシェバンで sh と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/tcsh\necho hi\n")
            self.assertEqual(detect_language("run", src), "sh")

    def test_拡張子なしkshシェバンはshと判定される(self):
        """拡張子なしファイルでも #!/bin/ksh のシェバンで sh と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/ksh\necho hi\n")
            self.assertEqual(detect_language("run", src), "sh")

    def test_拡張子なしksh93シェバンはshと判定される(self):
        """拡張子なしファイルでも #!/bin/ksh93 のシェバンで sh と判定される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/ksh93\necho hi\n")
            self.assertEqual(detect_language("run", src), "sh")

    def test_拡張子なし未知シェバンはotherと判定される(self):
        """サポート外のシェバン(例:ruby)は other に分類される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/usr/bin/ruby\nputs 1\n")
            self.assertEqual(detect_language("run", src), "other")

    def test_拡張子なしシェバンなしはotherと判定される(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("some content\n")
            self.assertEqual(detect_language("run", src), "other")

    def test_拡張子なしファイル不在はotherと判定される(self):
        self.assertEqual(detect_language("nonexistent_file", Path("/tmp")), "other")


class TestDirectClassification(unittest.TestCase):
    """TestDirectClassification: process_grep_lines_all の直接分類戻り値を観察するテスト。
    E2E は実 fixture のみで、不正 grep 行/バイナリ行のスキップ分岐を覆わないため keep。
    """

    def _make_direct_records(self, grep_lines: list[str], source_dir: Path) -> list:
        stats = ProcessStats()
        return process_grep_lines_all_compat(grep_lines, "TEST", source_dir, stats, None)

    def test_java行は定数として直接参照に分類される(self):
        """Java の static final 定数行が「定数」「直接」として分類される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/Foo.java:10:    static final String X = \"TARGET\""],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertIn("定数", records[0].usage_type)
            self.assertEqual(records[0].ref_type, "直接")

    def test_groovy行は条件判定として分類される(self):
        """Groovy の if 文比較行が「条件判定」として分類される。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/Svc.groovy:5:    if (code == TARGET) {{ return }}"],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "条件判定")

    def test_sh行は変数代入として分類される(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/run.sh:3:TARGET=\"777\""],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "変数代入")

    def test_未知拡張子は直接かつその他に分類される(self):
        """サポート外拡張子(.xml)は ref_type=直接、usage_type=その他になる。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/config.xml:1:<value>TARGET</value>"],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "その他")
            self.assertEqual(records[0].ref_type, "直接")

    def test_拡張子なしperlファイルはその他に分類されない(self):
        """拡張子なしでも Perl シェバンがあれば「その他」にフォールバックしない。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            script = src / "cleanup"
            script.write_text("#!/usr/bin/perl\nmy $x = TARGET;\n")
            records = self._make_direct_records(
                [f"{src}/cleanup:2:my $x = TARGET;"],
                src,
            )
            self.assertEqual(len(records), 1)
            # Perl classifies assignment as "変数代入" or similar — just not "その他"
            self.assertNotEqual(records[0].usage_type, "その他")

    def test_不正なgrep行はスキップされる(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                ["not a valid grep line"],
                src,
            )
            self.assertEqual(len(records), 0)

    def test_バイナリ行はスキップされる(self):
        """grep の "Binary file ... matches" 行はスキップされる。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                ["Binary file src/app.bin matches"],
                src,
            )
            self.assertEqual(len(records), 0)


class TestIndirectTracking(unittest.TestCase):
    """TestIndirectTracking: apply_indirect_tracking の間接参照戻り値を観察するテスト。
    E2E は間接件数を assertion せず、return [] mutation を見逃すため keep。
    """

    def test_groovyのstatic_final定数は間接参照を追跡する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Const.groovy").write_text(
                'static final String STATUS = "TARGET"\n'
            )
            (src / "Service.groovy").write_text(
                'if (s == STATUS) { return }\n'
            )
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="static final定数定義",
                filepath=str(src / "Const.groovy"), lineno="1",
                code='static final String STATUS = "TARGET"',
            )
            stats = ProcessStats()
            indirect = _apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("Service.groovy" in r.filepath for r in indirect))

    def test_sh変数定義は間接参照を追跡する(self):
        """シェル変数代入から $VAR 参照を間接参照として検出する。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            script = src / "deploy.sh"
            script.write_text('STATUS="TARGET"\necho $STATUS\n')
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(script), lineno="1",
                code='STATUS="TARGET"',
            )
            stats = ProcessStats()
            indirect = _apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("deploy.sh" in r.filepath for r in indirect))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in indirect))

    def test_dotnetのconst定義は間接参照を追跡する(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Consts.cs").write_text('const string STATUS = "TARGET";\n')
            (src / "Service.cs").write_text('if (x == STATUS) { return; }\n')
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="定数定義(Const/readonly)",
                filepath=str(src / "Consts.cs"), lineno="1",
                code='const string STATUS = "TARGET";',
            )
            stats = ProcessStats()
            indirect = _apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("Service.cs" in r.filepath for r in indirect))

    def test_対象外言語は間接参照を追跡しない(self):
        """サポート外言語(usage_type=その他)は間接参照を生成しない。"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="その他",
                filepath=str(src / "config.xml"), lineno="1",
                code="<value>TARGET</value>",
            )
            stats = ProcessStats()
            indirect = _apply_indirect_tracking([direct], src, stats, None)
            self.assertEqual(indirect, [])


class TestE2EAll(unittest.TestCase):
    """TestE2EAll: 全言語ディスパッチャー end-to-end のシナリオ観察を行う E2E gate。
    実 fixture (Java/Groovy/sh/xml/cleanup) を入力に grep 行→TSV 出力までの全パスを通す。
    """

    TESTS_DIR = Path(__file__).parent / "all"

    def test_全grep行がTSV出力に含まれる(self):
        """全grep行がTSVに含まれること(漏れゼロ確認)。"""
        src_dir   = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"

        self.assertTrue(src_dir.exists(), f"src_dir not found: {src_dir}")
        self.assertTrue(input_dir.exists(), f"input_dir not found: {input_dir}")

        grep_path = input_dir / "TARGET.grep"
        input_lines = [
            l for l in grep_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        self.assertGreater(len(input_lines), 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stats = ProcessStats()
            keyword = "TARGET"

            direct_records = process_grep_lines_all_compat(
                input_lines, keyword, src_dir, stats, None,
            )
            all_records = list(direct_records)
            all_records.extend(
                _apply_indirect_tracking(direct_records, src_dir, stats, None)
            )
            output_path = output_dir / "TARGET.tsv"
            write_tsv(all_records, output_path)

            # すべての直接参照 filepath が出力に含まれる
            output_filepaths = {r.filepath for r in all_records if r.ref_type == "直接"}
            for line in input_lines:
                parsed = parse_grep_line(line)
                if parsed:
                    self.assertIn(
                        parsed["filepath"], output_filepaths,
                        f"Missing in output: {parsed['filepath']}",
                    )

            # extension-less Perl file must not fall back to "other"
            cleanup_records = [r for r in all_records if r.ref_type == "直接" and r.filepath.endswith("cleanup")]
            if cleanup_records:
                self.assertNotEqual(cleanup_records[0].usage_type, "その他",
                    "cleanup file (Perl shebang) was classified as 'other' — shebang detection failed")

    def test_未知拡張子のusage_typeはその他になる(self):
        """E2E入力中の .xml ファイルは usage_type が「その他」になる。"""
        src_dir   = self.TESTS_DIR / "src"
        input_dir = self.TESTS_DIR / "input"
        grep_path = input_dir / "TARGET.grep"
        input_lines = grep_path.read_text(encoding="utf-8").splitlines()
        stats = ProcessStats()
        records = process_grep_lines_all_compat(input_lines, "TARGET", src_dir, stats, None)
        xml_records = [r for r in records if r.filepath.endswith(".xml")]
        self.assertEqual(len(xml_records), 1)
        self.assertEqual(xml_records[0].usage_type, "その他")

    def test_拡張子なしperlファイルはその他にならない(self):
        """E2E 入力中の cleanup ファイル(Perl シェバン)は その他 に分類されない。"""
        # Use repo root as src_dir so that "tests/all/src/cleanup" resolves correctly
        src_dir   = Path(__file__).parent.parent
        input_dir = self.TESTS_DIR / "input"
        grep_path = input_dir / "TARGET.grep"
        input_lines = grep_path.read_text(encoding="utf-8").splitlines()
        stats = ProcessStats()
        records = process_grep_lines_all_compat(input_lines, "TARGET", src_dir, stats, None)
        cleanup_records = [r for r in records if r.filepath.endswith("cleanup")]
        self.assertEqual(len(cleanup_records), 1)
        self.assertNotEqual(cleanup_records[0].usage_type, "その他")


class TestProcessGrepLinesAllIterable(unittest.TestCase):
    """TestProcessGrepLinesAllIterable: process_grep_lines_all の Iterable 受理を観察するテスト。
    E2E は list 入力のみで、generator reject mutation を見逃すため keep。
    """

    def test_ジェネレータ入力を受け付ける(self):
        stats = ProcessStats()
        def gen():
            yield "Foo.java:1:public class Foo {}"
        records = process_grep_lines_all_compat(gen(), "kw", Path("/tmp"), stats, None)
        self.assertEqual(len(records), 1)


class TestDispatcherAggregation(unittest.TestCase):
    """dispatcher.main の集約処理 (E-2): 複数 grep を 1 回の間接追跡で
    処理しても、grep ごとに 1 本ずつ処理した場合と完全一致の TSV が出る。
    """

    def test_複数grep集約でもTSVが完全一致する(self):
        from grep_helper.grep_input import iter_grep_lines
        from grep_helper.encoding import detect_encoding
        from collections import defaultdict

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "src"
            src_dir.mkdir()
            (src_dir / "a.sql").write_text(
                "SELECT * FROM t WHERE x = 'A';\n", encoding="utf-8",
            )
            (src_dir / "b.sql").write_text(
                "SELECT * FROM t WHERE y = 'B';\n", encoding="utf-8",
            )

            # 集約: 同じ input dir に 2 grep
            output_combined = tmp_path / "output_combined"
            output_combined.mkdir()
            stats = ProcessStats()
            all_direct = []
            for stem, line in [("A", "src/a.sql:1:SELECT * FROM t WHERE x = 'A';"),
                               ("B", "src/b.sql:1:SELECT * FROM t WHERE y = 'B';")]:
                grep_path = tmp_path / f"{stem}.grep"
                grep_path.write_text(line + "\n", encoding="utf-8")
                enc = detect_encoding(grep_path, None)
                direct = process_grep_lines_all(
                    iter_grep_lines(grep_path, enc), stem, src_dir, stats,
                )
                all_direct.extend(direct)
            indirect = apply_indirect_tracking(all_direct, src_dir, None, workers=1)
            indirect_by_kw = defaultdict(list)
            for rec in indirect:
                indirect_by_kw[rec.keyword].append(rec)
            kw_to_direct = defaultdict(list)
            for rec in all_direct:
                kw_to_direct[rec.keyword].append(rec)
            for kw, direct in kw_to_direct.items():
                write_tsv(direct + indirect_by_kw[kw], output_combined / f"{kw}.tsv")

            # 単独: 1 grep ずつ
            output_solo = tmp_path / "output_solo"
            output_solo.mkdir()
            for stem, line in [("A", "src/a.sql:1:SELECT * FROM t WHERE x = 'A';"),
                               ("B", "src/b.sql:1:SELECT * FROM t WHERE y = 'B';")]:
                grep_path = tmp_path / f"{stem}.grep"
                stats_solo = ProcessStats()
                enc = detect_encoding(grep_path, None)
                direct = process_grep_lines_all(
                    iter_grep_lines(grep_path, enc), stem, src_dir, stats_solo,
                )
                indirect = apply_indirect_tracking(direct, src_dir, None, workers=1)
                write_tsv(direct + indirect, output_solo / f"{stem}.tsv")

            for keyword in ("A", "B"):
                combined = (output_combined / f"{keyword}.tsv").read_bytes()
                solo = (output_solo / f"{keyword}.tsv").read_bytes()
                self.assertEqual(
                    combined, solo,
                    f"{keyword}.tsv が dispatcher の集約/単独で一致しない",
                )


class TestMainStreamingWhitebox(unittest.TestCase):
    """TestMainStreamingWhitebox: dispatcher.main のストリーミング実装を観察するテスト。
    inspect.getsource でソース文字列を覗き、read_text().splitlines() を使わず
    iter_grep_lines を使う実装契約を観察する。
    実装変更時は本クラスも同期更新が必要。
    """

    def test_mainはgrepファイル全体を読み込まない(self):
        import grep_helper.dispatcher
        src = inspect.getsource(grep_helper.dispatcher.main)
        self.assertNotIn("read_text(encoding=enc, errors=\"replace\").splitlines()", src)
        self.assertIn("iter_grep_lines", src)


class TestNoMmapFlag(unittest.TestCase):
    """--no-mmap フラグ + GREP_HELPER_NO_MMAP 環境変数の解決ロジック。"""

    def test_未指定環境変数なしならuse_mmap_True(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertTrue(_resolve_use_mmap(no_mmap_arg=False, env={}))

    def test_フラグ明示でuse_mmap_False(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertFalse(_resolve_use_mmap(no_mmap_arg=True, env={}))

    def test_環境変数で1ならuse_mmap_False(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertFalse(_resolve_use_mmap(
            no_mmap_arg=False, env={"GREP_HELPER_NO_MMAP": "1"},
        ))

    def test_環境変数で0ならuse_mmap_True(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertTrue(_resolve_use_mmap(
            no_mmap_arg=False, env={"GREP_HELPER_NO_MMAP": "0"},
        ))

    def test_フラグ優先(self):
        from grep_helper.dispatcher import _resolve_use_mmap
        self.assertFalse(_resolve_use_mmap(
            no_mmap_arg=True, env={"GREP_HELPER_NO_MMAP": "0"},
        ))

    def test_argparseで_no_mmapフラグが解釈される(self):
        from grep_helper.dispatcher import build_parser
        parser = build_parser()
        args = parser.parse_args(["--source-dir", "/tmp", "--no-mmap"])
        self.assertTrue(getattr(args, "no_mmap", False))

        args2 = parser.parse_args(["--source-dir", "/tmp"])
        self.assertFalse(getattr(args2, "no_mmap", False))


if __name__ == "__main__":
    unittest.main()
