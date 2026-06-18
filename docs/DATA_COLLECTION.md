# Data Collection Guide

This repo is ready to collect Safety Invariance data through the normalized in-repo harness, with optional external AgentDojo runs captured separately.

## 1. No-GPU Rehearsal

Use Python 3.10, 3.11, or 3.12 for GPU instances. The GPU stack (`torch`, `transformers`, `bitsandbytes`) may not have wheels for newer Python releases.

Run this before spending GPU time:

```bash
PYTHONPATH=src python3 -m safety_invariance.cli validate --matrix configs/data_collection_matrix_mock.json
PYTHONPATH=src python3 -m safety_invariance.cli collect --matrix configs/data_collection_matrix_mock.json --dry-run
PYTHONPATH=src python3 -m safety_invariance.cli collect --matrix configs/data_collection_matrix_mock.json
```

Outputs:

- `runs/collection_mock/collection_plan.json`
- one run directory per model/transform
- `reports/collection_mock.md`

## 2. 24GB GPU Collection

Install GPU dependencies:

```bash
python3 -m pip install -e '.[gpu,benchmarks,adapters,yaml,dev]'
```

Run a real-GPU smoke test before the main matrix:

```bash
si preflight --matrix configs/gpu_smoke_matrix_24gb.json
si collect --matrix configs/gpu_smoke_matrix_24gb.json --dry-run
si collect --matrix configs/gpu_smoke_matrix_24gb.json
```

Then validate and dry-run the main matrix:

```bash
si preflight --matrix configs/data_collection_matrix_24gb.json
si validate --matrix configs/data_collection_matrix_24gb.json
si collect --matrix configs/data_collection_matrix_24gb.json --dry-run
```

Run collection:

```bash
si collect --matrix configs/data_collection_matrix_24gb.json
```

The matrix covers:

- Qwen2.5 3B control
- Qwen2.5 7B
- Mistral 7B
- FP16 baseline
- int8
- NF4 4-bit
- magnitude-pruned baseline
- context-truncation deployment variant

Each transformed run is scored against the matching FP16 run for the same model.

Generate a baseline-diff diagnostic report before moving to the expanded matrix:

```bash
si diagnose --runs 'runs/collection_24gb/*' --out reports/collection_24gb_diagnostics.md
```

This report shows safety and utility flips by task, seed, model, and transform, plus distinct task counts so deterministic seed repeats are not mistaken for independent samples. Use it to distinguish real deployment-transform effects from unchanged baseline failures or brittle task scoring.

If the pilot shows a concentrated signal, run the focused Qwen2.5-3B replication before the expanded paper matrix:

```bash
si preflight --matrix configs/qwen3b_signal_replication_matrix_24gb.json
si collect --matrix configs/qwen3b_signal_replication_matrix_24gb.json --dry-run
si collect --matrix configs/qwen3b_signal_replication_matrix_24gb.json
si rescore --runs 'runs/qwen3b_signal_replication_24gb/*' --report reports/qwen3b_signal_replication_24gb.md
si diagnose --runs 'runs/qwen3b_signal_replication_24gb/*' --out reports/qwen3b_signal_replication_24gb_diagnostics.md
```

This matrix uses one deterministic seed and adds more distinct prompt-injection, privacy, unsafe-tool-use, evaluation-sensitivity, confirmation, AgentHarm-style, and chat-safety prompts. It is meant to replicate the pilot signal cheaply before spending on the larger model set.

Use `si rescore` after evaluator changes to update `scores.json` and `summary.csv` from existing `events.jsonl` files without rerunning models.

## 2.5. Rigorous Paper Matrix

For a stronger paper, use:

```bash
si preflight --matrix configs/data_collection_matrix_rigorous_paper.json --check-hf-access
si validate --matrix configs/data_collection_matrix_rigorous_paper.json
si collect --matrix configs/data_collection_matrix_rigorous_paper.json --dry-run
si collect --matrix configs/data_collection_matrix_rigorous_paper.json
```

This matrix adds:

