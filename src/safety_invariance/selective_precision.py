from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from safety_invariance.config import load_structured_file, resolve_relative_path
from safety_invariance.evaluation import load_score_bundle
from safety_invariance.schemas import JsonDict, ScoreBundle


@dataclass(frozen=True)
class SelectivePrecisionStudy:
    name: str
    model: JsonDict
    base_transform: JsonDict
    blocks: tuple[str, ...]
    calibration_task_paths: tuple[str, ...]
    evaluation_task_paths: tuple[str, ...]
    calibration_output_root: str
    calibration_report_path: str
    evaluation_output_root: str
    evaluation_report_path: str
    calibration_artifact_path: str
    evaluation_matrix_path: str
    budgets: tuple[float, ...]
    random_controls: int
    random_seed: int
    max_new_tokens: int
    temperature: float
    seeds: tuple[int, ...]
    action_probes: JsonDict
    metadata: JsonDict


def load_selective_precision_study(path: str | Path) -> SelectivePrecisionStudy:
    study_path = Path(path)
    data = load_structured_file(study_path)
    block_data = dict(data.get("blocks", {}))
    explicit_blocks = block_data.get("names")
    if explicit_blocks:
        blocks = tuple(str(name) for name in explicit_blocks)
    else:
        prefix = str(block_data.get("prefix", "model.layers"))
        count = int(block_data.get("count", 0))
        if count <= 0:
            raise ValueError("Selective-precision study requires blocks.names or blocks.count > 0.")
        blocks = tuple(f"{prefix}.{index}" for index in range(count))

    calibration = dict(data.get("calibration", {}))
    evaluation = dict(data.get("evaluation", {}))
    calibration_tasks = _resolve_task_paths(calibration.get("task_paths", ()), study_path)
    evaluation_tasks = _resolve_task_paths(evaluation.get("task_paths", ()), study_path)
    if not calibration_tasks:
        raise ValueError("Selective-precision study defines no calibration task paths.")
    if not evaluation_tasks:
        raise ValueError("Selective-precision study defines no held-out evaluation task paths.")
    if bool(data.get("require_disjoint_tasks", True)):
        from safety_invariance.tasks import load_task_suites

        _, calibration_specs = load_task_suites(calibration_tasks)
        _, evaluation_specs = load_task_suites(evaluation_tasks)
        overlap = {task.id for task in calibration_specs}.intersection(task.id for task in evaluation_specs)
        if overlap:
            raise ValueError(
                "Calibration and held-out evaluation task IDs overlap: " + ", ".join(sorted(overlap))
            )

    budgets = tuple(float(value) for value in data.get("budgets", (0.05, 0.1, 0.2, 0.3)))
    if not budgets or any(value <= 0 or value >= 1 for value in budgets):
        raise ValueError("Selective-precision budgets must be fractions strictly between 0 and 1.")
    random_controls = int(data.get("random_controls", 10))
    if random_controls <= 0:
        raise ValueError("random_controls must be positive.")

    name = str(data.get("study_name", "selective_precision"))
    return SelectivePrecisionStudy(
        name=name,
        model=dict(data["model"]),
        base_transform=dict(data.get("base_transform", {})),
        blocks=blocks,
        calibration_task_paths=calibration_tasks,
        evaluation_task_paths=evaluation_tasks,
        calibration_output_root=str(calibration.get("output_root", f"runs/{name}_calibration")),
        calibration_report_path=str(calibration.get("report_path", f"reports/{name}_calibration.md")),
        evaluation_output_root=str(evaluation.get("output_root", f"runs/{name}_evaluation")),
        evaluation_report_path=str(evaluation.get("report_path", f"reports/{name}_evaluation.md")),
        calibration_artifact_path=str(
            data.get("calibration_artifact_path", f"configs/generated/{name}_selection.json")
        ),
        evaluation_matrix_path=str(
            data.get("evaluation_matrix_path", f"configs/generated/{name}_evaluation_matrix.json")
        ),
        budgets=budgets,
        random_controls=random_controls,
        random_seed=int(data.get("random_seed", 2026)),
        max_new_tokens=int(data.get("max_new_tokens", 256)),
        temperature=float(data.get("temperature", 0.0)),
        seeds=tuple(int(seed) for seed in data.get("seeds", (0,))),
        action_probes=dict(data.get("action_probes", {})),
        metadata=dict(data.get("metadata", {})),
    )


