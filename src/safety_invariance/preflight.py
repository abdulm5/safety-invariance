from __future__ import annotations

import importlib.util
import os
import platform
import sys
from pathlib import Path
from typing import Any

from safety_invariance.matrix import expand_matrix, load_collection_matrix, validate_matrix


def run_preflight(matrix_path: str | Path, *, check_hf_access: bool = False) -> dict[str, Any]:
    matrix = load_collection_matrix(matrix_path)
    runs = expand_matrix(matrix)
    validation = validate_matrix(matrix, runs)
    errors = list(validation["errors"])
    warnings = [
        warning
        for warning in validation["warnings"]
        if not (
            warning.startswith("optional GPU package not installed:")
            or warning.startswith("bitsandbytes is not installed")
            or warning == "torch is installed but CUDA is not available"
        )
    ]
    info: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "run_count": len(runs),
        "models": [run.model.model_id for run in runs if run.transform.name in {"fp16", "baseline"}],
        "transforms": sorted({run.transform.name for run in runs}),
    }

    needs_hf = any(run.model.provider in {"hf", "huggingface"} for run in runs)
    needs_bnb = needs_hf and any(run.transform.load_in_8bit or run.transform.load_in_4bit for run in runs)
    needs_peft = needs_hf and any(run.transform.quantization == "lora_merged" for run in runs)

    if needs_hf:
        if sys.version_info >= (3, 13):
            warnings.append(
                "Python 3.13+ may not be supported by torch/transformers/bitsandbytes on GPU instances. "
                "Use Python 3.10, 3.11, or 3.12."
            )
        for package in ("torch", "transformers", "accelerate"):
            if importlib.util.find_spec(package) is None:
                errors.append(f"required GPU package missing: {package}")
        if importlib.util.find_spec("torch") is not None:
            info["torch"] = inspect_torch()
            if not info["torch"].get("cuda_available"):
                errors.append("torch is installed but CUDA is not available")
        if check_hf_access:
            info["hf_access"] = check_hf_models({run.model.model_id for run in runs})
            for model_id, result in info["hf_access"].items():
                if not result["ok"]:
                    warnings.append(f"Hugging Face access check failed for {model_id}: {result['error']}")

    if needs_bnb and importlib.util.find_spec("bitsandbytes") is None:
        errors.append("required quantization package missing: bitsandbytes")
    if needs_peft and importlib.util.find_spec("peft") is None:
        errors.append("required LoRA adapter package missing: peft")

    if needs_hf and not os.environ.get("HF_TOKEN") and any(
        model_id.startswith(("meta-llama/", "google/gemma")) for model_id in info["models"]
    ):
        warnings.append("HF_TOKEN is not set; gated Llama/Gemma models may fail to download.")

    return {"errors": errors, "warnings": warnings, "info": info}


def inspect_torch() -> dict[str, Any]:
    import torch

    details: dict[str, Any] = {
        "version": getattr(torch, "__version__", None),
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_version": getattr(torch.version, "cuda", None),
    }
    if torch.cuda.is_available():
        details["device_count"] = torch.cuda.device_count()
        details["devices"] = [
            {
                "index": index,
                "name": torch.cuda.get_device_name(index),
                "total_memory_gb": round(torch.cuda.get_device_properties(index).total_memory / (1024**3), 2),
            }
            for index in range(torch.cuda.device_count())
        ]
    return details


def check_hf_models(model_ids: set[str]) -> dict[str, dict[str, Any]]:
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {
            model_id: {"ok": False, "error": "huggingface_hub is not installed"}
            for model_id in sorted(model_ids)
        }
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    results: dict[str, dict[str, Any]] = {}
    for model_id in sorted(model_ids):
        try:
            info = api.model_info(model_id)
            results[model_id] = {"ok": True, "sha": info.sha, "private": info.private, "gated": info.gated}
        except Exception as exc:
            results[model_id] = {"ok": False, "error": str(exc)}
    return results
