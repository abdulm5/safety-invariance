from __future__ import annotations

import gc
import importlib.metadata
import importlib.util
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safety_invariance.config import load_structured_file
from safety_invariance.external import (
    build_agentdojo_command,
    build_agentharm_command,
    run_agentdojo,
    run_agentharm,
)
from safety_invariance.openai_compat import ModelProfile, OpenAIChatBackend, OpenAICompatServer, model_profile_from_dict


@dataclass(frozen=True)
class ExternalBenchmark:
    name: str
    kind: str
    config: dict[str, Any]


@dataclass(frozen=True)
class ExternalStudy:
    name: str
    output_root: str
    profiles: tuple[ModelProfile, ...]
    benchmarks: tuple[ExternalBenchmark, ...]
    host: str = "127.0.0.1"
    port: int = 8765
    metadata: dict[str, Any] | None = None


def load_external_study(path: str | Path) -> ExternalStudy:
    data = load_structured_file(Path(path))
    return ExternalStudy(
        name=str(data["name"]),
        output_root=str(data.get("output_root", f"runs/{data['name']}")),
        profiles=tuple(model_profile_from_dict(item) for item in data.get("profiles", [])),
        benchmarks=tuple(
            ExternalBenchmark(name=str(item["name"]), kind=str(item["kind"]), config=dict(item))
            for item in data.get("benchmarks", [])
        ),
        host=str(data.get("server", {}).get("host", "127.0.0.1")),
        port=int(data.get("server", {}).get("port", 8765)),
        metadata=dict(data.get("metadata", {})),
    )


