# University Lab Outreach Email

## Short Version

Subject: Research collaboration on safety invariance in quantized LLM agents

Dear Professor [Last Name],

I am an independent researcher working on a project about whether deployment transformations, especially quantization, preserve safety behavior in tool-using LLM agents. I am reaching out because your group’s work on [specific topic from their lab] seems closely aligned with the questions I am studying.

The core question is: if the checkpoint, tools, prompts, environment state, and native benchmark scorer are fixed, does a quantized agent take the same safe or unsafe action as the full-precision agent?

I have built a reproducible Python research harness and collected initial native AgentDojo and AgentHarm results. The strongest preliminary signal is on Qwen2.5-3B with FP16 versus NF4 4-bit quantization:

- Across 2,065 matched native AgentDojo cases, aggregate security is nearly unchanged: 0.110 for FP16 versus 0.108 for NF4.
- Underneath that aggregate, there are 73 paired security flips: 39 safe-to-unsafe and 34 unsafe-to-safe.
- On a deterministic repeat subset of 65 cases, the FP16/NF4 self-repeat noise floor is 7.7%, while the FP16-vs-NF4 transformation flip rate is 36.9%, about 4.8x higher.

This suggests that aggregate safety scores can hide execution-level safety instability in deployed tool-using agents. The current evidence does not support the simplistic claim that quantization always makes agents less safe; rather, it supports a more precise claim that deployment transformations are not safety-invariant and can induce paired safety flips that cancel out in aggregate metrics.

I am looking for mentorship and compute access to turn this pilot into a rigorous paper. The next steps are to replicate across stronger model families and real quantizers, add human validation of paired flips, run capability-conditioned analyses, and compare model-internal mixed precision with system-level escalation. Access to 48GB+ GPUs or cloud credits would materially help, but I am also looking for feedback on experimental design and paper positioning.

If this is relevant to your group, I would be grateful for the chance to share the repo, current reports, and a short research plan. I would also be happy to adapt the project toward your lab’s interests if there is a good fit.

Best,

Abdul Mohammad

## Slightly More Detailed Version

Subject: Collaboration request: safety invariance of quantized tool-using LLM agents

Dear Professor [Last Name],

I am working on a research project studying whether common one-GPU deployment transformations preserve safety behavior in LLM agents. I am especially focused on post-training quantization because it is widely used in real deployment, but most evaluations compare aggregate scores rather than matched executable trajectories.

The core invariance question is:

> If the model checkpoint, tools, prompts, environment state, and native benchmark scorer are fixed, does a deployment transformation preserve whether the agent takes a safe or unsafe action?

I have built an open-source Python harness that serves local Hugging Face models through an OpenAI-compatible interface, runs native AgentDojo and AgentHarm evaluations, stores structured artifacts, and generates paired safety-flip diagnostics. The current pilot includes Qwen2.5-3B FP16, NF4 4-bit, and frozen mixed-precision interventions.

The main preliminary result is that aggregate preservation can hide paired safety instability. On Qwen2.5-3B, FP16 and NF4 have almost identical aggregate AgentDojo security, 0.110 versus 0.108, across 2,065 matched native cases. But the paired analysis finds 73 security flips: 39 safe-to-unsafe regressions and 34 unsafe-to-safe improvements. I also ran a deterministic repeat subset to estimate the execution noise floor. On 65 matched cases, self-repeat flips are 7.7%, while FP16-vs-NF4 flips are 36.9%, about 4.8x higher.

I think the defensible claim is not that quantization always worsens safety. The more interesting claim is that quantization is not behaviorally safety-invariant for tool-using agents: safety changes can be localized, task-specific, and hidden by aggregate cancellation. This is particularly relevant when the behavioral unit is an executable tool call rather than a chatbot answer.

I am looking for research mentorship and compute access to make the study strong enough for a venue such as NeurIPS, ICML, ICLR, or NeurIPS Datasets and Benchmarks. The highest-value next steps are:

- replicate on stronger model families such as Llama-3.1-8B, Qwen3-8B, and Gemma-family models;
- compare NF4, INT8, AWQ, and GPTQ generated from the same source checkpoints;
- human-audit every paired safety flip plus a non-flip sample;
- report paired statistics, capability-conditioned safety, latency, throughput, and VRAM;
- test whether mixed precision or triggered escalation can reduce unsafe flips under a real one-GPU budget.

I can contribute the existing repo, pilot data, experiment execution, analysis scripts, and paper drafting. I would especially value guidance on experimental design, human validation, and paper framing. If this is aligned with your group, I would appreciate the opportunity to share the repo and a short project brief.

Best,

Abdul Mohammad

