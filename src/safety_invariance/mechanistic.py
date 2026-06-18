from __future__ import annotations

import gc
import json
import math
from pathlib import Path
from statistics import mean
from typing import Iterable

from safety_invariance.agent import build_agent_prompt
from safety_invariance.modeling import MechanisticSignature, load_model_client
from safety_invariance.schemas import JsonDict, TaskSpec, model_spec_from_dict, transform_spec_from_dict
from safety_invariance.selective_precision import SelectivePrecisionStudy
from safety_invariance.tasks import load_task_suites


def analyze_mechanistic_divergence(
    study: SelectivePrecisionStudy,
    *,
    split: str = "calibration",
    out: str | Path,
    selection_artifact: str | Path | None = None,
) -> JsonDict:
    if split not in {"calibration", "evaluation"}:
        raise ValueError("Mechanistic split must be 'calibration' or 'evaluation'.")
    task_paths = (
        study.calibration_task_paths if split == "calibration" else study.evaluation_task_paths
    )
    _, tasks = load_task_suites(task_paths)
    model_spec = model_spec_from_dict(study.model)
    baseline_transform = transform_spec_from_dict({"name": "fp16", "quantization": "none"})
    candidate_transform = transform_spec_from_dict(study.base_transform)

    baseline_model = load_model_client(model_spec, baseline_transform)
    baseline_signatures = {
        task.id: _inspect_task(baseline_model, task, study.action_probes.get(task.id))
        for task in tasks
    }
    del baseline_model
    _release_gpu_memory()

    candidate_model = load_model_client(model_spec, candidate_transform)
    task_results: list[JsonDict] = []
    for task in tasks:
        candidate_signature = _inspect_task(candidate_model, task, study.action_probes.get(task.id))
        task_results.append(
            compare_signatures(task, baseline_signatures[task.id], candidate_signature)
        )
    runtime = dict(getattr(candidate_model, "runtime_metadata", {}))
    del candidate_model
    _release_gpu_memory()

    layer_results = aggregate_layer_divergence(task_results)
    artifact_path = Path(selection_artifact or study.calibration_artifact_path)
    correlation = None
    if artifact_path.exists():
        selection = json.loads(artifact_path.read_text(encoding="utf-8"))
        causal_scores = {
            str(item["block"]): float(item["causal_score_per_gib"])
            for item in selection.get("block_results", ())
        }
        correlation = correlate_layer_and_causal_scores(layer_results, causal_scores)

    payload: JsonDict = {
        "schema_version": 1,
        "study_name": study.name,
        "split": split,
        "model_id": model_spec.model_id,
        "baseline_transform": "fp16",
        "candidate_transform": candidate_transform.name,
        "task_count": len(tasks),
        "task_results": task_results,
        "layer_results": layer_results,
        "causal_score_correlation": correlation,
        "candidate_runtime": runtime,
        "method": {
            "hidden_state": "Cosine and normalized L2 distance at the final prompt token.",
            "output_distribution": "Symmetric KL divergence between next-token distributions.",
            "action_margin": "Mean token log-likelihood(safe completion) minus unsafe completion.",
        },
    }
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def compare_signatures(
    task: TaskSpec,
    baseline: MechanisticSignature,
    candidate: MechanisticSignature,
) -> JsonDict:
    import torch

    if baseline.block_names != candidate.block_names:
        raise ValueError(f"Transformer block names differ for task {task.id}.")
    layer_distances: list[JsonDict] = []
    for block, left, right in zip(
        baseline.block_names,
        baseline.hidden_states,
        candidate.hidden_states,
        strict=True,
    ):
        left_tensor = left.float()
        right_tensor = right.float()
        cosine = torch.nn.functional.cosine_similarity(left_tensor, right_tensor, dim=0)
        normalized_l2 = torch.linalg.vector_norm(left_tensor - right_tensor) / max(
            float(torch.linalg.vector_norm(left_tensor).item()),
            1e-12,
        )
        layer_distances.append(
            {
                "block": block,
                "cosine_distance": float((1.0 - cosine).item()),
                "normalized_l2_distance": float(normalized_l2.item()),
            }
        )

    output_kl = symmetric_kl_divergence(baseline.next_token_logits, candidate.next_token_logits)
    baseline_margin = baseline.safety_action_margin
    candidate_margin = candidate.safety_action_margin
    return {
        "task_id": task.id,
        "category": task.category,
        "is_safety_task": task.category not in {"utility", "benign"},
        "layers": layer_distances,
        "next_token_symmetric_kl": output_kl,
        "next_token_argmax_agreement": int(
            baseline.next_token_logits.argmax().item() == candidate.next_token_logits.argmax().item()
        ),
        "baseline_safety_action_margin": baseline_margin,
        "candidate_safety_action_margin": candidate_margin,
        "baseline_preference_margin": baseline_margin,
        "candidate_preference_margin": candidate_margin,
        "safety_action_margin_delta": (
            None
            if baseline_margin is None or candidate_margin is None
            else candidate_margin - baseline_margin
        ),
    }


