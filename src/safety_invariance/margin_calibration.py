from __future__ import annotations

import gc
import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from safety_invariance.agent import build_agent_prompt
from safety_invariance.modeling import load_model_client
from safety_invariance.schemas import JsonDict, model_spec_from_dict, transform_spec_from_dict
from safety_invariance.selective_precision import (
    SelectivePrecisionStudy,
    selective_calibration_transforms,
)
from safety_invariance.tasks import load_task_suites


def collect_action_margins(
    study: SelectivePrecisionStudy,
    *,
    out: str | Path | None = None,
    skip_existing: bool = True,
    on_completed: Callable[[str, int, int], None] | None = None,
) -> JsonDict:
    output = Path(out or study.margin_artifact_path)
    _, tasks = load_task_suites(study.calibration_task_paths)
    tasks_by_id = {task.id: task for task in tasks}
    transforms = selective_calibration_transforms(study)
    fingerprint = _study_fingerprint(study, transforms)
    payload = _load_or_initialize(output, study, fingerprint, skip_existing=skip_existing)
    model_spec = model_spec_from_dict(study.model)

    for raw_transform in transforms:
        transform = transform_spec_from_dict(raw_transform)
        if skip_existing and transform.name in payload["transforms"]:
            continue
        started = time.perf_counter()
        model = load_model_client(model_spec, transform)
        task_results: JsonDict = {}
        try:
            for task_id, raw_probe in study.action_probes.items():
                task = tasks_by_id[task_id]
                probe = dict(raw_probe)
                preferred = str(
                    probe.get("preferred_completion", probe.get("safe_completion"))
                )
                dispreferred = str(
                    probe.get("dispreferred_completion", probe.get("unsafe_completion"))
                )
                if not hasattr(model, "preference_margin"):
                    raise RuntimeError(
                        "Action-margin collection requires a Hugging Face model client."
                    )
                result = model.preference_margin(
                    build_agent_prompt(task),
                    preferred_completion=preferred,
                    dispreferred_completion=dispreferred,
                )
                task_results[task_id] = {
                    "task_id": task_id,
                    "category": task.category,
                    "probe_kind": (
                        "utility" if task.category in {"utility", "benign"} else "safety"
                    ),
                    **result,
                }
            runtime_provider = getattr(model, "get_runtime_metadata", None)
            runtime = (
                runtime_provider()
                if callable(runtime_provider)
                else dict(getattr(model, "runtime_metadata", {}))
            )
            payload["transforms"][transform.name] = {
                "transform": raw_transform,
                "duration_seconds": time.perf_counter() - started,
                "runtime": runtime,
                "tasks": task_results,
            }
            payload["completed_transforms"] = sorted(payload["transforms"])
            _write_json_atomic(output, payload)
            if on_completed is not None:
                on_completed(transform.name, len(payload["transforms"]), len(transforms))
        finally:
            del model
            _release_model_memory()

    payload["complete"] = len(payload["transforms"]) == len(transforms)
    _write_json_atomic(output, payload)
    return payload


def _load_or_initialize(
    output: Path,
    study: SelectivePrecisionStudy,
    fingerprint: str,
    *,
    skip_existing: bool,
) -> JsonDict:
    if output.exists() and skip_existing:
        payload = json.loads(output.read_text(encoding="utf-8"))
        if payload.get("fingerprint") != fingerprint:
            raise ValueError(
                f"Existing margin artifact {output} was created from a different study definition; "
                "rerun with --no-skip-existing to replace it."
            )
        return payload
    return {
        "schema_version": 1,
        "study_name": study.name,
        "model": study.model,
        "ranking_method": study.ranking_method,
        "fingerprint": fingerprint,
        "probe_count": len(study.action_probes),
        "completed_transforms": [],
        "complete": False,
        "transforms": {},
    }


def _study_fingerprint(
    study: SelectivePrecisionStudy,
    transforms: tuple[JsonDict, ...],
) -> str:
    encoded = json.dumps(
        {
            "model": study.model,
            "transforms": transforms,
            "action_probes": study.action_probes,
            "task_files": [
                {
                    "name": Path(path).name,
                    "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                }
                for path in study.calibration_task_paths
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _release_model_memory() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        return
