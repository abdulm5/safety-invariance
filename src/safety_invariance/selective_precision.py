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
    margin_artifact_path: str
    evaluation_matrix_path: str
    budgets: tuple[float, ...]
    random_controls: int
    random_seed: int
    max_new_tokens: int
    temperature: float
    seeds: tuple[int, ...]
    action_probes: JsonDict
    ranking_method: str
    utility_penalty: float
    margin_epsilon: float
    metadata: JsonDict


def load_selective_precision_study(path: str | Path) -> SelectivePrecisionStudy:
    study_path = Path(path)
    data = _load_study_data(study_path)
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
    ranking_method = str(data.get("ranking_method", "action_margin"))
    if ranking_method not in {"action_margin", "binary_flip"}:
        raise ValueError("ranking_method must be 'action_margin' or 'binary_flip'.")
    action_probes = dict(data.get("action_probes", {}))
    if ranking_method == "action_margin":
        from safety_invariance.tasks import load_task_suites

        _, calibration_specs = load_task_suites(calibration_tasks)
        missing_probes = [task.id for task in calibration_specs if task.id not in action_probes]
        if missing_probes:
            raise ValueError(
                "Action-margin ranking requires probes for every calibration task; missing: "
                + ", ".join(missing_probes)
            )
        for task in calibration_specs:
            probe = dict(action_probes[task.id])
            preferred = probe.get("preferred_completion", probe.get("safe_completion"))
            dispreferred = probe.get("dispreferred_completion", probe.get("unsafe_completion"))
            if not preferred or not dispreferred:
                raise ValueError(
                    f"Action probe {task.id} requires preferred_completion and dispreferred_completion."
                )

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
        margin_artifact_path=str(
            data.get("margin_artifact_path", f"runs/{name}_action_margins.json")
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
        action_probes=action_probes,
        ranking_method=ranking_method,
        utility_penalty=float(data.get("utility_penalty", 0.5)),
        margin_epsilon=float(data.get("margin_epsilon", 0.05)),
        metadata=dict(data.get("metadata", {})),
    )


def _load_study_data(path: Path, seen: set[Path] | None = None) -> JsonDict:
    resolved = path.resolve()
    visited = set(seen or ())
    if resolved in visited:
        chain = " -> ".join(str(item) for item in (*visited, resolved))
        raise ValueError(f"Circular selective-precision study inheritance: {chain}")
    visited.add(resolved)
    data = dict(load_structured_file(path))
    parent = data.pop("extends", None)
    if parent is None:
        return data
    parent_path = resolve_relative_path(str(parent), path)
    return _deep_merge(_load_study_data(Path(parent_path), visited), data)


def _deep_merge(base: JsonDict, override: JsonDict) -> JsonDict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def selective_calibration_transforms(study: SelectivePrecisionStudy) -> tuple[JsonDict, ...]:
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
    return tuple(transforms)


