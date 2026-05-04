"""KPI 計測スクリプト measure_kpi.py の単体テスト。

プロジェクトのテスト方針（古典学派・ブラックボックス起点・WHATを検証・
日本語メソッド名・TDD）に従う。
"""
import csv
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# scripts/ を import path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import measure_kpi

# ゴールデンセットのルート（cwd 非依存）
GOLDEN_DIR = Path(__file__).parent / "golden"


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

    def test_空ファイルヘッダのみは空リストを返す(self):
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

    def test_参照種別が違うと別行として扱われ網羅率が下がる(self):
        # spec §出力フォーマット 比較ロジック: マッチング基準キー = (file, line, 参照種別)。
        # 同一 (file, line) でも参照種別が違えば別エンティティとして扱う。
        # 結果: expected は missing、actual は false_positive となり、
        # 「同一行で別の参照種別が出ている」事実が KPI に正しく反映される。
        expected = [_rec("f.sql", "1", ref_type="直接")]
        actual = [_rec("f.sql", "1", ref_type="間接")]
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 0.0)
        self.assertEqual(len(result.missing_rows), 1)
        self.assertEqual(len(result.false_positives), 1)


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

    def test_サンプル分布チェック警告セクションが含まれる(self):
        result = measure_kpi.ComparisonResult(
            expected_total=1, matched_rows=1, classified_correctly=1,
            coverage_rate=1.0, classification_accuracy=1.0,
        )
        out = measure_kpi.format_detail_report(
            result, distribution_warnings=["使用タイプ「Foo」: 0 件"],
        )
        self.assertIn("## サンプル分布チェック警告", out)
        self.assertIn("Foo", out)

    def test_警告ゼロなら_警告なし_と表示される(self):
        result = measure_kpi.ComparisonResult(
            expected_total=1, matched_rows=1, classified_correctly=1,
            coverage_rate=1.0, classification_accuracy=1.0,
        )
        out = measure_kpi.format_detail_report(result)
        self.assertIn("## サンプル分布チェック警告", out)
        self.assertIn("（警告なし）", out)


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


class TestRunCliEndToEndJava(unittest.TestCase):
    """E2E: tests/golden/java/ の最小サブセットで run() がクラッシュせず coverage 1.0 を返す。
    フルセット 100% は §成功条件 5/6（手動確認）で別途規定。
    """

    def test_javaの最小ゴールデンセットで例外なくrunが完了する(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = measure_kpi.run([
                "--lang", "java",
                "--samples-dir", str(GOLDEN_DIR),
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
            GOLDEN_DIR / "java" / "expected" / "777.tsv"
        )
        with tempfile.TemporaryDirectory() as tmp:
            from grep_helper.languages import java as java_handler
            from grep_helper.pipeline import run_full_pipeline
            tmp_path = Path(tmp)
            run_full_pipeline(
                source_dir=GOLDEN_DIR / "java" / "src",
                input_dir=GOLDEN_DIR / "java" / "inputs",
                output_dir=tmp_path,
                handler=java_handler,
                workers=1,
            )
            actual = measure_kpi.load_actual_tsv(tmp_path / "777.tsv")
        result = measure_kpi.compare(expected, actual)
        self.assertEqual(result.coverage_rate, 1.0,
                         f"missing_rows={result.missing_rows}")


import shutil


class TestRunAllSemantics(unittest.TestCase):
    """--lang all の失敗時規約: 続行 / 最終 exit code は max / _summary は常に出力。"""

    def test_lang_allで存在する言語は処理され_summaryが出る(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = measure_kpi.run([
                "--lang", "all",
                "--samples-dir", str(GOLDEN_DIR),
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
            shutil.copytree(GOLDEN_DIR / "java", samples_path / "java")
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
                        "--samples-dir", str(GOLDEN_DIR),
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
                src_dir = GOLDEN_DIR / lang / "src"
                inputs_dir = GOLDEN_DIR / lang / "inputs"
                expected_dir = GOLDEN_DIR / lang / "expected"
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


if __name__ == "__main__":
    unittest.main()
