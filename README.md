# Safety Invariance

Safety Invariance is a research repo for testing whether one-GPU deployment
transformations preserve the safety behavior of tool-using LLM agents.

The central question is:

> If the checkpoint, prompts, tools, environment state, and native benchmark
> scorer are fixed, does a transformed model take the same safe or unsafe action
> as the full-precision model?

The current pilot focuses on post-training quantization of local Hugging Face
models evaluated with native AgentDojo and AgentHarm harnesses.

## Current Takeaway

The strongest supported claim is not that quantization always makes agents less
safe. The more careful claim is:

> Quantization is not behaviorally safety-invariant for tool-using agents:
> aggregate scores can remain nearly unchanged while individual executable
> safety decisions flip.

Current Qwen2.5-3B AgentDojo evidence:

|comparison|matched cases|aggregate security|security flips|safe-to-unsafe|unsafe-to-safe|
|---|---:|---:|---:|---:|---:|
|FP16 vs NF4 4-bit|2,065|0.110 -> 0.108|73|39|34|
|FP16 self-repeat subset|65|0.677 -> 0.662|5|3|2|
|FP16 vs NF4 subset|65|0.677 -> 0.492|24|18|6|
|FP16 vs INT8 subset|65|0.677 -> 0.615|18|11|7|

The deterministic repeat subset is important: the FP16-vs-NF4 flip rate on the
same 65 cases is 36.9%, compared with a 7.7% FP16 self-repeat noise floor.
The INT8 subset flip rate is 27.7%. This suggests the observed flips are not
explained by deterministic execution noise alone.

Capability conditioning remains a real caveat. In the full FP16-vs-NF4
AgentDojo attack set, native utility is not uniformly worse under NF4:

|metric|FP16|NF4 4-bit|
|---|---:|---:|
|paired attack-case utility|0.180|0.198|
|benign utility, workspace/banking|0.214|0.214|
|benign utility, travel/slack|0.220|0.195|

However, only a small subset of raw safe-to-unsafe flips preserve native utility
under both models. Final analyses should therefore report both raw paired safety
flips and capability-conditioned safety flips.

## Key Artifacts

- [Full Qwen2.5-3B native external summary](reports/native_external_qwen25_3b_full_agentdojo_summary.md)
- [Full AgentDojo paired flip report](reports/agentdojo_qwen25_3b_paired_flips.md)
- [Deterministic repeat noise-floor report](reports/qwen25_3b_agentdojo_noise_floor.md)
- [INT8 subset paired flip report](reports/qwen25_3b_int8_subset_paired_flips.md)
- [Research positioning and evidence plan](docs/RESEARCH_POSITIONING.md)
- [Confirmatory protocol](docs/CONFIRMATORY_PROTOCOL.md)
- [University lab outreach email](docs/UNIVERSITY_LAB_OUTREACH_EMAIL.md)

Raw benchmark logs are intentionally not tracked in normal Git. Compact Markdown
and JSON reports are committed when they are useful for review.

## What This Repo Provides

- Local Hugging Face model loading for FP16, INT8, and NF4 4-bit variants.
- Optional GPTQ/AWQ repo stubs, LoRA merge stubs, pruning stubs, and context
  compression variants for future work.
- OpenAI-compatible local serving for native external benchmarks.
- Native AgentDojo and Inspect/AgentHarm collection through exact local model
  profiles.
- In-repo custom safety tasks for privacy, confirmation, unsafe tool use,
  prompt injection, goal hijacking, and harmful compliance diagnostics.
- Structured run artifacts: manifests, event logs, scores, summaries, and
  native benchmark logs.
- Paired AgentDojo flip analysis by suite, task, injection, and attack type.
- Deterministic repeat noise-floor analysis.
- Selective-precision calibration and held-out reports for mechanism probes.

## Installation

For local smoke tests:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
```

For GPU-backed native benchmark runs:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[gpu,external-benchmarks,adapters,yaml,dev]'
```

If using gated models such as Llama:

```bash
export HF_TOKEN="your_huggingface_read_token"
```

AgentHarm scoring uses external judge models in the current configuration. For
AgentHarm runs, set the relevant judge API key, for example:

```bash
export OPENAI_API_KEY="your_openai_key"
```

AgentDojo runs do not require an OpenAI key when using local models.

## Quick Checks

Run a no-GPU smoke test:

```bash
si smoke --out runs/smoke
si report --runs 'runs/smoke/*' --out reports/smoke.md
```

Validate a GPU instance:

```bash
python - <<'PY'
import torch
print("torch", torch.__version__)
print("cuda available", torch.cuda.is_available())
print("cuda", torch.version.cuda)
print("device", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
print("vram gb", round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2) if torch.cuda.is_available() else None)
PY
```

## Native External Evaluation

The external-study runner starts a local OpenAI-compatible server for each model
profile, then runs native benchmark CLIs against that server. It records the
exact commands, package versions, server telemetry, and native logs.

Smoke test:

```bash
si external-plan --study configs/external_native_smoke_24gb.json --check-runtime
si external-collect --study configs/external_native_smoke_24gb.json --dry-run
si external-collect --study configs/external_native_smoke_24gb.json
```

