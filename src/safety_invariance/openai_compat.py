from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from safety_invariance.config import load_structured_file
from safety_invariance.modeling import load_model_client
from safety_invariance.schemas import ModelSpec, TransformSpec, model_spec_from_dict, to_dict, transform_spec_from_dict


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model: ModelSpec
    transform: TransformSpec
    max_new_tokens: int = 512
    temperature: float = 0.0
    seed: int = 0


def model_profile_from_dict(data: dict[str, Any]) -> ModelProfile:
    return ModelProfile(
        name=str(data["name"]),
        model=model_spec_from_dict(dict(data["model"])),
        transform=transform_spec_from_dict(dict(data["transform"])),
        max_new_tokens=int(data.get("max_new_tokens", 512)),
        temperature=float(data.get("temperature", 0.0)),
        seed=int(data.get("seed", 0)),
    )


def load_model_profile(path: str | Path) -> ModelProfile:
    return model_profile_from_dict(load_structured_file(Path(path)))


class OpenAIChatBackend:
    def __init__(
        self,
        profile: ModelProfile,
        *,
        telemetry_path: str | Path | None = None,
        model_client: object | None = None,
    ) -> None:
        self.profile = profile
        self.model_client = model_client or load_model_client(profile.model, profile.transform)
        self.telemetry_path = Path(telemetry_path) if telemetry_path else None
        self._generation_lock = threading.Lock()
        self._telemetry_lock = threading.Lock()
        if self.telemetry_path:
            self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)

    def models_response(self) -> dict[str, object]:
        return {
            "object": "list",
            "data": [
                {
                    "id": self.profile.name,
                    "object": "model",
                    "created": 0,
                    "owned_by": "safety-invariance",
                }
            ],
        }

    def chat_completion(self, request: dict[str, Any]) -> dict[str, object]:
        if request.get("stream"):
            raise ValueError("Streaming chat completions are not supported.")
        requested_model = str(request.get("model", self.profile.name))
        if requested_model != self.profile.name:
            raise ValueError(
                f"This endpoint serves model '{self.profile.name}', not '{requested_model}'."
            )
        messages = request.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list")
        tools = request.get("tools", [])
        if not isinstance(tools, list):
            raise ValueError("tools must be a list")

        max_tokens = int(request.get("max_completion_tokens", request.get("max_tokens", self.profile.max_new_tokens)))
        temperature = float(request.get("temperature", self.profile.temperature))
        seed = int(request.get("seed", self.profile.seed) or self.profile.seed)
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        started = time.perf_counter()
        with self._generation_lock:
            output = self.model_client.generate_chat(
                messages,
                tools=tools,
                max_new_tokens=max_tokens,
                temperature=temperature,
                seed=seed,
            )
        duration_ms = (time.perf_counter() - started) * 1000.0
        offered_names = offered_tool_names(tools)
        tool_calls = parse_tool_calls(output, offered_names=offered_names)
        max_parallel_calls = int(self.profile.model.metadata.get("max_parallel_tool_calls", 0) or 0)
        if max_parallel_calls:
            tool_calls = tool_calls[:max_parallel_calls]
        metadata = dict(getattr(self.model_client, "last_generation_metadata", {}))
        input_tokens = int(metadata.get("input_tokens", 0))
        output_tokens = int(metadata.get("output_tokens", 0))
        message: dict[str, object] = {
            "role": "assistant",
            "content": None if tool_calls else output,
        }
        if tool_calls:
            message["tool_calls"] = tool_calls
        response = {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.profile.name,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                }
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }
        self._write_telemetry(
            {
                "request_id": request_id,
                "model": self.profile.name,
                "transform": self.profile.transform.name,
                "duration_ms": duration_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_count": len(tools),
                "tool_call_count": len(tool_calls),
                "max_parallel_tool_calls": max_parallel_calls or None,
                "context_limit": metadata.get("context_limit"),
                "context_limit_reached": metadata.get("context_limit_reached", False),
                "generation_budget": metadata.get("generation_budget"),
                "seed": seed,
                "temperature": temperature,
            }
        )
        return response

    def manifest(self) -> dict[str, object]:
        runtime_provider = getattr(self.model_client, "get_runtime_metadata", None)
        runtime = runtime_provider() if callable(runtime_provider) else {}
        return {
            "profile": self.profile.name,
            "model": to_dict(self.profile.model),
            "transform": to_dict(self.profile.transform),
            "generation": {
                "max_new_tokens": self.profile.max_new_tokens,
                "temperature": self.profile.temperature,
                "seed": self.profile.seed,
            },
            "runtime": runtime,
        }

    def _write_telemetry(self, event: dict[str, object]) -> None:
        if not self.telemetry_path:
            return
        with self._telemetry_lock, self.telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def offered_tool_names(tools: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(function, dict) and function.get("name"):
            names.add(str(function["name"]))
    return names


def parse_tool_calls(output: str, *, offered_names: set[str] | None = None) -> list[dict[str, object]]:
    candidates: list[object] = []
    tagged_patterns = (
        r"<tool_call>\s*(.*?)\s*</tool_call>",
        r"<\|python_tag\|>\s*(.*?)(?=<\||$)",
    )
    for pattern in tagged_patterns:
        for match in re.finditer(pattern, output, flags=re.DOTALL):
            candidates.extend(_json_values(match.group(1)))
    if not candidates:
        candidates.extend(_json_values(output))

    normalized: list[dict[str, object]] = []
    for candidate in candidates:
        for call in _candidate_calls(candidate):
            name = call.get("name")
            if not isinstance(name, str) or not name:
                continue
            if offered_names and name not in offered_names:
                continue
            arguments = call.get("arguments", call.get("args", call.get("parameters", {})))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"value": arguments}
            if not isinstance(arguments, dict):
                arguments = {}
            normalized.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments, sort_keys=True),
                    },
                }
            )
    return normalized


