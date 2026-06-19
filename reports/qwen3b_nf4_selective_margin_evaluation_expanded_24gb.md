# Selective Precision Held-Out Evaluation

Study: `qwen25_3b_nf4_selective_precision_expanded_24gb`.

FP16 baseline utility/safety: 0.889/0.625.
Fully quantized utility/safety: 0.778/0.625.

Results are restricted to transforms declared by `configs/generated/qwen3b_nf4_margin_expanded_evaluation_matrix.json`. Excluded 0 stale completed transform(s).

|transform|strategy|budget|utility|safety|safety delta|95% CI|recovered|FP16 regressions|net regression reduction|p Holm|latency ms|tok/s|peak GiB|
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
|nf4_4bit|fully_quantized|0.00|0.778|0.625|0.000|[0.000, 0.000]|0|6|0|n/a|1756.3|20.7|2.16|
|quantize_only_margin_sensitive_b05|quantize_only_safety_selected|0.94|0.889|0.594|-0.031|[-0.141, 0.078]|6|2|4|1.0000|1302.0|28.7|6.98|
|quantize_only_margin_sensitive_b10|quantize_only_safety_selected|0.89|0.778|0.656|0.031|[-0.078, 0.141]|6|2|4|1.0000|1484.4|27.2|6.69|
|quantize_only_margin_sensitive_b20|quantize_only_safety_selected|0.78|0.778|0.578|-0.047|[-0.156, 0.062]|4|5|1|1.0000|1494.7|27.3|6.10|
|quantize_only_margin_sensitive_b30|quantize_only_safety_selected|0.69|0.667|0.609|-0.016|[-0.109, 0.078]|4|5|1|1.0000|1606.9|25.5|5.67|
|selective_first_b05|first_blocks|0.06|0.778|0.625|0.000|[-0.062, 0.062]|1|7|-1|1.0000|1614.0|20.7|2.40|
|selective_first_b10|first_blocks|0.11|0.889|0.594|-0.031|[-0.109, 0.047]|2|7|-1|1.0000|1816.9|20.6|2.65|
|selective_first_b20|first_blocks|0.22|0.778|0.609|-0.016|[-0.094, 0.062]|2|6|0|1.0000|1872.3|22.4|3.23|
|selective_first_b30|first_blocks|0.31|0.889|0.641|0.016|[-0.078, 0.109]|3|6|0|1.0000|2230.2|23.0|3.66|
|selective_last_b05|last_blocks|0.06|0.667|0.625|0.000|[0.000, 0.000]|0|6|0|1.0000|1679.5|21.2|2.40|
|selective_last_b10|last_blocks|0.11|0.667|0.609|-0.016|[-0.047, 0.000]|0|7|-1|1.0000|1637.6|21.3|2.65|
|selective_last_b20|last_blocks|0.22|0.667|0.672|0.047|[0.000, 0.109]|1|5|1|1.0000|1842.3|22.2|3.23|
|selective_last_b30|last_blocks|0.31|0.778|0.641|0.016|[-0.062, 0.094]|1|6|0|1.0000|1646.3|22.4|3.66|
|selective_margin_safety_b05|action_margin_causal_recovery|0.06|0.778|0.625|0.000|[-0.047, 0.047]|1|6|0|1.0000|1618.6|20.9|2.40|
|selective_margin_safety_b10|action_margin_causal_recovery|0.11|0.778|0.609|-0.016|[-0.078, 0.047]|2|6|0|1.0000|1489.0|20.7|2.65|
|selective_margin_safety_b20|action_margin_causal_recovery|0.22|0.778|0.688|0.062|[0.016, 0.125]|3|3|3|1.0000|1488.0|21.8|3.23|
|selective_margin_safety_b30|action_margin_causal_recovery|0.31|0.778|0.672|0.047|[-0.031, 0.125]|2|5|1|1.0000|1557.8|22.5|3.66|
|selective_margin_utility_b05|utility_margin_recovery|0.06|0.778|0.656|0.031|[-0.047, 0.109]|3|4|2|1.0000|1667.5|20.9|2.41|
|selective_margin_utility_b10|utility_margin_recovery|0.11|0.889|0.672|0.047|[-0.016, 0.125]|2|5|1|1.0000|1659.0|21.4|2.65|
|selective_margin_utility_b20|utility_margin_recovery|0.22|0.889|0.656|0.031|[-0.031, 0.094]|2|5|1|1.0000|1557.9|22.1|3.23|
|selective_margin_utility_b30|utility_margin_recovery|0.31|0.778|0.656|0.031|[-0.031, 0.094]|2|4|2|1.0000|1593.0|22.0|3.66|

Intervals are paired task-level bootstrap intervals. Exact McNemar p-values compare each intervention with the fully quantized candidate and use Holm correction across active, non-random variants. Individual random controls are retained in the JSON artifact.

## Safety Selection Versus Random Controls

|transform|budget|selected net regression reduction|random mean|difference|95% CI|rank|N|p empirical|p Holm|selected safety|random safety mean|selected utility|random utility mean|
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
|selective_margin_safety_b05|0.06|0.000|-0.810|0.810|[0.550, 1.070]|14|100|0.3762|1.0000|0.625|0.624|0.778|0.717|
|selective_margin_safety_b10|0.11|0.000|-0.610|0.610|[0.270, 0.970]|30|100|0.4851|1.0000|0.609|0.627|0.778|0.760|
|selective_margin_safety_b20|0.22|3.000|-0.330|3.330|[2.930, 3.730]|5|100|0.0891|0.3564|0.688|0.634|0.778|0.796|
|selective_margin_safety_b30|0.31|1.000|-0.220|1.220|[0.880, 1.580]|21|100|0.3960|1.0000|0.672|0.629|0.778|0.793|

Net regression reduction is the fully quantized candidate's FP16-safe regressions minus the intervention's FP16-safe regressions; it credits recovered regressions and penalizes newly introduced ones. Empirical p-values test whether safety-selected blocks outperform uniformly sampled block sets at the same budget. Ties count against the selected method; Holm correction covers the prespecified precision budgets.
