from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from safety_invariance.reporting import find_score_files, fmt
from safety_invariance.evaluation import load_score_bundle
from safety_invariance.schemas import JsonDict, ScoreBundle


FAILURE_FLAG_KEYS = (
    "private_leak",
    "forbidden_tool",
    "missing_confirmation",
    "goal_hijack",
    "harmful_tool_use",
    "harmful_compliance",
    "over_refusal",
)

SUMMARY_METRIC_KEYS = (
    "prompt_injection_success_rate",
    "privacy_leak_rate",
    "unsafe_tool_call_rate",
    "failure_to_confirm_rate",
    "goal_hijacking_rate",
    "harmful_compliance_rate",
    "over_refusal_rate",
)


def render_diagnostic_report(pattern: str, baseline_transform: str = "fp16") -> str:
    bundles = tuple(load_score_bundle(path) for path in find_score_files(pattern))
    if not bundles:
        return "# Safety Invariance Diagnostics\n\nNo score files matched.\n"

    grouped: dict[tuple[str, str], list[ScoreBundle]] = defaultdict(list)
    for bundle in bundles:
        grouped[(bundle.model_id, bundle.task_suite)].append(bundle)

    lines = [
        "# Safety Invariance Diagnostics",
        "",
        "This report compares each transformed run against the matching baseline by model and task suite.",
        "",
    ]

    summary_rows: list[list[str]] = []
    detail_sections: list[str] = []
    for (model_id, task_suite), group in sorted(grouped.items()):
        baseline = next((bundle for bundle in group if bundle.transform == baseline_transform), None)
        if baseline is None:
            lines.extend(
                [
                    f"## {model_id}",
                    "",
                    f"No `{baseline_transform}` baseline found for `{task_suite}`.",
                    "",
                ]
            )
            continue

        baseline_scores = task_score_index(baseline.task_scores)
        for candidate in sorted(group, key=lambda bundle: bundle.transform):
            if candidate.transform == baseline_transform:
                continue
            diff = compare_to_baseline(candidate, baseline_scores)
            summary_rows.append(
                [
                    candidate.model_id,
                    candidate.transform,
                    fmt(candidate.utility_score),
                    fmt(candidate.safety_score),
                    fmt(candidate.retention.get("utility_retention")),
                    fmt(candidate.retention.get("safety_retention")),
                    fmt(candidate.retention.get("safety_utility_gap")),
                    str(len(diff["safety_regressions"])),
                    str(distinct_task_count(diff["safety_regressions"])),
                    str(len(diff["safety_improvements"])),
                    str(distinct_task_count(diff["safety_improvements"])),
                    str(len(diff["utility_regressions"])),
                    str(distinct_task_count(diff["utility_regressions"])),
                    str(len(diff["utility_improvements"])),
                    str(distinct_task_count(diff["utility_improvements"])),
                ]
            )
            detail_sections.append(render_candidate_detail(candidate, baseline, diff))

    if summary_rows:
        headers = [
            "model",
            "transform",
            "utility",
            "safety",
            "utility_ret",
            "safety_ret",
            "gap",
            "safety_regressions",
            "safety_regression_tasks",
            "safety_improvements",
            "safety_improvement_tasks",
            "utility_regressions",
            "utility_regression_tasks",
            "utility_improvements",
            "utility_improvement_tasks",
        ]
        lines.append("## Baseline Diffs")
        lines.append("")
        lines.append("|" + "|".join(headers) + "|")
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in summary_rows:
            lines.append("|" + "|".join(row) + "|")
        lines.append("")
        lines.extend(detail_sections)

    return "\n".join(lines)


def write_diagnostic_report(pattern: str, out: str | Path, baseline_transform: str = "fp16") -> Path:
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_diagnostic_report(pattern, baseline_transform=baseline_transform), encoding="utf-8")
    return output


def task_score_index(task_scores: Iterable[JsonDict]) -> dict[tuple[str, int], JsonDict]:
    indexed: dict[tuple[str, int], JsonDict] = {}
    for task_score in task_scores:
        indexed[(str(task_score.get("task_id")), int(task_score.get("seed", 0)))] = task_score
    return indexed


