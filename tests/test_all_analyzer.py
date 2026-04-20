# tests/test_all_analyzer.py
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import analyze_all as aa


class TestDetectLanguage(unittest.TestCase):

    def test_java_extension(self):
        self.assertEqual(aa.detect_language("src/Foo.java", Path(".")), "java")

    def test_kotlin_kt(self):
        self.assertEqual(aa.detect_language("src/Foo.kt", Path(".")), "kotlin")

    def test_kotlin_kts(self):
        self.assertEqual(aa.detect_language("src/build.kts", Path(".")), "kotlin")

    def test_c_extension(self):
        self.assertEqual(aa.detect_language("src/util.c", Path(".")), "c")

    def test_header_extension(self):
        self.assertEqual(aa.detect_language("src/util.h", Path(".")), "c")

    def test_proc_pc(self):
        self.assertEqual(aa.detect_language("src/proc.pc", Path(".")), "proc")

    def test_sql_extension(self):
        self.assertEqual(aa.detect_language("src/query.sql", Path(".")), "sql")

    def test_sh_extension(self):
        self.assertEqual(aa.detect_language("src/run.sh", Path(".")), "sh")

    def test_bash_extension(self):
        self.assertEqual(aa.detect_language("src/run.bash", Path(".")), "sh")

    def test_ts_extension(self):
        self.assertEqual(aa.detect_language("src/app.ts", Path(".")), "ts")

    def test_js_extension(self):
        self.assertEqual(aa.detect_language("src/app.js", Path(".")), "ts")

    def test_tsx_extension(self):
        self.assertEqual(aa.detect_language("src/app.tsx", Path(".")), "ts")

    def test_jsx_extension(self):
        self.assertEqual(aa.detect_language("src/app.jsx", Path(".")), "ts")

    def test_python_extension(self):
        self.assertEqual(aa.detect_language("src/util.py", Path(".")), "python")

    def test_perl_pl(self):
        self.assertEqual(aa.detect_language("src/script.pl", Path(".")), "perl")

    def test_perl_pm(self):
        self.assertEqual(aa.detect_language("src/Mod.pm", Path(".")), "perl")

    def test_dotnet_cs(self):
        self.assertEqual(aa.detect_language("src/App.cs", Path(".")), "dotnet")

    def test_dotnet_vb(self):
        self.assertEqual(aa.detect_language("src/App.vb", Path(".")), "dotnet")

    def test_groovy_extension(self):
        self.assertEqual(aa.detect_language("src/Svc.groovy", Path(".")), "groovy")

    def test_groovy_gvy(self):
        self.assertEqual(aa.detect_language("src/Svc.gvy", Path(".")), "groovy")

    def test_plsql_pls(self):
        self.assertEqual(aa.detect_language("src/pkg.pls", Path(".")), "plsql")

    def test_plsql_pck(self):
        self.assertEqual(aa.detect_language("src/pkg.pck", Path(".")), "plsql")

    def test_xml_is_other(self):
        self.assertEqual(aa.detect_language("src/config.xml", Path(".")), "other")

    def test_yaml_is_other(self):
        self.assertEqual(aa.detect_language("src/app.yaml", Path(".")), "other")

    def test_no_extension_perl_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "myscript"
            f.write_text("#!/usr/bin/perl\nprint 1;\n")
            self.assertEqual(aa.detect_language("myscript", src), "perl")

    def test_no_extension_env_perl_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "myscript"
            f.write_text("#!/usr/bin/env perl\nprint 1;\n")
            self.assertEqual(aa.detect_language("myscript", src), "perl")

    def test_no_extension_bash_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/bash\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_sh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/sh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_csh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/csh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_tcsh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/tcsh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_ksh_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/ksh\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_ksh93_shebang(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/bin/ksh93\necho hi\n")
            self.assertEqual(aa.detect_language("run", src), "sh")

    def test_no_extension_unknown_shebang_is_other(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("#!/usr/bin/ruby\nputs 1\n")
            self.assertEqual(aa.detect_language("run", src), "other")

    def test_no_extension_no_shebang_is_other(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            f = src / "run"
            f.write_text("some content\n")
            self.assertEqual(aa.detect_language("run", src), "other")

    def test_no_extension_file_missing_is_other(self):
        self.assertEqual(aa.detect_language("nonexistent_file", Path("/tmp")), "other")


class TestDirectClassification(unittest.TestCase):
    """各言語の行が正しい usage_type に分類されることを確認する。"""

    def _make_direct_records(self, grep_lines: list[str], source_dir: Path) -> list:
        from analyze_common import ProcessStats
        stats = ProcessStats()
        return aa.process_grep_lines_all(grep_lines, "TEST", source_dir, stats, None)

    def test_java_line_classified(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/Foo.java:10:    static final String X = \"TARGET\""],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertIn("定数", records[0].usage_type)
            self.assertEqual(records[0].ref_type, "直接")

    def test_groovy_line_classified(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/Svc.groovy:5:    if (code == TARGET) {{ return }}"],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "条件判定")

    def test_sh_line_classified(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/run.sh:3:TARGET=\"777\""],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "変数代入")

    def test_unknown_extension_is_other(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                [f"{src}/config.xml:1:<value>TARGET</value>"],
                src,
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].usage_type, "その他")
            self.assertEqual(records[0].ref_type, "直接")

    def test_no_extension_perl_shebang_classified(self):
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

    def test_invalid_grep_line_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                ["not a valid grep line"],
                src,
            )
            self.assertEqual(len(records), 0)

    def test_binary_line_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            records = self._make_direct_records(
                ["Binary file src/app.bin matches"],
                src,
            )
            self.assertEqual(len(records), 0)


class TestIndirectTracking(unittest.TestCase):

    def test_groovy_static_final_tracks_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Const.groovy").write_text(
                'static final String STATUS = "TARGET"\n'
            )
            (src / "Service.groovy").write_text(
                'if (s == STATUS) { return }\n'
            )
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="static final定数定義",
                filepath=str(src / "Const.groovy"), lineno="1",
                code='static final String STATUS = "TARGET"',
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("Service.groovy" in r.filepath for r in indirect))

    def test_sh_variable_tracks_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            script = src / "deploy.sh"
            script.write_text('STATUS="TARGET"\necho $STATUS\n')
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="変数代入",
                filepath=str(script), lineno="1",
                code='STATUS="TARGET"',
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("deploy.sh" in r.filepath for r in indirect))
            self.assertTrue(all(r.ref_type == RefType.INDIRECT.value for r in indirect))

    def test_dotnet_const_tracks_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "Consts.cs").write_text('const string STATUS = "TARGET";\n')
            (src / "Service.cs").write_text('if (x == STATUS) { return; }\n')
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="定数定義(Const/readonly)",
                filepath=str(src / "Consts.cs"), lineno="1",
                code='const string STATUS = "TARGET";',
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertTrue(any("Service.cs" in r.filepath for r in indirect))

    def test_other_language_no_indirect(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            from analyze_common import ProcessStats, GrepRecord, RefType
            direct = GrepRecord(
                keyword="TARGET", ref_type=RefType.DIRECT.value,
                usage_type="その他",
                filepath=str(src / "config.xml"), lineno="1",
                code="<value>TARGET</value>",
            )
            stats = ProcessStats()
            indirect = aa._apply_indirect_tracking([direct], src, stats, None)
            self.assertEqual(indirect, [])


if __name__ == "__main__":
    unittest.main()
