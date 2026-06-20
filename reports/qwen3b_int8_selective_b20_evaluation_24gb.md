# Selective Precision Held-Out Evaluation

Study: `qwen25_3b_int8_selective_b20_replication_24gb`.

FP16 baseline utility/safety: 0.889/0.625.
Fully quantized utility/safety: 0.778/0.594.

Paired FP16-to-quantized behavior: 5 safe-to-unsafe regression(s), 3 unsafe-to-safe improvement(s), and 8 total safety flip(s).

Results are restricted to transforms declared by `configs/generated/qwen3b_int8_b20_evaluation_matrix.json`. Excluded 0 stale completed transform(s).

|transform|strategy|budget|utility|safety|safety delta|95% CI|recovered|FP16 regressions|net regression reduction|p Holm|latency ms|tok/s|peak GiB|
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
|int8|fully_quantized|0.00|0.778|0.594|0.000|[0.000, 0.000]|0|5|0|n/a|5614.9|6.9|3.29|
|quantize_only_margin_sensitive_b20|quantize_only_safety_selected|0.78|0.778|0.625|0.031|[-0.078, 0.141]|5|2|3|1.0000|2383.2|16.4|5.30|
|selective_first_b20|first_blocks|0.22|0.889|0.609|0.016|[-0.094, 0.109]|4|3|2|1.0000|4694.1|8.1|3.86|
|selective_last_b20|last_blocks|0.22|0.778|0.562|-0.031|[-0.078, 0.000]|0|6|-1|1.0000|4478.9|8.5|3.84|
|selective_margin_safety_b20|action_margin_causal_recovery|0.22|0.889|0.594|0.000|[-0.078, 0.094]|2|5|0|1.0000|3910.6|8.4|3.84|
|selective_margin_utility_b20|utility_margin_recovery|0.22|1.000|0.641|0.047|[-0.031, 0.125]|3|2|3|1.0000|4368.2|8.3|3.86|

Intervals are paired task-level bootstrap intervals. Exact McNemar p-values compare each intervention with the fully quantized candidate and use Holm correction across active, non-random variants. Individual random controls are retained in the JSON artifact.

## Safety Selection Versus Random Controls

|transform|budget|selected net regression reduction|random mean|difference|95% CI|rank|N|p empirical|p Holm|selected safety|random safety mean|selected utility|random utility mean|
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
|selective_margin_safety_b20|0.22|0.000|0.050|-0.050|[-0.370, 0.260]|35|100|0.6139|0.6139|0.594|0.598|0.889|0.856|

Net regression reduction is the fully quantized candidate's FP16-safe regressions minus the intervention's FP16-safe regressions; it credits recovered regressions and penalizes newly introduced ones. Empirical p-values test whether safety-selected blocks outperform uniformly sampled block sets at the same budget. Ties count against the selected method; Holm correction covers the prespecified precision budgets.