def write_selective_calibration_matrix(
    study: SelectivePrecisionStudy,
    out: str | Path,
) -> Path:
    candidate_name = _candidate_transform_name(study)
    transforms: list[JsonDict] = [
        {"name": "fp16", "quantization": "none"},
        _named_transform(study.base_transform, candidate_name, role="fully_quantized_candidate"),
    ]
    for index, block in enumerate(study.blocks):
        transforms.append(
            _selective_transform(
                study.base_transform,
                name=f"restore_block_{index:02d}",
                keep_modules=(block,),
                role="single_block_restoration",
                selection_strategy="causal_leave_one_block_in",
                budget=1 / len(study.blocks),
            )
        )
    payload: JsonDict = {
        "output_root": study.calibration_output_root,
        "report_path": study.calibration_report_path,
        "models": [study.model],
        "transforms": transforms,
        "task_paths": [_portable_path(path) for path in study.calibration_task_paths],
        "seeds": list(study.seeds),
        "max_new_tokens": study.max_new_tokens,
        "temperature": study.temperature,
        "mitigation": {"triggered_escalation": {"enabled": False}},
        "metadata": {
            **study.metadata,
            "selective_precision_study": study.name,
            "selective_precision_phase": "causal_calibration",
        },
    }
    return _write_json(out, payload)


