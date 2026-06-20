from __future__ import annotations

import unittest

from safety_invariance.external import build_agentdojo_command, build_agentharm_command, build_toolsandbox_command


class ExternalWrapperTests(unittest.TestCase):
    def test_agentdojo_command(self) -> None:
        command = build_agentdojo_command(
            model="gpt-4o-2024-05-13",
            suite="workspace",
            user_tasks=("user_task_0",),
        )
        self.assertIn("agentdojo.scripts.benchmark", command)
        self.assertIn("workspace", command)

    def test_toolsandbox_command(self) -> None:
        command = build_toolsandbox_command(agent="Gorilla", scenario="wifi_off")
        self.assertEqual(command[:4], ["tool_sandbox", "--user", "GPT_4_o_2024_05_13", "--agent"])
        self.assertIn("Gorilla", command)
        self.assertIn("wifi_off", command)

    def test_agentharm_command(self) -> None:
        command = build_agentharm_command(
            model="openai-api/si/qwen25_3b_nf4",
            task="agentharm",
            split="test_public",
            refusal_judge="openai/gpt-4o-2024-08-06",
        )
        self.assertEqual(command[:3], ["inspect", "eval", "inspect_evals/agentharm"])
        self.assertIn("openai-api/si/qwen25_3b_nf4", command)
        self.assertIn("refusal_judge=openai/gpt-4o-2024-08-06", command)


if __name__ == "__main__":
    unittest.main()
