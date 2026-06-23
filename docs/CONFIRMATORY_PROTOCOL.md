# Native External Confirmation Protocol

The prospective corrections and extensions in
[`PROTOCOL_AMENDMENT_2026-06-21.md`](PROTOCOL_AMENDMENT_2026-06-21.md) govern
scope labels and analyses added after benign external results were inspected.
The original frozen matrix remains unchanged for auditability.

## Decision

Do not run more custom-suite model sweeps before this protocol. The existing custom results establish a reproducible pilot and provide frozen layer rankings. The next evidential bottlenecks are native benchmark validity, independent human labels, and cross-family confirmation.

The current action-margin selector is a negative result: it did not generalize across Qwen INT8 and Llama NF4. It remains a prespecified comparison, not the headline mitigation. The utility-ranked result is exploratory and may only be promoted if it succeeds on these untouched external tasks.

## Frozen Claims

Primary claim:

> Quantization is not behaviorally safety-invariant in tool-using agents: matched FP16 and quantized agents exhibit paired safe-to-unsafe and unsafe-to-safe flips that aggregate safety scores can conceal.

Primary endpoint: paired FP16-safe to transformed-unsafe regression rate, grouped by model and benchmark.

Secondary endpoints:

- unsafe-to-safe improvement rate and any-flip rate
- native utility and security deltas
- safety regression conditional on unchanged utility
- peak VRAM, warm p50/p95 latency, and output throughput
- selective-precision recovery and newly introduced regressions

## Confirmatory Matrix

The frozen matrix is `configs/external_confirmation_matrix_24gb.json`.

Models:

- Qwen2.5-3B-Instruct
- Llama-3.1-8B-Instruct
- Qwen3-8B in non-thinking mode
- Mistral-7B-Instruct-v0.3

Conditions:

- FP16 and locally quantized bitsandbytes NF4 for every model
- frozen safety-ranked 20% mixed precision for Qwen2.5-3B and Llama-3.1-8B
- frozen utility-ranked 20% mixed precision for the same models, explicitly exploratory

Benchmarks:

- AgentDojo v1.2.2 `workspace` and `banking` benign tasks, direct injection,
  and tool-knowledge injection
- AgentHarm public harmful and matched benign tasks through Inspect Evals

All model and benchmark revisions are pinned in the matrix. Official benchmark processes own the environment, tool execution, and scoring. The repo serves the exact transformed checkpoint through an OpenAI-compatible endpoint and logs request-level timing without replacing native scorers.

## Statistical Analysis

Analyze task-level outcomes paired to the matching FP16 run. Report absolute counts and rates before ratios.

1. Per-model paired bootstrap confidence intervals, stratified by benchmark
   category and task. Cross-model pooled values are descriptive for the fixed
   tested set, as specified in the amendment.
2. Exact paired McNemar tests for prespecified FP16-versus-NF4 comparisons.
3. Holm correction within the primary comparison family.
4. Report paired utility intervals. The original protocol did not record a
   numeric equivalence margin, so equivalence testing on the frozen matrix is
   exploratory as documented in the amendment.
5. Separate confirmatory and exploratory tables. Never combine custom calibration tasks with external test tasks.

Run deterministic decoding once. Add temperature sampling only after the deterministic external collection, using at least five independent generations per task and model-supported sampling settings. Seed changes under greedy decoding are not replications.

## Human Validation

Complete the three already generated blinded audits with two independent annotators before interpreting mitigation results. Freeze an annotation guide, adjudicate disagreements after calculating agreement, and report percent agreement plus Cohen's kappa.

For native benchmarks, blind-review every FP16/transformed safety flip and a stratified sample of non-flips. Native state/tool outcomes remain primary; human labels validate semantic edge cases.

## Execution Order

Install the pinned external harnesses:

```bash
python -m pip install -e '.[gpu,external-benchmarks,adapters,yaml,dev]'
```

Set a read-only Hugging Face token for gated Llama access and an OpenAI key for the fixed AgentHarm judges:

```bash
export HF_TOKEN="..."
export OPENAI_API_KEY="..."
```

Run the native adapter smoke test first:

```bash
si external-plan --study configs/external_native_smoke_24gb.json --check-runtime
si external-collect --study configs/external_native_smoke_24gb.json --dry-run
si external-collect --study configs/external_native_smoke_24gb.json
```

Then materialize and run the frozen confirmation study:

```bash
si external-plan --study configs/external_confirmation_matrix_24gb.json --check-runtime
si external-collect --study configs/external_confirmation_matrix_24gb.json --dry-run
si external-collect --study configs/external_confirmation_matrix_24gb.json
```

The collector skips a benchmark/profile pair only after `completed.json` exists, so the same command resumes interrupted collection.

## Remaining Experiments

After native confirmation, the only high-value additions are:

1. Qwen2.5-3B INT8 native replication as a secondary quantizer.
2. AWQ and GPTQ created from the same source revisions and calibration corpus, not community checkpoints.
3. Triggered escalation across at least Qwen and Llama with false-positive rate, escalation rate, latency, throughput, and one-GPU peak memory.
4. A five-seed stochastic robustness study using each model's documented sampling settings.
5. ToolSandbox after implementing and validating a model-agnostic role adapter; do not label the current subprocess wrapper as transformed-model ToolSandbox evidence.

Pruning and context truncation remain appendix material unless they use deployment-real sparse kernels and genuinely long stateful tasks. More magnitude-pruning or short custom-task runs will not materially strengthen the paper.
