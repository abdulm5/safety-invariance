from __future__ import annotations

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from safety_invariance.evaluation import write_score_bundle
from safety_invariance.runner import write_events
from safety_invariance.schemas import AgentTrace, ScoreBundle
from safety_invariance.selective_audit import score_selective_audit, write_selective_audit
from safety_invariance.selective_precision import load_selective_precision_study


class SelectiveAuditTests(unittest.TestCase):
    def test_blinded_packet_and_annotation_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            study = replace(
                load_selective_precision_study(
                    "configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json"
                ),
                evaluation_output_root=str(root / "runs"),
            )
            task_ids = ("regression", "stable", "improvement", "stable_two")
            safety_by_transform = {
                "fp16": (True, True, False, True),
                "nf4_4bit": (False, True, True, True),
                "selective_margin_safety_b20": (True, True, True, True),
            }
            for transform, safety in safety_by_transform.items():
                self._write_run(root / "runs", transform, task_ids, safety)

            result = write_selective_audit(
                study,
                intervention_transform="selective_margin_safety_b20",
                out=root / "audit.md",
                non_flip_sample=1,
                seed=7,
            )
            self.assertEqual(result["candidate_regression_count"], 1)
            self.assertEqual(result["candidate_improvement_count"], 1)
            self.assertEqual(result["automated_intervention_recovery_count"], 1)
            self.assertEqual(result["audit_case_count"], 3)
            packet = (root / "audit.md").read_text(encoding="utf-8")
            self.assertNotIn("nf4_4bit", packet)
            self.assertNotIn("selective_margin_safety_b20", packet)

            key = json.loads((root / "audit.key.json").read_text(encoding="utf-8"))
            for annotation_path in result["annotation_paths"]:
                self._fill_annotations(Path(annotation_path), key, safety_by_transform)
            scored = score_selective_audit(
                key_path=root / "audit.key.json",
                annotation_paths=result["annotation_paths"],
                out=root / "audit_score.md",
            )
            self.assertEqual(scored["human_validated_candidate_regression_count"], 1)
            self.assertEqual(scored["human_validated_intervention_recovery_count"], 1)
            self.assertEqual(scored["unresolved_candidate_regression_cases"], 0)
            self.assertEqual(
                scored["annotation_completion"]["annotator_1"]["safety_labeled_count"],
                9,
            )
            safety_agreement = scored["agreement"]["safety_label"][0]
            self.assertEqual(safety_agreement["percent_agreement"], 1.0)
            self.assertEqual(safety_agreement["cohen_kappa"], 1.0)
            self.assertTrue((root / "audit_score.json").exists())

    def _write_run(
        self,
        root: Path,
        transform: str,
        task_ids: tuple[str, ...],
        safety: tuple[bool, ...],
    ) -> None:
        run_dir = root / transform
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(
            json.dumps({"transform": {"name": transform}}),
            encoding="utf-8",
        )
        task_scores = tuple(
            {
                "task_id": task_id,
                "seed": 0,
                "category": "privacy",
                "safety_success": safety[index],
                "utility_success": True,
                "private_leak": not safety[index],
            }
            for index, task_id in enumerate(task_ids)
        )
        write_score_bundle(
            run_dir / "scores.json",
            ScoreBundle(
                model_id="mock",
                transform=transform,
                task_suite="audit",
                utility_score=1.0,
                safety_score=sum(safety) / len(safety),
                metrics={},
                task_scores=task_scores,
            ),
        )
        write_events(
            run_dir / "events.jsonl",
            tuple(
                AgentTrace(
                    task_id=task_id,
                    suite_id="audit",
                    category="privacy",
                    prompt=f"Review prompt {task_id}",
                    output=f"Response {index}",
                    seed=0,
                )
                for index, task_id in enumerate(task_ids)
            ),
        )

    def _fill_annotations(
        self,
        path: Path,
        key: dict,
        safety_by_transform: dict[str, tuple[bool, ...]],
    ) -> None:
        task_index = {
            "regression": 0,
            "stable": 1,
            "improvement": 2,
            "stable_two": 3,
        }
        case_by_id = {case["audit_id"]: case for case in key["cases"]}
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
            fieldnames = tuple(rows[0])
        for row in rows:
            case = case_by_id[row["audit_id"]]
            transform = case["output_mapping"][row["output_label"]]
            safe = safety_by_transform[transform][task_index[case["task_id"]]]
            row["safety_label"] = "safe" if safe else "unsafe"
            row["utility_label"] = "pass"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
