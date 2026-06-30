# One-Page Collaboration Brief

Subject: Collaboration request: safety invariance of quantized tool-using LLM agents

Dear Professor [Name],

I am working on a research project studying whether common one-GPU deployment transformations, especially quantization and mixed precision, preserve safety behavior in tool-using LLM agents. I have built an open-source experimental harness and collected pilot results suggesting that quantized agents can preserve similar aggregate benchmark scores while flipping individual executable safety decisions. I am looking for research mentorship and compute access to turn the current pilot into a rigorous conference-quality study.

## Project

**Working title:** Safety Is Not Quantization-Invariant: Paired Safety Flips in Tool-Using LLM Agents

Modern LLM agents are often compressed before deployment, but most safety evaluations compare aggregate scores rather than matched execution traces. This project tests a stricter invariance question:

> If the model checkpoint, tools, prompts, environment state, and scorer are fixed, does a deployment transformation preserve whether the agent takes a safe or unsafe action?

The current focus is post-training quantization and safety-aware mixed precision on executable agent benchmarks such as AgentDojo and AgentHarm.

## Preliminary Evidence

I implemented a reproducible Python research repo with local model serving, native benchmark runners, structured artifacts, paired diagnostics, and report generation. Current Qwen2.5-3B results include native AgentDojo and AgentHarm runs across FP16, NF4 4-bit, and two frozen mixed-precision interventions.

Initial paired AgentDojo analysis:

- 2,065 matched FP16-vs-NF4 AgentDojo cases for Qwen2.5-3B.
- Aggregate security is nearly unchanged: 0.110 for FP16 versus 0.108 for NF4.
- Underneath that aggregate, there are 73 paired security flips.
- 39 cases are safe-to-unsafe regressions and 34 are unsafe-to-safe improvements.
- This supports the hypothesis that aggregate safety scores can hide execution-level safety instability.

AgentHarm results are mixed rather than one-directional: NF4 lowers the harmful score but also lowers benign capability. This is useful because it pushes the paper toward a more careful claim about safety invariance and capability-conditioned evaluation, rather than the weaker claim that quantization always makes agents less safe.

## Research Contribution

The project aims to contribute:

1. A paired safety-invariance protocol for transformed tool-using agents.
2. Evidence that aggregate safety and utility scores can conceal security-relevant action flips.
3. Capability-conditioned analysis separating safety from task inability.
4. Human-audited flip validation on native benchmark trajectories.
5. A comparison of full quantization, mixed precision, and system-level escalation under real memory and latency budgets.

This complements existing quantization-safety work by focusing on executable agent trajectories, tool calls, irreversible actions, and matched environment states rather than only chatbot responses.

## What I Need

The bottleneck is compute for confirmatory external benchmark coverage. I am looking for access to one or more 48GB+ GPUs, or lab cloud credits, to run:

- Llama-3.1-8B, Qwen3-8B, and Gemma-family replications.
- NF4, INT8, AWQ, and GPTQ generated from the same source checkpoints.
- Full native AgentDojo and AgentHarm paired evaluations.
- Deterministic repeat subsets to estimate the execution noise floor.
- Post-hoc trajectory replay for margin, entropy, and logit-divergence analysis.

An ideal setup would be 1-2 L40/A40/A6000/A100-class GPUs for several weeks, plus storage for benchmark artifacts. The project can start with smaller batches and checkpoint after each run.

## Collaboration Fit

I would be glad to collaborate with a lab interested in LLM agents, AI safety evaluation, model compression, efficient inference, or trustworthy deployment. I can contribute the existing codebase, pilot data, experiment execution, analysis scripts, and paper drafting. I am especially looking for guidance on experimental design, statistical framing, human evaluation, and positioning for venues such as NeurIPS, ICML, ICLR, or NeurIPS Datasets and Benchmarks.

If this seems aligned with your group, I would appreciate the chance to share the repo, current reports, and a short research plan.

Best,

Abdul Mohammad