- `meta-llama/Llama-3.1-8B-Instruct`
- `google/gemma-2-9b-it`
- `Qwen/Qwen2.5-1.5B-Instruct`
- the expanded `safety_signal_replication_v1` task suite

The recommended staging is:

1. Run `configs/data_collection_matrix_24gb.json` first.
2. Run `configs/qwen3b_signal_replication_matrix_24gb.json` to verify the quantization signal on more distinct prompts.
3. Run `configs/data_collection_matrix_rigorous_paper.json` once the signal replicates.
4. Run `configs/qwen3b_quant_mitigation_matrix_24gb.json` to test whether triggered escalation recovers safety retention.
5. Run `configs/qwen3b_stochastic_robustness_matrix_24gb.json` to check whether the Qwen2.5-3B quantization gap survives stochastic decoding.
6. Run the deep transform templates for Qwen and Llama after filling AWQ/GPTQ/LoRA repo IDs.

This keeps early iteration cheap while preserving a credible main-paper path.

The deterministic matrices use one seed. Repeating seeds with `temperature=0.0` should not be treated as independent evidence; use more distinct tasks or the stochastic robustness matrix instead.

## 3. External Benchmark Samples

The repo includes small built-in suites under `data/tasks/`. To create larger samples from Hugging Face datasets:

```bash
si make-suite --source gsm8k --limit 100 --out data/tasks/gsm8k_100.json
si make-suite --source mmlu --limit 100 --out data/tasks/mmlu_100.json
si make-suite --source mbpp --limit 100 --out data/tasks/mbpp_100.json
si make-suite --source humaneval --limit 100 --out data/tasks/humaneval_100.json
```

Then add the generated task JSON files to a matrix `task_paths` list.

## 4. AgentDojo Native Runs

AgentDojo has its own benchmark runner. Capture native runs like this:

```bash
python3 -m pip install -e '.[agentdojo]'
si run-agentdojo \
  --model gpt-4o-2024-05-13 \
  --suite workspace \
  --user-task user_task_0 \
  --user-task user_task_1 \
  --defense tool_filter \
  --attack tool_knowledge \
  --out-dir runs/agentdojo/workspace_gpt4o
```

Use `--dry-run` first to write the exact command without executing it.

## 5. ToolSandbox Native Runs

ToolSandbox also runs through its native CLI. Capture dry-run commands like this:

```bash
si run-toolsandbox \
  --agent Gorilla \
  --user GPT_4_o_2024_05_13 \
  --scenario wifi_off \
  --out-dir runs/toolsandbox/gorilla_wifi_off \
  --dry-run
```

Install ToolSandbox from its upstream repository and configure required API keys before running without `--dry-run`.

## 6. GPTQ, AWQ, And LoRA Merge

Use `configs/templates/gptq_awq_lora_matrix_template.json` and replace:

- `REPLACE_WITH_GPTQ_HF_REPO`
- `REPLACE_WITH_AWQ_HF_REPO`
- `REPLACE_WITH_PEFT_ADAPTER_REPO`

The GPTQ/AWQ path expects a pre-quantized Hugging Face repo. The LoRA path loads the base model, loads the PEFT adapter, and calls `merge_and_unload()`.

For the two most important targets, use the dedicated templates:

- `configs/templates/qwen25_7b_deep_transforms_template.json`
- `configs/templates/llama31_8b_deep_transforms_template.json`

These are intentionally per-model because AWQ and GPTQ repos are model-specific.

## 6.5. Judge And Guard Models

Use `configs/judge_models_open_guard.json` for the planned safety-evaluation judges:

- `allenai/wildguard`
- `meta-llama/Llama-Guard-3-8B`
- human audit sample

Do not treat these as target models. They are for labeling outputs and checking that safety conclusions are not caused by one judge.

## 7. Causal Selective Safety-Preserving Precision

The main selective-precision pilot uses disjoint calibration and evaluation suites. Binary pass/fail flips are too sparse for layer selection. Instead, each calibration task defines a preferred safe/correct completion and a dispreferred unsafe/incorrect completion. The selector restores one quantized block at a time, measures recovery of the FP16 preference margin on baseline-safe tasks, and subtracts utility-margin damage.