def write_selective_calibration_matrix(
    study: SelectivePrecisionStudy,
    out: str | Path,
) -> Path:
    transforms = selective_calibration_transforms(study)
    payload: JsonDict = {
        "output_root": study.calibration_output_root,
        "report_path": study.calibration_report_path,
        "models": [study.model],
        "transforms": list(transforms),
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

    ranking_rule = (
        "Descending net recovery of baseline-safe/candidate-unsafe examples per GiB of restored "
        "parameters, then aggregate safety gain and utility gain."
    )
    if study.ranking_method == "action_margin":
        margin_path = Path(study.margin_artifact_path)
        if not margin_path.exists():
            raise ValueError(
                f"Action-margin artifact is missing: {margin_path}. Run si selective-margin-collect first."
            )
        margin_payload = json.loads(margin_path.read_text(encoding="utf-8"))
        if not margin_payload.get("complete"):
            raise ValueError(
                f"Action-margin artifact is incomplete: {margin_path}. Resume si selective-margin-collect."
            )
        block_results = apply_action_margin_scores(
            study,
            margin_payload,
            block_results,
            baseline_scores=baseline_scores,
        )
        ranking_rule = (
            "Descending safe-vs-unsafe completion-margin recovery per GiB on baseline-safe safety "
            f"probes, minus {study.utility_penalty:.3f} times utility-margin damage."
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
            -float(
                item.get(
                    "utility_margin_recovery_per_gib",
                    item["utility_score_gain"],
                )
            ),
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
        "ranking_method": study.ranking_method,
        "margin_artifact_path": (
            study.margin_artifact_path if study.ranking_method == "action_margin" else None
        ),
        "ranking_rule": ranking_rule,
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


def apply_action_margin_scores(
    study: SelectivePrecisionStudy,
    margin_payload: JsonDict,
    block_results: list[JsonDict],
    *,
    baseline_scores: dict[tuple[str, int], JsonDict],
) -> list[JsonDict]:
    transforms = dict(margin_payload.get("transforms", {}))
    candidate_name = _candidate_transform_name(study)
    try:
        baseline_tasks = dict(transforms["fp16"]["tasks"])
        candidate_tasks = dict(transforms[candidate_name]["tasks"])
    except KeyError as exc:
        raise ValueError("Margin artifact is missing FP16 or fully quantized task margins.") from exc

    baseline_safe_by_task: dict[str, bool] = {}
    for (task_id, _seed), score in baseline_scores.items():
        baseline_safe_by_task[task_id] = baseline_safe_by_task.get(task_id, True) and bool(
            score.get("safety_success")
        )

    augmented: list[JsonDict] = []
    for row in block_results:
        transform_name = str(row["transform"])
        try:
            intervention_tasks = dict(transforms[transform_name]["tasks"])
        except KeyError as exc:
            raise ValueError(
                f"Margin artifact is missing intervention transform {transform_name}."
            ) from exc
        safety_details: list[JsonDict] = []
        utility_details: list[JsonDict] = []
        for task_id, baseline_task in baseline_tasks.items():
            if task_id not in candidate_tasks or task_id not in intervention_tasks:
                raise ValueError(
                    f"Margin artifact has inconsistent task coverage for {task_id} in {transform_name}."
                )
            baseline_margin = float(baseline_task["preference_margin"])
            candidate_margin = float(candidate_tasks[task_id]["preference_margin"])
            intervention_margin = float(intervention_tasks[task_id]["preference_margin"])
            probe_kind = str(baseline_task["probe_kind"])
            if probe_kind == "safety":
                if not baseline_safe_by_task.get(task_id, False):
                    continue
                recovery = safety_margin_recovery(
                    baseline_margin,
                    candidate_margin,
                    intervention_margin,
                    epsilon=study.margin_epsilon,
                )
                safety_details.append(
                    {
                        "task_id": task_id,
                        "baseline_margin": baseline_margin,
                        "candidate_margin": candidate_margin,
                        "intervention_margin": intervention_margin,
                        "candidate_degradation": max(0.0, baseline_margin - candidate_margin),
                        "normalized_recovery": recovery,
                    }
                )
            else:
                recovery = fidelity_margin_recovery(
                    baseline_margin,
                    candidate_margin,
                    intervention_margin,
                    epsilon=study.margin_epsilon,
                )
                utility_details.append(
                    {
                        "task_id": task_id,
                        "baseline_margin": baseline_margin,
                        "candidate_margin": candidate_margin,
                        "intervention_margin": intervention_margin,
                        "normalized_recovery": recovery,
                    }
                )

        safety_recovery = mean(
            detail["normalized_recovery"] for detail in safety_details
        ) if safety_details else 0.0
        utility_recovery = mean(
            detail["normalized_recovery"] for detail in utility_details
        ) if utility_details else 0.0
        utility_damage = mean(
            max(0.0, -float(detail["normalized_recovery"]))
            for detail in utility_details
        ) if utility_details else 0.0
        objective = safety_recovery - study.utility_penalty * utility_damage
        cost_gib = max(float(row["high_precision_cost_bytes"]) / (1024**3), 1e-9)
        updated = dict(row)
        updated.update(
            {
                "ranking_method": "action_margin",
                "safety_margin_probe_count": len(safety_details),
                "degraded_safety_margin_probe_count": sum(
                    float(detail["candidate_degradation"]) > 0 for detail in safety_details
                ),
                "utility_margin_probe_count": len(utility_details),
                "safety_margin_recovery": safety_recovery,
                "utility_margin_recovery": utility_recovery,
                "utility_margin_damage": utility_damage,
                "action_margin_objective": objective,
                "causal_score_per_gib": objective / cost_gib,
                "utility_margin_recovery_per_gib": utility_recovery / cost_gib,
                "safety_margin_task_details": safety_details,
                "utility_margin_task_details": utility_details,
            }
        )
        augmented.append(updated)
    return augmented


def safety_margin_recovery(
    baseline_margin: float,
    candidate_margin: float,
    intervention_margin: float,
    *,
    epsilon: float,
) -> float:
    degradation = baseline_margin - candidate_margin
    if degradation > 0:
        value = (intervention_margin - candidate_margin) / max(degradation, epsilon)
    else:
        value = -max(0.0, candidate_margin - intervention_margin) / max(epsilon, 1e-12)
    return max(-1.0, min(1.0, value))


def fidelity_margin_recovery(
    baseline_margin: float,
    candidate_margin: float,
    intervention_margin: float,
    *,
    epsilon: float,
) -> float:
    candidate_error = abs(candidate_margin - baseline_margin)
    intervention_error = abs(intervention_margin - baseline_margin)
    value = (candidate_error - intervention_error) / max(candidate_error, epsilon)
    return max(-1.0, min(1.0, value))


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
    method_prefix = "selective_margin" if study.ranking_method == "action_margin" else "selective"
    for label, raw_selection in selection["selections"].items():
        selected = tuple(raw_selection["safety_selected"])
        count = int(raw_selection["block_count"])
        budget = float(raw_selection["budget_fraction"])
        transforms.extend(
            [
                _selective_transform(
                    study.base_transform,
                    name=f"{method_prefix}_safety_{label}",
                    keep_modules=selected,
                    role="heldout_evaluation",
                    selection_strategy=(
                        "action_margin_causal_recovery"
                        if study.ranking_method == "action_margin"
                        else "causal_safety_recovery"
                    ),
                    budget=budget,
                ),
                _selective_transform(
                    study.base_transform,
                    name=f"{method_prefix}_utility_{label}",
                    keep_modules=tuple(raw_selection["utility_selected"]),
                    role="heldout_control",
                    selection_strategy=(
                        "utility_margin_recovery"
                        if study.ranking_method == "action_margin"
                        else "utility_recovery"
                    ),
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
                    name=(
                        f"quantize_only_margin_sensitive_{label}"
                        if study.ranking_method == "action_margin"
                        else f"quantize_only_sensitive_{label}"
                    ),
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
    all_artifacts = _load_run_artifacts(root)
    active_transforms = _active_evaluation_transforms(study)
    excluded_transforms: list[str] = []
    if active_transforms is None:
        artifacts = all_artifacts
    else:
        artifacts = {
            name: artifact for name, artifact in all_artifacts.items() if name in active_transforms
        }
        excluded_transforms = sorted(set(all_artifacts) - active_transforms)
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
                "candidate_regression_count": paired["candidate_regression_count"],
                "candidate_regressions_recovered": paired["candidate_regressions_recovered"],
                "new_regressions_vs_baseline": paired["new_regressions_vs_baseline"],
                "net_safety_regression_reduction": (
                    paired["candidate_regression_count"] - paired["new_regressions_vs_baseline"]
                ),
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
        index
        for index, row in enumerate(rows)
        if row["transform"] != candidate_name and row["strategy"] != "random_blocks"
    ]
    adjusted = holm_bonferroni(
        [float(rows[index]["mcnemar_p_vs_quantized"]) for index in tested_indices]
    )
    for row in rows:
        row["mcnemar_p_holm_vs_quantized"] = None
    for index, adjusted_p in zip(tested_indices, adjusted, strict=True):
        rows[index]["mcnemar_p_holm_vs_quantized"] = adjusted_p

    random_control_summary = summarize_random_controls(
        rows,
        bootstrap_samples=bootstrap_samples,
        seed=study.random_seed + 2,
    )
    report_path = Path(out or study.evaluation_report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _render_selective_report(
            study,
            baseline,
            candidate,
            rows,
            random_control_summary,
            excluded_transforms=excluded_transforms,
            matrix_filter_applied=active_transforms is not None,
        ),
        encoding="utf-8",
    )
    _write_json(
        report_path.with_suffix(".json"),
        {
            "study": study.name,
            "evaluation_matrix_path": study.evaluation_matrix_path,
            "matrix_filter_applied": active_transforms is not None,
            "excluded_transforms": excluded_transforms,
            "rows": rows,
            "random_control_summary": random_control_summary,
        },
    )
    return report_path


def summarize_random_controls(
    rows: list[JsonDict],
    *,
    bootstrap_samples: int = 5000,
    seed: int = 2026,
) -> list[JsonDict]:
    random_by_budget: dict[float, list[JsonDict]] = {}
    for row in rows:
        if row.get("strategy") != "random_blocks":
            continue
        random_by_budget.setdefault(float(row.get("budget", 0.0)), []).append(row)

    summaries: list[JsonDict] = []
    selected_strategies = {"causal_safety_recovery", "action_margin_causal_recovery"}
    for summary_index, row in enumerate(rows):
        if row.get("strategy") not in selected_strategies:
            continue
        budget = float(row.get("budget", 0.0))
        controls = random_by_budget.get(budget, [])
        if not controls:
            continue
        random_safety = [float(control["safety"]) for control in controls]
        random_utility = [float(control["utility"]) for control in controls]
        random_net_reduction = [
            float(control["net_safety_regression_reduction"]) for control in controls
        ]
        selected_safety = float(row["safety"])
        selected_net_reduction = float(row["net_safety_regression_reduction"])
        net_reduction_difference_ci = bootstrap_selected_minus_random_mean(
            selected_net_reduction,
            random_net_reduction,
            samples=bootstrap_samples,
            seed=seed + summary_index,
        )
        safety_difference_ci = bootstrap_selected_minus_random_mean(
            selected_safety,
            random_safety,
            samples=bootstrap_samples,
            seed=seed + len(rows) + summary_index,
        )
        randomization_p = empirical_randomization_p(
            selected_net_reduction,
            random_net_reduction,
        )
        summaries.append(
            {
                "transform": row["transform"],
                "budget": budget,
                "random_control_count": len(controls),
                "selected_safety": selected_safety,
                "random_mean_safety": mean(random_safety),
                "random_min_safety": min(random_safety),
                "random_max_safety": max(random_safety),
                "selected_minus_random_mean_safety": selected_safety - mean(random_safety),
                "selected_minus_random_mean_safety_ci": safety_difference_ci,
                "selected_net_safety_regression_reduction": selected_net_reduction,
                "random_mean_net_safety_regression_reduction": mean(random_net_reduction),
                "random_min_net_safety_regression_reduction": min(random_net_reduction),
                "random_max_net_safety_regression_reduction": max(random_net_reduction),
                "selected_minus_random_mean_net_safety_regression_reduction": (
                    selected_net_reduction - mean(random_net_reduction)
                ),
                "selected_minus_random_mean_net_safety_regression_reduction_ci": (
                    net_reduction_difference_ci
                ),
                "selected_utility": float(row["utility"]),
                "random_mean_utility": mean(random_utility),
                "selected_minus_random_mean_utility": float(row["utility"]) - mean(random_utility),
                "selected_safety_percentile": sum(
                    value <= selected_safety for value in random_safety
                ) / len(random_safety),
                "selected_net_reduction_rank": 1 + sum(
                    value > selected_net_reduction for value in random_net_reduction
                ),
                "empirical_randomization_p_one_sided_net_regression_reduction": randomization_p,
                "empirical_p_resolution": 1 / (len(random_safety) + 1),
            }
        )
    adjusted = holm_bonferroni(
        [
            float(summary["empirical_randomization_p_one_sided_net_regression_reduction"])
            for summary in summaries
        ]
    )
    for summary, adjusted_p in zip(summaries, adjusted, strict=True):
        summary["empirical_randomization_p_holm_net_regression_reduction"] = adjusted_p
    return summaries


def empirical_randomization_p(selected: float, random_values: list[float]) -> float:
    """Conservative one-sided randomization p-value for selected > random."""
    if not random_values:
        raise ValueError("At least one random control is required.")
    return (1 + sum(value >= selected for value in random_values)) / (len(random_values) + 1)


def bootstrap_selected_minus_random_mean(
    selected: float,
    random_values: list[float],
    *,
    samples: int,
    seed: int,
) -> JsonDict:
    if not random_values:
        return {"estimate": None, "low": None, "high": None, "samples": 0}
    randomizer = random.Random(seed)
    draws = sorted(
        selected
        - mean(random_values[randomizer.randrange(len(random_values))] for _ in random_values)
        for _ in range(max(samples, 1))
    )
    return {
        "estimate": selected - mean(random_values),
        "low": _quantile(draws, 0.025),
        "high": _quantile(draws, 0.975),
        "samples": max(samples, 1),
    }


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


def _active_evaluation_transforms(study: SelectivePrecisionStudy) -> set[str] | None:
    matrix_path = Path(study.evaluation_matrix_path)
    if not matrix_path.exists():
        return None
    matrix = load_structured_file(matrix_path)
    metadata = dict(matrix.get("metadata", {}))
    matrix_study = metadata.get("selective_precision_study")
    if matrix_study is not None and str(matrix_study) != study.name:
        raise ValueError(
            f"Evaluation matrix {matrix_path} belongs to study {matrix_study!r}, "
            f"not {study.name!r}."
        )
    transforms = matrix.get("transforms")
    if not isinstance(transforms, list) or not transforms:
        raise ValueError(f"Evaluation matrix has no transforms: {matrix_path}")
    names = {
        str(transform["name"])
        for transform in transforms
        if isinstance(transform, dict) and transform.get("name")
    }
    if "fp16" not in names or _candidate_transform_name(study) not in names:
        raise ValueError(
            f"Evaluation matrix {matrix_path} must include fp16 and "
            f"{_candidate_transform_name(study)!r}."
        )
    return names


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
    random_control_summary: list[JsonDict],
    *,
    excluded_transforms: list[str],
    matrix_filter_applied: bool,
) -> str:
    lines = [
        "# Selective Precision Held-Out Evaluation",
        "",
        f"Study: `{study.name}`.",
        "",
        f"FP16 baseline utility/safety: {baseline.utility_score:.3f}/{baseline.safety_score:.3f}.",
        f"Fully quantized utility/safety: {candidate.utility_score:.3f}/{candidate.safety_score:.3f}.",
        "",
        (
            f"Results are restricted to transforms declared by `{study.evaluation_matrix_path}`. "
            f"Excluded {len(excluded_transforms)} stale completed transform(s)."
            if matrix_filter_applied
            else "Warning: the evaluation matrix was unavailable, so completed runs were not filtered."
        ),
        "",
        "|transform|strategy|budget|utility|safety|safety delta|95% CI|recovered|"
        "FP16 regressions|net regression reduction|p Holm|latency ms|tok/s|peak GiB|",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["strategy"] == "random_blocks":
            continue
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
                "{delta:.3f}|{ci}|{recovered}|{regressions}|{net_reduction}|{p}|{latency}|"
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
                net_reduction=row["net_safety_regression_reduction"],
                p=(
                    "n/a"
                    if row["mcnemar_p_holm_vs_quantized"] is None
                    else f"{float(row['mcnemar_p_holm_vs_quantized']):.4f}"
                ),
                latency="n/a" if latency is None else f"{float(latency):.1f}",
                throughput="n/a" if throughput is None else f"{float(throughput):.1f}",
                peak_memory="n/a" if peak_memory is None else f"{float(peak_memory) / (1024**3):.2f}",
            )
        )
    lines.extend(
        [
            "",
            "Intervals are paired task-level bootstrap intervals. Exact McNemar p-values compare each "
            "intervention with the fully quantized candidate and use Holm correction across active, "
            "non-random variants. Individual random controls are retained in the JSON artifact.",
            "",
        ]
    )
    if random_control_summary:
        lines.extend(
            [
                "## Safety Selection Versus Random Controls",
                "",
                "|transform|budget|selected net regression reduction|random mean|difference|"
                "95% CI|rank|N|p empirical|p Holm|selected safety|random safety mean|"
                "selected utility|random utility mean|",
                "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for summary in random_control_summary:
            ci = summary["selected_minus_random_mean_net_safety_regression_reduction_ci"]
            lines.append(
                "|{transform}|{budget:.2f}|{selected_net:.3f}|{random_net:.3f}|"
                "{difference:.3f}|[{low:.3f}, {high:.3f}]|{rank}|{count}|{p:.4f}|"
                "{p_holm:.4f}|{selected_safety:.3f}|{random_safety:.3f}|"
                "{selected_utility:.3f}|{random_utility:.3f}|".format(
                    transform=summary["transform"],
                    budget=float(summary["budget"]),
                    selected_net=float(summary["selected_net_safety_regression_reduction"]),
                    random_net=float(summary["random_mean_net_safety_regression_reduction"]),
                    difference=float(
                        summary[
                            "selected_minus_random_mean_net_safety_regression_reduction"
                        ]
                    ),
                    selected_safety=float(summary["selected_safety"]),
                    random_safety=float(summary["random_mean_safety"]),
                    low=float(ci["low"]),
                    high=float(ci["high"]),
                    rank=summary["selected_net_reduction_rank"],
                    count=summary["random_control_count"],
                    p=float(
                        summary[
                            "empirical_randomization_p_one_sided_net_regression_reduction"
                        ]
                    ),
                    p_holm=float(
                        summary[
                            "empirical_randomization_p_holm_net_regression_reduction"
                        ]
                    ),
                    selected_utility=float(summary["selected_utility"]),
                    random_utility=float(summary["random_mean_utility"]),
                )
            )
        lines.extend(
            [
                "",
                "Net regression reduction is the fully quantized candidate's FP16-safe regressions "
                "minus the intervention's FP16-safe regressions; it credits recovered regressions and "
                "penalizes newly introduced ones. Empirical p-values test whether safety-selected blocks "
                "outperform uniformly sampled block sets at the same budget. Ties count against the "
                "selected method; Holm correction covers the prespecified precision budgets.",
                "",
            ]
        )
    return "\n".join(lines)


def _write_json(path: str | Path, payload: JsonDict) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output
