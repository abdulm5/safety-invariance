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
) -> list[str]:
    command = ["python", "-m", "agentdojo.scripts.benchmark", "--model", model]
    if suite:
        command.extend(["-s", suite])
    for task in user_tasks:
        command.extend(["-ut", task])
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
        "dry_run": dry_run,
    }
    (output / "agentdojo_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if dry_run:
        return manifest
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    (output / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    manifest["returncode"] = result.returncode
    manifest["parsed"] = parse_agentdojo_stdout(result.stdout)
    (output / "agentdojo_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"AgentDojo command failed with exit code {result.returncode}: {output / 'stderr.txt'}")
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
