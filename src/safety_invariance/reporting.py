from __future__ import annotations

import glob
from pathlib import Path

from safety_invariance.evaluation import load_score_bundle
from safety_invariance.runner import SUMMARY_FIELDS, summary_row
from safety_invariance.schemas import ScoreBundle


def find_score_files(pattern: str) -> list[Path]:
    files: list[Path] = []
    for match in glob.glob(pattern):
        path = Path(match)
        if path.is_dir():
            score_path = path / "scores.json"
            if score_path.exists():
                files.append(score_path)
        elif path.name == "scores.json":
            files.append(path)
    return sorted(files)


def load_bundles(pattern: str) -> tuple[ScoreBundle, ...]:
    return tuple(load_score_bundle(path) for path in find_score_files(pattern))


def render_markdown_report(bundles: tuple[ScoreBundle, ...]) -> str:
    if not bundles:
        return "# Safety Invariance Report\n\nNo score files matched.\n"
    headers = [
        "model",
        "transform",
        "suite",
        "utility",
        "safety",
        "utility_ret",
        "safety_ret",
        "gap",
        "privacy_leak",
        "unsafe_tool",
        "fail_confirm",
        "harmful",
        "latency_ms",
        "escalation",
    ]
    lines = [
        "# Safety Invariance Report",
        "",
        "|" + "|".join(headers) + "|",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for bundle in bundles:
        row = summary_row(bundle)
        values = [
            bundle.model_id,
            bundle.transform,
            bundle.task_suite,
            fmt(row["utility_score"]),
            fmt(row["safety_score"]),
            fmt(row.get("utility_retention")),
            fmt(row.get("safety_retention")),
            fmt(row.get("safety_utility_gap")),
            fmt(row.get("privacy_leak_rate")),
            fmt(row.get("unsafe_tool_call_rate")),
            fmt(row.get("failure_to_confirm_rate")),
            fmt(row.get("harmful_compliance_rate")),
            fmt(row.get("mean_duration_ms")),
            fmt(row.get("escalation_rate")),
        ]
        lines.append("|" + "|".join(values) + "|")
    lines.append("")
    return "\n".join(lines)


def fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_markdown_report(pattern: str, out: str | Path) -> Path:
    bundles = load_bundles(pattern)
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown_report(bundles), encoding="utf-8")
    return output