def symmetric_kl_divergence(left_logits, right_logits) -> float:
    import torch

    left_log_probs = torch.log_softmax(left_logits.float(), dim=-1)
    right_log_probs = torch.log_softmax(right_logits.float(), dim=-1)
    left_probs = left_log_probs.exp()
    right_probs = right_log_probs.exp()
    left_to_right = torch.sum(left_probs * (left_log_probs - right_log_probs))
    right_to_left = torch.sum(right_probs * (right_log_probs - left_log_probs))
    return float((0.5 * (left_to_right + right_to_left)).item())


def aggregate_layer_divergence(task_results: Iterable[JsonDict]) -> list[JsonDict]:
    by_layer: dict[str, dict[str, list[float]]] = {}
    for task in task_results:
        group = "safety" if task["is_safety_task"] else "utility"
        for layer in task["layers"]:
            values = by_layer.setdefault(
                str(layer["block"]),
                {"safety_cosine": [], "utility_cosine": [], "safety_l2": [], "utility_l2": []},
            )
            values[f"{group}_cosine"].append(float(layer["cosine_distance"]))
            values[f"{group}_l2"].append(float(layer["normalized_l2_distance"]))

    rows: list[JsonDict] = []
    for block, values in by_layer.items():
        safety_cosine = _optional_mean(values["safety_cosine"])
        utility_cosine = _optional_mean(values["utility_cosine"])
        safety_l2 = _optional_mean(values["safety_l2"])
        utility_l2 = _optional_mean(values["utility_l2"])
        rows.append(
            {
                "block": block,
                "safety_task_count": len(values["safety_cosine"]),
                "utility_task_count": len(values["utility_cosine"]),
                "safety_mean_cosine_distance": safety_cosine,
                "utility_mean_cosine_distance": utility_cosine,
                "safety_specific_cosine_excess": _optional_difference(safety_cosine, utility_cosine),
                "safety_mean_normalized_l2": safety_l2,
                "utility_mean_normalized_l2": utility_l2,
                "safety_specific_l2_excess": _optional_difference(safety_l2, utility_l2),
            }
        )
    return sorted(rows, key=lambda row: _block_sort_key(str(row["block"])))


def correlate_layer_and_causal_scores(
    layer_results: Iterable[JsonDict],
    causal_scores: dict[str, float],
) -> JsonDict:
    pairs: list[tuple[float, float]] = []
    matched_blocks: list[str] = []
    for layer in layer_results:
        block = str(layer["block"])
        divergence = layer.get("safety_mean_cosine_distance")
        if block not in causal_scores or divergence is None:
            continue
        pairs.append((float(divergence), float(causal_scores[block])))
        matched_blocks.append(block)
    return {
        "pearson_r": pearson_correlation(pairs),
        "matched_block_count": len(pairs),
        "matched_blocks": matched_blocks,
        "x": "safety_mean_cosine_distance",
        "y": "causal_score_per_gib",
    }


def pearson_correlation(pairs: Iterable[tuple[float, float]]) -> float | None:
    values = list(pairs)
    if len(values) < 2:
        return None
    xs = [pair[0] for pair in values]
    ys = [pair[1] for pair in values]
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in values)
    x_scale = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_scale = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if x_scale == 0 or y_scale == 0:
        return None
    return numerator / (x_scale * y_scale)


def _inspect_task(model, task: TaskSpec, raw_probe: object) -> MechanisticSignature:
    if not hasattr(model, "inspect_prompt"):
        raise RuntimeError("Mechanistic analysis requires a Hugging Face model client.")
    probe = dict(raw_probe) if isinstance(raw_probe, dict) else {}
    return model.inspect_prompt(
        build_agent_prompt(task),
        safe_completion=probe.get("preferred_completion", probe.get("safe_completion")),
        unsafe_completion=probe.get("dispreferred_completion", probe.get("unsafe_completion")),
    )


def _release_gpu_memory() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        return


def _optional_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _optional_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _block_sort_key(block: str) -> tuple[str, int]:
    prefix, _, suffix = block.rpartition(".")
    try:
        return prefix, int(suffix)
    except ValueError:
        return block, 0
