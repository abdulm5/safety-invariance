from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

from safety_invariance.config import load_structured_file
from safety_invariance.evaluation import score_traces, with_retention, write_score_bundle
from safety_invariance.reporting import write_markdown_report
from safety_invariance.runner import load_events, write_summary_csv
from safety_invariance.schemas import ScoreBundle, run_config_from_dict
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
    traces = load_events(path / "events.jsonl")
    return score_traces(
        traces,
        tasks,
        model_id=config.model.model_id,
        transform=config.transform.name,
        task_suite=suite_id,
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
