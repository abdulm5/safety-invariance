from __future__ import annotations

import importlib.metadata
import platform
from typing import Any


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def collect_environment() -> dict[str, Any]:
    packages = {
        "safety-invariance": package_version("safety-invariance"),
        "torch": package_version("torch"),
        "transformers": package_version("transformers"),
        "accelerate": package_version("accelerate"),
        "bitsandbytes": package_version("bitsandbytes"),
    }
    gpu: dict[str, Any] = {"available": False}
    try:
        import torch

        gpu["available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            gpu["device_count"] = torch.cuda.device_count()
            gpu["devices"] = [
                {
                    "index": index,
                    "name": torch.cuda.get_device_name(index),
                    "total_memory_gb": round(
                        torch.cuda.get_device_properties(index).total_memory / (1024**3), 2
                    ),
                }
                for index in range(torch.cuda.device_count())
            ]
    except Exception as exc:  # pragma: no cover - depends on optional GPU stack.
        gpu["error"] = str(exc)
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "gpu": gpu,
    }
