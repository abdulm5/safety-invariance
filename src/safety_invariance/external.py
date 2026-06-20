from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path


def build_agentdojo_command(
    *,
    model: str,
    suite: str | None = None,
    attack: str = "tool_knowledge",
    defense: str = "tool_filter",
    user_tasks: tuple[str, ...] = (),
    extra_args: tuple[str, ...] = (),
    model_id: str | None = None,
    benchmark_version: str | None = None,
    logdir: str | Path | None = None,
    injection_tasks: tuple[str, ...] = (),
) -> list[str]:
    command = ["python", "-m", "agentdojo.scripts.benchmark", "--model", model]
    if model_id:
        command.extend(["--model-id", model_id])
    if benchmark_version:
        command.extend(["--benchmark-version", benchmark_version])
    if logdir:
        command.extend(["--logdir", str(logdir)])
    if suite:
        command.extend(["-s", suite])
    for task in user_tasks:
        command.extend(["-ut", task])
    for task in injection_tasks:
        command.extend(["-it", task])
    if defense:
        command.extend(["--defense", defense])
    if attack:
        command.extend(["--attack", attack])
    command.extend(extra_args)
    return command


def run_agentdojo(
    *,
    model: str,
    out_dir: str | Path,
    suite: str | None = None,
    attack: str = "tool_knowledge",
    defense: str = "tool_filter",
    user_tasks: tuple[str, ...] = (),
    extra_args: tuple[str, ...] = (),
    dry_run: bool = False,
    model_id: str | None = None,
    benchmark_version: str | None = None,
    injection_tasks: tuple[str, ...] = (),
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    command = build_agentdojo_command(
        model=model,
        suite=suite,
        attack=attack,
        defense=defense,
        user_tasks=user_tasks,
        extra_args=extra_args,
        model_id=model_id,
        benchmark_version=benchmark_version,
        logdir=output / "native_logs",
        injection_tasks=injection_tasks,
    )
    manifest = {
        "benchmark": "agentdojo",
        "command": command,
        "shell_command": shlex.join(command),
        "model": model,
        "suite": suite,
        "attack": attack,
        "defense": defense,
        "user_tasks": list(user_tasks),
        "injection_tasks": list(injection_tasks),
        "model_id": model_id,
        "benchmark_version": benchmark_version,
        "dry_run": dry_run,
    }
    (output / "agentdojo_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if dry_run:
        return manifest
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    (output / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    manifest["returncode"] = result.returncode
    manifest["parsed"] = parse_agentdojo_stdout(result.stdout)
    (output / "agentdojo_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"AgentDojo command failed with exit code {result.returncode}: {output / 'stderr.txt'}")
    return manifest


def build_agentharm_command(
    *,
    model: str,
    task: str = "agentharm",
    split: str = "test_public",
    log_dir: str | Path | None = None,
    refusal_judge: str | None = None,
    semantic_judge: str | None = None,
    extra_args: tuple[str, ...] = (),
) -> list[str]:
    command = [
        "inspect",
        "eval",
        f"inspect_evals/{task}",
        "--model",
        model,
        "--display",
        "plain",
        "--max-connections",
        "1",
    ]
    if log_dir:
        command.extend(["--log-dir", str(log_dir)])
    command.extend(["-T", f"split={split}"])
    if refusal_judge:
        command.extend(["-T", f"refusal_judge={refusal_judge}"])
    if semantic_judge:
        command.extend(["-T", f"semantic_judge={semantic_judge}"])
    command.extend(extra_args)
    return command


def run_agentharm(
    *,
    model: str,
    out_dir: str | Path,
    task: str = "agentharm",
    split: str = "test_public",
    refusal_judge: str | None = None,
    semantic_judge: str | None = None,
    extra_args: tuple[str, ...] = (),
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    command = build_agentharm_command(
        model=model,
        task=task,
        split=split,
        log_dir=output / "native_logs",
        refusal_judge=refusal_judge,
        semantic_judge=semantic_judge,
        extra_args=extra_args,
    )
    manifest: dict[str, object] = {
        "benchmark": "agentharm",
        "command": command,
        "shell_command": shlex.join(command),
        "model": model,
        "task": task,
        "split": split,
        "refusal_judge": refusal_judge,
        "semantic_judge": semantic_judge,
        "dry_run": dry_run,
    }
    manifest_path = output / "agentharm_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if dry_run:
        return manifest
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    (output / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    manifest["returncode"] = result.returncode
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"AgentHarm command failed with exit code {result.returncode}: {output / 'stderr.txt'}")
    return manifest


def build_toolsandbox_command(
    *,
    agent: str,
    user: str = "GPT_4_o_2024_05_13",
    scenario: str | None = None,
    extra_args: tuple[str, ...] = (),
) -> list[str]:
    command = ["tool_sandbox", "--user", user, "--agent", agent]
    if scenario:
        command.extend(["--scenario", scenario])
    command.extend(extra_args)
    return command


def run_toolsandbox(
    *,
    agent: str,
    out_dir: str | Path,
    user: str = "GPT_4_o_2024_05_13",
    scenario: str | None = None,
    extra_args: tuple[str, ...] = (),
    dry_run: bool = False,
) -> dict[str, object]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    command = build_toolsandbox_command(
        agent=agent,
        user=user,
        scenario=scenario,
        extra_args=extra_args,
    )
    manifest = {
        "benchmark": "toolsandbox",
        "command": command,
        "shell_command": shlex.join(command),
        "agent": agent,
        "user": user,
        "scenario": scenario,
        "dry_run": dry_run,
    }
    (output / "toolsandbox_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if dry_run:
        return manifest
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    (output / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    manifest["returncode"] = result.returncode
    (output / "toolsandbox_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"ToolSandbox command failed with exit code {result.returncode}: {output / 'stderr.txt'}")
    return manifest


def parse_agentdojo_stdout(stdout: str) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for line in stdout.splitlines():
        lower = line.lower()
        if "average utility" in lower:
            parsed["average_utility"] = _extract_percent(line)
        if "average security" in lower:
            parsed["average_security"] = _extract_percent(line)
    return parsed


def _extract_percent(line: str) -> float:
    for token in line.replace("%", " %").split():
        try:
            value = float(token)
        except ValueError:
            continue
        if "%" in line:
            return value / 100.0
        return value
    return 0.0
