from __future__ import annotations

import json
import math
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from safety_invariance.agent import run_task
from safety_invariance.evaluation import score_trace, write_score_bundle
from safety_invariance.matrix import expand_matrix, load_collection_matrix, run_collection_matrix
from safety_invariance.modeling import HFModelClient, MockModelClient
from safety_invariance.margin_calibration import collect_action_margins
from safety_invariance.schemas import ModelSpec, ScoreBundle, TransformSpec
from safety_invariance.selective_precision import (
    analyze_selective_calibration,
    apply_action_margin_scores,
    bootstrap_selected_minus_random_mean,
    empirical_randomization_p,
    exact_mcnemar_p,
    holm_bonferroni,
    load_selective_precision_study,
    paired_bootstrap_delta,
    fidelity_margin_recovery,
    write_selective_calibration_matrix,
    write_selective_precision_report,
    safety_margin_recovery,
    summarize_random_controls,
    write_selective_evaluation_matrix,
)
from safety_invariance.tasks import load_task_file, validate_tasks


class SelectivePrecisionTests(unittest.TestCase):
    def test_nf4_selective_precision_uses_post_load_restoration(self) -> None:
        client = object.__new__(HFModelClient)
        client.transform = TransformSpec(
            name="selective_nf4",
            quantization="nf4_4bit",
            load_in_4bit=True,
            keep_modules_high_precision=("model.layers.1",),
        )
        client.compatibility = {}
        self.assertTrue(client._uses_post_load_restoration())
        self.assertEqual(
            client.compatibility["selective_precision_backend"],
            "post_load_replacement",
        )

    def test_nf4_selective_precision_can_request_legacy_skip_backend(self) -> None:
        client = object.__new__(HFModelClient)
        client.transform = TransformSpec(
            name="selective_nf4",
            quantization="nf4_4bit",
            load_in_4bit=True,
            keep_modules_high_precision=("model.layers.1",),
            metadata={"selective_precision_backend": "skip_modules"},
        )
        client.compatibility = {}
        self.assertFalse(client._uses_post_load_restoration())

    def test_int8_selective_precision_uses_post_load_restoration(self) -> None:
        client = object.__new__(HFModelClient)
        client.transform = TransformSpec(
            name="selective_int8",
            quantization="int8",
            load_in_8bit=True,
            keep_modules_high_precision=("model.layers.1",),
        )
        client.compatibility = {}
        self.assertTrue(client._uses_post_load_restoration())
        self.assertEqual(
            client.compatibility["selective_precision_backend"],
            "post_load_replacement",
        )

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
        self.assertEqual(study.ranking_method, "action_margin")
        self.assertEqual(len(study.action_probes), 23)
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

    def test_expanded_study_inherits_probes_and_powers_heldout_design(self) -> None:
        study = load_selective_precision_study(
            "configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json"
        )
        self.assertEqual(study.random_controls, 100)
        self.assertEqual(len(study.action_probes), 23)
        self.assertEqual(len(study.evaluation_task_paths), 7)
        self.assertTrue(
            any(
                path.endswith("selective_precision_safety_heldout_expanded.json")
                for path in study.evaluation_task_paths
            )
        )
        _, expanded_tasks = load_task_file(
            "data/tasks/selective_precision_safety_heldout_expanded.json"
        )
        self.assertEqual(len(expanded_tasks), 48)
        self.assertEqual(validate_tasks(expanded_tasks), [])

        selections = {}
        for budget in study.budgets:
            count = max(1, math.ceil(budget * len(study.blocks)))
            label = f"b{round(budget * 100):02d}"
            selections[label] = {
                "budget_fraction": count / len(study.blocks),
                "block_count": count,
                "safety_selected": list(study.blocks[:count]),
                "utility_selected": list(study.blocks[-count:]),
                "first_blocks": list(study.blocks[:count]),
                "last_blocks": list(study.blocks[-count:]),
            }
        with tempfile.TemporaryDirectory() as temp:
            matrix_path = write_selective_evaluation_matrix(
                study,
                {"selections": selections},
                Path(temp) / "expanded_matrix.json",
            )
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["transforms"]), 422)
        self.assertEqual(
            sum(
                transform.get("metadata", {}).get("selection_strategy") == "random_blocks"
                for transform in matrix["transforms"]
            ),
            400,
        )

    def test_expanded_heldout_tasks_separate_safe_and_drifted_mock_profiles(self) -> None:
        _, tasks = load_task_file(
            "data/tasks/selective_precision_safety_heldout_expanded.json"
        )
        for profile, expected_safety in (("safe", True), ("drifted", False)):
            model = MockModelClient(
                ModelSpec(metadata={"mock_profile": profile}),
                TransformSpec(name=profile),
            )
            observed = []
            for task in tasks:
                trace = run_task(
                    task,
                    model,
                    max_new_tokens=64,
                    temperature=0.0,
                    seed=0,
                )
                _, safety_success, _ = score_trace(task, trace)
                observed.append(safety_success)
            self.assertEqual(observed, [expected_safety] * len(tasks))

    def test_b20_replication_studies_generate_focused_matrices(self) -> None:
        cases = (
            (
                "configs/llama31_8b_nf4_selective_b20_replication_24gb.json",
                32,
                "nf4_4bit",
            ),
            (
                "configs/qwen3b_int8_selective_b20_replication_24gb.json",
                36,
                "int8",
            ),
        )
        for path, block_count, candidate_transform in cases:
            with self.subTest(path=path):
                study = load_selective_precision_study(path)
                self.assertEqual(len(study.blocks), block_count)
                self.assertEqual(study.budgets, (0.2,))
                self.assertEqual(study.random_controls, 100)
                self.assertEqual(study.base_transform["name"], candidate_transform)
                if candidate_transform == "int8":
                    self.assertTrue(study.base_transform["load_in_8bit"])
                    self.assertFalse(study.base_transform["load_in_4bit"])
                count = math.ceil(0.2 * block_count)
                selection = {
                    "selections": {
                        "b20": {
                            "budget_fraction": count / block_count,
                            "block_count": count,
                            "safety_selected": list(study.blocks[:count]),
                            "utility_selected": list(study.blocks[-count:]),
                            "first_blocks": list(study.blocks[:count]),
                            "last_blocks": list(study.blocks[-count:]),
                        }
                    }
                }
                with tempfile.TemporaryDirectory() as temp:
                    matrix_path = write_selective_evaluation_matrix(
                        study,
                        selection,
                        Path(temp) / "matrix.json",
                    )
                    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
                self.assertEqual(len(matrix["transforms"]), 107)
                self.assertEqual(matrix["transforms"][1]["name"], candidate_transform)
                self.assertEqual(
                    sum(
                        transform.get("metadata", {}).get("selection_strategy")
                        == "random_blocks"
                        for transform in matrix["transforms"]
                    ),
                    100,
                )

        smoke = load_collection_matrix("configs/qwen3b_int8_selective_smoke_24gb.json")
        smoke_runs = expand_matrix(smoke)
        self.assertEqual(len(smoke_runs), 3)
        self.assertEqual(
            smoke_runs[2].transform.keep_modules_high_precision,
            ("model.layers.17",),
        )

    def test_action_margin_recovery_scores_dense_interventions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            study = load_selective_precision_study(self._write_study(Path(temp)))
        study = replace(study, ranking_method="action_margin", utility_penalty=0.5)
        block_results = [
            {
                "block": "model.layers.0",
                "transform": "restore_block_00",
                "high_precision_cost_bytes": 1024**3,
                "safety_score_gain": 0.0,
                "utility_score_gain": 0.0,
            },
            {
                "block": "model.layers.1",
                "transform": "restore_block_01",
                "high_precision_cost_bytes": 1024**3,
                "safety_score_gain": 0.0,
                "utility_score_gain": 0.0,
            },
        ]
        margins = {
            "transforms": {
                "fp16": {
                    "tasks": {
                        "safe": {"probe_kind": "safety", "preference_margin": 2.0},
                        "utility": {"probe_kind": "utility", "preference_margin": 1.0},
                    }
                },
                "nf4_4bit": {
                    "tasks": {
                        "safe": {"probe_kind": "safety", "preference_margin": 0.0},
                        "utility": {"probe_kind": "utility", "preference_margin": 0.8},
                    }
                },
                "restore_block_00": {
                    "tasks": {
                        "safe": {"probe_kind": "safety", "preference_margin": 2.0},
                        "utility": {"probe_kind": "utility", "preference_margin": 0.0},
                    }
                },
                "restore_block_01": {
                    "tasks": {
                        "safe": {"probe_kind": "safety", "preference_margin": 0.5},
                        "utility": {"probe_kind": "utility", "preference_margin": 1.0},
                    }
                },
            }
        }
        scored = apply_action_margin_scores(
            study,
            margins,
            block_results,
            baseline_scores={
                ("safe", 0): {"safety_success": True, "category": "privacy"},
                ("utility", 0): {"safety_success": True, "category": "utility"},
            },
        )
        self.assertAlmostEqual(scored[0]["safety_margin_recovery"], 1.0)
        self.assertAlmostEqual(scored[0]["utility_margin_damage"], 1.0)
        self.assertGreater(scored[0]["action_margin_objective"], scored[1]["action_margin_objective"])
        self.assertAlmostEqual(safety_margin_recovery(2.0, 0.0, 2.0, epsilon=0.05), 1.0)
        self.assertAlmostEqual(fidelity_margin_recovery(1.0, 0.8, 1.0, epsilon=0.05), 1.0)

    def test_margin_collection_is_complete_and_resumable_with_fake_model(self) -> None:
        class FakeMarginModel:
            def preference_margin(self, prompt, *, preferred_completion, dispreferred_completion):
                del prompt
                preferred = -float(len(preferred_completion)) / 100
                dispreferred = -float(len(dispreferred_completion)) / 100
                return {
                    "preferred_log_likelihood": preferred,
                    "dispreferred_log_likelihood": dispreferred,
                    "preference_margin": preferred - dispreferred,
                }

            def get_runtime_metadata(self):
                return {"backend": "fake"}

        study = load_selective_precision_study(
            "configs/qwen3b_nf4_selective_precision_study_24gb.json"
        )
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "margins.json"
            with patch(
                "safety_invariance.margin_calibration.load_model_client",
                return_value=FakeMarginModel(),
            ) as loader:
                payload = collect_action_margins(study, out=output)
                resumed = collect_action_margins(study, out=output)
            self.assertTrue(payload["complete"])
            self.assertEqual(len(payload["completed_transforms"]), 38)
            self.assertEqual(payload["probe_count"], 23)
            self.assertEqual(loader.call_count, 38)
            self.assertEqual(resumed["fingerprint"], payload["fingerprint"])

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

    def test_action_margin_analyzer_generates_new_selected_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            study = load_selective_precision_study(self._write_study(root))
            margin_path = root / "margins.json"
            study = replace(
                study,
                ranking_method="action_margin",
                margin_artifact_path=str(margin_path),
            )
            run_root = root / "calibration"
            bundles = {
                "fp16": self._bundle("fp16", [True, True, True], [True, True, True]),
                "nf4_4bit": self._bundle("nf4_4bit", [False, False, True], [True, True, True]),
                "restore_block_00": self._bundle("restore_block_00", [True, False, True], [True, True, True]),
                "restore_block_01": self._bundle("restore_block_01", [True, True, True], [True, True, True]),
                "restore_block_02": self._bundle("restore_block_02", [False, False, True], [True, True, True]),
                "restore_block_03": self._bundle("restore_block_03", [False, False, False], [True, True, True]),
            }
            for bundle in bundles.values():
                self._write_run(run_root, bundle, role="calibration")
            margins = {"complete": True, "transforms": {}}
            transform_margins = {
                "fp16": 2.0,
                "nf4_4bit": 0.0,
                "restore_block_00": 1.0,
                "restore_block_01": 2.0,
                "restore_block_02": 0.0,
                "restore_block_03": -1.0,
            }
            for transform, margin in transform_margins.items():
                margins["transforms"][transform] = {
                    "tasks": {
                        f"task_{index}": {
                            "probe_kind": "safety",
                            "preference_margin": margin,
                        }
                        for index in range(3)
                    }
                }
            margin_path.write_text(json.dumps(margins), encoding="utf-8")
            matrix_path = root / "margin_evaluation.json"
            result = analyze_selective_calibration(
                study,
                run_root=run_root,
                out=root / "selection.json",
                evaluation_matrix_out=matrix_path,
            )
            self.assertEqual(result["ranking_method"], "action_margin")
            self.assertEqual(result["safety_ranking"][0], "model.layers.1")
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            transforms = {item["name"]: item for item in matrix["transforms"]}
            self.assertEqual(
                transforms["selective_margin_safety_b25"]["keep_modules_high_precision"],
                ["model.layers.1"],
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
            random_0 = self._bundle(
                "selective_random_b25_r00",
                [False, False, True, True],
                [True, True, True, True],
            )
            random_1 = self._bundle(
                "selective_random_b25_r01",
                [True, True, True, True],
                [True, True, True, True],
            )
            for random_bundle in (random_0, random_1):
                self._write_run(
                    run_root,
                    random_bundle,
                    role="heldout_control",
                    strategy="random_blocks",
                    budget=0.25,
                )
            stale = self._bundle("stale_binary_variant", [False] * 4, [False] * 4)
            self._write_run(
                run_root,
                stale,
                role="heldout_evaluation",
                strategy="causal_safety_recovery",
                budget=0.25,
            )
            Path(study.evaluation_matrix_path).write_text(
                json.dumps(
                    {
                        "metadata": {"selective_precision_study": study.name},
                        "transforms": [
                            {"name": "fp16"},
                            {"name": "nf4_4bit"},
                            {"name": "selective"},
                            {"name": "selective_random_b25_r00"},
                            {"name": "selective_random_b25_r01"},
                        ],
                    }
                ),
                encoding="utf-8",
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
            self.assertIn("2 safe-to-unsafe regression(s)", text)
            self.assertIn("2 total safety flip(s)", text)
            self.assertIn("Safety Selection Versus Random Controls", text)
            self.assertIn("net regression reduction", text)
            self.assertIn("Excluded 1 stale completed transform", text)
            self.assertNotIn("stale_binary_variant", text)
            self.assertNotIn("selective_random_b25_r00", text)
            self.assertTrue(report.with_suffix(".json").exists())
            payload = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(payload["excluded_transforms"], ["stale_binary_variant"])
            self.assertEqual(
                {row["transform"] for row in payload["rows"]},
                {
                    "nf4_4bit",
                    "selective",
                    "selective_random_b25_r00",
                    "selective_random_b25_r01",
                },
            )
            self.assertEqual(len(payload["random_control_summary"]), 1)
            rows_by_transform = {row["transform"]: row for row in payload["rows"]}
            self.assertIsNotNone(
                rows_by_transform["selective"]["mcnemar_p_holm_vs_quantized"]
            )
            self.assertIsNone(
                rows_by_transform["selective_random_b25_r00"][
                    "mcnemar_p_holm_vs_quantized"
                ]
            )

    def test_random_control_summary_compares_equal_budgets(self) -> None:
        rows = [
            {
                "transform": "selected",
                "strategy": "action_margin_causal_recovery",
                "budget": 0.1,
                "safety": 0.8,
                "utility": 0.9,
                "net_safety_regression_reduction": 2,
            },
            {
                "transform": "random_0",
                "strategy": "random_blocks",
                "budget": 0.1,
                "safety": 0.6,
                "utility": 0.8,
                "net_safety_regression_reduction": 0,
            },
            {
                "transform": "random_1",
                "strategy": "random_blocks",
                "budget": 0.1,
                "safety": 0.7,
                "utility": 1.0,
                "net_safety_regression_reduction": 1,
            },
        ]
        summary = summarize_random_controls(rows)
        self.assertEqual(len(summary), 1)
        self.assertAlmostEqual(summary[0]["random_mean_safety"], 0.65)
        self.assertAlmostEqual(summary[0]["selected_minus_random_mean_safety"], 0.15)
        self.assertEqual(summary[0]["selected_safety_percentile"], 1.0)
        self.assertEqual(summary[0]["selected_net_reduction_rank"], 1)
        self.assertAlmostEqual(
            summary[0]["selected_minus_random_mean_net_safety_regression_reduction"],
            1.5,
        )
        self.assertAlmostEqual(
            summary[0]["empirical_randomization_p_one_sided_net_regression_reduction"],
            1 / 3,
        )
        self.assertAlmostEqual(
            summary[0]["empirical_randomization_p_holm_net_regression_reduction"],
            1 / 3,
        )
        self.assertAlmostEqual(empirical_randomization_p(0.8, [0.6, 0.7]), 1 / 3)
        interval = bootstrap_selected_minus_random_mean(
            0.8,
            [0.6, 0.7],
            samples=100,
            seed=9,
        )
        self.assertAlmostEqual(interval["estimate"], 0.15)

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
            "ranking_method": "binary_flip",
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
