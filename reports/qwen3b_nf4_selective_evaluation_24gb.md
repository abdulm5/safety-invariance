# Selective Precision Held-Out Evaluation

Study: `qwen25_3b_nf4_selective_precision_24gb`.

FP16 baseline utility/safety: 0.889/0.812.
Fully quantized utility/safety: 0.778/0.688.

|transform|strategy|budget|utility|safety|safety delta|95% CI|recovered|baseline regressions|p Holm|latency ms|tok/s|peak GiB|
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
|nf4_4bit|fully_quantized|0.00|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1902.5|20.7|2.16|
|quantize_only_sensitive_b05|quantize_only_safety_selected|0.94|1.000|0.812|0.125|[0.000, 0.312]|2|0|1.0000|1370.1|29.4|6.98|
|quantize_only_sensitive_b10|quantize_only_safety_selected|0.89|0.889|0.875|0.188|[0.000, 0.375]|2|0|1.0000|1548.5|27.6|6.69|
|quantize_only_sensitive_b20|quantize_only_safety_selected|0.78|0.889|0.812|0.125|[-0.125, 0.375]|2|1|1.0000|1635.0|26.2|6.10|
|quantize_only_sensitive_b30|quantize_only_safety_selected|0.69|0.556|0.875|0.188|[0.000, 0.375]|2|0|1.0000|1374.0|24.6|5.67|
|selective_first_b05|first_blocks|0.06|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1834.3|21.4|2.40|
|selective_first_b10|first_blocks|0.11|0.889|0.688|0.000|[-0.188, 0.188]|1|2|1.0000|2096.6|21.6|2.65|
|selective_first_b20|first_blocks|0.22|0.778|0.688|0.000|[-0.250, 0.250]|1|3|1.0000|2524.4|22.8|3.23|
|selective_first_b30|first_blocks|0.31|0.889|0.750|0.062|[-0.125, 0.250]|1|2|1.0000|2766.9|23.1|3.66|
|selective_last_b05|last_blocks|0.06|0.667|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1702.8|21.4|2.40|
|selective_last_b10|last_blocks|0.11|0.667|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1634.3|20.7|2.65|
|selective_last_b20|last_blocks|0.22|0.667|0.750|0.062|[0.000, 0.188]|0|2|1.0000|1778.6|21.8|3.23|
|selective_last_b30|last_blocks|0.31|0.778|0.688|0.000|[-0.188, 0.188]|0|3|1.0000|2069.9|20.5|3.66|
|selective_random_b05_r00|random_blocks|0.06|0.889|0.750|0.062|[0.000, 0.188]|1|1|1.0000|2428.1|21.3|2.40|
|selective_random_b05_r01|random_blocks|0.06|0.667|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1764.5|21.0|2.40|
|selective_random_b05_r02|random_blocks|0.06|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1710.7|21.0|2.40|
|selective_random_b05_r03|random_blocks|0.06|0.667|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1900.4|20.3|2.40|
|selective_random_b05_r04|random_blocks|0.06|0.667|0.625|-0.062|[-0.188, 0.000]|0|3|1.0000|1778.0|21.0|2.41|
|selective_random_b05_r05|random_blocks|0.06|0.778|0.688|0.000|[-0.188, 0.188]|0|3|1.0000|1780.3|21.2|2.41|
|selective_random_b05_r06|random_blocks|0.06|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1746.3|21.0|2.40|
|selective_random_b05_r07|random_blocks|0.06|0.667|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1727.7|21.2|2.41|
|selective_random_b05_r08|random_blocks|0.06|0.778|0.688|0.000|[-0.188, 0.188]|1|2|1.0000|2011.7|21.2|2.41|
|selective_random_b05_r09|random_blocks|0.06|0.778|0.688|0.000|[-0.188, 0.188]|0|3|1.0000|2236.1|21.7|2.40|
|selective_random_b10_r00|random_blocks|0.11|0.778|0.688|0.000|[-0.188, 0.188]|1|2|1.0000|2114.4|20.9|2.65|
|selective_random_b10_r01|random_blocks|0.11|0.667|0.562|-0.125|[-0.312, 0.000]|0|4|1.0000|1956.3|20.8|2.65|
|selective_random_b10_r02|random_blocks|0.11|0.778|0.688|0.000|[-0.188, 0.188]|1|2|1.0000|1632.7|20.9|2.65|
|selective_random_b10_r03|random_blocks|0.11|0.778|0.750|0.062|[0.000, 0.188]|0|2|1.0000|1933.4|21.3|2.65|
|selective_random_b10_r04|random_blocks|0.11|0.667|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1590.8|20.7|2.65|
|selective_random_b10_r05|random_blocks|0.11|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|2463.6|21.3|2.65|
|selective_random_b10_r06|random_blocks|0.11|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1838.2|20.6|2.65|
|selective_random_b10_r07|random_blocks|0.11|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1861.3|20.8|2.65|
|selective_random_b10_r08|random_blocks|0.11|0.778|0.625|-0.062|[-0.188, 0.000]|0|3|1.0000|1988.6|20.9|2.65|
|selective_random_b10_r09|random_blocks|0.11|0.667|0.688|0.000|[-0.188, 0.188]|0|3|1.0000|1904.8|20.5|2.65|
|selective_random_b20_r00|random_blocks|0.22|0.889|0.688|0.000|[-0.250, 0.250]|1|3|1.0000|2960.7|22.6|3.23|
|selective_random_b20_r01|random_blocks|0.22|0.889|0.750|0.062|[0.000, 0.188]|0|2|1.0000|2135.2|22.0|3.23|
|selective_random_b20_r02|random_blocks|0.22|0.889|0.688|0.000|[-0.250, 0.250]|1|3|1.0000|2956.7|22.5|3.23|
|selective_random_b20_r03|random_blocks|0.22|0.889|0.688|0.000|[-0.188, 0.188]|1|2|1.0000|2197.2|22.4|3.23|
|selective_random_b20_r04|random_blocks|0.22|0.889|0.688|0.000|[-0.250, 0.250]|1|3|1.0000|1979.7|21.8|3.23|
|selective_random_b20_r05|random_blocks|0.22|0.667|0.750|0.062|[-0.125, 0.250]|1|2|1.0000|1700.2|21.9|3.23|
|selective_random_b20_r06|random_blocks|0.22|0.667|0.625|-0.062|[-0.188, 0.000]|0|3|1.0000|1670.6|22.0|3.23|
|selective_random_b20_r07|random_blocks|0.22|0.778|0.812|0.125|[0.000, 0.312]|1|1|1.0000|1980.2|22.4|3.23|
|selective_random_b20_r08|random_blocks|0.22|0.778|0.812|0.125|[0.000, 0.312]|1|1|1.0000|1973.1|21.6|3.23|
|selective_random_b20_r09|random_blocks|0.22|0.778|0.688|0.000|[-0.188, 0.188]|0|3|1.0000|2004.0|21.8|3.23|
|selective_random_b30_r00|random_blocks|0.31|0.889|0.625|-0.062|[-0.188, 0.000]|0|3|1.0000|2183.6|22.6|3.66|
|selective_random_b30_r01|random_blocks|0.31|0.889|0.750|0.062|[0.000, 0.188]|1|1|1.0000|1709.0|22.3|3.66|
|selective_random_b30_r02|random_blocks|0.31|0.778|0.875|0.188|[0.000, 0.375]|1|1|1.0000|2114.3|22.5|3.66|
|selective_random_b30_r03|random_blocks|0.31|0.667|0.625|-0.062|[-0.252, 0.125]|0|4|1.0000|1968.1|22.2|3.66|
|selective_random_b30_r04|random_blocks|0.31|0.778|0.750|0.062|[0.000, 0.188]|1|1|1.0000|1612.0|22.5|3.66|
|selective_random_b30_r05|random_blocks|0.31|0.889|0.625|-0.062|[-0.188, 0.000]|0|3|1.0000|2605.3|23.0|3.66|
|selective_random_b30_r06|random_blocks|0.31|0.889|0.875|0.188|[0.000, 0.375]|1|1|1.0000|2446.2|22.9|3.66|
|selective_random_b30_r07|random_blocks|0.31|0.889|0.812|0.125|[0.000, 0.312]|0|2|1.0000|2222.0|21.5|3.66|
|selective_random_b30_r08|random_blocks|0.31|1.000|0.812|0.125|[0.000, 0.312]|1|1|1.0000|1758.8|22.5|3.66|
|selective_random_b30_r09|random_blocks|0.31|0.889|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1667.3|22.6|3.66|
|selective_safety_b05|causal_safety_recovery|0.06|0.667|0.750|0.062|[0.000, 0.188]|1|1|1.0000|1638.1|21.3|2.40|
|selective_safety_b10|causal_safety_recovery|0.11|0.778|0.688|0.000|[-0.188, 0.188]|1|2|1.0000|2049.8|22.0|2.65|
|selective_safety_b20|causal_safety_recovery|0.22|0.889|0.625|-0.062|[-0.188, 0.000]|0|3|1.0000|2051.1|21.7|3.23|
|selective_safety_b30|causal_safety_recovery|0.31|0.889|0.750|0.062|[0.000, 0.188]|1|1|1.0000|2157.2|22.5|3.66|
|selective_utility_b05|utility_recovery|0.06|0.778|0.688|0.000|[0.000, 0.000]|0|2|1.0000|1912.4|21.5|2.41|
|selective_utility_b10|utility_recovery|0.11|0.889|0.750|0.062|[-0.125, 0.250]|1|2|1.0000|3235.6|21.9|2.65|
|selective_utility_b20|utility_recovery|0.22|0.889|0.812|0.125|[0.000, 0.312]|1|1|1.0000|2404.8|22.7|3.23|
|selective_utility_b30|utility_recovery|0.31|0.889|0.750|0.062|[0.000, 0.188]|1|1|1.0000|2237.2|21.7|3.66|

Intervals are paired task-level bootstrap intervals. Exact McNemar p-values compare each intervention with the fully quantized candidate and use Holm correction across reported variants.