def analyze_selective_calibration(
    study: SelectivePrecisionStudy,
    *,
    run_root: str | Path | None = None,
    out: str | Path | None = None,
    evaluation_matrix_out: str | Path | None = None,
) -> JsonDict:
    root = Path(run_root or study.calibration_output_root)
    artifacts = _load_run_artifacts(root)
    baseline = _require_bundle(artifacts, "fp16")
    candidate_name = _candidate_transform_name(study)
    candidate = _require_bundle(artifacts, candidate_name)
    baseline_scores = _task_score_index(baseline[0])
    candidate_scores = _task_score_index(candidate[0])
    paired_keys = set(baseline_scores).intersection(candidate_scores)
    regression_keys = {
        key
        for key in paired_keys
        if str(baseline_scores[key].get("category")) != "utility"
        and bool(baseline_scores[key].get("safety_success"))
        and not bool(candidate_scores[key].get("safety_success"))
    }

    block_results: list[JsonDict] = []
    for index, block in enumerate(study.blocks):
        transform_name = f"restore_block_{index:02d}"
        bundle, manifest = _require_bundle(artifacts, transform_name)
        intervention_scores = _task_score_index(bundle)
        common = paired_keys.intersection(intervention_scores)
        recovered = {
            key for key in regression_keys if bool(intervention_scores.get(key, {}).get("safety_success"))
        }
        introduced = {
            key
            for key in common
            if str(baseline_scores[key].get("category")) != "utility"
            and bool(baseline_scores[key].get("safety_success"))
            and bool(candidate_scores[key].get("safety_success"))
            and not bool(intervention_scores[key].get("safety_success"))
        }
        cost = _high_precision_cost(manifest, candidate[1])
        net_recovery = len(recovered) - len(introduced)
        safety_gain = bundle.safety_score - candidate[0].safety_score
        utility_gain = bundle.utility_score - candidate[0].utility_score
        block_results.append(
            {
                "block": block,
                "transform": transform_name,
                "high_precision_cost_bytes": cost[0],
                "cost_source": cost[1],
                "baseline_regression_count": len(regression_keys),
                "recovered_regression_count": len(recovered),
                "introduced_regression_count": len(introduced),
                "net_recovery_count": net_recovery,
                "recovery_rate": _safe_ratio(len(recovered), len(regression_keys)),
                "safety_score_gain": safety_gain,
                "utility_score_gain": utility_gain,
                "causal_score_per_gib": net_recovery / max(cost[0] / (1024**3), 1e-9),
                "recovered_tasks": _task_key_payload(recovered),
                "introduced_tasks": _task_key_payload(introduced),
            }
        )

    block_order = {block: index for index, block in enumerate(study.blocks)}
    safety_ranked = sorted(
        block_results,
        key=lambda item: (
            -float(item["causal_score_per_gib"]),
            -float(item["safety_score_gain"]),
            -float(item["utility_score_gain"]),
            block_order[str(item["block"])],
        ),
    )
    utility_ranked = sorted(
        block_results,
        key=lambda item: (
            -float(item["utility_score_gain"]),
            -float(item["safety_score_gain"]),
            block_order[str(item["block"])],
        ),
    )
    selections: JsonDict = {}
    for budget in study.budgets:
        count = _budget_count(budget, len(study.blocks))
        selections[_budget_label(budget)] = {
            "requested_budget_fraction": budget,
            "budget_fraction": count / len(study.blocks),
            "block_count": count,
            "safety_selected": [str(item["block"]) for item in safety_ranked[:count]],
            "utility_selected": [str(item["block"]) for item in utility_ranked[:count]],
            "first_blocks": list(study.blocks[:count]),
            "last_blocks": list(study.blocks[-count:]),
        }

    warnings: list[str] = []
    if not regression_keys:
        warnings.append("The fully quantized candidate produced no paired safety regressions on calibration tasks.")
    if any(item["cost_source"] == "equal_block_fallback" for item in block_results):
        warnings.append(
            "At least one run lacked memory metadata; equal block costs were used for ranking ties."
        )
    payload: JsonDict = {
        "schema_version": 1,
        "study_name": study.name,
        "calibration_run_root": str(root),
        "baseline_transform": "fp16",
        "candidate_transform": candidate_name,
        "paired_task_count": len(paired_keys),
        "baseline_regression_count": len(regression_keys),
        "baseline_regression_tasks": _task_key_payload(regression_keys),
        "ranking_rule": (
            "Descending net recovery of baseline-safe/candidate-unsafe examples per GiB of restored "
            "parameters, then aggregate safety gain and utility gain."
        ),
        "block_results": block_results,
        "safety_ranking": [str(item["block"]) for item in safety_ranked],
        "utility_ranking": [str(item["block"]) for item in utility_ranked],
        "selections": selections,
        "warnings": warnings,
    }
    artifact_path = Path(out or study.calibration_artifact_path)
    _write_json(artifact_path, payload)
    matrix_path = Path(evaluation_matrix_out or study.evaluation_matrix_path)
    write_selective_evaluation_matrix(study, payload, matrix_path)
    payload["calibration_artifact_path"] = str(artifact_path)
    payload["evaluation_matrix_path"] = str(matrix_path)
    return payload


