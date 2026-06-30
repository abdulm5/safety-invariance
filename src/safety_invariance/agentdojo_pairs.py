from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentDojoOutcome:
    key: tuple[str, str, str, str, str]
    benchmark: str
    suite: str
    user_task_id: str
    injection_task_id: str
    attack_type: str
    utility: bool
    security: bool
    path: str


def write_agentdojo_pair_report(
    roots: list[str | Path] | tuple[str | Path, ...],
    out: str | Path,
    *,
    baseline_profile: str = "qwen25_3b_fp16",
    candidate_profiles: list[str] | tuple[str, ...] = (),
    json_out: str | Path | None = None,
) -> Path:
    result = analyze_agentdojo_pairs(
        roots,
        baseline_profile=baseline_profile,
        candidate_profiles=candidate_profiles,
    )
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_agentdojo_pair_report(result), encoding="utf-8")
    if json_out:
        json_path = Path(json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def analyze_agentdojo_pairs(
    roots: list[str | Path] | tuple[str | Path, ...],
    *,
    baseline_profile: str = "qwen25_3b_fp16",
    candidate_profiles: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    root_paths = tuple(Path(root) for root in roots)
    profiles = _load_profiles(root_paths)
    if baseline_profile not in profiles:
        raise ValueError(f"baseline profile not found: {baseline_profile}")
    if not candidate_profiles:
        candidate_profiles = tuple(profile for profile in profiles if profile != baseline_profile)
    missing = [profile for profile in candidate_profiles if profile not in profiles]
    if missing:
        raise ValueError("candidate profile(s) not found: " + ", ".join(missing))
    baseline = profiles[baseline_profile]
    comparisons = [
        _compare_outcomes(
            baseline_profile=baseline_profile,
            baseline=baseline,
            candidate_profile=candidate,
            candidate=profiles[candidate],
        )
        for candidate in candidate_profiles
    ]
    return {
        "roots": [str(root) for root in root_paths],
        "baseline_profile": baseline_profile,
        "profile_counts": {
            profile: len(outcomes)
            for profile, outcomes in profiles.items()
        },
        "comparisons": comparisons,
    }


def render_agentdojo_pair_report(result: dict[str, Any]) -> str:
    lines = [
        "# AgentDojo Paired Flip Report",
        "",
        "Roots: " + ", ".join(f"`{root}`" for root in result["roots"]) + ".",
        f"Baseline profile: `{result['baseline_profile']}`.",
        "",
        "A safety regression is a matched task where the baseline is secure and the candidate is insecure. "
        "Capability-conditioned regressions additionally require both baseline and candidate utility to be true.",
        "",
        "## Summary",
        "",
        "|candidate|matched|security base|security cand|safe→unsafe|unsafe→safe|security flips|utility base|utility cand|utility regressions|utility improvements|capability overlap|safe→unsafe with utility preserved|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["comparisons"]:
        lines.append(
            "|{candidate}|{matched}|{base_sec:.3f}|{cand_sec:.3f}|{s2u}|{u2s}|{sflip}|{base_util:.3f}|{cand_util:.3f}|{ureg}|{uimp}|{overlap}|{preserved}|".format(
                candidate=row["candidate_profile"],
                matched=row["matched_count"],
                base_sec=row["baseline_security_rate"],
                cand_sec=row["candidate_security_rate"],
                s2u=row["safe_to_unsafe"],
                u2s=row["unsafe_to_safe"],
                sflip=row["security_flips"],
                base_util=row["baseline_utility_rate"],
                cand_util=row["candidate_utility_rate"],
                ureg=row["utility_regressions"],
                uimp=row["utility_improvements"],
                overlap=row["capability_overlap_count"],
                preserved=row["safe_to_unsafe_with_utility_preserved"],
            )
        )
    lines.extend(["", "## Safety Regressions", ""])
    for row in result["comparisons"]:
        lines.extend(
            [
                f"### {row['candidate_profile']}",
                "",
                "|benchmark|suite|user task|injection task|attack|baseline util|candidate util|",
                "|---|---|---|---|---|---:|---:|",
            ]
        )
        regressions = row["safety_regression_examples"]
        if not regressions:
            lines.append("|None|||||||")
        else:
            for item in regressions[:50]:
                lines.append(
                    "|{benchmark}|{suite}|{user_task_id}|{injection_task_id}|{attack_type}|{baseline_utility}|{candidate_utility}|".format(
                        **item
                    )
                )
        lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- This report uses native AgentDojo JSON logs, not stdout aggregates.",
            "- It is valid for task-level paired analysis because keys match the same suite, user task, injection task, and attack type.",
            "- For paper tables, use the summary counts; use examples for qualitative inspection and human audit sampling.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_profiles(root_paths: tuple[Path, ...]) -> dict[str, dict[tuple[str, str, str, str, str], AgentDojoOutcome]]:
    profiles: dict[str, dict[tuple[str, str, str, str, str], AgentDojoOutcome]] = {}
    for root in root_paths:
        if not root.exists():
            raise ValueError(f"AgentDojo root not found: {root}")
        for profile_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            profile_outcomes = profiles.setdefault(profile_dir.name, {})
            for benchmark_dir in sorted(path for path in profile_dir.iterdir() if path.is_dir()):
                if not benchmark_dir.name.startswith("agentdojo_"):
                    continue
                for log_path in benchmark_dir.glob("native_logs/**/*.json"):
                    outcome = _read_outcome(benchmark_dir.name, log_path)
                    if outcome.key in profile_outcomes:
                        raise ValueError(
                            f"duplicate AgentDojo key for {profile_dir.name}: {outcome.key}"
                        )
                    profile_outcomes[outcome.key] = outcome
    return profiles


def _read_outcome(benchmark: str, path: Path) -> AgentDojoOutcome:
    data = json.loads(path.read_text(encoding="utf-8"))
    suite = str(data.get("suite_name") or "")
    user_task_id = str(data.get("user_task_id") or "")
    injection_task_id = str(data.get("injection_task_id") or "none")
    attack_type = str(data.get("attack_type") or "none")
    key = (benchmark, suite, user_task_id, injection_task_id, attack_type)
    return AgentDojoOutcome(
        key=key,
        benchmark=benchmark,
        suite=suite,
        user_task_id=user_task_id,
        injection_task_id=injection_task_id,
        attack_type=attack_type,
        utility=bool(data.get("utility", False)),
        security=bool(data.get("security", False)),
        path=str(path),
    )


def _compare_outcomes(
    *,
    baseline_profile: str,
    baseline: dict[tuple[str, str, str, str, str], AgentDojoOutcome],
    candidate_profile: str,
    candidate: dict[tuple[str, str, str, str, str], AgentDojoOutcome],
) -> dict[str, Any]:
    del baseline_profile
    keys = sorted(set(baseline) & set(candidate))
    if not keys:
        raise ValueError(f"no matched AgentDojo outcomes for {candidate_profile}")
    safe_to_unsafe: list[dict[str, Any]] = []
    unsafe_to_safe: list[dict[str, Any]] = []
    utility_regressions = 0
    utility_improvements = 0
    capability_overlap = 0
    safe_to_unsafe_with_utility_preserved = 0
    base_security_true = 0
    cand_security_true = 0
    base_utility_true = 0
    cand_utility_true = 0
    for key in keys:
        base = baseline[key]
        cand = candidate[key]
        base_security_true += int(base.security)
        cand_security_true += int(cand.security)
        base_utility_true += int(base.utility)
        cand_utility_true += int(cand.utility)
        if base.utility and cand.utility:
            capability_overlap += 1
        if base.security and not cand.security:
            item = _example(base, cand)
            safe_to_unsafe.append(item)
            if base.utility and cand.utility:
                safe_to_unsafe_with_utility_preserved += 1
        elif not base.security and cand.security:
            unsafe_to_safe.append(_example(base, cand))
        if base.utility and not cand.utility:
            utility_regressions += 1
        elif not base.utility and cand.utility:
            utility_improvements += 1
    matched = len(keys)
    return {
        "candidate_profile": candidate_profile,
        "matched_count": matched,
        "baseline_only_count": len(set(baseline) - set(candidate)),
        "candidate_only_count": len(set(candidate) - set(baseline)),
        "baseline_security_rate": base_security_true / matched,
        "candidate_security_rate": cand_security_true / matched,
        "baseline_utility_rate": base_utility_true / matched,
        "candidate_utility_rate": cand_utility_true / matched,
        "safe_to_unsafe": len(safe_to_unsafe),
        "unsafe_to_safe": len(unsafe_to_safe),
        "security_flips": len(safe_to_unsafe) + len(unsafe_to_safe),
        "utility_regressions": utility_regressions,
        "utility_improvements": utility_improvements,
        "utility_flips": utility_regressions + utility_improvements,
        "capability_overlap_count": capability_overlap,
        "safe_to_unsafe_with_utility_preserved": safe_to_unsafe_with_utility_preserved,
        "safety_regression_examples": safe_to_unsafe,
        "safety_improvement_examples": unsafe_to_safe,
    }


def _example(base: AgentDojoOutcome, cand: AgentDojoOutcome) -> dict[str, Any]:
    return {
        "benchmark": base.benchmark,
        "suite": base.suite,
        "user_task_id": base.user_task_id,
        "injection_task_id": base.injection_task_id,
        "attack_type": base.attack_type,
        "baseline_utility": base.utility,
        "candidate_utility": cand.utility,
        "baseline_path": base.path,
        "candidate_path": cand.path,
    }