def compare_to_baseline(candidate: ScoreBundle, baseline_scores: dict[tuple[str, int], JsonDict]) -> JsonDict:
    diff: JsonDict = {
        "safety_regressions": [],
        "safety_improvements": [],
        "utility_regressions": [],
        "utility_improvements": [],
        "new_tasks": [],
    }
    for task_score in candidate.task_scores:
        key = (str(task_score.get("task_id")), int(task_score.get("seed", 0)))
        baseline = baseline_scores.get(key)
        if baseline is None:
            diff["new_tasks"].append(task_score)
            continue
        add_bool_flip(
            diff,
            "safety",
            baseline=bool(baseline.get("safety_success")),
            candidate=bool(task_score.get("safety_success")),
            task_score=task_score,
            baseline_score=baseline,
        )
        add_bool_flip(
            diff,
            "utility",
            baseline=bool(baseline.get("utility_success")),
            candidate=bool(task_score.get("utility_success")),
            task_score=task_score,
            baseline_score=baseline,
        )
    return diff


def add_bool_flip(
    diff: JsonDict,
    kind: str,
    *,
    baseline: bool,
    candidate: bool,
    task_score: JsonDict,
    baseline_score: JsonDict,
) -> None:
    if baseline and not candidate:
        diff[f"{kind}_regressions"].append({"candidate": task_score, "baseline": baseline_score})
    elif not baseline and candidate:
        diff[f"{kind}_improvements"].append({"candidate": task_score, "baseline": baseline_score})


def distinct_task_count(rows: list[JsonDict]) -> int:
    return len({str(row["candidate"].get("task_id", "")) for row in rows})


def render_candidate_detail(candidate: ScoreBundle, baseline: ScoreBundle, diff: JsonDict) -> str:
    lines = [
        f"## {candidate.model_id} / {candidate.transform}",
        "",
        f"Baseline: `{baseline.transform}`. Utility {fmt(baseline.utility_score)} -> {fmt(candidate.utility_score)}. "
        f"Safety {fmt(baseline.safety_score)} -> {fmt(candidate.safety_score)}.",
        "",
        "### Metric Deltas",
        "",
        "|metric|baseline|candidate|delta|",
        "|---|---|---|---|",
    ]
    for key in SUMMARY_METRIC_KEYS:
        before = baseline.metrics.get(key)
        after = candidate.metrics.get(key)
        delta = None if before is None or after is None else after - before
        lines.append(f"|{key}|{fmt(before)}|{fmt(after)}|{fmt(delta)}|")
    lines.append("")
    for title, key in (
        ("Safety Regressions", "safety_regressions"),
        ("Safety Improvements", "safety_improvements"),
        ("Utility Regressions", "utility_regressions"),
        ("Utility Improvements", "utility_improvements"),
    ):
        lines.extend(render_flip_table(title, diff[key]))
    return "\n".join(lines)


def render_flip_table(title: str, rows: list[JsonDict]) -> list[str]:
    lines = [f"### {title}", ""]
    if not rows:
        lines.extend(["None.", ""])
        return lines
    lines.extend(
        [
            "|task|seed|category|baseline_flags|candidate_flags|",
            "|---|---|---|---|---|",
        ]
    )
    for row in rows:
        candidate = row["candidate"]
        baseline = row["baseline"]
        lines.append(
            "|"
            + "|".join(
                (
                    str(candidate.get("task_id", "")),
                    str(candidate.get("seed", 0)),
                    str(candidate.get("category", "")),
                    flags_for_score(baseline),
                    flags_for_score(candidate),
                )
            )
            + "|"
        )
    lines.append("")
    return lines


def flags_for_score(task_score: JsonDict) -> str:
    flags = [key for key in FAILURE_FLAG_KEYS if task_score.get(key)]
    if not task_score.get("utility_success", True):
        flags.append("utility_failed")
    if not task_score.get("safety_success", True) and not flags:
        flags.append("safety_failed")
    return ", ".join(flags)
