from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from safety_invariance.cli import run_smoke


class SmokeTests(unittest.TestCase):
    def test_smoke_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "smoke"
            run_smoke(out)
            for run_name in ("fp16", "nf4_4bit"):
                run_dir = out / run_name
                self.assertTrue((run_dir / "manifest.json").exists())
                self.assertTrue((run_dir / "events.jsonl").exists())
                self.assertTrue((run_dir / "scores.json").exists())
                self.assertTrue((run_dir / "summary.csv").exists())

            baseline = json.loads((out / "fp16" / "scores.json").read_text(encoding="utf-8"))
            transformed = json.loads((out / "nf4_4bit" / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(baseline["retention"]["utility_retention"], 1.0)
            self.assertIn("safety_utility_gap", transformed["retention"])
            self.assertTrue((out / "summary.md").exists())


if __name__ == "__main__":
    unittest.main()
