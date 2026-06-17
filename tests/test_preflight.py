from __future__ import annotations

import unittest

from safety_invariance.preflight import run_preflight


class PreflightTests(unittest.TestCase):
    def test_mock_matrix_does_not_require_gpu_packages(self) -> None:
        result = run_preflight("configs/data_collection_matrix_mock.json")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["info"]["run_count"], 5)


if __name__ == "__main__":
    unittest.main()
