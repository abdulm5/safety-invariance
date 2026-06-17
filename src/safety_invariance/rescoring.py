from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

from safety_invariance.agent import parse_tool_calls
from safety_invariance.config import load_structured_file
from safety_invariance.evaluation import score_traces, with_retention, write_score_bundle
from safety_invariance.mitigations import detect_safety_events
from safety_invariance.reporting import write_markdown_report
from safety_invariance.runner import load_events, write_summary_csv
from safety_invariance.schemas import AgentTrace, ScoreBundle, TaskSpec, run_config_from_dict
from safety_invariance.tasks import load_task_suites


def find_run_dirs(pattern: str) -> tuple[Path, ...]:
    run_dirs: list[Path] = []
    for match in glob.glob(pattern):
        path = Path(match)
        if path.name == "scores.json":
            path = path.parent
        if not path.is_dir():
            continue
        if (path / "events.jsonl").exists() and (path / "config.resolved.json").exists():
            run_dirs.append(path)
    return tuple(sorted(run_dirs))


def rescore_run_dir(run_dir: str | Path) -> ScoreBundle:
    path = Path(run_dir)
    config = run_config_from_dict(load_structured_file(path / "config.resolved.json"))
    suite_id, tasks = load_task_suites(config.task_paths)
    tasks_by_id = {task.id: task for task in tasks}
    traces = tuple(reparse_trace(trace, tasks_by_id[trace.task_id]) for trace in load_events(path / "events.jsonl"))
    return score_traces(
        traces,
        tasks,
        model_id=config.model.model_id,
        transform=config.transform.name,
        task_suite=suite_id,
    )


def reparse_trace(trace: AgentTrace, task: TaskSpec) -> AgentTrace:
    tool_calls = parse_tool_calls(trace.output)
    safety_events = detect_safety_events(task, trace.output, tool_calls)
    metadata = {
        **trace.metadata,
        "rescore_reparsed_tool_calls": True,
        "original_tool_call_count": len(trace.tool_calls),
        "reparsed_tool_call_count": len(tool_calls),
    }
    return AgentTrace(
        task_id=trace.task_id,
        suite_id=trace.suite_id,
        category=trace.category,
        prompt=trace.prompt,
        output=trace.output,
        tool_calls=tool_calls,
        safety_events=safety_events,
        final_decision=trace.final_decision,
        utility_success=trace.utility_success,
        safety_success=trace.safety_success,
        duration_ms=trace.duration_ms,
        seed=trace.seed,
        metadata=metadata,
    )


def rescore_run_dirs(
    pattern: str,
    *,
    baseline_transform: str = "fp16",
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    run_dirs = find_run_dirs(pattern)
    bundles = {run_dir: rescore_run_dir(run_dir) for run_dir in run_dirs}
    baselines = {
        (bundle.model_id, bundle.task_suite): bundle
        for bundle in bundles.values()
        if bundle.transform == baseline_transform
    }

    rescored: list[str] = []
    for run_dir, bundle in bundles.items():
        baseline = baselines.get((bundle.model_id, bundle.task_suite))
        scored = with_retention(bundle, baseline) if baseline is not None else bundle
        write_score_bundle(run_dir / "scores.json", scored)
        write_summary_csv(run_dir / "summary.csv", scored)
        rescored.append(str(run_dir))

    report = None
    if report_path:
        report = str(write_markdown_report(pattern, report_path))

    return {
        "baseline_transform": baseline_transform,
        "rescore_count": len(rescored),
        "rescored": rescored,
        "report_path": report,
    }
