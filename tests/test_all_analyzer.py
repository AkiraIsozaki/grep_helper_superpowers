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


if __name__ == "__main__":
    unittest.main()
