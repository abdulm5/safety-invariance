# AgentDojo Deterministic Repeat Noise Floor

Original roots: `runs/native_external_confirmation_24gb`, `runs/native_agentdojo_remaining_suites_extension_48gb`.
Repeat root: `runs/native_qwen25_3b_noise_floor_24gb`.
Matched subset count: 65.

This report compares deterministic self-repeats against the FP16-vs-NF4 transformation effect on the same native AgentDojo keys.

## Summary

|comparison|matched|security base|security cand|security flips|flip rate|safe→unsafe|unsafe→safe|utility flips|safe→unsafe with utility preserved|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|fp16 self-repeat|65|0.677|0.662|5|0.077|3|2|6|0|
|nf4 self-repeat|65|0.492|0.446|3|0.046|3|0|3|1|
|fp16 vs nf4 original|65|0.677|0.492|24|0.369|18|6|19|2|
|fp16 vs nf4 repeat|65|0.662|0.446|26|0.400|20|6|16|3|

## Interpretation

- Self-repeat noise floor: 0.077.
- Original FP16-vs-NF4 transformation flip rate on the same subset: 0.369.
- Transform/noise ratio: 4.80x.
- If the transform rate is clearly above the self-repeat floor, the paired flips are less likely to be explained by deterministic execution noise alone.
