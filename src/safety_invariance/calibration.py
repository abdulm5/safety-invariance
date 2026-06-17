from __future__ import annotations

import json
from pathlib import Path

from safety_invariance.mitigations import apply_selective_precision, select_safety_sensitive_modules, summarize_divergence
from safety_invariance.runner import load_events
from safety_invariance.schemas import TransformSpec, to_dict, transform_spec_from_dict


def calibrate_selective_precision(
    *,
    baseline_run_dir: str | Path,
    candidate_run_dir: str | Path,
    out: str | Path,
    base_transform: dict | None = None,
    max_modules: int = 4,
) -> dict[str, object]:
    baseline_traces = load_events(Path(baseline_run_dir) / "events.jsonl")
    candidate_traces = load_events(Path(candidate_run_dir) / "events.jsonl")
    divergence = summarize_divergence(baseline_traces, candidate_traces)
    modules = select_safety_sensitive_modules(divergence, max_modules=max_modules)
    if base_transform is None:
        manifest_path = Path(candidate_run_dir) / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            base_transform = manifest.get("transform", {})
        else:
            base_transform = {"name": "nf4_4bit", "quantization": "nf4_4bit", "load_in_4bit": True}
    transform = apply_selective_precision(transform_spec_from_dict(base_transform), modules)
    payload = {
        "divergence": divergence,
        "selected_modules": list(modules),
        "transform": to_dict(transform),
        "usage": {
            "copy_transform_into_config": True,
            "note": "For int8, selected modules are passed to bitsandbytes skip_modules where supported. For 4-bit, support depends on the installed transformers/bitsandbytes backend.",
        },
    }
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload
