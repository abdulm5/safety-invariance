# Native External Benchmark Report

Roots: `runs/native_external_confirmation_24gb`, `runs/native_agentdojo_remaining_suites_extension_48gb`.
Baseline profile: `qwen25_3b_fp16`.

This report is aggregate-level. It uses committed native stdout/manifests and profile telemetry. Per-sample paired flips require the raw native logs or an Inspect runtime capable of reading `.eval` files.

## Profile Summary

|profile|transform|peak GiB|requests|p50 ms|p95 ms|tok/s|context hits|
|---|---|---:|---:|---:|---:|---:|---:|
|qwen25_3b_fp16|fp16|12.03|9793|3689.2|19403.8|21.94|17|
|qwen25_3b_nf4|nf4_4bit|5.88|10569|3460.1|16751.2|18.60|0|
|qwen25_3b_nf4_safety_b20_frozen|nf4_safety_b20_frozen|5.90|10817|2692.6|14075.5|18.84|1|
|qwen25_3b_nf4_utility_b20_frozen|nf4_utility_b20_frozen|5.89|8939|3716.4|17169.9|18.96|11|

## Native Benchmark Aggregates

|profile|WB benign utility|WB direct security|WB tool security|TS benign utility|TS direct security|TS tool security|AgentHarm harmful score|AgentHarm benign score|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|qwen25_3b_fp16|0.214|0.011|0.013|0.220|0.061|0.118|0.470|0.546|
|qwen25_3b_nf4|0.214|0.004|0.016|0.195|0.049|0.122|0.425|0.513|
|qwen25_3b_nf4_safety_b20_frozen|n/a|0.003|0.016|0.122|0.061|0.135|0.416|0.459|
|qwen25_3b_nf4_utility_b20_frozen|n/a|0.007|0.013|0.171|0.053|0.114|0.450|0.487|

WB = workspace/banking. TS = travel/slack.

## AgentDojo Utility Aggregates

|profile|WB direct utility|WB tool utility|TS direct utility|TS tool utility|
|---|---:|---:|---:|---:|
|qwen25_3b_fp16|0.178|0.182|0.163|0.135|
|qwen25_3b_nf4|0.209|0.216|0.155|0.122|
|qwen25_3b_nf4_safety_b20_frozen|0.182|0.212|0.102|0.110|
|qwen25_3b_nf4_utility_b20_frozen|0.171|0.188|0.102|0.122|

## AgentHarm Aggregates

|profile|harmful score|harmful refusals|benign score|benign refusals|
|---|---:|---:|---:|---:|
|qwen25_3b_fp16|0.470|0.114|0.546|0.000|
|qwen25_3b_nf4|0.425|0.023|0.513|0.000|
|qwen25_3b_nf4_safety_b20_frozen|0.416|0.017|0.459|0.000|
|qwen25_3b_nf4_utility_b20_frozen|0.450|0.028|0.487|0.000|

## Baseline Deltas

AgentHarm harmful score is reported as lower-is-safer. AgentHarm benign score, AgentDojo utility, and AgentDojo security are higher-is-better.

|profile|transform|WB benign utility Δ|WB direct sec Δ|WB tool sec Δ|TS benign utility Δ|TS direct sec Δ|TS tool sec Δ|harmful score Δ|benign AgentHarm Δ|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|qwen25_3b_nf4|nf4_4bit|+0.000|-0.007|+0.003|-0.024|-0.012|+0.004|-0.045|-0.033|
|qwen25_3b_nf4_safety_b20_frozen|nf4_safety_b20_frozen|n/a|-0.009|+0.003|-0.098|+0.000|+0.016|-0.054|-0.087|
|qwen25_3b_nf4_utility_b20_frozen|nf4_utility_b20_frozen|n/a|-0.004|+0.000|-0.049|-0.008|-0.004|-0.020|-0.059|

## Mitigation Versus Full NF4

|profile|strategy|TS direct sec Δ|TS tool sec Δ|harmful score Δ|TS benign utility Δ|AgentHarm benign Δ|
|---|---|---:|---:|---:|---:|---:|
|qwen25_3b_nf4_safety_b20_frozen|action_margin_causal_recovery|+0.012|+0.012|-0.009|-0.073|-0.054|
|qwen25_3b_nf4_utility_b20_frozen|utility_margin_recovery|+0.004|-0.008|+0.025|-0.024|-0.026|

## AgentHarm Category Scores

### agentharm_public_harmful

|profile|Disinfo|Harass|Drugs|Fraud|Hate|Cyber|Sexual|Copyright|refusal avg|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|qwen25_3b_fp16|0.644|0.434|0.610|0.340|0.336|0.587|0.428|0.428|0.111|
|qwen25_3b_nf4|0.577|0.374|0.537|0.321|0.374|0.461|0.505|0.295|0.024|
|qwen25_3b_nf4_safety_b20_frozen|0.552|0.431|0.615|0.231|0.346|0.500|0.423|0.286|0.018|
|qwen25_3b_nf4_utility_b20_frozen|0.635|0.512|0.585|0.350|0.329|0.428|0.560|0.233|0.029|

### agentharm_public_benign

|profile|Disinfo|Harass|Drugs|Fraud|Hate|Cyber|Sexual|Copyright|refusal avg|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|qwen25_3b_fp16|0.534|0.509|0.606|0.634|0.487|0.615|0.476|0.518|0.000|
|qwen25_3b_nf4|0.622|0.523|0.594|0.512|0.378|0.635|0.519|0.350|0.000|
|qwen25_3b_nf4_safety_b20_frozen|0.533|0.542|0.572|0.417|0.340|0.476|0.477|0.331|0.000|
|qwen25_3b_nf4_utility_b20_frozen|0.651|0.510|0.535|0.548|0.318|0.473|0.493|0.374|0.000|

## Interpretation Notes

- Confirmatory comparison: `qwen25_3b_fp16` versus `qwen25_3b_nf4`.
- Selective precision rows are external replications of frozen selections; utility-selected rows remain exploratory.
- Aggregate deltas can hide paired behavior flips. Use raw AgentDojo/Inspect logs for final paired statistical tests.
