from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safety_invariance.agentdojo_pairs import AgentDojoOutcome, _load_profiles


def write_agentdojo_noise_floor_report(
    roots: list[str | Path] | tuple[str | Path, ...],
    repeat_root: str | Path,
    out: str | Path,
    *,
    fp16_profile: str = "qwen25_3b_fp16",
    nf4_profile: str = "qwen25_3b_nf4",
    fp16_repeat_profile: str = "qwen25_3b_fp16_repeat_noise",
    nf4_repeat_profile: str = "qwen25_3b_nf4_repeat_noise",
    json_out: str | Path | None = None,
) -> Path:
    result = analyze_agentdojo_noise_floor(
        roots,
        repeat_root,
        fp16_profile=fp16_profile,
        nf4_profile=nf4_profile,
        fp16_repeat_profile=fp16_repeat_profile,
        nf4_repeat_profile=nf4_repeat_profile,
    )
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_agentdojo_noise_floor_report(result), encoding="utf-8")
    if json_out:
        json_path = Path(json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def analyze_agentdojo_noise_floor(
    roots: list[str | Path] | tuple[str | Path, ...],
    repeat_root: str | Path,
    *,
    fp16_profile: str = "qwen25_3b_fp16",
    nf4_profile: str = "qwen25_3b_nf4",
    fp16_repeat_profile: str = "qwen25_3b_fp16_repeat_noise",
    nf4_repeat_profile: str = "qwen25_3b_nf4_repeat_noise",
) -> dict[str, Any]:
    root_paths = tuple(Path(root) for root in (*roots, repeat_root))
    profiles = _load_profiles(root_paths)
    required = (fp16_profile, nf4_profile, fp16_repeat_profile, nf4_repeat_profile)
    missing = [profile for profile in required if profile not in profiles]
    if missing:
        raise ValueError("profile(s) not found: " + ", ".join(missing))
    selected_keys = sorted(
        set(profiles[fp16_profile])
        & set(profiles[nf4_profile])
        & set(profiles[fp16_repeat_profile])
        & set(profiles[nf4_repeat_profile])
    )
    if not selected_keys:
        raise ValueError("no matched AgentDojo noise-floor keys found")
    rows = [
        _compare_on_keys(
            "fp16 self-repeat",
            profiles[fp16_profile],
            profiles[fp16_repeat_profile],
            selected_keys,
        ),
        _compare_on_keys(
            "nf4 self-repeat",
            profiles[nf4_profile],
            profiles[nf4_repeat_profile],
            selected_keys,
        ),
        _compare_on_keys(
            "fp16 vs nf4 original",
            profiles[fp16_profile],
            profiles[nf4_profile],
            selected_keys,
        ),
        _compare_on_keys(
            "fp16 vs nf4 repeat",
            profiles[fp16_repeat_profile],
            profiles[nf4_repeat_profile],
            selected_keys,
        ),
    ]
    self_noise = max(rows[0]["security_flip_rate"], rows[1]["security_flip_rate"])
    transform_rate = rows[2]["security_flip_rate"]
    return {
        "roots": [str(root) for root in roots],
        "repeat_root": str(repeat_root),
        "profiles": {
            "fp16": fp16_profile,
            "nf4": nf4_profile,
            "fp16_repeat": fp16_repeat_profile,
            "nf4_repeat": nf4_repeat_profile,
        },
        "matched_subset_count": len(selected_keys),
        "noise_floor_security_flip_rate": self_noise,
        "transform_security_flip_rate": transform_rate,
        "transform_to_noise_ratio": None if self_noise == 0 else transform_rate / self_noise,
        "comparisons": rows,
    }


def render_agentdojo_noise_floor_report(result: dict[str, Any]) -> str:
    ratio = result["transform_to_noise_ratio"]
    ratio_text = "undefined" if ratio is None else f"{ratio:.2f}x"
    lines = [
        "# AgentDojo Deterministic Repeat Noise Floor",
        "",
        "Original roots: " + ", ".join(f"`{root}`" for root in result["roots"]) + ".",
        f"Repeat root: `{result['repeat_root']}`.",
        f"Matched subset count: {result['matched_subset_count']}.",
        "",
        "This report compares deterministic self-repeats against the FP16-vs-NF4 transformation effect on the same native AgentDojo keys.",
        "",
        "## Summary",
        "",
        "|comparison|matched|security base|security cand|security flips|flip rate|safe→unsafe|unsafe→safe|utility flips|safe→unsafe with utility preserved|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["comparisons"]:
        lines.append(
            "|{label}|{matched}|{base_sec:.3f}|{cand_sec:.3f}|{flips}|{rate:.3f}|{s2u}|{u2s}|{uflips}|{preserved}|".format(
                label=row["label"],
                matched=row["matched_count"],
                base_sec=row["baseline_security_rate"],
                cand_sec=row["candidate_security_rate"],
                flips=row["security_flips"],
                rate=row["security_flip_rate"],
                s2u=row["safe_to_unsafe"],
                u2s=row["unsafe_to_safe"],
                uflips=row["utility_flips"],
                preserved=row["safe_to_unsafe_with_utility_preserved"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- Self-repeat noise floor: {result['noise_floor_security_flip_rate']:.3f}.",
            f"- Original FP16-vs-NF4 transformation flip rate on the same subset: {result['transform_security_flip_rate']:.3f}.",
            f"- Transform/noise ratio: {ratio_text}.",
            "- If the transform rate is clearly above the self-repeat floor, the paired flips are less likely to be explained by deterministic execution noise alone.",
            "",
        ]
    )
    return "\n".join(lines)


def _compare_on_keys(
    label: str,
    baseline: dict[tuple[str, str, str, str, str], AgentDojoOutcome],
    candidate: dict[tuple[str, str, str, str, str], AgentDojoOutcome],
    keys: list[tuple[str, str, str, str, str]],
) -> dict[str, Any]:
    safe_to_unsafe = 0
    unsafe_to_safe = 0
    utility_regressions = 0
    utility_improvements = 0
    capability_overlap = 0
    preserved = 0
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
            safe_to_unsafe += 1
            if base.utility and cand.utility:
                preserved += 1
        elif not base.security and cand.security:
            unsafe_to_safe += 1
        if base.utility and not cand.utility:
            utility_regressions += 1
        elif not base.utility and cand.utility:
            utility_improvements += 1
    matched = len(keys)
    security_flips = safe_to_unsafe + unsafe_to_safe
    utility_flips = utility_regressions + utility_improvements
    return {
        "label": label,
        "matched_count": matched,
        "baseline_security_rate": base_security_true / matched,
        "candidate_security_rate": cand_security_true / matched,
        "baseline_utility_rate": base_utility_true / matched,
        "candidate_utility_rate": cand_utility_true / matched,
        "safe_to_unsafe": safe_to_unsafe,
        "unsafe_to_safe": unsafe_to_safe,
        "security_flips": security_flips,
        "security_flip_rate": security_flips / matched,
        "utility_regressions": utility_regressions,
        "utility_improvements": utility_improvements,
        "utility_flips": utility_flips,
        "utility_flip_rate": utility_flips / matched,
        "capability_overlap_count": capability_overlap,
        "safe_to_unsafe_with_utility_preserved": preserved,
    }
