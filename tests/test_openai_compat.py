from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from safety_invariance.openai_compat import ModelProfile, OpenAIChatBackend, parse_tool_calls
from safety_invariance.schemas import ModelSpec, TransformSpec


class FakeChatModel:
    last_generation_metadata = {"input_tokens": 12, "output_tokens": 8}

    def generate_chat(self, messages, *, tools, max_new_tokens, temperature, seed):
        del messages, tools, max_new_tokens, temperature, seed
        return '<tool_call>{"name":"search_documents","arguments":{"query":"safe"}}</tool_call>'


class OpenAICompatTests(unittest.TestCase):
    def test_parses_qwen_and_llama_tool_formats(self) -> None:
        qwen = parse_tool_calls(
            '<tool_call>{"name":"search_documents","arguments":{"query":"x"}}</tool_call>',
            offered_names={"search_documents"},
        )
        llama = parse_tool_calls(
            '<|python_tag|>{"name":"send_email","parameters":{"to":"a@example.com"}}',
            offered_names={"send_email"},
        )
        self.assertEqual(qwen[0]["function"]["name"], "search_documents")
        self.assertEqual(json.loads(qwen[0]["function"]["arguments"]), {"query": "x"})
        self.assertEqual(llama[0]["function"]["name"], "send_email")

    def test_rejects_hallucinated_tool_names(self) -> None:
        calls = parse_tool_calls(
            '{"name":"unknown_tool","arguments":{}}',
            offered_names={"search_documents"},
        )
        self.assertEqual(calls, [])

    def test_chat_completion_emits_openai_shape_and_telemetry(self) -> None:
        profile = ModelProfile(
            name="mock-profile",
            model=ModelSpec(),
            transform=TransformSpec(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            telemetry = Path(tmp) / "events.jsonl"
            backend = OpenAIChatBackend(
                profile,
                model_client=FakeChatModel(),
                telemetry_path=telemetry,
            )
            response = backend.chat_completion(
                {
                    "model": "mock-profile",
                    "messages": [{"role": "user", "content": "Find the document"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {"name": "search_documents", "parameters": {"type": "object"}},
                        }
                    ],
                    "temperature": 0,
                }
            )
            choice = response["choices"][0]
            self.assertEqual(choice["finish_reason"], "tool_calls")
            self.assertEqual(choice["message"]["tool_calls"][0]["function"]["name"], "search_documents")
            self.assertEqual(response["usage"]["total_tokens"], 20)
            self.assertEqual(json.loads(telemetry.read_text())["tool_call_count"], 1)


if __name__ == "__main__":
    unittest.main()