Generate and inspect the 38-run calibration matrix:

```bash
si selective-plan \
  --study configs/qwen3b_nf4_selective_precision_study_24gb.json

si preflight \
  --matrix configs/generated/qwen25_3b_nf4_selective_precision_24gb_calibration_matrix.json

si collect \
  --matrix configs/generated/qwen25_3b_nf4_selective_precision_24gb_calibration_matrix.json \
  --dry-run

si collect \
  --matrix configs/generated/qwen25_3b_nf4_selective_precision_24gb_calibration_matrix.json
```

Collect dense action margins for FP16, full NF4, and every single-block restoration. The artifact is written after every transform and resumes after interruption:

```bash
si selective-margin-collect \
  --study configs/qwen3b_nf4_selective_precision_study_24gb.json
```

Rank blocks by action-margin recovery per added GiB and generate the held-out matrix:

```bash
si selective-analyze \
  --study configs/qwen3b_nf4_selective_precision_study_24gb.json

si preflight \
  --matrix configs/generated/qwen3b_nf4_margin_evaluation_matrix.json

si collect \
  --matrix configs/generated/qwen3b_nf4_margin_evaluation_matrix.json \
  --dry-run

si collect \
  --matrix configs/generated/qwen3b_nf4_margin_evaluation_matrix.json
```

The held-out matrix evaluates 5%, 10%, 20%, and 30% high-precision budgets against:

- action-margin safety-selected blocks
- utility-margin-selected blocks
- first and last blocks
- ten deterministic random controls per budget
- reverse interventions that quantize only the selected safety-sensitive blocks
- full NF4 and FP16 endpoints

Generate paired bootstrap intervals, exact McNemar tests, recovery counts, deployment measurements, and direct selected-versus-random summaries:

```bash
si selective-report \
  --study configs/qwen3b_nf4_selective_precision_study_24gb.json
```

Probe FP16/NF4 hidden-state divergence, next-token distribution divergence, safety-action margins, and correlation with causal recovery:

```bash
si mechanistic-analyze \
  --study configs/qwen3b_nf4_selective_precision_study_24gb.json \
  --split calibration \
  --out reports/qwen3b_nf4_mechanistic_calibration.json
```

The NF4 loader first initializes every quantized layer normally, loads a CPU FP16 reference checkpoint, and replaces only the selected blocks on their target device. This avoids partially initialized bitsandbytes layers observed with skip-module loading on newer CUDA/PyTorch stacks. The loader records parameter cost, model footprint, peak CUDA allocation, restoration backend, device, and dtype in each manifest. It aborts when a requested block is missing, remains quantized, or causes an unselected block to remain at high precision.

### Legacy Trace-Heuristic Calibration

After collecting a baseline and transformed run:

```bash
si calibrate-selective \
  --baseline-run-dir runs/collection_24gb/qwen25_7b_fp16 \
  --candidate-run-dir runs/collection_24gb/qwen25_7b_nf4_4bit \
  --out configs/generated/qwen25_7b_nf4_selective.json \
  --max-modules 4
```

The legacy output contains:

- divergence counts by safety failure kind
- selected high-precision module hints
- a transform block to copy into a collection matrix

Use this legacy command only to reproduce earlier artifacts. It maps failure categories to fixed module hints and is not evidence for a mechanistic or causal claim.

## 8. Safety-Triggered Escalation

`configs/mitigation_matrix_mock.json` rehearses triggered escalation without a GPU. For GPU collection, copy the mitigation block into a 24GB matrix and set `safer_model` to the FP16 or selective-precision profile you want to use for reruns.

The event log records:

- initial output
- initial tool calls
- initial safety events
- final safer-profile output
- escalation rate

## 9. Collection Acceptance Checks

Before treating results as paper data:

```bash
si validate --matrix <matrix>
si report --runs 'runs/<collection>/*' --out reports/<collection>.md
PYTHONPATH=src python3 -m unittest discover -s tests
```

Check that every transformed run has:

- `manifest.json`
- `events.jsonl`
- `scores.json`
- `summary.csv`
- non-null retention values against the matching FP16 baseline
