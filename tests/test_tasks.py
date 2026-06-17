from __future__ import annotations

import unittest

from safety_invariance.tasks import load_task_suites


class TaskLoadingTests(unittest.TestCase):
    def test_loads_agentdojo_and_custom_suites(self) -> None:
        suite_id, tasks = load_task_suites(
            [
                "data/tasks/agentdojo_minimal.json",
                "data/tasks/custom_safety.json",
            ]
        )
        self.assertEqual(suite_id, "agentdojo_minimal_v1+custom_safety_v1")
        self.assertGreaterEqual(len(tasks), 6)
        self.assertTrue(any(task.untrusted_context for task in tasks))
        self.assertTrue(any(task.contains_private_data for task in tasks))

    def test_loads_signal_replication_suite(self) -> None:
        suite_id, tasks = load_task_suites(["data/tasks/safety_signal_replication.json"])
        self.assertEqual(suite_id, "safety_signal_replication_v1")
        self.assertGreaterEqual(len(tasks), 15)
        self.assertTrue(any(task.category == "agentharm" for task in tasks))
        self.assertTrue(any(task.category == "evaluation_sensitivity" for task in tasks))
        self.assertTrue(any(task.requires_confirmation for task in tasks))


if __name__ == "__main__":
    unittest.main()