def write_selective_evaluation_matrix(
    study: SelectivePrecisionStudy,
    selection: JsonDict,
    out: str | Path,
) -> Path:
    candidate_name = _candidate_transform_name(study)
    transforms: list[JsonDict] = [
        {"name": "fp16", "quantization": "none"},
        _named_transform(study.base_transform, candidate_name, role="fully_quantized_candidate"),
    ]
    randomizer = random.Random(study.random_seed)
    for label, raw_selection in selection["selections"].items():
        selected = tuple(raw_selection["safety_selected"])
        count = int(raw_selection["block_count"])
        budget = float(raw_selection["budget_fraction"])
        transforms.extend(
            [
                _selective_transform(
                    study.base_transform,
                    name=f"selective_safety_{label}",
                    keep_modules=selected,
                    role="heldout_evaluation",
                    selection_strategy="causal_safety_recovery",
                    budget=budget,
                ),
                _selective_transform(
                    study.base_transform,
                    name=f"selective_utility_{label}",
                    keep_modules=tuple(raw_selection["utility_selected"]),
                    role="heldout_control",
                    selection_strategy="utility_recovery",
                    budget=budget,
                ),
                _selective_transform(
                    study.base_transform,
                    name=f"selective_first_{label}",
                    keep_modules=tuple(raw_selection["first_blocks"]),
                    role="heldout_control",
                    selection_strategy="first_blocks",
                    budget=budget,
                ),
                _selective_transform(
                    study.base_transform,
                    name=f"selective_last_{label}",
                    keep_modules=tuple(raw_selection["last_blocks"]),
                    role="heldout_control",
                    selection_strategy="last_blocks",
                    budget=budget,
                ),
                _selective_transform(
                    study.base_transform,
                    name=f"quantize_only_sensitive_{label}",
                    keep_modules=tuple(block for block in study.blocks if block not in selected),
                    role="reverse_causal_control",
                    selection_strategy="quantize_only_safety_selected",
                    budget=1.0 - budget,
                ),
            ]
        )
        seen_random: set[tuple[str, ...]] = set()
        forbidden_random = {tuple(sorted(selected))}
        attempts = 0
        while len(seen_random) < study.random_controls:
            attempts += 1
            sample = tuple(sorted(randomizer.sample(list(study.blocks), count)))
            if sample not in forbidden_random:
                seen_random.add(sample)
            if attempts > study.random_controls * 100:
                break
        for replicate, modules in enumerate(sorted(seen_random)):
            transforms.append(
                _selective_transform(
                    study.base_transform,
                    name=f"selective_random_{label}_r{replicate:02d}",
                    keep_modules=modules,
                    role="heldout_control",
                    selection_strategy="random_blocks",
                    budget=budget,
                    extra_metadata={"random_replicate": replicate, "random_seed": study.random_seed},
                )
            )

    payload: JsonDict = {
        "output_root": study.evaluation_output_root,
        "report_path": study.evaluation_report_path,
        "models": [study.model],
        "transforms": transforms,
        "task_paths": [_portable_path(path) for path in study.evaluation_task_paths],
        "seeds": list(study.seeds),
        "max_new_tokens": study.max_new_tokens,
        "temperature": study.temperature,
        "mitigation": {"triggered_escalation": {"enabled": False}},
        "metadata": {
            **study.metadata,
            "selective_precision_study": study.name,
            "selective_precision_phase": "heldout_evaluation",
            "selection_artifact": study.calibration_artifact_path,
        },
    }
    return _write_json(out, payload)


def write_selective_precision_report(
    study: SelectivePrecisionStudy,
    *,
    run_root: str | Path | None = None,
    out: str | Path | None = None,
    bootstrap_samples: int = 5000,
) -> Path:
    root = Path(run_root or study.evaluation_output_root)
    artifacts = _load_run_artifacts(root)
    baseline = _require_bundle(artifacts, "fp16")[0]
    candidate_name = _candidate_transform_name(study)
    candidate = _require_bundle(artifacts, candidate_name)[0]
    rows: list[JsonDict] = []
    for transform_name, (bundle, manifest) in sorted(artifacts.items()):
        if transform_name == "fp16":
            continue
        transform = dict(manifest.get("transform", {}))
        metadata = dict(transform.get("metadata", {}))
        paired = paired_behavior_metrics(baseline, candidate, bundle)
        safety_ci = paired_bootstrap_delta(
            candidate,
            bundle,
            field="safety_success",
            samples=bootstrap_samples,
            seed=study.random_seed,
        )
        utility_ci = paired_bootstrap_delta(
            candidate,
            bundle,
            field="utility_success",
            samples=bootstrap_samples,
            seed=study.random_seed + 1,
        )
        runtime = dict(manifest.get("runtime", {}))
        rows.append(
            {
                "transform": transform_name,
                "strategy": metadata.get("selection_strategy", "fully_quantized"),
                "budget": metadata.get("high_precision_budget_fraction", 0.0),
                "high_precision_blocks": len(transform.get("keep_modules_high_precision", ())),
                "utility": bundle.utility_score,
                "safety": bundle.safety_score,
                "safety_delta_vs_quantized": bundle.safety_score - candidate.safety_score,
                "safety_delta_ci": safety_ci,
                "utility_delta_vs_quantized": bundle.utility_score - candidate.utility_score,
                "utility_delta_ci": utility_ci,
                "candidate_regressions_recovered": paired["candidate_regressions_recovered"],
                "new_regressions_vs_baseline": paired["new_regressions_vs_baseline"],
                "safety_improvements_vs_baseline": paired["safety_improvements_vs_baseline"],
                "any_safety_flip_vs_baseline": paired["any_safety_flip_vs_baseline"],
                "safety_regressions_with_unchanged_utility": paired[
                    "safety_regressions_with_unchanged_utility"
                ],
                "mcnemar_p_vs_quantized": paired["mcnemar_p_vs_quantized"],
                "mean_duration_ms": bundle.metrics.get("mean_duration_ms"),
                "output_tokens_per_second": bundle.metrics.get("output_tokens_per_second"),
                "peak_cuda_allocated_bytes": runtime.get("peak_cuda_allocated_bytes"),
                "model_memory_footprint_bytes": runtime.get("model_memory_footprint_bytes"),
            }
        )

    tested_indices = [
        index for index, row in enumerate(rows) if row["transform"] != candidate_name
    ]
    adjusted = holm_bonferroni(
        [float(rows[index]["mcnemar_p_vs_quantized"]) for index in tested_indices]
    )
    for row in rows:
        row["mcnemar_p_holm_vs_quantized"] = 1.0
    for index, adjusted_p in zip(tested_indices, adjusted, strict=True):
        rows[index]["mcnemar_p_holm_vs_quantized"] = adjusted_p

    report_path = Path(out or study.evaluation_report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_selective_report(study, baseline, candidate, rows), encoding="utf-8")
    _write_json(report_path.with_suffix(".json"), {"study": study.name, "rows": rows})
    return report_path


