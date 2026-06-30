from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from safety_invariance.native_report import (
    build_native_external_report,
    parse_agentdojo_stdout,
    parse_agentharm_stdout,
    summarize_server_events,
    write_native_external_report,
)


AGENTDOJO_STDOUT = """Finished benchmark for suite: 'banking'
Results for suite workspace
Average utility: 12.50%

Passed injection tasks as user tasks: 3/14
Average security: 0.36%
Results for suite combined
Average utility: 17.76%

Passed injection tasks as user tasks: 8/23
Average security: 1.14%
"""


AGENTHARM_STDOUT = """agentharm (176 samples): openai-api/si/qwen25_3b_fp16
total time:                                                 2:47:16
combined_scorer
avg_score                    0.470
avg_full_score               0.102
avg_refusals                 0.114
Disinformation_avg_scores    0.644
Fraud_avg_scores             0.340
Fraud_avg_refusals           0.208
Log: runs/foo.eval
"""


class NativeReportTests(unittest.TestCase):
    def test_parse_agentdojo_stdout(self) -> None:
        parsed = parse_agentdojo_stdout(AGENTDOJO_STDOUT)

        self.assertAlmostEqual(parsed["workspace"]["average_utility"], 0.125)
        self.assertAlmostEqual(parsed["combined"]["average_utility"], 0.1776)
        self.assertAlmostEqual(parsed["combined"]["average_security"], 0.0114)
        self.assertEqual(parsed["combined"]["injection_user_task_passed"], 8)
        self.assertEqual(parsed["combined"]["injection_user_task_total"], 23)

    def test_parse_agentharm_stdout(self) -> None:
        parsed = parse_agentharm_stdout(AGENTHARM_STDOUT)

        self.assertEqual(parsed["samples"], 176)
        self.assertEqual(parsed["total_time"], "2:47:16")
        self.assertEqual(parsed["log_path"], "runs/foo.eval")
        self.assertAlmostEqual(parsed["metrics"]["avg_score"], 0.470)
        self.assertAlmostEqual(parsed["metrics"]["Fraud_avg_refusals"], 0.208)

    def test_summarize_server_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "duration_ms": 1000,
                                "input_tokens": 10,
                                "output_tokens": 5,
                                "tool_call_count": 1,
                                "context_limit_reached": False,
                            }
                        ),
                        json.dumps(
                            {
                                "duration_ms": 3000,
                                "input_tokens": 20,
                                "output_tokens": 15,
                                "tool_call_count": 2,
                                "context_limit_reached": True,
                            }
                        ),
                    ]
                )
            )

            summary = summarize_server_events(path)

            self.assertEqual(summary["request_count"], 2)
            self.assertEqual(summary["input_tokens"], 30)
            self.assertEqual(summary["output_tokens"], 20)
            self.assertEqual(summary["context_limit_hits"], 1)
            self.assertAlmostEqual(summary["output_tokens_per_second"], 5.0)

    def test_write_native_external_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            _write_profile(root, "qwen25_3b_fp16", "fp16", dojo_security=0.0114, harmful=0.47)
            _write_profile(root, "qwen25_3b_nf4", "nf4_4bit", dojo_security=0.0043, harmful=0.42)
            out = Path(tmp) / "report.md"
            json_out = Path(tmp) / "report.json"

            write_native_external_report(root, out, json_out=json_out)
            report = build_native_external_report(root)

            self.assertTrue(out.exists())
            self.assertTrue(json_out.exists())
            self.assertEqual(report.baseline_profile, "qwen25_3b_fp16")
            self.assertEqual(len(report.comparisons), 1)
            self.assertAlmostEqual(report.comparisons[0]["agentharm_harmful_score_delta"], -0.05)
            self.assertIn("Native External Benchmark Report", out.read_text())

    def test_report_merges_multiple_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            _write_profile(first, "qwen25_3b_fp16", "fp16", dojo_security=0.0114, harmful=0.47)
            _write_profile(second, "qwen25_3b_fp16", "fp16", dojo_security=0.0114, harmful=0.47)
            remaining = second / "qwen25_3b_fp16" / "agentdojo_remaining_direct_v122"
            remaining.mkdir()
            remaining.joinpath("stdout.txt").write_text(
                """Results for suite combined
Average utility: 30.00%
Average security: 2.00%
"""
            )

            report = build_native_external_report([first, second])

            profile = report.profiles["qwen25_3b_fp16"]
            self.assertEqual(len(report.roots), 2)
            self.assertIn("agentdojo_benign_v122", profile["agentdojo"])
            self.assertIn("agentdojo_remaining_direct_v122", profile["agentdojo"])
            self.assertAlmostEqual(
                profile["agentdojo"]["agentdojo_remaining_direct_v122"]["combined"]["average_security"],
                0.02,
            )

    def test_report_can_filter_candidate_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            _write_profile(root, "qwen25_3b_fp16", "fp16", dojo_security=0.0114, harmful=0.47)
            _write_profile(root, "qwen25_3b_nf4", "nf4_4bit", dojo_security=0.0043, harmful=0.42)
            _write_profile(root, "llama31_8b_nf4", "nf4_4bit", dojo_security=0.0080, harmful=0.44)
            out = Path(tmp) / "report.md"

            write_native_external_report(
                root,
                out,
                candidate_profiles=("qwen25_3b_nf4",),
            )
            report = build_native_external_report(
                root,
                candidate_profiles=("qwen25_3b_nf4",),
            )

            self.assertEqual(set(report.profiles), {"qwen25_3b_fp16", "qwen25_3b_nf4"})
            self.assertNotIn("llama31_8b_nf4", out.read_text())


def _write_profile(root: Path, name: str, transform: str, *, dojo_security: float, harmful: float) -> None:
    profile = root / name
    profile.mkdir(parents=True)
    (profile / "server_manifest.json").write_text(
        json.dumps(
            {
                "transform": {"name": transform, "metadata": {}},
                "model": {"model_id": "Qwen/Qwen2.5-3B-Instruct"},
                "runtime": {
                    "peak_cuda_reserved_bytes": 2 * 1024**3,
                    "peak_cuda_allocated_bytes": 1 * 1024**3,
                    "model_memory_footprint_bytes": 1 * 1024**3,
                },
            }
        )
    )
    (profile / "server_events.jsonl").write_text(
        json.dumps({"duration_ms": 1000, "input_tokens": 10, "output_tokens": 10}) + "\n"
    )
    for benchmark in ("agentdojo_benign_v122", "agentdojo_direct_v122", "agentdojo_tool_knowledge_v122"):
        path = profile / benchmark
        path.mkdir()
        path.joinpath("stdout.txt").write_text(
            f"""Results for suite combined
Average utility: 20.00%
Passed injection tasks as user tasks: 1/2
Average security: {dojo_security * 100:.2f}%
"""
        )
    for benchmark, score in (
        ("agentharm_public_harmful", harmful),
        ("agentharm_public_benign", 0.50),
    ):
        path = profile / benchmark
        path.mkdir()
        path.joinpath("stdout.txt").write_text(
            f"""agentharm (176 samples): model
combined_scorer
avg_score                    {score:.3f}
Disinformation_avg_scores    {score:.3f}
"""
        )


if __name__ == "__main__":
    unittest.main()
