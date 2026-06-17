from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from safety_invariance.diagnostics import render_diagnostic_report, write_diagnostic_report
from safety_invariance.evaluation import write_score_bundle
from safety_invariance.schemas import ScoreBundle


class DiagnosticTests(unittest.TestCase):
    def test_render_diagnostic_report_counts_baseline_flips(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "fp16").mkdir()
            (root / "nf4").mkdir()
            write_score_bundle(
                root / "fp16" / "scores.json",
                ScoreBundle(
                    model_id="mock",
                    transform="fp16",
                    task_suite="suite",
                    utility_score=1.0,
                    safety_score=1.0,
                    metrics={"privacy_leak_rate": 0.0},
                    task_scores=(
                        {
                            "task_id": "privacy",
                            "seed": 0,
                            "category": "privacy",
                            "utility_success": True,
                            "safety_success": True,
                        },
                    ),
                    retention={"utility_retention": 1.0, "safety_retention": 1.0, "safety_utility_gap": 0.0},
                ),
            )
            write_score_bundle(
                root / "nf4" / "scores.json",
                ScoreBundle(
                    model_id="mock",
                    transform="nf4_4bit",
                    task_suite="suite",
                    utility_score=1.0,
                    safety_score=0.0,
                    metrics={"privacy_leak_rate": 1.0},
                    task_scores=(
                        {
                            "task_id": "privacy",
                            "seed": 0,
                            "category": "privacy",
                            "utility_success": True,
                            "safety_success": False,
                            "private_leak": True,
                        },
                    ),
                    retention={"utility_retention": 1.0, "safety_retention": 0.0, "safety_utility_gap": 1.0},
                ),
            )

            report = render_diagnostic_report(str(root / "*"))

        self.assertIn("Safety Regressions", report)
        self.assertIn("|mock|nf4_4bit|1.000|0.000|1.000|0.000|1.000|1|0|0|0|", report)
        self.assertIn("privacy", report)
        self.assertIn("private_leak", report)

    def test_write_diagnostic_report_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = write_diagnostic_report(str(root / "missing" / "*"), root / "reports" / "diag.md")
            self.assertTrue(output.exists())
            self.assertIn("No score files matched", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
