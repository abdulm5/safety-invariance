from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any


_FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")
_SAMPLES_RE = re.compile(r"\((\d+)\s+samples\)")
_INJECTION_RE = re.compile(r"Passed injection tasks as user tasks:\s*(\d+)\s*/\s*(\d+)")
_AGENTHARM_METRIC_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]+)\s+([-+]?(?:\d+\.\d+|\d+))\s*$")


@dataclass(frozen=True)
class NativeReport:
    roots: tuple[Path, ...]
    baseline_profile: str
    profiles: dict[str, dict[str, Any]]
    comparisons: list[dict[str, Any]]


def write_native_external_report(
    root: str | Path | list[str | Path] | tuple[str | Path, ...],
    out: str | Path,
    *,
    baseline_profile: str = "qwen25_3b_fp16",
    json_out: str | Path | None = None,
) -> Path:
    report = build_native_external_report(root, baseline_profile=baseline_profile)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_native_external_report(report), encoding="utf-8")
    if json_out:
        json_path = Path(json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(_report_to_json(report), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return out_path


def build_native_external_report(
    root: str | Path | list[str | Path] | tuple[str | Path, ...],
    *,
    baseline_profile: str = "qwen25_3b_fp16",
) -> NativeReport:
    root_paths = _normalize_roots(root)
    profile_dirs: dict[str, list[Path]] = {}
    for root_path in root_paths:
        for profile_dir in sorted(path for path in root_path.iterdir() if path.is_dir()):
            profile_dirs.setdefault(profile_dir.name, []).append(profile_dir)
    profiles = {
        profile_name: _load_profile(dirs)
        for profile_name, dirs in sorted(profile_dirs.items())
    }
    if baseline_profile not in profiles:
        raise ValueError(f"baseline profile not found: {baseline_profile}")
    comparisons = [
        _compare_profiles(baseline_profile, profiles[baseline_profile], name, data)
        for name, data in profiles.items()
        if name != baseline_profile
    ]
    return NativeReport(
        roots=root_paths,
        baseline_profile=baseline_profile,
        profiles=profiles,
        comparisons=comparisons,
    )


def render_native_external_report(report: NativeReport) -> str:
    baseline = report.profiles[report.baseline_profile]
    lines: list[str] = [
        "# Native External Benchmark Report",
        "",
        "Roots: " + ", ".join(f"`{root}`" for root in report.roots) + ".",
        f"Baseline profile: `{report.baseline_profile}`.",
        "",
        "This report is aggregate-level. It uses committed native stdout/manifests and profile telemetry. "
        "Per-sample paired flips require the raw native logs or an Inspect runtime capable of reading `.eval` files.",
        "",
        "## Profile Summary",
        "",
        "|profile|transform|peak GiB|requests|p50 ms|p95 ms|tok/s|context hits|",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, data in report.profiles.items():
        telemetry = data["telemetry"]
        lines.append(
            "|{profile}|{transform}|{peak:.2f}|{requests}|{p50:.1f}|{p95:.1f}|{tps:.2f}|{hits}|".format(
                profile=name,
                transform=data.get("transform", ""),
                peak=_safe_float(data.get("peak_reserved_gib")),
                requests=int(telemetry.get("request_count", 0)),
                p50=_safe_float(telemetry.get("latency_p50_ms")),
                p95=_safe_float(telemetry.get("latency_p95_ms")),
                tps=_safe_float(telemetry.get("output_tokens_per_second")),
                hits=int(telemetry.get("context_limit_hits", 0)),
            )
        )

    lines.extend(
        [
            "",
            "## Native Benchmark Aggregates",
            "",
            "|profile|WB benign utility|WB direct security|WB tool security|TS benign utility|TS direct security|TS tool security|AgentHarm harmful score|AgentHarm benign score|",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, data in report.profiles.items():
        dojo = data["agentdojo"]
        harm = data["agentharm"]
        lines.append(
            "|{profile}|{wb_benign}|{wb_direct_sec}|{wb_tool_sec}|{ts_benign}|{ts_direct_sec}|{ts_tool_sec}|{harmful}|{harm_benign}|".format(
                profile=name,
                wb_benign=_fmt(_suite_metric(dojo, "agentdojo_benign_v122", "combined", "average_utility")),
                wb_direct_sec=_fmt(_suite_metric(dojo, "agentdojo_direct_v122", "combined", "average_security")),
                wb_tool_sec=_fmt(_suite_metric(dojo, "agentdojo_tool_knowledge_v122", "combined", "average_security")),
                ts_benign=_fmt(_suite_metric(dojo, "agentdojo_remaining_benign_v122", "combined", "average_utility")),
                ts_direct_sec=_fmt(_suite_metric(dojo, "agentdojo_remaining_direct_v122", "combined", "average_security")),
                ts_tool_sec=_fmt(_suite_metric(dojo, "agentdojo_remaining_tool_knowledge_v122", "combined", "average_security")),
                harmful=_fmt(_harm_metric(harm, "agentharm_public_harmful", "avg_score")),
                harm_benign=_fmt(_harm_metric(harm, "agentharm_public_benign", "avg_score")),
            )
        )

    lines.extend(
        [
            "",
            "WB = workspace/banking. TS = travel/slack.",
            "",
            "## AgentDojo Utility Aggregates",
            "",
            "|profile|WB direct utility|WB tool utility|TS direct utility|TS tool utility|",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, data in report.profiles.items():
        dojo = data["agentdojo"]
        lines.append(
            "|{profile}|{wb_direct}|{wb_tool}|{ts_direct}|{ts_tool}|".format(
                profile=name,
                wb_direct=_fmt(_suite_metric(dojo, "agentdojo_direct_v122", "combined", "average_utility")),
                wb_tool=_fmt(_suite_metric(dojo, "agentdojo_tool_knowledge_v122", "combined", "average_utility")),
                ts_direct=_fmt(_suite_metric(dojo, "agentdojo_remaining_direct_v122", "combined", "average_utility")),
                ts_tool=_fmt(_suite_metric(dojo, "agentdojo_remaining_tool_knowledge_v122", "combined", "average_utility")),
            )
        )

    lines.extend(
        [
            "",
            "## AgentHarm Aggregates",
            "",
            "|profile|harmful score|harmful refusals|benign score|benign refusals|",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, data in report.profiles.items():
        harm = data["agentharm"]
        lines.append(
            "|{profile}|{harmful}|{harmful_refusal}|{benign}|{benign_refusal}|".format(
                profile=name,
                harmful=_fmt(_harm_metric(harm, "agentharm_public_harmful", "avg_score")),
                harmful_refusal=_fmt(_harm_metric(harm, "agentharm_public_harmful", "avg_refusals")),
                benign=_fmt(_harm_metric(harm, "agentharm_public_benign", "avg_score")),
                benign_refusal=_fmt(_harm_metric(harm, "agentharm_public_benign", "avg_refusals")),
            )
        )

    lines.extend(
        [
            "",
            "## Baseline Deltas",
            "",
            "AgentHarm harmful score is reported as lower-is-safer. AgentHarm benign score, AgentDojo utility, and AgentDojo security are higher-is-better.",
            "",
            "|profile|transform|WB benign utility Δ|WB direct sec Δ|WB tool sec Δ|TS benign utility Δ|TS direct sec Δ|TS tool sec Δ|harmful score Δ|benign AgentHarm Δ|",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report.comparisons:
        lines.append(
            "|{profile}|{transform}|{benign}|{direct}|{tool}|{r_benign}|{r_direct}|{r_tool}|{harmful}|{harm_benign}|".format(
                profile=row["profile"],
                transform=row["transform"],
                benign=_fmt(row["agentdojo_benign_utility_delta"], signed=True),
                direct=_fmt(row["agentdojo_direct_security_delta"], signed=True),
                tool=_fmt(row["agentdojo_tool_security_delta"], signed=True),
                r_benign=_fmt(row["agentdojo_remaining_benign_utility_delta"], signed=True),
                r_direct=_fmt(row["agentdojo_remaining_direct_security_delta"], signed=True),
                r_tool=_fmt(row["agentdojo_remaining_tool_security_delta"], signed=True),
                harmful=_fmt(row["agentharm_harmful_score_delta"], signed=True),
                harm_benign=_fmt(row["agentharm_benign_score_delta"], signed=True),
            )
        )

    nf4 = report.profiles.get("qwen25_3b_nf4")
    if nf4:
        lines.extend(
            [
                "",
                "## Mitigation Versus Full NF4",
                "",
                "|profile|strategy|direct security Δ|tool security Δ|harmful score Δ|benign utility Δ|AgentHarm benign Δ|",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for name, data in report.profiles.items():
            if name in {report.baseline_profile, "qwen25_3b_nf4"}:
                continue
            strategy = str(data.get("selection", data.get("transform", "")))
            row = _compare_profiles("qwen25_3b_nf4", nf4, name, data)
            lines.append(
                "|{profile}|{strategy}|{direct}|{tool}|{harmful}|{benign}|{harm_benign}|".format(
                    profile=name,
                    strategy=strategy,
                    direct=_fmt(row["agentdojo_remaining_direct_security_delta"], signed=True),
                    tool=_fmt(row["agentdojo_remaining_tool_security_delta"], signed=True),
                    harmful=_fmt(row["agentharm_harmful_score_delta"], signed=True),
                    benign=_fmt(row["agentdojo_remaining_benign_utility_delta"], signed=True),
                    harm_benign=_fmt(row["agentharm_benign_score_delta"], signed=True),
                )
            )

    lines.extend(
        [
            "",
            "## AgentHarm Category Scores",
            "",
        ]
    )
    for benchmark in ("agentharm_public_harmful", "agentharm_public_benign"):
        lines.extend(
            [
                f"### {benchmark}",
                "",
                "|profile|Disinfo|Harass|Drugs|Fraud|Hate|Cyber|Sexual|Copyright|refusal avg|",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for name, data in report.profiles.items():
            metrics = data["agentharm"].get(benchmark, {}).get("metrics", {})
            refusals = [
                value
                for key, value in metrics.items()
                if key.endswith("_avg_refusals") and isinstance(value, (int, float))
            ]
            refusal_avg = sum(refusals) / len(refusals) if refusals else None
            lines.append(
                "|{profile}|{disinfo}|{harass}|{drugs}|{fraud}|{hate}|{cyber}|{sexual}|{copyright}|{refusal}|".format(
                    profile=name,
                    disinfo=_fmt(metrics.get("Disinformation_avg_scores")),
                    harass=_fmt(metrics.get("Harassment_avg_scores")),
                    drugs=_fmt(metrics.get("Drugs_avg_scores")),
                    fraud=_fmt(metrics.get("Fraud_avg_scores")),
                    hate=_fmt(metrics.get("Hate_avg_scores")),
                    cyber=_fmt(metrics.get("Cybercrime_avg_scores")),
                    sexual=_fmt(metrics.get("Sexual_avg_scores")),
                    copyright=_fmt(metrics.get("Copyright_avg_scores")),
                    refusal=_fmt(refusal_avg),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation Notes",
            "",
            "- Confirmatory comparison: `qwen25_3b_fp16` versus `qwen25_3b_nf4`.",
            "- Selective precision rows are external replications of frozen selections; utility-selected rows remain exploratory.",
            "- Aggregate deltas can hide paired behavior flips. Use raw AgentDojo/Inspect logs for final paired statistical tests.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_agentdojo_stdout(stdout: str) -> dict[str, dict[str, float | int]]:
    suites: dict[str, dict[str, float | int]] = {}
    current: str | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Results for suite "):
            current = stripped.removeprefix("Results for suite ").strip()
            suites.setdefault(current, {})
            continue
        if current is None:
            continue
        lower = stripped.lower()
        if "average utility" in lower:
            suites[current]["average_utility"] = _extract_percent(stripped)
        elif "average security" in lower:
            suites[current]["average_security"] = _extract_percent(stripped)
        else:
            match = _INJECTION_RE.search(stripped)
            if match:
                passed = int(match.group(1))
                total = int(match.group(2))
                suites[current]["injection_user_task_passed"] = passed
                suites[current]["injection_user_task_total"] = total
                suites[current]["injection_user_task_rate"] = passed / total if total else math.nan
    return suites


def parse_agentharm_stdout(stdout: str) -> dict[str, Any]:
    metrics: dict[str, float] = {}
    samples: int | None = None
    total_time: str | None = None
    log_path: str | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if samples is None:
            sample_match = _SAMPLES_RE.search(stripped)
            if sample_match:
                samples = int(sample_match.group(1))
        if stripped.startswith("total time:"):
            total_time = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Log:"):
            log_path = stripped.split(":", 1)[1].strip()
        metric_match = _AGENTHARM_METRIC_RE.match(stripped)
        if metric_match:
            metrics[metric_match.group(1)] = float(metric_match.group(2))
    return {
        "samples": samples,
        "total_time": total_time,
        "log_path": log_path,
        "metrics": metrics,
    }


def summarize_server_events(path: str | Path) -> dict[str, float | int]:
    return _summarize_server_event_paths((Path(path),))


def _summarize_server_event_paths(paths: tuple[Path, ...]) -> dict[str, float | int]:
    durations: list[float] = []
    input_tokens = 0
    output_tokens = 0
    tool_calls = 0
    context_limit_hits = 0
    request_count = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            request_count += 1
            duration = float(event.get("duration_ms", 0.0))
            durations.append(duration)
            input_tokens += int(event.get("input_tokens", 0) or 0)
            output_tokens += int(event.get("output_tokens", 0) or 0)
            tool_calls += int(event.get("tool_call_count", 0) or 0)
            context_limit_hits += int(bool(event.get("context_limit_reached", False)))
    total_seconds = sum(durations) / 1000.0
    return {
        "request_count": request_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "context_limit_hits": context_limit_hits,
        "latency_p50_ms": median(durations) if durations else math.nan,
        "latency_p95_ms": _percentile(durations, 0.95),
        "output_tokens_per_second": output_tokens / total_seconds if total_seconds > 0 else math.nan,
    }


def _load_profile(profile_dirs: list[Path]) -> dict[str, Any]:
    manifest = _read_json(profile_dirs[0] / "server_manifest.json")
    transform = manifest.get("transform", {})
    runtime = manifest.get("runtime", {})
    agentdojo: dict[str, Any] = {}
    agentharm: dict[str, Any] = {}
    telemetry_paths: list[Path] = []
    peak_allocated: list[float] = []
    peak_reserved: list[float] = []
    footprint: list[float] = []
    for profile_dir in profile_dirs:
        local_manifest = _read_json(profile_dir / "server_manifest.json")
        if local_manifest:
            manifest = local_manifest
            local_runtime = local_manifest.get("runtime", {})
            _append_if_float(peak_allocated, _bytes_to_gib(local_runtime.get("peak_cuda_allocated_bytes")))
            _append_if_float(peak_reserved, _bytes_to_gib(local_runtime.get("peak_cuda_reserved_bytes")))
            _append_if_float(footprint, _bytes_to_gib(local_runtime.get("model_memory_footprint_bytes")))
        for benchmark_dir in sorted(path for path in profile_dir.iterdir() if path.is_dir()):
            stdout_path = benchmark_dir / "stdout.txt"
            if not stdout_path.exists():
                continue
            stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
            if benchmark_dir.name.startswith("agentdojo_"):
                agentdojo[benchmark_dir.name] = parse_agentdojo_stdout(stdout)
            elif benchmark_dir.name.startswith("agentharm_"):
                agentharm[benchmark_dir.name] = parse_agentharm_stdout(stdout)
        telemetry_path = profile_dir / "server_events.jsonl"
        if telemetry_path.exists():
            telemetry_paths.append(telemetry_path)
    telemetry = _summarize_server_event_paths(tuple(telemetry_paths)) if telemetry_paths else {}
    metadata = transform.get("metadata", {}) if isinstance(transform, dict) else {}
    return {
        "profile": profile_dirs[0].name,
        "sources": [str(path) for path in profile_dirs],
        "model_id": manifest.get("model", {}).get("model_id"),
        "transform": transform.get("name") if isinstance(transform, dict) else None,
        "selection": metadata.get("selection") if isinstance(metadata, dict) else None,
        "agentdojo": agentdojo,
        "agentharm": agentharm,
        "telemetry": telemetry,
        "peak_allocated_gib": max(peak_allocated) if peak_allocated else _bytes_to_gib(runtime.get("peak_cuda_allocated_bytes")),
        "peak_reserved_gib": max(peak_reserved) if peak_reserved else _bytes_to_gib(runtime.get("peak_cuda_reserved_bytes")),
        "memory_footprint_gib": max(footprint) if footprint else _bytes_to_gib(runtime.get("model_memory_footprint_bytes")),
        "manifest": manifest,
    }


def _compare_profiles(
    baseline_name: str,
    baseline: dict[str, Any],
    profile_name: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    del baseline_name
    return {
        "profile": profile_name,
        "transform": candidate.get("transform"),
        "agentdojo_benign_utility_delta": _delta(
            _suite_metric(candidate["agentdojo"], "agentdojo_benign_v122", "combined", "average_utility"),
            _suite_metric(baseline["agentdojo"], "agentdojo_benign_v122", "combined", "average_utility"),
        ),
        "agentdojo_direct_security_delta": _delta(
            _suite_metric(candidate["agentdojo"], "agentdojo_direct_v122", "combined", "average_security"),
            _suite_metric(baseline["agentdojo"], "agentdojo_direct_v122", "combined", "average_security"),
        ),
        "agentdojo_tool_security_delta": _delta(
            _suite_metric(candidate["agentdojo"], "agentdojo_tool_knowledge_v122", "combined", "average_security"),
            _suite_metric(baseline["agentdojo"], "agentdojo_tool_knowledge_v122", "combined", "average_security"),
        ),
        "agentharm_harmful_score_delta": _delta(
            _harm_metric(candidate["agentharm"], "agentharm_public_harmful", "avg_score"),
            _harm_metric(baseline["agentharm"], "agentharm_public_harmful", "avg_score"),
        ),
        "agentharm_benign_score_delta": _delta(
            _harm_metric(candidate["agentharm"], "agentharm_public_benign", "avg_score"),
            _harm_metric(baseline["agentharm"], "agentharm_public_benign", "avg_score"),
        ),
        "agentdojo_remaining_benign_utility_delta": _delta(
            _suite_metric(candidate["agentdojo"], "agentdojo_remaining_benign_v122", "combined", "average_utility"),
            _suite_metric(baseline["agentdojo"], "agentdojo_remaining_benign_v122", "combined", "average_utility"),
        ),
        "agentdojo_remaining_direct_security_delta": _delta(
            _suite_metric(candidate["agentdojo"], "agentdojo_remaining_direct_v122", "combined", "average_security"),
            _suite_metric(baseline["agentdojo"], "agentdojo_remaining_direct_v122", "combined", "average_security"),
        ),
        "agentdojo_remaining_tool_security_delta": _delta(
            _suite_metric(candidate["agentdojo"], "agentdojo_remaining_tool_knowledge_v122", "combined", "average_security"),
            _suite_metric(baseline["agentdojo"], "agentdojo_remaining_tool_knowledge_v122", "combined", "average_security"),
        ),
    }


def _suite_metric(
    agentdojo: dict[str, Any],
    benchmark: str,
    suite: str,
    metric: str,
) -> float | None:
    value = agentdojo.get(benchmark, {}).get(suite, {}).get(metric)
    return float(value) if isinstance(value, (int, float)) else None


def _harm_metric(agentharm: dict[str, Any], benchmark: str, metric: str) -> float | None:
    value = agentharm.get(benchmark, {}).get("metrics", {}).get(metric)
    return float(value) if isinstance(value, (int, float)) else None


def _delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _extract_percent(line: str) -> float:
    match = _FLOAT_RE.search(line)
    if not match:
        return math.nan
    value = float(match.group(0))
    return value / 100.0 if "%" in line else value


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[int(index)]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _bytes_to_gib(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return float(value) / (1024**3)


def _append_if_float(values: list[float], value: float | None) -> None:
    if value is not None:
        values.append(value)


def _safe_float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else math.nan


def _fmt(value: object, *, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "n/a"
    if signed:
        return f"{number:+.3f}"
    return f"{number:.3f}"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _report_to_json(report: NativeReport) -> dict[str, Any]:
    return {
        "roots": [str(root) for root in report.roots],
        "baseline_profile": report.baseline_profile,
        "profiles": report.profiles,
        "comparisons": report.comparisons,
    }


def _normalize_roots(root: str | Path | list[str | Path] | tuple[str | Path, ...]) -> tuple[Path, ...]:
    if isinstance(root, (str, Path)):
        roots = (Path(root),)
    else:
        roots = tuple(Path(item) for item in root)
    if not roots:
        raise ValueError("at least one root is required")
    missing = [str(path) for path in roots if not path.exists()]
    if missing:
        raise ValueError("external root(s) not found: " + ", ".join(missing))
    return roots
