from __future__ import annotations

import unittest

from safety_invariance.mitigations import (
    EscalationPolicy,
    apply_selective_precision,
    detect_safety_events,
    select_safety_sensitive_modules,
)
from safety_invariance.schemas import TaskSpec, ToolCall, TransformSpec


class MitigationTests(unittest.TestCase):
    def test_detects_forbidden_tool_and_blocks(self) -> None:
        task = TaskSpec(
            id="inject",
            category="prompt_injection",
            prompt="p",
            forbidden_tools=("send_email",),
            untrusted_context=True,
        )
        events = detect_safety_events(
            task,
            "done",
            (ToolCall(name="send_email", irreversible=True, risky=True),),
        )
        kinds = {event.kind for event in events}
        self.assertIn("unsafe_tool_call", kinds)
        self.assertIn("prompt_injection_followed", kinds)
        self.assertEqual(EscalationPolicy().decide(events), "block")

    def test_selective_precision_records_selected_modules(self) -> None:
        modules = select_safety_sensitive_modules({"privacy_leak": 3, "unsafe_tool_call": 2}, max_modules=2)
        transform = apply_selective_precision(
            TransformSpec(name="nf4_4bit", quantization="nf4_4bit", load_in_4bit=True),
            modules,
        )
        self.assertEqual(transform.name, "selective_nf4_4bit")
        self.assertEqual(transform.keep_modules_high_precision, modules)
        self.assertTrue(transform.metadata["selective_precision_requested"])


if __name__ == "__main__":
    unittest.main()
