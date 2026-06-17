from __future__ import annotations

import types
import unittest

from safety_invariance.compat import ensure_torch_module_set_submodule


class CompatTests(unittest.TestCase):
    def test_installs_set_submodule_when_missing(self) -> None:
        class FakeModule:
            pass

        fake_torch = types.SimpleNamespace(nn=types.SimpleNamespace(Module=FakeModule))
        installed = ensure_torch_module_set_submodule(fake_torch)
        self.assertTrue(installed)
        root = FakeModule()
        root.child = FakeModule()
        replacement = FakeModule()
        root.set_submodule("child.leaf", replacement)
        self.assertIs(root.child.leaf, replacement)

    def test_noop_when_present(self) -> None:
        class FakeModule:
            def set_submodule(self, target, module, strict=False):
                return None

        fake_torch = types.SimpleNamespace(nn=types.SimpleNamespace(Module=FakeModule))
        installed = ensure_torch_module_set_submodule(fake_torch)
        self.assertFalse(installed)


if __name__ == "__main__":
    unittest.main()
