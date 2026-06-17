from __future__ import annotations

import json
import re
import importlib.util
import gc
from dataclasses import dataclass
from pathlib import Path

from safety_invariance.config import load_structured_file, resolve_relative_path
from safety_invariance.evaluation import load_score_bundle, with_retention, write_score_bundle
from safety_invariance.reporting import write_markdown_report
from safety_invariance.runner import run_experiment, write_summary_csv
from safety_invariance.schemas import (
    JsonDict,
    RunConfig,
    model_spec_from_dict,
    transform_spec_from_dict,
)
from safety_invariance.tasks import load_task_suites, validate_tasks


@dataclass(frozen=True)
class CollectionMatrix:
    output_root: str
    report_path: str
    models: tuple[JsonDict, ...]
    transforms: tuple[JsonDict, ...]
    task_paths: tuple[str, ...]
    seeds: tuple[int, ...]
    max_new_tokens: int = 256
    temperature: float = 0.0
    mitigation: JsonDict | None = None
    context_compression: JsonDict | None = None
    metadata: JsonDict | None = None


def load_collection_matrix(path: str | Path) -> CollectionMatrix:
    matrix_path = Path(path)
    data = load_structured_file(matrix_path)
    task_paths = tuple(str(resolve_relative_path(task_path, matrix_path)) for task_path in data["task_paths"])
    return CollectionMatrix(
        output_root=data.get("output_root", "runs/collection"),
        report_path=data.get("report_path", "reports/collection.md"),
        models=tuple(data.get("models", ())),
        transforms=tuple(data.get("transforms", ())),
        task_paths=task_paths,
        seeds=tuple(data.get("seeds", (0,))),
        max_new_tokens=int(data.get("max_new_tokens", 256)),
        temperature=float(data.get("temperature", 0.0)),
        mitigation=dict(data.get("mitigation", {})),
        context_compression=dict(data.get("context_compression", {})),
        metadata=dict(data.get("metadata", {})),
    )


def expand_matrix(matrix: CollectionMatrix) -> tuple[RunConfig, ...]:
    runs: list[RunConfig] = []
    for raw_model in matrix.models:
        model = model_spec_from_dict(raw_model)
        model_name = slug(model.metadata.get("label", model.model_id))
        for raw_transform in matrix.transforms:
            transform = transform_spec_from_dict(raw_transform)
            run_name = f"{model_name}_{slug(transform.name)}"
            runs.append(
                RunConfig(
                    run_name=run_name,
                    output_dir=str(Path(matrix.output_root) / run_name),
                    model=model,
                    transform=transform,
                    task_paths=matrix.task_paths,
                    seeds=matrix.seeds,
                    max_new_tokens=matrix.max_new_tokens,
                    temperature=matrix.temperature,
                    context_compression=dict(raw_transform.get("context_compression", matrix.context_compression or {})),
                    mitigation=dict(raw_transform.get("mitigation", matrix.mitigation or {})),
                    metadata={
                        **(matrix.metadata or {}),
                        "collection_matrix": True,
                    },
                )
            )
    return tuple(runs)


