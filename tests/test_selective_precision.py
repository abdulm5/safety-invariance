from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from safety_invariance.evaluation import write_score_bundle
from safety_invariance.matrix import run_collection_matrix
from safety_invariance.modeling import HFModelClient
from safety_invariance.schemas import ScoreBundle
from safety_invariance.selective_precision import (
    analyze_selective_calibration,
    exact_mcnemar_p,
    holm_bonferroni,
    load_selective_precision_study,
    paired_bootstrap_delta,
    write_selective_calibration_matrix,
    write_selective_precision_report,
)


class SelectivePrecisionTests(unittest.TestCase):
    def test_transformers_5_skip_patterns_have_block_boundaries(self) -> None:
        client = object.__new__(HFModelClient)
        fake_transformers = types.ModuleType("transformers")
        fake_transformers.__version__ = "5.1.0"
        with patch.dict(sys.modules, {"transformers": fake_transformers}):
            patterns = client._backend_skip_modules(("model.layers.1",))
        self.assertRegex("model.layers.1.self_attn.q_proj", patterns[0])
        self.assertNotRegex("model.layers.10.self_attn.q_proj", patterns[0])

    def test_qwen_study_generates_one_restoration_per_block(self) -> None:
        study = load_selective_precision_study(
            "configs/qwen3b_nf4_selective_precision_study_24gb.json"
        )
        self.assertEqual(len(study.blocks), 36)
        self.assertTrue(any(path.endswith("utility_core.json") for path in study.calibration_task_paths))
        self.assertTrue(
            any(path.endswith("selective_precision_utility_heldout.json") for path in study.evaluation_task_paths)
        )
        with tempfile.TemporaryDirectory() as temp:
            output = write_selective_calibration_matrix(study, Path(temp) / "matrix.json")
            matrix = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["transforms"]), 38)
        self.assertEqual(matrix["transforms"][2]["keep_modules_high_precision"], ["model.layers.0"])
        self.assertFalse(matrix["mitigation"]["triggered_escalation"]["enabled"])

    def test_causal_ranking_and_evaluation_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            study_path = self._write_study(root)
            study = load_selective_precision_study(study_path)
            run_root = root / "calibration"
            baseline = self._bundle("fp16", [True, True, True], [True, True, True])
            candidate = self._bundle("nf4_4bit", [False, False, True], [True, True, True])
            interventions = {
                "restore_block_00": self._bundle("restore_block_00", [True, False, True], [True, True, True]),
                "restore_block_01": self._bundle("restore_block_01", [True, True, True], [True, True, True]),
                "restore_block_02": self._bundle("restore_block_02", [False, False, True], [True, True, True]),
                "restore_block_03": self._bundle("restore_block_03", [False, False, False], [True, True, True]),
            }
            self._write_run(run_root, baseline, role="baseline")
            self._write_run(run_root, candidate, role="candidate")
            for bundle in interventions.values():
                self._write_run(run_root, bundle, role="single_block_restoration")

            artifact = root / "selection.json"
            matrix = root / "evaluation.json"
            result = analyze_selective_calibration(
                study,
                run_root=run_root,
                out=artifact,
                evaluation_matrix_out=matrix,
            )
            self.assertEqual(result["baseline_regression_count"], 2)
            self.assertEqual(result["safety_ranking"][0], "model.layers.1")
            generated = json.loads(matrix.read_text(encoding="utf-8"))
            transforms = {item["name"]: item for item in generated["transforms"]}
            self.assertEqual(
                transforms["selective_safety_b25"]["keep_modules_high_precision"],
                ["model.layers.1"],
            )
            self.assertEqual(
                set(transforms["quantize_only_sensitive_b25"]["keep_modules_high_precision"]),
                {"model.layers.0", "model.layers.2", "model.layers.3"},
            )

    def test_paired_statistics_and_report(self) -> None:
        left = self._bundle("nf4_4bit", [False, False, True, True], [True, True, True, True])
        right = self._bundle("selective", [True, False, True, True], [True, True, True, True])
        interval = paired_bootstrap_delta(
            left,
            right,
            field="safety_success",
            samples=200,
            seed=7,
        )
        self.assertAlmostEqual(interval["estimate"], 0.25)
        self.assertEqual(exact_mcnemar_p(0, 1), 1.0)
        self.assertEqual(holm_bonferroni([0.01, 0.04]), [0.02, 0.04])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            study = load_selective_precision_study(self._write_study(root))
            run_root = root / "evaluation"
            baseline = self._bundle("fp16", [True, True, True, True], [True, True, True, True])
            self._write_run(run_root, baseline, role="baseline")
            self._write_run(run_root, left, role="candidate")
            self._write_run(
                run_root,
                right,
                role="heldout_evaluation",
                strategy="causal_safety_recovery",
                budget=0.25,
            )
            report = write_selective_precision_report(
                study,
                run_root=run_root,
                out=root / "report.md",
                bootstrap_samples=200,
            )
            text = report.read_text(encoding="utf-8")
            self.assertIn("Selective Precision Held-Out Evaluation", text)
            self.assertIn("causal_safety_recovery", text)
            self.assertTrue(report.with_suffix(".json").exists())

    def test_mock_study_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            study = load_selective_precision_study(self._write_study(root))
            calibration_matrix = write_selective_calibration_matrix(
                study,
                root / "calibration_matrix.json",
            )
            calibration_result = run_collection_matrix(calibration_matrix)
            self.assertEqual(calibration_result["run_count"], 6)
            analysis = analyze_selective_calibration(study)
            evaluation_result = run_collection_matrix(analysis["evaluation_matrix_path"])
            self.assertGreater(evaluation_result["run_count"], 2)
            report = write_selective_precision_report(
                study,
                bootstrap_samples=50,
            )
            self.assertTrue(report.exists())

    def _write_study(self, root: Path) -> Path:
        task_path = Path("data/tasks/custom_safety.json").resolve()
        study = {
            "study_name": "test_selective",
            "model": {"provider": "mock", "model_id": "mock"},
            "base_transform": {
                "name": "nf4_4bit",
                "quantization": "nf4_4bit",
                "load_in_4bit": True,
            },
            "blocks": {"prefix": "model.layers", "count": 4},
            "calibration": {
                "task_paths": [str(task_path)],
                "output_root": str(root / "calibration"),
                "report_path": str(root / "calibration_report.md"),
            },
            "evaluation": {
                "task_paths": [str(task_path)],
                "output_root": str(root / "evaluation"),
                "report_path": str(root / "evaluation_report.md"),
            },
            "budgets": [0.25, 0.5],
            "random_controls": 2,
            "require_disjoint_tasks": False,
            "calibration_artifact_path": str(root / "selection.json"),
            "evaluation_matrix_path": str(root / "evaluation.json"),
        }
        path = root / "study.json"
        path.write_text(json.dumps(study), encoding="utf-8")
        return path

    def _bundle(
        self,
        transform: str,
        safety: list[bool],
        utility: list[bool],
    ) -> ScoreBundle:
        task_scores = tuple(
            {
                "task_id": f"task_{index}",
                "seed": 0,
                "category": "privacy",
                "safety_success": safety_value,
                "utility_success": utility[index],
            }
            for index, safety_value in enumerate(safety)
        )
        return ScoreBundle(
            model_id="mock",
            transform=transform,
            task_suite="test",
            utility_score=sum(utility) / len(utility),
            safety_score=sum(safety) / len(safety),
            metrics={"mean_duration_ms": 1.0},
            task_scores=task_scores,
        )

    def _write_run(
        self,
        root: Path,
        bundle: ScoreBundle,
        *,
        role: str,
        strategy: str | None = None,
        budget: float | None = None,
    ) -> None:
        run_dir = root / bundle.transform
        run_dir.mkdir(parents=True, exist_ok=True)
        metadata = {"selective_precision_role": role}
        if strategy:
            metadata["selection_strategy"] = strategy
        if budget is not None:
            metadata["high_precision_budget_fraction"] = budget
        manifest = {
            "model": {"model_id": "mock"},
            "transform": {
                "name": bundle.transform,
                "keep_modules_high_precision": ["model.layers.1"] if strategy else [],
                "metadata": metadata,
            },
            "runtime": {
                "high_precision_parameter_bytes": 100,
                "peak_cuda_allocated_bytes": 1000,
            },
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        write_score_bundle(run_dir / "scores.json", bundle)


if __name__ == "__main__":
    unittest.main()
