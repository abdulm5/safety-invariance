from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ModelSpec:
    provider: str = "mock"
    model_id: str = "mock-safe-agent"
    revision: str | None = None
    device_map: str = "auto"
    torch_dtype: str = "auto"
    cache_dir: str | None = None
    trust_remote_code: bool = False
    metadata: JsonDict = field(default_factory=dict)


@dataclass(frozen=True)
class TransformSpec:
    name: str = "fp16"
    quantization: str = "none"
    load_in_8bit: bool = False
    load_in_4bit: bool = False
    bnb_4bit_quant_type: str = "nf4"
    keep_modules_high_precision: tuple[str, ...] = ()
    metadata: JsonDict = field(default_factory=dict)


@dataclass(frozen=True)
class TaskSpec:
    id: str
    category: str
    prompt: str
    suite_id: str = "custom"
    expected_tool: str | None = None
    forbidden_tools: tuple[str, ...] = ()
    requires_confirmation: bool = False
    contains_private_data: bool = False
    untrusted_context: bool = False
    success_keywords: tuple[str, ...] = ()
    failure_keywords: tuple[str, ...] = ()
    private_markers: tuple[str, ...] = ()
    attacker_goal_keywords: tuple[str, ...] = ()
    metadata: JsonDict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: JsonDict = field(default_factory=dict)
    risky: bool = False
    irreversible: bool = False


@dataclass(frozen=True)
class SafetyEvent:
    kind: str
    severity: str
    message: str
    action: str = "record"
    tool_call: ToolCall | None = None
    metadata: JsonDict = field(default_factory=dict)


@dataclass(frozen=True)
class AgentTrace:
    task_id: str
    suite_id: str
    category: str
    prompt: str
    output: str
    tool_calls: tuple[ToolCall, ...] = ()
    safety_events: tuple[SafetyEvent, ...] = ()
    final_decision: str = "allow"
    utility_success: bool = False
    safety_success: bool = True
    duration_ms: float = 0.0
    seed: int = 0
    metadata: JsonDict = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreBundle:
    model_id: str
    transform: str
    task_suite: str
    utility_score: float
    safety_score: float
    metrics: JsonDict
    task_scores: tuple[JsonDict, ...] = ()
    retention: JsonDict = field(default_factory=dict)


@dataclass(frozen=True)
class RunConfig:
    run_name: str
    output_dir: str
    model: ModelSpec
    transform: TransformSpec
    task_paths: tuple[str, ...]
    seeds: tuple[int, ...] = (0,)
    max_new_tokens: int = 256
    temperature: float = 0.0
    context_compression: JsonDict = field(default_factory=dict)
    mitigation: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    @property
    def run_dir(self) -> Path:
        return Path(self.output_dir)


def to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [to_dict(item) for item in value]
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_dict(item) for key, item in value.items()}
    return value


def _tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def model_spec_from_dict(data: JsonDict) -> ModelSpec:
    return ModelSpec(
        provider=data.get("provider", "mock"),
        model_id=data.get("model_id", "mock-safe-agent"),
        revision=data.get("revision"),
        device_map=data.get("device_map", "auto"),
        torch_dtype=data.get("torch_dtype", "auto"),
        cache_dir=data.get("cache_dir"),
        trust_remote_code=bool(data.get("trust_remote_code", False)),
        metadata=dict(data.get("metadata", {})),
    )


def transform_spec_from_dict(data: JsonDict) -> TransformSpec:
    quantization = data.get("quantization", "none")
    return TransformSpec(
        name=data.get("name", quantization if quantization != "none" else "fp16"),
        quantization=quantization,
        load_in_8bit=bool(data.get("load_in_8bit", quantization == "int8")),
        load_in_4bit=bool(data.get("load_in_4bit", quantization in {"nf4_4bit", "4bit"})),
        bnb_4bit_quant_type=data.get("bnb_4bit_quant_type", "nf4"),
        keep_modules_high_precision=tuple(data.get("keep_modules_high_precision", ())),
        metadata=dict(data.get("metadata", {})),
    )


def task_spec_from_dict(data: JsonDict, default_suite_id: str = "custom") -> TaskSpec:
    return TaskSpec(
        id=data["id"],
        category=data.get("category", "custom"),
        prompt=data["prompt"],
        suite_id=data.get("suite_id", default_suite_id),
        expected_tool=data.get("expected_tool"),
        forbidden_tools=tuple(data.get("forbidden_tools", ())),
        requires_confirmation=bool(data.get("requires_confirmation", False)),
        contains_private_data=bool(data.get("contains_private_data", False)),
        untrusted_context=bool(data.get("untrusted_context", False)),
        success_keywords=tuple(data.get("success_keywords", ())),
        failure_keywords=tuple(data.get("failure_keywords", ())),
        private_markers=tuple(data.get("private_markers", ())),
        attacker_goal_keywords=tuple(data.get("attacker_goal_keywords", ())),
        metadata=dict(data.get("metadata", {})),
    )


def tool_call_from_dict(data: JsonDict) -> ToolCall:
    return ToolCall(
        name=data["name"],
        args=dict(data.get("args", {})),
        risky=bool(data.get("risky", False)),
        irreversible=bool(data.get("irreversible", False)),
    )


def safety_event_from_dict(data: JsonDict) -> SafetyEvent:
    tool_data = data.get("tool_call")
    return SafetyEvent(
        kind=data["kind"],
        severity=data.get("severity", "medium"),
        message=data.get("message", ""),
        action=data.get("action", "record"),
        tool_call=tool_call_from_dict(tool_data) if tool_data else None,
        metadata=dict(data.get("metadata", {})),
    )


def agent_trace_from_dict(data: JsonDict) -> AgentTrace:
    return AgentTrace(
        task_id=data["task_id"],
        suite_id=data.get("suite_id", "custom"),
        category=data.get("category", "custom"),
        prompt=data.get("prompt", ""),
        output=data.get("output", ""),
        tool_calls=tuple(tool_call_from_dict(item) for item in data.get("tool_calls", ())),
        safety_events=tuple(safety_event_from_dict(item) for item in data.get("safety_events", ())),
        final_decision=data.get("final_decision", "allow"),
        utility_success=bool(data.get("utility_success", False)),
        safety_success=bool(data.get("safety_success", True)),
        duration_ms=float(data.get("duration_ms", 0.0)),
        seed=int(data.get("seed", 0)),
        metadata=dict(data.get("metadata", {})),
    )


def run_config_from_dict(data: JsonDict) -> RunConfig:
    task_paths = data.get("task_paths")
    if task_paths is None and data.get("task_path"):
        task_paths = [data["task_path"]]
    if not task_paths:
        raise ValueError("Run config must define task_paths or task_path.")
    return RunConfig(
        run_name=data.get("run_name", "run"),
        output_dir=data.get("output_dir", "runs/run"),
        model=model_spec_from_dict(data.get("model", {})),
        transform=transform_spec_from_dict(data.get("transform", {})),
        task_paths=tuple(task_paths),
        seeds=tuple(data.get("seeds", (0,))),
        max_new_tokens=int(data.get("max_new_tokens", 256)),
        temperature=float(data.get("temperature", 0.0)),
        context_compression=dict(data.get("context_compression", {})),
        mitigation=dict(data.get("mitigation", {})),
        metadata=dict(data.get("metadata", {})),
    )
