from __future__ import annotations

import unittest

from safety_invariance.mechanistic import (
    aggregate_layer_divergence,
    correlate_layer_and_causal_scores,
    pearson_correlation,
)


class MechanisticAnalysisTests(unittest.TestCase):
    def test_aggregates_safety_specific_layer_divergence(self) -> None:
        tasks = [
            {
                "is_safety_task": True,
                "layers": [
                    {"block": "model.layers.0", "cosine_distance": 0.3, "normalized_l2_distance": 0.4},
                    {"block": "model.layers.1", "cosine_distance": 0.2, "normalized_l2_distance": 0.3},
                ],
            },
            {
                "is_safety_task": False,
                "layers": [
                    {"block": "model.layers.0", "cosine_distance": 0.1, "normalized_l2_distance": 0.2},
                    {"block": "model.layers.1", "cosine_distance": 0.2, "normalized_l2_distance": 0.3},
                ],
            },
        ]
        rows = aggregate_layer_divergence(tasks)
        self.assertAlmostEqual(rows[0]["safety_specific_cosine_excess"], 0.2)
        correlation = correlate_layer_and_causal_scores(
            rows,
            {"model.layers.0": 2.0, "model.layers.1": 1.0},
        )
        self.assertEqual(correlation["matched_block_count"], 2)
        self.assertIsNotNone(correlation["pearson_r"])

    def test_pearson_handles_degenerate_scores(self) -> None:
        self.assertAlmostEqual(pearson_correlation([(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]), 1.0)
        self.assertIsNone(pearson_correlation([(1.0, 2.0), (1.0, 3.0)]))


if __name__ == "__main__":
    unittest.main()
