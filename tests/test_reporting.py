from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from safety_invariance.evaluation import write_score_bundle
from safety_invariance.reporting import render_markdown_report, write_markdown_report
from safety_invariance.schemas import ScoreBundle


class ReportingTests(unittest.TestCase):
    def test_render_report_includes_gap_columns(self) -> None:
        bundle = ScoreBundle(
            model_id="mock",
            transform="nf4_4bit",
            task_suite="suite",
            utility_score=0.9,
            safety_score=0.7,
            metrics={"privacy_leak_rate": 0.2},
            retention={"utility_retention": 0.9, "safety_retention": 0.7, "safety_utility_gap": 0.2},
        )
        report = render_markdown_report((bundle,))
        self.assertIn("safety_ret", report)
        self.assertIn("0.200", report)

    def test_write_report_from_run_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "run"
            run_dir.mkdir()
            write_score_bundle(
                run_dir / "scores.json",
                ScoreBundle(
                    model_id="mock",
                    transform="fp16",
                    task_suite="suite",
                    utility_score=1.0,
                    safety_score=1.0,
                    metrics={},
                ),
            )
            out = write_markdown_report(str(root / "*"), root / "report.md")
            self.assertTrue(out.exists())
            self.assertIn("mock", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
