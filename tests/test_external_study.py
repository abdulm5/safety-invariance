from __future__ import annotations

import unittest
from pathlib import Path

from safety_invariance.external_study import external_study_plan, load_external_study, validate_external_study


ROOT = Path(__file__).resolve().parents[1]
STUDY_PATH = ROOT / "configs" / "external_confirmation_matrix_24gb.json"


class ExternalStudyTests(unittest.TestCase):
    def test_frozen_confirmation_study_is_valid(self) -> None:
        study = load_external_study(STUDY_PATH)
        validation = validate_external_study(study)
        self.assertEqual(validation["errors"], [])
        self.assertEqual(len(study.profiles), 12)
        self.assertEqual(len(study.benchmarks), 5)

    def test_plan_uses_native_openai_compatible_adapters(self) -> None:
        study = load_external_study(STUDY_PATH)
        plan = external_study_plan(study)
        self.assertEqual(plan["run_count"], 60)
        dojo = next(run for run in plan["runs"] if run["kind"] == "agentdojo")
        harm = next(run for run in plan["runs"] if run["kind"] == "agentharm")
        self.assertIn("VLLM_PARSED", dojo["command"])
        self.assertIn("--model-id", dojo["command"])
        self.assertIn("openai-api/si/", " ".join(harm["command"]))


if __name__ == "__main__":
    unittest.main()
