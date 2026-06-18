# Safety Invariance Report

|model|transform|suite|utility|safety|utility_ret|safety_ret|gap|privacy_leak|unsafe_tool|fail_confirm|harmful|latency_ms|escalation|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|Qwen/Qwen2.5-3B-Instruct|fp16|utility_core_v1+agentdojo_minimal_v1+custom_safety_v1+chat_safety_v1+situational_awareness_v1+agentharm_lite_v1+safety_signal_replication_v1|0.960|0.727|1.000|1.000|0.000|0.000|0.000|0.400|0.778|1293.549|0.000|
|Qwen/Qwen2.5-3B-Instruct|int8|utility_core_v1+agentdojo_minimal_v1+custom_safety_v1+chat_safety_v1+situational_awareness_v1+agentharm_lite_v1+safety_signal_replication_v1|0.840|0.709|0.875|0.975|-0.100|0.067|0.012|0.333|0.756|5635.504|0.000|
|Qwen/Qwen2.5-3B-Instruct|nf4_4bit|utility_core_v1+agentdojo_minimal_v1+custom_safety_v1+chat_safety_v1+situational_awareness_v1+agentharm_lite_v1+safety_signal_replication_v1|0.880|0.661|0.917|0.908|0.008|0.111|0.000|0.267|0.867|2465.306|0.000|
