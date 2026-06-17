from __future__ import annotations

import json
import csv
from pathlib import Path

from safety_invariance.schemas import TaskSpec, task_spec_from_dict


def load_task_file(path: str | Path) -> tuple[str, tuple[TaskSpec, ...]]:
    task_path = Path(path)
    if task_path.suffix.lower() == ".jsonl":
        return load_jsonl_task_file(task_path)
    if task_path.suffix.lower() == ".csv":
        return load_csv_task_file(task_path)
    data = json.loads(task_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Task file must contain an object: {task_path}")
    suite_id = data.get("suite_id", task_path.stem)
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError(f"Task file must contain a non-empty tasks list: {task_path}")
    tasks = tuple(task_spec_from_dict(item, default_suite_id=suite_id) for item in raw_tasks)
    return suite_id, tasks


def load_jsonl_task_file(path: Path) -> tuple[str, tuple[TaskSpec, ...]]:
    tasks: list[TaskSpec] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError(f"Line {line_no} in {path} is not an object.")
            tasks.append(task_spec_from_dict(data, default_suite_id=path.stem))
    if not tasks:
        raise ValueError(f"Task JSONL file is empty: {path}")
    suite_id = tasks[0].suite_id or path.stem
    return suite_id, tuple(tasks)


def load_csv_task_file(path: Path) -> tuple[str, tuple[TaskSpec, ...]]:
    tasks: list[TaskSpec] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            data = dict(row)
            for key in (
                "forbidden_tools",
                "success_keywords",
                "failure_keywords",
                "private_markers",
                "attacker_goal_keywords",
            ):
                if data.get(key):
                    data[key] = [item.strip() for item in data[key].split("|") if item.strip()]
            for key in ("requires_confirmation", "contains_private_data", "untrusted_context"):
                data[key] = str(data.get(key, "")).lower() in {"1", "true", "yes", "y"}
            tasks.append(task_spec_from_dict(data, default_suite_id=path.stem))
    if not tasks:
        raise ValueError(f"Task CSV file is empty: {path}")
    suite_id = tasks[0].suite_id or path.stem
    return suite_id, tuple(tasks)


def load_task_suites(paths: tuple[str, ...] | list[str]) -> tuple[str, tuple[TaskSpec, ...]]:
    suite_ids: list[str] = []
    tasks: list[TaskSpec] = []
    for path in paths:
        suite_id, suite_tasks = load_task_file(path)
        suite_ids.append(suite_id)
        tasks.extend(suite_tasks)
    joined_suite_id = "+".join(suite_ids)
    return joined_suite_id, tuple(tasks)


def validate_tasks(tasks: tuple[TaskSpec, ...]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for task in tasks:
        if task.id in seen:
            errors.append(f"duplicate task id: {task.id}")
        seen.add(task.id)
        if not task.prompt.strip():
            errors.append(f"{task.id}: empty prompt")
        if task.requires_confirmation and not (task.expected_tool or task.forbidden_tools):
            errors.append(f"{task.id}: confirmation task should define expected_tool or forbidden_tools")
        if task.contains_private_data and not task.private_markers:
            errors.append(f"{task.id}: privacy task should define private_markers")
        if task.untrusted_context and not (task.forbidden_tools or task.attacker_goal_keywords):
            errors.append(f"{task.id}: untrusted task should define forbidden_tools or attacker_goal_keywords")
    return errors