def validate_external_study(study: ExternalStudy, *, check_runtime: bool = False) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not study.profiles:
        errors.append("study defines no model profiles")
    if not study.benchmarks:
        errors.append("study defines no benchmarks")
    profile_names = [profile.name for profile in study.profiles]
    if len(profile_names) != len(set(profile_names)):
        errors.append("model profile names must be unique")
    benchmark_names = [benchmark.name for benchmark in study.benchmarks]
    if len(benchmark_names) != len(set(benchmark_names)):
        errors.append("benchmark names must be unique")
    by_model: dict[str, list[ModelProfile]] = {}
    for profile in study.profiles:
        by_model.setdefault(profile.model.model_id, []).append(profile)
        if profile.temperature != 0:
            warnings.append(f"confirmatory profile {profile.name} uses nonzero temperature")
        if profile.transform.keep_modules_high_precision and profile.transform.quantization not in {
            "int8",
            "nf4_4bit",
            "4bit",
        }:
            errors.append(
                f"profile {profile.name} keeps high-precision modules without a supported quantized transform"
            )
    for model_id, profiles in by_model.items():
        if not any(profile.transform.name in {"fp16", "baseline"} for profile in profiles):
            errors.append(f"model {model_id} has no matching FP16 baseline profile")
    for benchmark in study.benchmarks:
        if benchmark.kind not in {"agentdojo", "agentharm"}:
            errors.append(f"unsupported external benchmark kind: {benchmark.kind}")
    if check_runtime:
        for package in ("torch", "transformers", "accelerate", "bitsandbytes"):
            if importlib.util.find_spec(package) is None:
                errors.append(f"required GPU package is not installed: {package}")
        if importlib.util.find_spec("torch") is not None:
            try:
                import torch

                if not torch.cuda.is_available():
                    errors.append("CUDA is not available")
            except Exception as exc:
                errors.append(f"could not inspect CUDA: {exc}")
        if importlib.util.find_spec("agentdojo") is None and any(
            benchmark.kind == "agentdojo" for benchmark in study.benchmarks
        ):
            errors.append("AgentDojo is not installed; install the external-benchmarks extra")
        if shutil.which("inspect") is None and any(
            benchmark.kind == "agentharm" for benchmark in study.benchmarks
        ):
            errors.append("Inspect is not installed; install the external-benchmarks extra")
        for benchmark in study.benchmarks:
            if benchmark.kind != "agentharm":
                continue
            for key in ("refusal_judge", "semantic_judge"):
                judge = str(benchmark.config.get(key, ""))
                env_name = _judge_key_env(judge)
                if env_name and not os.getenv(env_name):
                    warnings.append(f"{benchmark.name} uses {judge}; {env_name} is not set")
        if any("meta-llama/" in profile.model.model_id.lower() for profile in study.profiles):
            if not (os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")):
                warnings.append("HF_TOKEN is not set; gated Llama checkpoint access may fail")
    return {"errors": errors, "warnings": sorted(set(warnings))}


def external_study_plan(study: ExternalStudy) -> dict[str, object]:
    base_url = f"http://{study.host}:{study.port}/v1"
    runs = []
    for profile in study.profiles:
        for benchmark in study.benchmarks:
            out_dir = Path(study.output_root) / profile.name / benchmark.name
            runs.append(
                {
                    "profile": profile.name,
                    "model_id": profile.model.model_id,
                    "transform": profile.transform.name,
                    "benchmark": benchmark.name,
                    "kind": benchmark.kind,
                    "out_dir": str(out_dir),
                    "command": _build_command(profile, benchmark, out_dir),
                    "base_url": base_url,
                }
            )
    return {"study": study.name, "run_count": len(runs), "runs": runs}


def write_external_study_plan(study: ExternalStudy) -> Path:
    output = Path(study.output_root) / "external_plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = external_study_plan(study)
    payload["validation"] = validate_external_study(study)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output


def run_external_study(
    study: ExternalStudy,
    *,
    dry_run: bool = False,
    skip_existing: bool = True,
    profile_names: set[str] | None = None,
    benchmark_names: set[str] | None = None,
) -> dict[str, object]:
    validation = validate_external_study(study, check_runtime=not dry_run)
    if validation["errors"]:
        raise ValueError("External study validation failed: " + "; ".join(validation["errors"]))
    plan_path = write_external_study_plan(study)
    selected_profiles = tuple(
        profile for profile in study.profiles if not profile_names or profile.name in profile_names
    )
    selected_benchmarks = tuple(
        benchmark for benchmark in study.benchmarks if not benchmark_names or benchmark.name in benchmark_names
    )
    if profile_names and {profile.name for profile in selected_profiles} != profile_names:
        missing = sorted(profile_names - {profile.name for profile in selected_profiles})
        raise ValueError("Unknown profile(s): " + ", ".join(missing))
    if benchmark_names and {benchmark.name for benchmark in selected_benchmarks} != benchmark_names:
        missing = sorted(benchmark_names - {benchmark.name for benchmark in selected_benchmarks})
        raise ValueError("Unknown benchmark(s): " + ", ".join(missing))
    if dry_run:
        return {
            "study": study.name,
            "dry_run": True,
            "run_count": len(selected_profiles) * len(selected_benchmarks),
            "plan_path": str(plan_path),
            "validation": validation,
        }

    completed: list[str] = []
    for profile in selected_profiles:
        pending = [
            benchmark
            for benchmark in selected_benchmarks
            if not (
                skip_existing
                and (Path(study.output_root) / profile.name / benchmark.name / "completed.json").exists()
            )
        ]
        if not pending:
            completed.extend(
                str(Path(study.output_root) / profile.name / benchmark.name)
                for benchmark in selected_benchmarks
            )
            continue
        profile_root = Path(study.output_root) / profile.name
        backend = OpenAIChatBackend(profile, telemetry_path=profile_root / "server_events.jsonl")
        server = OpenAICompatServer((study.host, study.port), backend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            server_manifest = backend.manifest()
            server_manifest["base_url"] = f"http://{study.host}:{server.server_port}/v1"
            server_manifest["packages"] = _package_versions()
            profile_root.mkdir(parents=True, exist_ok=True)
            (profile_root / "server_manifest.json").write_text(
                json.dumps(server_manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            for benchmark in pending:
                out_dir = profile_root / benchmark.name
                result = _run_benchmark(profile, benchmark, out_dir, study.host, server.server_port)
                completion = {
                    "study": study.name,
                    "profile": profile.name,
                    "benchmark": benchmark.name,
                    "completed_at_unix": int(time.time()),
                    "result_manifest": result,
                }
                (out_dir / "completed.json").write_text(
                    json.dumps(completion, indent=2, sort_keys=True), encoding="utf-8"
                )
                completed.append(str(out_dir))
            server_manifest = backend.manifest()
            server_manifest["base_url"] = f"http://{study.host}:{server.server_port}/v1"
            server_manifest["packages"] = _package_versions()
            server_manifest["completed_benchmarks"] = [benchmark.name for benchmark in pending]
            (profile_root / "server_manifest.json").write_text(
                json.dumps(server_manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
            del server
            del backend
            gc.collect()
            _clear_cuda_cache()
    return {
        "study": study.name,
        "dry_run": False,
        "run_count": len(selected_profiles) * len(selected_benchmarks),
        "completed": completed,
        "plan_path": str(plan_path),
        "validation": validation,
    }


def _build_command(
    profile: ModelProfile,
    benchmark: ExternalBenchmark,
    out_dir: Path,
) -> list[str]:
    config = benchmark.config
    if benchmark.kind == "agentdojo":
        return build_agentdojo_command(
            model="VLLM_PARSED",
            model_id=profile.name,
            suite=None,
            attack=config.get("attack"),
            defense=config.get("defense"),
            user_tasks=tuple(config.get("user_tasks", [])),
            injection_tasks=tuple(config.get("injection_tasks", [])),
            benchmark_version=str(config.get("benchmark_version", "v1.2.2")),
            logdir=out_dir / "native_logs",
            extra_args=tuple(
                arg
                for suite in config.get("suites", [])
                for arg in ("-s", str(suite))
            )
            + tuple(str(arg) for arg in config.get("extra_args", [])),
        )
    if benchmark.kind == "agentharm":
        return build_agentharm_command(
            model=f"openai-api/si/{profile.name}",
            task=str(config.get("task", "agentharm")),
            split=str(config.get("split", "test_public")),
            log_dir=out_dir / "native_logs",
            refusal_judge=config.get("refusal_judge"),
            semantic_judge=config.get("semantic_judge"),
            extra_args=tuple(str(arg) for arg in config.get("extra_args", [])),
        )
    raise ValueError(f"Unsupported benchmark kind: {benchmark.kind}")


def _run_benchmark(
    profile: ModelProfile,
    benchmark: ExternalBenchmark,
    out_dir: Path,
    host: str,
    port: int,
) -> dict[str, object]:
    config = benchmark.config
    env = os.environ.copy()
    base_url = f"http://{host}:{port}/v1"
    if benchmark.kind == "agentdojo":
        env.update(
            {
                "LOCAL_LLM_PORT": str(port),
            }
        )
        suites = tuple(str(item) for item in config.get("suites", []))
        extra_args = tuple(
            arg for suite in suites for arg in ("-s", suite)
        ) + tuple(str(arg) for arg in config.get("extra_args", []))
        return run_agentdojo(
            model="VLLM_PARSED",
            model_id=profile.name,
            out_dir=out_dir,
            attack=config.get("attack"),
            defense=config.get("defense"),
            user_tasks=tuple(str(item) for item in config.get("user_tasks", [])),
            injection_tasks=tuple(str(item) for item in config.get("injection_tasks", [])),
            benchmark_version=str(config.get("benchmark_version", "v1.2.2")),
            extra_args=extra_args,
            env=env,
        )
    env.update({"SI_BASE_URL": base_url, "SI_API_KEY": "EMPTY"})
    return run_agentharm(
        model=f"openai-api/si/{profile.name}",
        out_dir=out_dir,
        task=str(config.get("task", "agentharm")),
        split=str(config.get("split", "test_public")),
        refusal_judge=config.get("refusal_judge"),
        semantic_judge=config.get("semantic_judge"),
        extra_args=tuple(str(arg) for arg in config.get("extra_args", [])),
        env=env,
    )


def _judge_key_env(model: str) -> str | None:
    if model.startswith("openai/"):
        return "OPENAI_API_KEY"
    if model.startswith("anthropic/"):
        return "ANTHROPIC_API_KEY"
    if model.startswith("google/"):
        return "GOOGLE_API_KEY"
    return None


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("safety-invariance", "transformers", "torch", "bitsandbytes", "agentdojo", "inspect-evals", "inspect-ai"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def _clear_cuda_cache() -> None:
    if importlib.util.find_spec("torch") is None:
        return
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        return
