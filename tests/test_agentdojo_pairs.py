from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from safety_invariance.agentdojo_pairs import analyze_agentdojo_pairs, write_agentdojo_pair_report


class AgentDojoPairTests(unittest.TestCase):
    def test_counts_security_and_utility_flips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            _write_outcome(root, "qwen25_3b_fp16", "task_a", "inj_1", utility=True, security=True)
            _write_outcome(root, "qwen25_3b_nf4", "task_a", "inj_1", utility=True, security=False)
            _write_outcome(root, "qwen25_3b_fp16", "task_b", "inj_1", utility=False, security=False)
            _write_outcome(root, "qwen25_3b_nf4", "task_b", "inj_1", utility=True, security=True)
            _write_outcome(root, "qwen25_3b_fp16", "task_c", "inj_1", utility=True, security=True)
            _write_outcome(root, "qwen25_3b_nf4", "task_c", "inj_1", utility=False, security=True)

            result = analyze_agentdojo_pairs([root])
            row = result["comparisons"][0]

            self.assertEqual(row["matched_count"], 3)
            self.assertEqual(row["safe_to_unsafe"], 1)
            self.assertEqual(row["unsafe_to_safe"], 1)
            self.assertEqual(row["security_flips"], 2)
            self.assertEqual(row["utility_regressions"], 1)
            self.assertEqual(row["utility_improvements"], 1)
            self.assertEqual(row["safe_to_unsafe_with_utility_preserved"], 1)
            self.assertEqual(row["capability_overlap_count"], 1)

    def test_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            _write_outcome(root, "qwen25_3b_fp16", "task_a", "inj_1", utility=True, security=True)
            _write_outcome(root, "qwen25_3b_nf4", "task_a", "inj_1", utility=True, security=False)
            out = Path(tmp) / "pairs.md"
            json_out = Path(tmp) / "pairs.json"

            write_agentdojo_pair_report([root], out, json_out=json_out)

            self.assertTrue(out.exists())
            self.assertTrue(json_out.exists())
            self.assertIn("AgentDojo Paired Flip Report", out.read_text())


def _write_outcome(
    root: Path,
    profile: str,
    user_task_id: str,
    injection_task_id: str,
    *,
    utility: bool,
    security: bool,
) -> None:
    path = (
        root
        / profile
        / "agentdojo_direct_v122"
        / "native_logs"
        / "vllm_parsed"
        / "workspace"
        / user_task_id
        / "direct"
        / f"{injection_task_id}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "suite_name": "workspace",
                "user_task_id": user_task_id,
                "injection_task_id": injection_task_id,
                "attack_type": "direct",
                "utility": utility,
                "security": security,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
