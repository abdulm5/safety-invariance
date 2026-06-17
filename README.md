# Safety Invariance

Measuring whether one-GPU deployment transformations preserve LLM-agent safety behavior as well as they preserve ordinary task utility.

The repo supports:

- mock-model smoke runs without a GPU
- Hugging Face model loading for FP16, 8-bit, and NF4 4-bit variants
- GPTQ/AWQ pre-quantized Hugging Face repos, PEFT LoRA merge, magnitude pruning, and context compression variants
- custom, AgentDojo-style, chat-safety, AgentHarm-lite, SAD-style, and utility task fixtures
- structured run artifacts
- utility retention, safety retention, and Safety-Utility Gap reporting
- selective precision calibration and safety-triggered safer-profile reruns

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

## Scope

See [docs/DATA_COLLECTION.md](docs/DATA_COLLECTION.md) for the full data-collection workflow. True 4-bit mixed-precision module surgery still depends on backend support; the repo calibrates module hints and applies them where the installed quantization backend exposes a skip/not-convert path.