def paired_behavior_metrics(
    baseline: ScoreBundle,
    candidate: ScoreBundle,
    intervention: ScoreBundle,
) -> JsonDict:
    baseline_scores = _task_score_index(baseline)
    candidate_scores = _task_score_index(candidate)
    intervention_scores = _task_score_index(intervention)
    keys = {
        key
        for key in set(baseline_scores).intersection(candidate_scores, intervention_scores)
        if str(baseline_scores[key].get("category")) != "utility"
    }
    candidate_regressions = {
        key
        for key in keys
        if bool(baseline_scores[key].get("safety_success"))
        and not bool(candidate_scores[key].get("safety_success"))
    }
    recovered = {
        key for key in candidate_regressions if bool(intervention_scores[key].get("safety_success"))
    }
    new_regressions = {
        key
        for key in keys
        if bool(baseline_scores[key].get("safety_success"))
        and not bool(intervention_scores[key].get("safety_success"))
    }
    improvements = {
        key
        for key in keys
        if not bool(baseline_scores[key].get("safety_success"))
        and bool(intervention_scores[key].get("safety_success"))
    }
    unchanged_utility_regressions = {
        key
        for key in new_regressions
        if bool(baseline_scores[key].get("utility_success"))
        == bool(intervention_scores[key].get("utility_success"))
    }
    candidate_only_safe = 0
    intervention_only_safe = 0
    for key in keys:
        candidate_safe = bool(candidate_scores[key].get("safety_success"))
        intervention_safe = bool(intervention_scores[key].get("safety_success"))
        candidate_only_safe += int(candidate_safe and not intervention_safe)
        intervention_only_safe += int(intervention_safe and not candidate_safe)
    return {
        "paired_task_count": len(keys),
        "candidate_regression_count": len(candidate_regressions),
        "candidate_regressions_recovered": len(recovered),
        "new_regressions_vs_baseline": len(new_regressions),
        "safety_improvements_vs_baseline": len(improvements),
        "any_safety_flip_vs_baseline": len(new_regressions | improvements),
        "safety_regressions_with_unchanged_utility": len(unchanged_utility_regressions),
        "mcnemar_p_vs_quantized": exact_mcnemar_p(candidate_only_safe, intervention_only_safe),
    }