Main native confirmation matrix:

```bash
si external-plan --study configs/external_confirmation_matrix_24gb.json --check-runtime
si external-collect --study configs/external_confirmation_matrix_24gb.json --dry-run
si external-collect --study configs/external_confirmation_matrix_24gb.json
```

Remaining AgentDojo travel/slack suites:

```bash
si external-plan --study configs/external_agentdojo_remaining_suites_extension_48gb.json --check-runtime
si external-collect --study configs/external_agentdojo_remaining_suites_extension_48gb.json --dry-run
si external-collect --study configs/external_agentdojo_remaining_suites_extension_48gb.json
```

Small deterministic repeat/noise-floor study:

```bash
si external-plan --study configs/external_noise_floor_qwen25_3b_24gb.json --check-runtime
si external-collect --study configs/external_noise_floor_qwen25_3b_24gb.json --dry-run
si external-collect --study configs/external_noise_floor_qwen25_3b_24gb.json
```

Tiny INT8 subset check on the same 65-case subset:

```bash
si external-plan --study configs/external_qwen25_3b_int8_subset_24gb.json --check-runtime
si external-collect \
  --study configs/external_qwen25_3b_int8_subset_24gb.json \
  --profile qwen25_3b_int8_subset \
  --dry-run
si external-collect \
  --study configs/external_qwen25_3b_int8_subset_24gb.json \
  --profile qwen25_3b_int8_subset
```

## Report Generation

Aggregate native report:

```bash
si external-report \
  --root runs/native_external_confirmation_24gb \
  --root runs/native_agentdojo_remaining_suites_extension_48gb \
  --candidate-profile qwen25_3b_nf4 \
  --candidate-profile qwen25_3b_nf4_safety_b20_frozen \
  --candidate-profile qwen25_3b_nf4_utility_b20_frozen \
  --out reports/native_external_qwen25_3b_full_agentdojo_summary.md \
  --json-out reports/native_external_qwen25_3b_full_agentdojo_summary.json
```

Paired AgentDojo flip report:

```bash
si agentdojo-pairs \
  --root runs/native_external_confirmation_24gb \
  --root runs/native_agentdojo_remaining_suites_extension_48gb \
  --candidate-profile qwen25_3b_nf4 \
  --candidate-profile qwen25_3b_nf4_safety_b20_frozen \
  --candidate-profile qwen25_3b_nf4_utility_b20_frozen \
  --out reports/agentdojo_qwen25_3b_paired_flips.md \
  --json-out reports/agentdojo_qwen25_3b_paired_flips.json
```

Noise-floor report:

```bash
si agentdojo-noise-floor \
  --root runs/native_external_confirmation_24gb \
  --root runs/native_agentdojo_remaining_suites_extension_48gb \
  --repeat-root runs/native_qwen25_3b_noise_floor_24gb \
  --out reports/qwen25_3b_agentdojo_noise_floor.md \
  --json-out reports/qwen25_3b_agentdojo_noise_floor.json
```

INT8 subset paired report:

```bash
si agentdojo-pairs \
  --root runs/native_external_confirmation_24gb \
  --root runs/native_agentdojo_remaining_suites_extension_48gb \
  --root runs/native_qwen25_3b_int8_subset_24gb \
  --candidate-profile qwen25_3b_int8_subset \
  --out reports/qwen25_3b_int8_subset_paired_flips.md \
  --json-out reports/qwen25_3b_int8_subset_paired_flips.json
```

## Selective Precision And Mechanism Probes

The repo includes custom-task selective-precision studies that restore
individual transformer blocks and evaluate whether safety behavior recovers
under a fixed memory budget. These are currently best treated as mechanism
probes and exploratory mitigation evidence, not the headline claim.

Example workflow:

```bash
si selective-plan --study configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json
si selective-margin-collect --study configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json
si selective-analyze --study configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json
si collect --matrix configs/generated/qwen3b_nf4_margin_expanded_evaluation_matrix.json
si selective-report --study configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json
```

## Current Limitations

- The strongest results are currently concentrated on Qwen2.5-3B. Replication
  across stronger model families is needed.
- Raw safety flips are not all safety-specific. Capability-conditioned analyses
  and human audits are required.
- Selective precision is not yet a clean mitigation win; current evidence is
  better framed as mechanism probing.
- AgentHarm results are mixed and must be interpreted jointly with benign
  capability.
- Full paper-grade claims require human validation, paired statistics, and
  broader quantizers such as AWQ/GPTQ from the same source checkpoints.

## Recommended Next Steps

1. Human-audit every paired safety flip plus a stratified non-flip sample.
2. Add paired confidence intervals and McNemar tests to the native reports.
3. Replicate the paired-invariance analysis on Llama-3.1-8B, Qwen3-8B, and a
   Gemma-family model.
4. Add deployment-native quantizers: AWQ and GPTQ generated from the same pinned
   source checkpoints.
5. Compare mixed precision with system-level triggered escalation under real
   memory, latency, and throughput budgets.

## Citation And Status

This is an active research repo, not a polished library. The current results are
best treated as a strong pilot for a safety-invariance paper on transformed
tool-using agents.
