from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from safety_invariance.noise_floor import analyze_agentdojo_noise_floor, write_agentdojo_noise_floor_report


class AgentDojoNoiseFloorTests(unittest.TestCase):
    def test_compares_self_repeat_with_transform_effect_on_same_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "original"
            repeat = Path(tmp) / "repeat"
            key_args = [
                ("task_a", "inj_1"),
                ("task_b", "inj_1"),
                ("task_c", "inj_1"),
                ("task_d", "inj_1"),
            ]
            for task, inj in key_args:
                _write_outcome(original, "qwen25_3b_fp16", task, inj, utility=True, security=True)
                _write_outcome(repeat, "qwen25_3b_fp16_repeat_noise", task, inj, utility=True, security=True)

            _write_outcome(original, "qwen25_3b_nf4", "task_a", "inj_1", utility=True, security=False)
            _write_outcome(original, "qwen25_3b_nf4", "task_b", "inj_1", utility=True, security=True)
            _write_outcome(original, "qwen25_3b_nf4", "task_c", "inj_1", utility=True, security=False)
            _write_outcome(original, "qwen25_3b_nf4", "task_d", "inj_1", utility=True, security=True)
            _write_outcome(repeat, "qwen25_3b_nf4_repeat_noise", "task_a", "inj_1", utility=True, security=False)
            _write_outcome(repeat, "qwen25_3b_nf4_repeat_noise", "task_b", "inj_1", utility=True, security=True)
            _write_outcome(repeat, "qwen25_3b_nf4_repeat_noise", "task_c", "inj_1", utility=True, security=False)
            _write_outcome(repeat, "qwen25_3b_nf4_repeat_noise", "task_d", "inj_1", utility=True, security=False)

            result = analyze_agentdojo_noise_floor([original], repeat)

            rows = {row["label"]: row for row in result["comparisons"]}
            self.assertEqual(result["matched_subset_count"], 4)
            self.assertEqual(rows["fp16 self-repeat"]["security_flips"], 0)
            self.assertEqual(rows["nf4 self-repeat"]["security_flips"], 1)
            self.assertEqual(rows["fp16 vs nf4 original"]["security_flips"], 2)
            self.assertAlmostEqual(result["noise_floor_security_flip_rate"], 0.25)
            self.assertAlmostEqual(result["transform_security_flip_rate"], 0.50)
            self.assertAlmostEqual(result["transform_to_noise_ratio"], 2.0)

    def test_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "original"
            repeat = Path(tmp) / "repeat"
            _write_outcome(original, "qwen25_3b_fp16", "task_a", "inj_1", utility=True, security=True)
            _write_outcome(original, "qwen25_3b_nf4", "task_a", "inj_1", utility=True, security=False)
            _write_outcome(repeat, "qwen25_3b_fp16_repeat_noise", "task_a", "inj_1", utility=True, security=True)
            _write_outcome(repeat, "qwen25_3b_nf4_repeat_noise", "task_a", "inj_1", utility=True, security=False)
            out = Path(tmp) / "noise.md"
            json_out = Path(tmp) / "noise.json"

            write_agentdojo_noise_floor_report([original], repeat, out, json_out=json_out)

            self.assertTrue(out.exists())
            self.assertTrue(json_out.exists())
            self.assertIn("AgentDojo Deterministic Repeat Noise Floor", out.read_text())


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
