# Research Positioning And Evidence Plan

Last reviewed: 2026-06-21.

## Defensible Paper Claim

The paper should make one primary claim:

> Post-training quantization is not behaviorally safety-invariant for tool-using
> agents. Matched full-precision and quantized agents can take different
> security-relevant actions on the same executable task even when aggregate
> utility and safety scores are nearly unchanged.

The unit of evidence is a paired task and environment state, not a difference
between unpaired benchmark averages. The primary adverse endpoint is a task on
which the full-precision agent is safe and the transformed agent is unsafe.

The paper should not claim that quantization always reduces safety. Both
safe-to-unsafe and unsafe-to-safe changes are expected, and cancellation is part
of the motivating result. It should also not claim that safety-aware mixed
precision is new in general or that the current action-margin selector is an
effective mitigation. The existing cross-model and cross-quantizer selector
results do not support that claim.

## Relationship To Prior Work

### Safety under quantization

- [Q-resafe](https://arxiv.org/abs/2506.20251) evaluates safety degradation
  across several quantization methods and proposes quantization-aware safety
  patching. It establishes that ordinary chatbot safety can degrade after
  quantization.
- [Alignment-Aware Quantization](https://arxiv.org/abs/2511.07842) places an
  alignment-preserving contrastive objective inside post-training quantization.
  It is a direct baseline for any claim that a safety-aware quantizer preserves
  alignment.
- [Critical Weight Protection](https://arxiv.org/abs/2601.12033) identifies and
  preserves fairness- and safety-critical weights during quantization. This
  means selective high precision cannot by itself be presented as the paper's
  novelty.
- [Q-realign](https://arxiv.org/abs/2601.08089) treats quantization and safety
  recovery as a joint deployment operation after fine-tuning.
- [Uncertainty Drives Social Bias Changes in Quantized LLMs](https://openreview.net/forum?id=fc6iDWDtpg)
  reports that aggregate bias scores can hide paired response flips. The present
  project must distinguish itself through executable agent trajectories,
  security outcomes, capability conditioning, and irreversible tool actions.

### Agent safety evaluation

- [AgentDojo](https://arxiv.org/abs/2406.13352) provides executable tool-use
  environments, benign utility tasks, and prompt-injection security cases. Its
  native environment and scorers should remain primary for prompt-injection
  claims.
- [AgentHarm](https://arxiv.org/abs/2410.09024) provides harmful multi-step
  agent tasks and benign counterparts. Harmful compliance should be interpreted
  jointly with benign counterpart capability.
- [ToolSandbox](https://arxiv.org/abs/2408.04682) provides stateful multi-turn
  tasks with milestone and minefield scoring. It is useful for testing
  clarification, insufficient information, and premature irreversible actions.
- [AgentDyn](https://arxiv.org/abs/2602.03117) and
  [AutoDojo](https://arxiv.org/abs/2606.15057) show that static prompt-injection
  suites can overstate robustness. One adaptive or dynamic attack extension is
  valuable, but it should be a separate extension rather than a replacement for
  the frozen AgentDojo comparisons.

### Efficient mixed precision

- [SliM-LLM](https://openreview.net/forum?id=PO9bBEPNWy) and
  [GANQ](https://openreview.net/forum?id=pkKQGJ5d99) emphasize that a mixed
  precision method must demonstrate a real memory or throughput operating point,
  not only behavioral recovery in a dequantization-based research backend.

## Actual Novelty Boundary

The strongest defensible contributions are:

1. A paired safety-invariance protocol for transformed tool-using agents that
   holds the checkpoint, prompts, tools, environment state, and native scorer
   fixed.
2. Execution-level evidence that aggregate preservation can conceal opposing
   security-relevant behavioral flips.
3. Capability-conditioned analysis that separates safety from inability to use
   tools or complete the underlying task.
4. A causal and predictive analysis of which decision points are susceptible to
   transformation, including honest negative evidence when layer-local
   restoration does not generalize.
5. Deployment Pareto measurements and a comparison between model-internal
   mixed precision and system-level escalation.

This is primarily an agent safety and evaluation paper unless a mitigation
consistently beats random, utility-ranked, first/last, and published
safety-aware quantization baselines on untouched external tasks.

## Estimands

Report the following separately for every model, quantizer, benchmark, and
attack family:

- safe-to-unsafe regression count and rate
- unsafe-to-safe improvement count and rate
- any paired safety flip count and rate
- benign utility regression, improvement, and flip rates
- attack success and utility under attack
- harmful task success and refusal rate
- benign counterpart success
- peak VRAM, warm latency, throughput, and out-of-memory incidence

Two capability-conditioned analyses are required:

1. AgentDojo security among cases for which the relevant user and injection
   tasks are demonstrably solvable. Report the benchmark's native
   injection-task-as-user-task check and utility under attack beside security.
2. AgentHarm harmful compliance paired with performance on the corresponding
   benign behavior. A refusal by an agent that cannot complete the benign task
   is not strong evidence of safety.

Do not use retention ratios as primary endpoints. Report absolute paired rates
first. Do not pool floor-effect models into a headline average.

## Non-Destructive Extensions

These additions reuse completed artifacts and do not require rerunning the
current experiment matrix.

### 1. Complete benchmark coverage

The frozen AgentDojo configuration currently runs `workspace` and `banking`.
Add `travel` and `slack` as a separately labeled extension. Never describe the
two-suite result as full AgentDojo.

The extension is already defined in
`configs/external_agentdojo_remaining_suites_extension_48gb.json`; it inherits
the exact frozen model profiles and runs only the omitted suites.

### 2. Estimate the execution noise floor

Repeat a frozen, stratified 10% subset twice under the identical profile and
hardware. Measure FP16-to-FP16 and quantized-to-quantized self-flip rates. The
transformation effect should be reported relative to this empirical
nondeterminism floor. This is a small repeat, not a new full collection.

### 3. Replay stored trajectories

Use native benchmark logs to reconstruct each assistant decision prefix and run
forward-only scoring with the matching checkpoint. Measure entropy, preferred
action margin, FP16/quantized logit divergence, trajectory depth, and whether an
irreversible tool was available. This avoids rerunning environments and tests
whether uncertainty predicts observed safety flips.

The replay analysis must be post-hoc and predictive, not described as a
preregistered endpoint. Split replay cases before fitting any predictor and
report held-out AUROC/AUPRC with bootstrap intervals.

### 4. Add one deployment-native quantizer

Run AWQ or GPTQ generated from the same pinned source checkpoint and calibration
corpus. Reuse the existing FP16 task outcomes as the paired baseline. Record the
serving backend because changing the agent parser or prompt template would break
the pairing.

### 5. Add one adaptive attack extension

After static AgentDojo collection, run a fixed-budget adaptive attack on a
prespecified subset of baseline-solvable tasks. Keep it separate from the frozen
static attack family and disclose the attacker model, optimization budget, and
selection procedure.

### 6. Finish human validation

Blind-review every safety flip plus a stratified non-flip sample. Two independent
annotators label the native trajectory and final environment effect. Compute
agreement before adjudication. Keep benchmark-native execution outcomes primary.

## Statistical Rules

- Make per-model paired inference primary. With only a few intentionally chosen
  models, do not claim that model-resampling intervals estimate performance over
  the population of all LLMs.
- Use exact McNemar tests for binary paired endpoints and paired bootstrap
  intervals stratified by benchmark category within each model.
- Treat pooled cross-model values as descriptive. A model-stratified bootstrap
  may summarize the tested set but is not population-level evidence.
- Correct the prespecified FP16-versus-quantized family with Holm's procedure.
- Report confidence intervals and effect sizes even when tests are not
  significant.
- Separate confirmatory, prospective-extension, and post-hoc analyses in every
  table and figure.

## Priority Order

1. Finish and back up the currently running Qwen2.5-3B AgentDojo collection.
2. Build the paired native report and complete blinded annotation using the
   stored artifacts.
3. Run AgentHarm harmful/benign pairs and the remaining AgentDojo suites.
4. Run the 8B FP16/transformed pairs on one 48GB hardware class.
5. Add one deployment-native quantizer and controlled systems measurements.
6. Run the small deterministic repeat and trajectory-replay analyses.
7. Add one adaptive attack subset only after the fixed static analysis is
   complete.

More custom prompt sets, magnitude pruning without sparse kernels, or broad
model sweeps with floor-level baseline capability are lower-value than these
steps.
