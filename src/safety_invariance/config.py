from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safety_invariance.schemas import JsonDict, RunConfig, run_config_from_dict


def load_structured_file(path: str | Path) -> JsonDict:
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        data: Any = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "YAML configs require the optional dependency: pip install -e '.[yaml]'"
            ) from exc
        data = yaml.safe_load(text)
    else:
        raise ValueError(f"Unsupported config format: {config_path.suffix}")
    if not isinstance(data, dict):
        raise ValueError(f"Expected object at top level of {config_path}")
    return data


def load_run_config(path: str | Path) -> RunConfig:
    data = load_structured_file(path)
    config = run_config_from_dict(data)
    task_paths = tuple(str(resolve_relative_path(task_path, Path(path))) for task_path in config.task_paths)
    return RunConfig(
        run_name=config.run_name,
        output_dir=config.output_dir,
        model=config.model,
        transform=config.transform,
        task_paths=task_paths,
        seeds=config.seeds,
        max_new_tokens=config.max_new_tokens,
        temperature=config.temperature,
        context_compression=config.context_compression,
        mitigation=config.mitigation,
        metadata=config.metadata,
    )


def resolve_relative_path(raw_path: str, config_path: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    candidates = [
        Path.cwd() / path,
        config_path.resolve().parent / path,
        config_path.resolve().parent.parent / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
