from __future__ import annotations

import unittest

from safety_invariance.external import build_agentdojo_command, build_toolsandbox_command


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


if __name__ == "__main__":
    unittest.main()
