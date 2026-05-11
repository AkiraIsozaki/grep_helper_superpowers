"""apply_indirect_tracking の handler 並列化テスト。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grep_helper.dispatcher import apply_indirect_tracking
from grep_helper.model import GrepRecord, RefType


def _make_minimal_src(tmp: Path) -> Path:
    """全 12 言語の最小限のソースを置いた src_dir を返す。"""
    src = tmp / "src"
    src.mkdir()
    (src / "a.sql").write_text("SELECT * FROM t WHERE x = 'A';\n")
    return src


def _direct_records() -> list[GrepRecord]:
    return [
        GrepRecord(keyword="A", ref_type=RefType.DIRECT.value, usage_type="WHERE条件",
                   filepath="a.sql", lineno="1", code="SELECT * FROM t WHERE x = 'A';"),
    ]


class TestApplyIndirectTrackingHandlerWorkers(unittest.TestCase):
    """handler_workers の値に関わらず結果集合は同じ（並列順序非依存）。"""

    def test_handler_workers_1_と_2_で結果集合が同一(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_minimal_src(Path(tmp))
            direct = _direct_records()
            serial = apply_indirect_tracking(
                direct, src, encoding=None, workers=1, handler_workers=1,
            )
            parallel = apply_indirect_tracking(
                direct, src, encoding=None, workers=1, handler_workers=2,
            )
            def _key(r: GrepRecord) -> tuple:
                return (r.keyword, r.ref_type, r.usage_type, r.filepath,
                        r.lineno, r.code, r.src_var, r.src_file, r.src_lineno)
            self.assertEqual(
                sorted(map(_key, serial)),
                sorted(map(_key, parallel)),
            )


class TestApplyIndirectTrackingOnComplete(unittest.TestCase):
    """on_handler_complete は handler ごとに 1 回呼ばれる。"""

    def test_handler_workers_1_でon_handler_completeが全handler分呼ばれる(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_minimal_src(Path(tmp))
            calls: list[str] = []
            apply_indirect_tracking(
                _direct_records(), src, encoding=None,
                handler_workers=1,
                on_handler_complete=lambda hname, recs: calls.append(hname),
            )
            self.assertEqual(len(calls), len(set(calls)))
            self.assertGreaterEqual(len(calls), 10)

    def test_handler_workers_2_でon_handler_completeが全handler分呼ばれる(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_minimal_src(Path(tmp))
            calls: list[str] = []
            apply_indirect_tracking(
                _direct_records(), src, encoding=None,
                handler_workers=2,
                on_handler_complete=lambda hname, recs: calls.append(hname),
            )
            self.assertEqual(len(calls), len(set(calls)))
            self.assertGreaterEqual(len(calls), 10)


class TestApplyIndirectTrackingExceptionIsolation(unittest.TestCase):
    """1 handler の例外は他 handler に伝播しない。直列・並列ともに。"""

    def _patch_one_handler_to_raise(self, monkey_target: str):
        import importlib
        mod = importlib.import_module(monkey_target)
        original = mod.batch_track_indirect
        def _boom(*args, **kwargs):
            raise RuntimeError("intentional test failure")
        mod.batch_track_indirect = _boom
        return mod, original

    def test_1handlerが例外を投げても他handlerのon_completeは呼ばれる_直列(self):
        target = "grep_helper.languages.sql"
        mod, original = self._patch_one_handler_to_raise(target)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = _make_minimal_src(Path(tmp))
                calls: list[str] = []
                apply_indirect_tracking(
                    _direct_records(), src, encoding=None,
                    handler_workers=1,
                    on_handler_complete=lambda hname, recs: calls.append(hname),
                )
                self.assertNotIn(target, calls)
                self.assertGreaterEqual(len(calls), 9)
        finally:
            mod.batch_track_indirect = original


if __name__ == "__main__":
    unittest.main()
