# Prospective Protocol Amendment: 2026-06-21

## Purpose

This amendment preserves `configs/external_confirmation_matrix_24gb.json` and
all data already collected from it. It documents corrections and additional
analyses identified during a literature and validity audit. It does not change
the original primary endpoint or relabel observed analyses as preregistered.

At the time of this amendment, benign AgentDojo aggregate results had been
inspected. The Qwen2.5-3B direct and tool-knowledge collection had started, but
its completed benchmark outcomes had not been inspected. Therefore, the rules
below are prospective only for unobserved outcomes and explicitly post-hoc where
stated.

## Corrections To Scope

1. The frozen AgentDojo matrix includes `workspace` and `banking`, not all four
   AgentDojo suites. Results from this matrix must be called the two-suite native
   confirmation. `travel` and `slack` will be a separate extension.
2. The original protocol says that a utility equivalence margin is fixed before
   reading external results, but it does not record a numeric margin. No
   confirmatory equivalence claim will be made from that statement. Utility
   differences and paired intervals remain valid; any equivalence analysis is
   exploratory unless a margin is prospectively fixed for a new untouched
   extension.
3. The intentionally included Mistral floor control will not contribute to a
   headline pooled effect when its baseline task capability is insufficient.

## Unchanged Primary Endpoint

The primary endpoint remains the paired FP16-safe to transformed-unsafe
regression rate, reported separately by model and benchmark. Unsafe-to-safe
changes and total flips remain required because aggregate cancellation is a
central hypothesis.

## Required Capability Conditioning

AgentDojo tables will jointly report:

- native security
- benign utility
- utility under attack
- injection-task-as-user-task capability
- safe-to-unsafe regression among capability-eligible task pairs

AgentHarm tables will jointly report harmful task success or refusal and the
matched benign counterpart outcome. Capability-conditioned harmful compliance
is required as a secondary endpoint.

These analyses reduce confounding from agents that appear safe because they
cannot execute the requested tool workflow.

## Deterministic Repeat

A stratified 10% task subset will be selected by a stable hash of benchmark,
suite, and task identifiers before repeat outcomes are read. The same condition
will be run twice on the same GPU class to estimate within-condition self-flips.
This repeat is a measurement-noise analysis, not an independent model seed.

## Prospective Extensions

The following data will not be merged silently into the frozen family:

1. AgentDojo `travel` and `slack` suites.
2. One locally generated AWQ or GPTQ condition from the same pinned checkpoint.
3. One fixed-budget adaptive prompt-injection subset.
4. Controlled warm latency, throughput, and peak-memory repetitions.

Each extension receives a separate configuration, output root, table section,
and multiple-testing family.

The remaining AgentDojo suites are defined in
`configs/external_agentdojo_remaining_suites_extension_48gb.json`. The config
inherits the frozen profiles and replaces only the benchmark list and output
root, preventing profile drift and avoiding any rerun of `workspace` or
`banking`.

Run it on the same 48GB hardware class used for the 8B attack collection:

```bash
si external-plan \
  --study configs/external_agentdojo_remaining_suites_extension_48gb.json \
  --check-runtime
si external-collect \
  --study configs/external_agentdojo_remaining_suites_extension_48gb.json \
  --dry-run
si external-collect \
  --study configs/external_agentdojo_remaining_suites_extension_48gb.json
```

## Post-Hoc Mechanistic Analysis

Stored native trajectories may be replayed for forward-only measurements of
decision entropy, action margin, logit divergence, and trajectory depth. Any
predictor of safety flips will be labeled post-hoc, trained and evaluated on
disjoint tasks, and compared with simple uncertainty and trajectory-length
baselines.

## Interpretation Guardrails

- Do not claim that quantization monotonically decreases safety.
- Do not claim the current action-margin selector is validated unless untouched
  external results support it against random and utility-ranked controls.
- Do not claim that selective high precision is itself novel.
- Do not call bitsandbytes NF4 a speed improvement unless controlled throughput
  measurements show one.
- Do not generalize from the tested fixed model set to all LLMs without an
  explicit model-sampling argument.
