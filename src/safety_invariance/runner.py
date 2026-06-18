from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from safety_invariance.agent import run_task
from safety_invariance.environment import collect_environment
from safety_invariance.evaluation import score_trace, score_traces, write_score_bundle
from safety_invariance.mitigations import EscalationPolicy
from safety_invariance.modeling import load_model_client
from safety_invariance.schemas import (
    AgentTrace,
    RunConfig,
    ScoreBundle,
    model_spec_from_dict,
    to_dict,
    transform_spec_from_dict,
)
from safety_invariance.tasks import load_task_suites


def run_experiment(config: RunConfig) -> ScoreBundle:
    run_dir = config.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    suite_id, tasks = load_task_suites(config.task_paths)
    model = load_model_client(config.model, config.transform)
    policy = EscalationPolicy.from_config(config.mitigation)
    safer_model = load_safer_model(config) if policy.rerun_with_safer_profile else None

    traces: list[AgentTrace] = []
    for seed in config.seeds:
        random.seed(seed)
        for task in tasks:
            trace = run_task(
                task,
                model,
                max_new_tokens=config.max_new_tokens,
                temperature=config.temperature,
                seed=seed,
                escalation_policy=policy,
                safer_model=safer_model,
                context_compression=config.context_compression,
            )
            utility_success, safety_success, details = score_trace(task, trace)
            traces.append(
                AgentTrace(
                    task_id=trace.task_id,
                    suite_id=trace.suite_id,
                    category=trace.category,
                    prompt=trace.prompt,
                    output=trace.output,
                    tool_calls=trace.tool_calls,
                    safety_events=trace.safety_events,
                    final_decision=trace.final_decision,
                    utility_success=utility_success,
                    safety_success=safety_success,
                    duration_ms=trace.duration_ms,
                    seed=trace.seed,
                    metadata={**trace.metadata, "score_details": details},
                )
            )

    runtime_provider = getattr(model, "get_runtime_metadata", None)
    runtime = runtime_provider() if callable(runtime_provider) else dict(getattr(model, "runtime_metadata", {}))
    write_manifest(
        run_dir,
        config,
        suite_id,
        len(tasks),
        runtime=dict(runtime),
    )
    write_events(run_dir / "events.jsonl", tuple(traces))
    bundle = score_traces(
        tuple(traces),
        tasks,
        model_id=config.model.model_id,
        transform=config.transform.name,
        task_suite=suite_id,
    )
    write_score_bundle(run_dir / "scores.json", bundle)
    write_summary_csv(run_dir / "summary.csv", bundle)
    return bundle


def write_manifest(
    run_dir: Path,
    config: RunConfig,
    suite_id: str,
    task_count: int,
    *,
    runtime: dict[str, object] | None = None,
) -> None:
    manifest = {
        "run_name": config.run_name,
        "task_suite": suite_id,
        "task_count": task_count,
        "seeds": list(config.seeds),
        "model": to_dict(config.model),
        "transform": to_dict(config.transform),
        "max_new_tokens": config.max_new_tokens,
        "temperature": config.temperature,
        "context_compression": config.context_compression,
        "mitigation": config.mitigation,
        "metadata": config.metadata,
        "runtime": runtime or {},
        "environment": collect_environment(),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_events(path: Path, traces: tuple[AgentTrace, ...]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(to_dict(trace), sort_keys=True) + "\n")


def load_events(path: str | Path) -> tuple[AgentTrace, ...]:
    from safety_invariance.schemas import agent_trace_from_dict

    traces: list[AgentTrace] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                traces.append(agent_trace_from_dict(json.loads(line)))
    return tuple(traces)


def load_safer_model(config: RunConfig):
    raw = dict(config.mitigation.get("safer_model", {}))
    if not raw:
        raw = {
            "model": to_dict(config.model),
            "transform": {
                "name": "fp16_safer",
                "quantization": "none",
            },
        }
    model = model_spec_from_dict(raw.get("model", to_dict(config.model)))
    transform = transform_spec_from_dict(raw.get("transform", {"name": "fp16_safer", "quantization": "none"}))
    return load_model_client(model, transform)


SUMMARY_FIELDS = [
    "model_id",
    "transform",
    "task_suite",
    "utility_score",
    "safety_score",
    "utility_retention",
    "safety_retention",
    "safety_utility_gap",
    "prompt_injection_success_rate",
    "privacy_leak_rate",
    "unsafe_tool_call_rate",
    "failure_to_confirm_rate",
    "goal_hijacking_rate",
    "harmful_compliance_rate",
    "over_refusal_rate",
    "mean_duration_ms",
    "output_tokens_per_second",
    "escalation_rate",
]


def write_summary_csv(path: Path, bundle: ScoreBundle) -> None:
    row = summary_row(bundle)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerow(row)


def summary_row(bundle: ScoreBundle) -> dict[str, object]:
    row: dict[str, object] = {
        "model_id": bundle.model_id,
        "transform": bundle.transform,
        "task_suite": bundle.task_suite,
        "utility_score": bundle.utility_score,
        "safety_score": bundle.safety_score,
    }
    for key in SUMMARY_FIELDS:
        if key in row:
            continue
        if key in bundle.retention:
            row[key] = bundle.retention[key]
        else:
            row[key] = bundle.metrics.get(key)
    return row
