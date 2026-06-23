# Safety Invariance

Measuring whether one-GPU deployment transformations preserve LLM-agent safety behavior as well as they preserve ordinary task utility.

The repo supports:

- mock-model smoke runs without a GPU
- Hugging Face model loading for FP16, 8-bit, and NF4 4-bit variants
- GPTQ/AWQ pre-quantized Hugging Face repos, PEFT LoRA merge, magnitude pruning, and context compression variants
- custom, AgentDojo-style, chat-safety, AgentHarm-lite, SAD-style, and utility task fixtures
- structured run artifacts
- utility retention, safety retention, and Safety-Utility Gap reporting
- causal block-restoration calibration, held-out mixed-precision controls, mechanism probes, and safety-triggered safer-profile reruns

## Quick Start

```bash
PYTHONPATH=src python3 -m safety_invariance.cli smoke --out runs/smoke
PYTHONPATH=src python3 -m safety_invariance.cli report --runs 'runs/smoke/*' --out reports/smoke.md
PYTHONPATH=src python3 -m safety_invariance.cli collect --matrix configs/data_collection_matrix_mock.json --dry-run
```

Install the package locally if you want the `si` console command:

```bash
python3 -m pip install -e '.[dev]'
si smoke --out runs/smoke
```

GPU-backed runs require optional dependencies:

```bash
python3 -m pip install -e '.[gpu,benchmarks,adapters,yaml,dev]'
si validate --matrix configs/data_collection_matrix_24gb.json
si collect --matrix configs/data_collection_matrix_24gb.json --dry-run
```

## Core Metrics

```text
utility_retention = utility_after_transform / utility_before_transform
safety_retention = safety_after_transform / safety_before_transform
safety_utility_gap = utility_retention - safety_retention
```

When a baseline score is zero, the corresponding retention is reported as `null` because the ratio is undefined.

## Artifacts

Each run directory contains:

- `manifest.json`: run metadata, package versions, GPU metadata, model and transform specs
- `events.jsonl`: per-task prompts, outputs, parsed tool calls, safety events, and timing
- `scores.json`: utility and safety scores with failure-rate metrics
- `summary.csv`: one row suitable for paper tables

## Selective-Precision Pilot

The Qwen2.5-3B/NF4 pilot restores each transformer block independently and measures how much it recovers FP16 preferred-versus-dispreferred completion margins. The selector subtracts utility-margin damage, then evaluates the ranking against utility-ranked, first/last, repeated random, and reverse controls on disjoint behavioral tasks:

```bash
si selective-plan --study configs/qwen3b_nf4_selective_precision_study_24gb.json
si collect --matrix configs/generated/qwen25_3b_nf4_selective_precision_24gb_calibration_matrix.json
si selective-margin-collect --study configs/qwen3b_nf4_selective_precision_study_24gb.json
si selective-analyze --study configs/qwen3b_nf4_selective_precision_study_24gb.json
si collect --matrix configs/generated/qwen3b_nf4_margin_evaluation_matrix.json
si selective-report --study configs/qwen3b_nf4_selective_precision_study_24gb.json
si mechanistic-analyze \
  --study configs/qwen3b_nf4_selective_precision_study_24gb.json \
  --out reports/qwen3b_nf4_mechanistic_calibration.json
```

Margin collection checkpoints its artifact after every transform and resumes by default. For NF4, the loader initializes the complete quantized model first and then replaces selected blocks from a CPU FP16 reference checkpoint. It fails the run if a selected block is missing, remains quantized, or causes an unselected block to remain at high precision.

After the pilot is backed up, generate the powered held-out study from the same frozen calibration artifacts:

```bash
si selective-analyze \
  --study configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json
si collect \
  --matrix configs/generated/qwen3b_nf4_margin_expanded_evaluation_matrix.json
si selective-report \
  --study configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json
```

The expanded study has 64 held-out safety outcomes, 9 utility/benign outcomes, and 100 random block controls at each of four budgets. Reports whitelist transforms from the generated evaluation matrix, keep individual random controls in JSON, and test net reduction of FP16-to-NF4 safety regressions with conservative empirical p-values and Holm correction. These custom tasks improve power for the mechanism study but do not replace full external benchmark evaluation.

Create a blinded audit packet for the FP16/NF4/b20 flips, then score two completed independent annotation files:

```bash
si selective-audit \
  --study configs/qwen3b_nf4_selective_precision_expanded_study_24gb.json \
  --intervention-transform selective_margin_safety_b20 \
  --out reports/qwen3b_nf4_b20_blinded_audit.md

si selective-audit-score \
  --key reports/qwen3b_nf4_b20_blinded_audit.key.json \
  --annotations reports/qwen3b_nf4_b20_blinded_audit.annotator_1.csv \
  --annotations reports/qwen3b_nf4_b20_blinded_audit.annotator_2.csv \
  --out reports/qwen3b_nf4_b20_human_audit.md
```

Focused 20% replication studies are defined for `Llama-3.1-8B-Instruct` with NF4 and Qwen2.5-3B with INT8. Each independently recalibrates its block ranking and evaluates 100 random controls.

## Native External Confirmation

The official AgentDojo and Inspect/AgentHarm harnesses can run against the exact local transformed checkpoint through the repo's OpenAI-compatible endpoint. Run the two-profile adapter smoke before the frozen 60-run confirmation matrix:

```bash
python -m pip install -e '.[gpu,external-benchmarks,adapters,yaml,dev]'
si external-plan --study configs/external_native_smoke_24gb.json --check-runtime
si external-collect --study configs/external_native_smoke_24gb.json

si external-plan --study configs/external_confirmation_matrix_24gb.json --check-runtime
si external-collect --study configs/external_confirmation_matrix_24gb.json --dry-run
si external-collect --study configs/external_confirmation_matrix_24gb.json
```

The collector preserves native logs and scorers, records exact commands and package versions, and resumes only completed profile/benchmark pairs. See [docs/CONFIRMATORY_PROTOCOL.md](docs/CONFIRMATORY_PROTOCOL.md) for frozen hypotheses, analysis rules, human validation, and follow-on experiments.

The current literature boundary, defensible novelty claim, capability-conditioned estimands, and non-destructive extension plan are documented in [docs/RESEARCH_POSITIONING.md](docs/RESEARCH_POSITIONING.md). A dated [protocol amendment](docs/PROTOCOL_AMENDMENT_2026-06-21.md) transparently corrects the two-suite AgentDojo scope and the missing numeric equivalence margin without changing the frozen matrix or invalidating collected runs.

## Scope

See [docs/DATA_COLLECTION.md](docs/DATA_COLLECTION.md) for the full data-collection workflow. The legacy bitsandbytes skip-module backend remains available by explicit transform metadata, but the verified post-load replacement backend is the default for NF4.
