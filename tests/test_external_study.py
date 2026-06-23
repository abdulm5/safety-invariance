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

    def test_native_smoke_covers_benign_and_injection_paths(self) -> None:
        study = load_external_study(ROOT / "configs" / "external_native_smoke_24gb.json")
        self.assertEqual(
            {benchmark.config.get("attack") for benchmark in study.benchmarks},
            {None, "direct", "tool_knowledge"},
        )
        self.assertEqual(len(external_study_plan(study)["runs"]), 6)

    def test_remaining_suites_extension_inherits_frozen_profiles(self) -> None:
        study = load_external_study(
            ROOT / "configs" / "external_agentdojo_remaining_suites_extension_48gb.json"
        )
        frozen = load_external_study(STUDY_PATH)
        self.assertEqual(study.profiles, frozen.profiles)
        self.assertEqual(len(study.benchmarks), 3)
        self.assertEqual(len(external_study_plan(study)["runs"]), 36)
        self.assertEqual(
            {suite for benchmark in study.benchmarks for suite in benchmark.config["suites"]},
            {"travel", "slack"},
        )
        self.assertEqual(study.metadata["agentdojo_revision"], frozen.metadata["agentdojo_revision"])
        self.assertEqual(study.metadata["protocol_status"], "prospective_extension_2026_06_21")


if __name__ == "__main__":
    unittest.main()