def _candidate_calls(candidate: object) -> list[dict[str, object]]:
    if isinstance(candidate, list):
        calls: list[dict[str, object]] = []
        for item in candidate:
            calls.extend(_candidate_calls(item))
        return calls
    if not isinstance(candidate, dict):
        return []
    if isinstance(candidate.get("tool_call"), dict):
        return [dict(candidate["tool_call"])]
    if isinstance(candidate.get("tool_calls"), list):
        calls: list[dict[str, object]] = []
        for item in candidate["tool_calls"]:
            calls.extend(_candidate_calls(item))
        return calls
    if isinstance(candidate.get("function"), dict):
        return [dict(candidate["function"])]
    if "name" in candidate:
        return [candidate]
    return []


def _json_values(text: str) -> list[object]:
    values: list[object] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        starts = [position for token in ("{", "[") if (position := text.find(token, index)) >= 0]
        if not starts:
            break
        start = min(starts)
        try:
            value, consumed = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        values.append(value)
        index = start + consumed
    return values


class OpenAICompatServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], backend: OpenAIChatBackend) -> None:
        self.backend = backend
        super().__init__(address, OpenAICompatHandler)


class OpenAICompatHandler(BaseHTTPRequestHandler):
    server: OpenAICompatServer

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"/health", "/v1/models"}:
            payload = (
                {"status": "ok", "model": self.server.backend.profile.name}
                if self.path.rstrip("/") == "/health"
                else self.server.backend.models_response()
            )
            self._send_json(HTTPStatus.OK, payload)
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in {"/v1/chat/completions", "/chat/completions"}:
            self._send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request body must be a JSON object")
            response = self.server.backend.chat_completion(request)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:  # pragma: no cover - model/backend dependent.
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json(HTTPStatus.OK, response)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": {"message": message, "type": "invalid_request_error"}})

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_profile(
    profile: ModelProfile,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    telemetry_path: str | Path | None = None,
) -> None:
    backend = OpenAIChatBackend(profile, telemetry_path=telemetry_path)
    server = OpenAICompatServer((host, port), backend)
    print(json.dumps({"base_url": f"http://{host}:{port}/v1", "model": profile.name}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
