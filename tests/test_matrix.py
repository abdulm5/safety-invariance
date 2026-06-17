from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from safety_invariance.benchmark_importers import builtin_suite, write_task_suite
from safety_invariance.matrix import expand_matrix, load_collection_matrix, run_collection_matrix


class MatrixTests(unittest.TestCase):
    def test_mock_matrix_dry_run_writes_plan(self) -> None:
        result = run_collection_matrix("configs/data_collection_matrix_mock.json", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertGreaterEqual(result["run_count"], 4)
        self.assertTrue(Path(result["plan_path"]).exists())

    def test_expand_matrix_has_baseline_per_model(self) -> None:
        matrix = load_collection_matrix("configs/data_collection_matrix_mock.json")
        runs = expand_matrix(matrix)
        self.assertTrue(any(run.transform.name == "fp16" for run in runs))
        self.assertTrue(all(run.task_paths for run in runs))

    def test_qwen3b_signal_replication_matrix_expands(self) -> None:
        matrix = load_collection_matrix("configs/qwen3b_signal_replication_matrix_24gb.json")
        runs = expand_matrix(matrix)
        self.assertEqual(len(runs), 4)
        self.assertEqual(matrix.seeds, (0,))
        self.assertTrue(any(path.endswith("safety_signal_replication.json") for path in matrix.task_paths))

    def test_rigorous_paper_matrix_uses_distinct_prompt_suite(self) -> None:
        matrix = load_collection_matrix("configs/data_collection_matrix_rigorous_paper.json")
        runs = expand_matrix(matrix)
        self.assertEqual(matrix.seeds, (0,))
        self.assertTrue(any(path.endswith("safety_signal_replication.json") for path in matrix.task_paths))
        self.assertTrue(any(run.model.model_id == "google/gemma-2-9b-it" for run in runs))

    def test_qwen3b_mitigation_matrix_contains_triggered_variants(self) -> None:
        matrix = load_collection_matrix("configs/qwen3b_quant_mitigation_matrix_24gb.json")
        runs = expand_matrix(matrix)
        names = {run.transform.name for run in runs}
        self.assertIn("int8_triggered_escalation", names)
        self.assertIn("nf4_4bit_triggered_escalation", names)
        self.assertTrue(any(run.mitigation.get("triggered_escalation", {}).get("rerun_with_safer_profile") for run in runs))

    def test_qwen3b_stochastic_matrix_uses_sampling(self) -> None:
        matrix = load_collection_matrix("configs/qwen3b_stochastic_robustness_matrix_24gb.json")
        runs = expand_matrix(matrix)
        self.assertGreater(matrix.temperature, 0.0)
        self.assertGreater(len(matrix.seeds), 1)
        self.assertEqual(len(runs), 3)

    def test_builtin_suite_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            suite_id, description, tasks = builtin_suite("chat_safety", limit=1)
            out = write_task_suite(Path(temp) / "suite.json", suite_id, description, tasks)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["suite_id"], "chat_safety_v1")
            self.assertEqual(len(payload["tasks"]), 1)


if __name__ == "__main__":
    unittest.main()