def run_collection_matrix(
    path: str | Path,
    *,
    dry_run: bool = False,
    skip_existing: bool = True,
) -> dict[str, object]:
    matrix = load_collection_matrix(path)
    runs = expand_matrix(matrix)
    validation = validate_matrix(matrix, runs)
    if validation["errors"]:
        raise ValueError("Matrix validation failed: " + "; ".join(validation["errors"]))
    plan_path = write_run_plan(matrix, runs)
    if dry_run:
        return {"dry_run": True, "run_count": len(runs), "plan_path": str(plan_path), "validation": validation}

    completed: list[str] = []
    for config in runs:
        score_path = config.run_dir / "scores.json"
        if skip_existing and score_path.exists():
            completed.append(str(config.run_dir))
            continue
        config.run_dir.mkdir(parents=True, exist_ok=True)
        (config.run_dir / "config.resolved.json").write_text(
            json.dumps(run_config_to_json(config), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        try:
            run_experiment(config)
        finally:
            cleanup_after_run()
        completed.append(str(config.run_dir))

    apply_matrix_retention(runs)
    report = write_markdown_report(str(Path(matrix.output_root) / "*"), matrix.report_path)
    return {
        "dry_run": False,
        "run_count": len(runs),
        "completed": completed,
        "plan_path": str(plan_path),
        "report_path": str(report),
        "validation": validation,
    }


def apply_matrix_retention(runs: tuple[RunConfig, ...]) -> None:
    baselines = {
        config.model.model_id: config
        for config in runs
        if config.transform.name in {"fp16", "baseline"}
    }
    for config in runs:
        score_path = config.run_dir / "scores.json"
        if not score_path.exists():
            continue
        bundle = load_score_bundle(score_path)
        baseline_config = baselines.get(config.model.model_id)
        if baseline_config is None:
            continue
        baseline = load_score_bundle(baseline_config.run_dir / "scores.json")
        scored = with_retention(bundle, baseline)
        write_score_bundle(score_path, scored)
        write_summary_csv(config.run_dir / "summary.csv", scored)


def validate_matrix(matrix: CollectionMatrix, runs: tuple[RunConfig, ...] | None = None) -> dict[str, list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if not matrix.models:
        errors.append("matrix defines no models")
    if not matrix.transforms:
        errors.append("matrix defines no transforms")
    if not any(transform.get("name") in {"fp16", "baseline"} for transform in matrix.transforms):
        errors.append("matrix must include an FP16/baseline transform for retention scoring")
    try:
        _, tasks = load_task_suites(matrix.task_paths)
        errors.extend(validate_tasks(tasks))
    except Exception as exc:
        errors.append(str(exc))
    for raw_transform in matrix.transforms:
        quantization = raw_transform.get("quantization", raw_transform.get("name", "none"))
        if quantization in {"gptq", "awq"} and not raw_transform.get("metadata", {}).get("quantized_model_id"):
            errors.append(f"{quantization} transform requires metadata.quantized_model_id")
        if quantization == "lora_merged" and not raw_transform.get("metadata", {}).get("peft_adapter_id"):
            errors.append("lora_merged transform requires metadata.peft_adapter_id")
        if quantization == "pruned" and raw_transform.get("metadata", {}).get("pruning_amount", 0.2) <= 0:
            errors.append("pruned transform requires pruning_amount > 0")
    if any(model.get("provider") in {"hf", "huggingface"} for model in matrix.models):
        for package in ("torch", "transformers", "accelerate"):
            if importlib.util.find_spec(package) is None:
                warnings.append(f"optional GPU package not installed: {package}")
        if any(transform.get("load_in_8bit") or transform.get("load_in_4bit") for transform in matrix.transforms):
            if importlib.util.find_spec("bitsandbytes") is None:
                warnings.append("bitsandbytes is not installed; int8/nf4 runs will fail")
        if importlib.util.find_spec("torch") is not None:
            try:
                import torch

                if not torch.cuda.is_available():
                    warnings.append("torch is installed but CUDA is not available")
            except Exception as exc:  # pragma: no cover - environment dependent.
                warnings.append(f"could not inspect CUDA availability: {exc}")
    if runs:
        seen: set[str] = set()
        for run in runs:
            if run.run_name in seen:
                errors.append(f"duplicate run name: {run.run_name}")
            seen.add(run.run_name)
    return {"warnings": warnings, "errors": errors}


def write_run_plan(matrix: CollectionMatrix, runs: tuple[RunConfig, ...]) -> Path:
    output = Path(matrix.output_root) / "collection_plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "run_count": len(runs),
                "runs": [run_config_to_json(run) for run in runs],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output


def run_config_to_json(config: RunConfig) -> JsonDict:
    return {
        "run_name": config.run_name,
        "output_dir": config.output_dir,
        "model": {
            "provider": config.model.provider,
            "model_id": config.model.model_id,
            "revision": config.model.revision,
            "device_map": config.model.device_map,
            "torch_dtype": config.model.torch_dtype,
            "cache_dir": config.model.cache_dir,
            "trust_remote_code": config.model.trust_remote_code,
            "metadata": config.model.metadata,
        },
        "transform": {
            "name": config.transform.name,
            "quantization": config.transform.quantization,
            "load_in_8bit": config.transform.load_in_8bit,
            "load_in_4bit": config.transform.load_in_4bit,
            "bnb_4bit_quant_type": config.transform.bnb_4bit_quant_type,
            "keep_modules_high_precision": list(config.transform.keep_modules_high_precision),
            "metadata": config.transform.metadata,
        },
        "task_paths": list(config.task_paths),
        "seeds": list(config.seeds),
        "max_new_tokens": config.max_new_tokens,
        "temperature": config.temperature,
        "context_compression": config.context_compression,
        "mitigation": config.mitigation,
        "metadata": config.metadata,
    }


def slug(value: object) -> str:
    text = str(value).split("/")[-1].lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "run"


def cleanup_after_run() -> None:
    gc.collect()
    if importlib.util.find_spec("torch") is None:
        return
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        return