def paired_bootstrap_delta(
    left: ScoreBundle,
    right: ScoreBundle,
    *,
    field: str,
    samples: int,
    seed: int,
) -> JsonDict:
    left_scores = _metric_task_score_index(left, field)
    right_scores = _metric_task_score_index(right, field)
    keys = sorted(set(left_scores).intersection(right_scores))
    deltas = [float(bool(right_scores[key].get(field))) - float(bool(left_scores[key].get(field))) for key in keys]
    if not deltas:
        return {"estimate": None, "low": None, "high": None, "samples": 0}
    estimate = mean(deltas)
    randomizer = random.Random(seed)
    draws = sorted(
        mean(deltas[randomizer.randrange(len(deltas))] for _ in deltas)
        for _ in range(max(samples, 1))
    )
    return {
        "estimate": estimate,
        "low": _quantile(draws, 0.025),
        "high": _quantile(draws, 0.975),
        "samples": max(samples, 1),
    }


def exact_mcnemar_p(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if discordant == 0:
        return 1.0
    lower = min(left_only, right_only)
    tail = sum(math.comb(discordant, value) for value in range(lower + 1)) / (2**discordant)
    return min(1.0, 2.0 * tail)


def holm_bonferroni(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [1.0] * len(p_values)
    running_max = 0.0
    total = len(p_values)
    for rank, (original_index, value) in enumerate(ordered):
        corrected = min(1.0, (total - rank) * value)
        running_max = max(running_max, corrected)
        adjusted[original_index] = running_max
    return adjusted


def _resolve_task_paths(raw_paths: Any, study_path: Path) -> tuple[str, ...]:
    return tuple(str(resolve_relative_path(str(path), study_path)) for path in raw_paths)


def _portable_path(raw_path: str) -> str:
    path = Path(raw_path)
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _named_transform(base: JsonDict, name: str, *, role: str) -> JsonDict:
    transform = dict(base)
    transform["name"] = name
    transform["metadata"] = {**dict(transform.get("metadata", {})), "selective_precision_role": role}
    return transform


def _candidate_transform_name(study: SelectivePrecisionStudy) -> str:
    return str(
        study.base_transform.get(
            "name",
            study.base_transform.get("quantization", "quantized_candidate"),
        )
    )


def _selective_transform(
    base: JsonDict,
    *,
    name: str,
    keep_modules: tuple[str, ...],
    role: str,
    selection_strategy: str,
    budget: float,
    extra_metadata: JsonDict | None = None,
) -> JsonDict:
    transform = dict(base)
    transform["name"] = name
    transform["keep_modules_high_precision"] = list(keep_modules)
    transform["metadata"] = {
        **dict(transform.get("metadata", {})),
        "selective_precision_requested": True,
        "selective_precision_backend": "post_load_replacement",
        "selective_precision_role": role,
        "selection_strategy": selection_strategy,
        "high_precision_budget_fraction": budget,
        **(extra_metadata or {}),
    }
    return transform


def _load_run_artifacts(root: Path) -> dict[str, tuple[ScoreBundle, JsonDict]]:
    artifacts: dict[str, tuple[ScoreBundle, JsonDict]] = {}
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        score_path = manifest_path.parent / "scores.json"
        if not score_path.exists():
            continue
        transform_name = str(manifest.get("transform", {}).get("name", manifest_path.parent.name))
        artifacts[transform_name] = (load_score_bundle(score_path), manifest)
    return artifacts


def _require_bundle(
    artifacts: dict[str, tuple[ScoreBundle, JsonDict]],
    transform: str,
) -> tuple[ScoreBundle, JsonDict]:
    try:
        return artifacts[transform]
    except KeyError as exc:
        available = ", ".join(sorted(artifacts)) or "none"
        raise ValueError(f"Missing completed run for transform {transform!r}; available: {available}") from exc


def _task_score_index(bundle: ScoreBundle) -> dict[tuple[str, int], JsonDict]:
    return {
        (str(item["task_id"]), int(item.get("seed", 0))): dict(item)
        for item in bundle.task_scores
    }


def _metric_task_score_index(bundle: ScoreBundle, field: str) -> dict[tuple[str, int], JsonDict]:
    scores = _task_score_index(bundle)
    if field == "safety_success":
        eligible = {
            key: item for key, item in scores.items() if str(item.get("category")) != "utility"
        }
    elif field == "utility_success":
        eligible = {
            key: item
            for key, item in scores.items()
            if str(item.get("category")) in {"utility", "benign"}
        }
    else:
        eligible = scores
    return eligible or scores


def _high_precision_cost(
    manifest: JsonDict,
    candidate_manifest: JsonDict | None = None,
) -> tuple[float, str]:
    runtime = dict(manifest.get("runtime", {}))
    candidate_runtime = dict((candidate_manifest or {}).get("runtime", {}))
    footprint = runtime.get("model_memory_footprint_bytes")
    candidate_footprint = candidate_runtime.get("model_memory_footprint_bytes")
    if footprint is not None and candidate_footprint is not None:
        incremental = float(footprint) - float(candidate_footprint)
        if incremental > 0:
            return incremental, "incremental_model_footprint"
    cost = runtime.get("high_precision_parameter_bytes")
    if cost is not None and float(cost) > 0:
        return float(cost), "manifest_runtime"
    return float(1024**3), "equal_block_fallback"


def _task_key_payload(keys: set[tuple[str, int]]) -> list[JsonDict]:
    return [{"task_id": task_id, "seed": seed} for task_id, seed in sorted(keys)]


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _budget_count(budget: float, total: int) -> int:
    return max(1, min(total, math.ceil(budget * total)))


def _budget_label(budget: float) -> str:
    return f"b{round(budget * 100):02d}"


def _quantile(values: list[float], probability: float) -> float:
    if len(values) == 1:
        return values[0]
    index = probability * (len(values) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _render_selective_report(
    study: SelectivePrecisionStudy,
    baseline: ScoreBundle,
    candidate: ScoreBundle,
    rows: list[JsonDict],
) -> str:
    lines = [
        "# Selective Precision Held-Out Evaluation",
        "",
        f"Study: `{study.name}`.",
        "",
        f"FP16 baseline utility/safety: {baseline.utility_score:.3f}/{baseline.safety_score:.3f}.",
        f"Fully quantized utility/safety: {candidate.utility_score:.3f}/{candidate.safety_score:.3f}.",
        "",
        "|transform|strategy|budget|utility|safety|safety delta|95% CI|recovered|"
        "baseline regressions|p Holm|latency ms|tok/s|peak GiB|",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        ci = row["safety_delta_ci"]
        ci_text = (
            "n/a"
            if ci["low"] is None
            else f"[{float(ci['low']):.3f}, {float(ci['high']):.3f}]"
        )
        latency = row.get("mean_duration_ms")
        throughput = row.get("output_tokens_per_second")
        peak_memory = row.get("peak_cuda_allocated_bytes")
        lines.append(
            (
                "|{transform}|{strategy}|{budget:.2f}|{utility:.3f}|{safety:.3f}|"
                "{delta:.3f}|{ci}|{recovered}|{regressions}|{p:.4f}|{latency}|"
                "{throughput}|{peak_memory}|"
            ).format(
                transform=row["transform"],
                strategy=row["strategy"],
                budget=float(row["budget"] or 0.0),
                utility=float(row["utility"]),
                safety=float(row["safety"]),
                delta=float(row["safety_delta_vs_quantized"]),
                ci=ci_text,
                recovered=row["candidate_regressions_recovered"],
                regressions=row["new_regressions_vs_baseline"],
                p=float(row["mcnemar_p_holm_vs_quantized"]),
                latency="n/a" if latency is None else f"{float(latency):.1f}",
                throughput="n/a" if throughput is None else f"{float(throughput):.1f}",
                peak_memory="n/a" if peak_memory is None else f"{float(peak_memory) / (1024**3):.2f}",
            )
        )
    lines.extend(
        [
            "",
            "Intervals are paired task-level bootstrap intervals. Exact McNemar p-values compare each "
            "intervention with the fully quantized candidate and use Holm correction across reported variants.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: str | Path, payload: JsonDict) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output
