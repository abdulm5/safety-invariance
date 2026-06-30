# Final University Lab Outreach Email

## Recommended Email

Subject: Research collaboration on safety invariance in quantized LLM agents

Dear Professor [Last Name],

I am an independent researcher working on a project about whether deployment transformations, especially quantization, preserve safety behavior in tool-using LLM agents. I am reaching out because your group’s work on [specific lab topic] seems closely aligned with the questions I am studying.

The core question is simple: if the checkpoint, tools, prompts, environment state, and native benchmark scorer are fixed, does a quantized agent take the same safe or unsafe action as the full-precision agent?

I have built a reproducible Python harness for local model serving, native AgentDojo/AgentHarm evaluation, structured artifacts, and paired safety-flip analysis. The strongest preliminary signal is on Qwen2.5-3B:

- Across 2,065 matched native AgentDojo cases, aggregate security is nearly unchanged: 0.110 for FP16 versus 0.108 for NF4 4-bit.
- Underneath that aggregate, there are 73 paired security flips: 39 safe-to-unsafe and 34 unsafe-to-safe.
- On a deterministic repeat subset of 65 cases, the self-repeat noise floor is 7.7%, while the FP16-vs-NF4 flip rate is 36.9%, about 4.8x higher.
- On the same 65-case subset, FP16-vs-INT8 has an additional 27.7% paired security flip rate, suggesting the effect is not specific to NF4.

This does not support the simplistic claim that quantization always makes agents less safe. The more careful claim is that deployment transformations are not behaviorally safety-invariant: they can induce task-specific execution flips that cancel out in aggregate metrics.

I am looking for mentorship and compute access to turn this pilot into a rigorous paper. The next steps are to replicate across stronger model families and real quantizers, human-audit the paired flips, run capability-conditioned analyses, and compare model-internal mixed precision with system-level escalation. Access to 48GB+ GPUs or lab cloud credits would materially help, but I would also value feedback on experimental design and paper positioning.

If this is relevant to your group, I would be grateful for the chance to share the repo, current reports, and a short research plan. I would also be happy to adapt the project toward your lab’s interests if there is a good fit.

Best,

Abdul Mohammad

## Optional Follow-Up / Attachment Text

Working title: Safety Is Not Quantization-Invariant: Paired Safety Flips in Tool-Using LLM Agents

The project tests the following invariance question:

> If the model checkpoint, tools, prompts, environment state, and native benchmark scorer are fixed, does a deployment transformation preserve whether the agent takes a safe or unsafe action?

Current pilot evidence:

- Qwen2.5-3B FP16 vs NF4 on 2,065 matched native AgentDojo cases.
- Aggregate security: 0.110 FP16 vs 0.108 NF4.
- Paired security flips: 73 total, with 39 safe-to-unsafe and 34 unsafe-to-safe.
- Deterministic repeat subset: 7.7% self-repeat flip rate.
- Same subset FP16 vs NF4: 36.9% flip rate.
- Same subset FP16 vs INT8: 27.7% flip rate.

Planned next steps:

- replicate on stronger model families such as Llama-3.1-8B, Qwen3-8B, and Gemma-family models;
- compare NF4, INT8, AWQ, and GPTQ generated from the same source checkpoints;
- human-audit every paired safety flip plus a non-flip sample;
- report paired statistics, capability-conditioned safety, latency, throughput, and VRAM;
- test whether mixed precision or triggered escalation can reduce unsafe flips under a real one-GPU budget.

I can contribute the existing codebase, pilot data, experiment execution, analysis scripts, and paper drafting. I am especially looking for guidance on experimental design, human validation, statistical framing, and access to compute for confirmatory runs.
