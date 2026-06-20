# Selective Precision Held-Out Evaluation

Study: `llama31_8b_nf4_selective_b20_replication_24gb`.

FP16 baseline utility/safety: 0.667/0.844.
Fully quantized utility/safety: 0.556/0.797.

Paired FP16-to-quantized behavior: 5 safe-to-unsafe regression(s), 2 unsafe-to-safe improvement(s), and 7 total safety flip(s).

Results are restricted to transforms declared by `configs/generated/llama31_8b_nf4_b20_evaluation_matrix.json`. Excluded 0 stale completed transform(s).

|transform|strategy|budget|utility|safety|safety delta|95% CI|recovered|FP16 regressions|net regression reduction|p Holm|latency ms|tok/s|peak GiB|
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
|nf4_4bit|fully_quantized|0.00|0.556|0.797|0.000|[0.000, 0.000]|0|5|0|n/a|1390.4|22.3|5.88|
|quantize_only_margin_sensitive_b20|quantize_only_safety_selected|0.78|0.556|0.828|0.031|[-0.062, 0.125]|5|3|2|1.0000|1183.6|27.6|15.83|
|selective_first_b20|first_blocks|0.22|0.778|0.828|0.031|[-0.078, 0.141]|5|4|1|1.0000|1698.6|24.4|8.52|
|selective_last_b20|last_blocks|0.22|0.556|0.750|-0.047|[-0.125, 0.031]|2|7|-2|1.0000|1706.7|23.6|8.52|
|selective_margin_safety_b20|action_margin_causal_recovery|0.22|0.778|0.812|0.016|[-0.062, 0.094]|3|5|0|1.0000|1830.5|24.0|8.52|
|selective_margin_utility_b20|utility_margin_recovery|0.22|0.778|0.844|0.047|[-0.016, 0.109]|3|3|2|1.0000|1545.8|23.4|8.52|

Intervals are paired task-level bootstrap intervals. Exact McNemar p-values compare each intervention with the fully quantized candidate and use Holm correction across active, non-random variants. Individual random controls are retained in the JSON artifact.

## Safety Selection Versus Random Controls

|transform|budget|selected net regression reduction|random mean|difference|95% CI|rank|N|p empirical|p Holm|selected safety|random safety mean|selected utility|random utility mean|
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
|selective_margin_safety_b20|0.22|0.000|0.580|-0.580|[-1.030, -0.100]|58|100|0.6931|0.6931|0.812|0.825|0.778|0.676|

Net regression reduction is the fully quantized candidate's FP16-safe regressions minus the intervention's FP16-safe regressions; it credits recovered regressions and penalizes newly introduced ones. Empirical p-values test whether safety-selected blocks outperform uniformly sampled block sets at the same budget. Ties count against the selected method; Holm correction covers the prespecified precision budgets.
